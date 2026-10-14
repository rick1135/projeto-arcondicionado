"""Controle Elgin na bandeja do Windows. Execute com --show para abrir o painel."""

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime
import json
import math
from pathlib import Path
from types import SimpleNamespace
import queue
import sqlite3
import sys
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox
import traceback
import winreg

from PIL import Image, ImageDraw, ImageFont, ImageTk
import pystray

from elgin_app import ElginApp, MODOS, VENTILACAO
from ekaza_plug import medidas as medidas_tomada, run_operation as operar_tomada
from ekaza_plug import ler_config as config_tomada
from bridge import EnergyBridge
from energy_cost import DEFAULT_TARIFF, load_tariff, monthly_cost, format_brl
from energy_history import EnergyHistory, MONTHS, format_kwh, format_source, local_now, reference_data, reference_snapshot
from elgin_art import (
    CARD_Y1, CARD_Y2, ECO_BOX, FOOTER_LINE_Y, HEIGHT, MAX_TEMP, MIN_TEMP,
    MINUS_BOX, PLUS_BOX, PLUG_CARD_BOX, PLUG_ACTION_BOX, POWER_BOX, SLIDER_BOX, TOP_BOX, WIDTH,
    card_box, render_assets, temp_from_x,
)


SETTINGS = Path(__file__).with_name("settings.json")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "Elgin AC Tray"

# Cores do Design Atmosphere Dark OS (Google Stitch)
BG = "#0e141b"
SURFACE_LOW = "#161c23"
SURFACE_CONTAINER = "#1a2027"
SURFACE_HIGH = "#252a32"
SURFACE_HIGHEST = "#2f353d"
SURFACE_BRIGHT = "#343a42"
TEXT = "#dde3ed"
MUTED = "#bac9cc"
PRIMARY = "#00e5ff"
PRIMARY_HERO = "#c3f5ff"
PRIMARY_DIM = "#00daf3"
SECONDARY = "#7bd0ff"
TERTIARY = "#5be9ad"
TERTIARY_BG = "#a8ffd2"
OUTLINE = "#849396"
OUTLINE_VARIANT = "#3b494c"
SLATE_300 = "#cbd5e1"
SLATE_400 = "#94a3b8"
SLATE_500 = "#64748b"
FONT = "Segoe UI"

STATUS_OK = ("#5be9ad", "#a8ffd2", SLATE_400)
STATUS_SYNC = ("#f59e0b", "#fcd34d", "#fcd34d")
STATUS_ERROR = ("#ef4444", None, "#fca5a5")

WIND_PERIOD = 4.5      # s, animação de pulso do vento
BEACON_PERIOD = 2.5    # s, luz de status
PING_PERIOD = 1.0      # s, anel de ping pulsante
STATUS_DOT = (31, 804, 5)


def tracked(text, spacer="\u2009"):
    """Simula letter-spacing que o Tk não suporta nativamente."""
    return spacer.join(text)


def mix(color, other, amount):
    """Mistura duas cores; amount=1 devolve `color`."""
    a = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    b = other if isinstance(other, tuple) else [int(other[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(y + (x - y) * amount) for x, y in zip(a, b))


def startup_command():
    python = Path(sys.executable).with_name("pythonw.exe")
    return f'"{python}" "{Path(__file__).resolve()}" --background'


def startup_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_NAME)
            return value == startup_command()
    except FileNotFoundError:
        return False


def set_startup(enabled):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_NAME)
            except FileNotFoundError:
                pass


def save_startup_preference(enabled):
    SETTINGS.write_text(json.dumps({"start_with_windows": enabled}, indent=2) + "\n",
                        encoding="utf-8")


def apply_startup_preference():
    try:
        settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
        enabled = settings.get("start_with_windows", True)
    except FileNotFoundError:
        enabled = True
        save_startup_preference(enabled)
    set_startup(bool(enabled))


def icon_image(temperature=None, power=False):
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 5, 60, 59), radius=16, fill="#151e24")
    if temperature is None:
        draw.rounded_rectangle((11, 18, 53, 39), radius=7, fill="#f0f6f8")
        draw.line((16, 34, 48, 34), fill="#19313e", width=3)
        draw.line((19, 46, 45, 46), fill="#00e5ff", width=4)
    else:
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 30)
        except OSError:
            font = ImageFont.load_default(size=30)
        draw.text((32, 29), str(temperature), font=font, anchor="mm",
                  fill="#c3f5ff" if power else "#f1f7f9")
        draw.line((19, 50, 45, 50), fill="#00e5ff" if power else "#64748b", width=3)
    return image


def work_area():
    rect = wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0,
                                               ctypes.byref(rect), 0)
    return rect.left, rect.top, rect.right, rect.bottom


class TrayApp:
    def __init__(self, root, show_at_start=False, preview=False):
        self.root = root
        self.root.withdraw()
        self.root.title("Elgin AC")
        self.preview = preview
        left, top, right, bottom = work_area()
        self.scale = min(1.0, (right - left - 24) / WIDTH,
                         (bottom - top - 24) / HEIGHT)
        self.view_width = round(WIDTH * self.scale)
        self.view_height = round(HEIGHT * self.scale)
        assets = render_assets(self.scale)
        photo = ImageTk.PhotoImage
        self.img_base = photo(assets["base"])
        self.img_blank = photo(assets["blank"])
        self.top_off = photo(assets["top_off"])
        self.top_on = [photo(image) for image in assets["top_on"]]
        self.eco_imgs = [photo(image) for image in assets["eco"]]
        self.slider_imgs = [photo(image) for image in assets["slider"]]
        dot_x, dot_y, _ = STATUS_DOT
        self.footer_bg = assets["base"].getpixel(
            (round(dot_x * self.scale), round((dot_y - 12) * self.scale)))[:3]
        self.fonts = {}
        self.root.overrideredirect(not preview)
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.canvas = tk.Canvas(root, width=self.view_width,
                                height=self.view_height, bg=BG,
                                highlightthickness=0, takefocus=True)
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self.click)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.canvas.bind("<Motion>", self.motion)
        self.canvas.bind("<MouseWheel>", self.energy_scroll)
        self.root.bind("<Escape>", lambda _e: self.hide())
        self.root.bind("<FocusOut>", self.focus_out)
        self.root.bind("<space>", lambda _e: self.power())
        self.root.bind("<Left>", lambda _e: self.energy_key(-1))
        self.root.bind("<Right>", lambda _e: self.energy_key(1))
        self.root.bind("<Tab>", self.energy_tab)
        self.root.bind("<Shift-Tab>", lambda e: self.energy_tab(e, -1))
        self.root.bind("<Return>", self.energy_activate)
        self.root.bind("<r>", lambda _e: self.refresh_all())
        self.root.protocol("WM_DELETE_WINDOW", self.hide)

        self.dps = {}
        self.error = ""
        self.busy = False
        self.updated = None
        self.page = "control"  # "control", "extras", "plug", "plug_confirm", "settings"
        self.menu = None
        self.hotspots = []
        self.hover = None
        self.dragging = False
        self.pending_temp = None
        self.last_normal_fan = "auto"
        self.selected_timer_hours = "0100"  # Preset padrão: 1 hora
        self.phase = 0.0
        self.frame_idx = 0
        self.top_item = None
        self.ping_item = None
        self.dot_item = None
        self.status_colors = STATUS_SYNC
        self.reconnecting = False
        self.closed = False
        self.events = queue.Queue()
        self.results = queue.Queue()
        self.worker = None
        self.plug_dps = {}
        self.plug_error = ""
        self.plug_busy = False
        self.plug_updated = None
        self.plug_results = queue.Queue()
        self.energy_error = ""
        self.energy_tariff = load_tariff()
        try:
            self.energy_store = EnergyHistory()
        except (OSError, ValueError, sqlite3.Error):
            self.energy_store = None
            self.energy_error = "Histórico local indisponível"
        self.cloud_energy = None
        self.cloud_error = ""
        self.cloud_busy = False
        self.cloud_attempts = {}
        self.cloud_results = queue.Queue()
        self.cloud_failures = {}
        try:
            self.cloud_energy = EnergyBridge(config_tomada()['device_id'],
                                             cache_path=Path(__file__).with_name('energy_history.sqlite3'))
        except Exception:
            self.cloud_error = 'Cloud indisponível: confira configuração da tomada e pasta.'
        self.energy_year = local_now().year
        self.energy_month_offset = 0
        self.energy_chart_start = 0
        self.energy_selected_day = 1
        self.startup_error = ""
        try:
            apply_startup_preference()
        except OSError as exc:
            self.startup_error = f"Não foi possível configurar o início automático: {exc}"

        self.icon = pystray.Icon(
            "ElginAC", icon_image(), "Elgin AC",
            menu=pystray.Menu(
                pystray.MenuItem("Abrir controle", self.enqueue_show, default=True),
                pystray.MenuItem("Atualizar", self.enqueue_refresh),
                pystray.MenuItem("Sair", self.enqueue_exit),
            ),
        )
        self.tray_thread = threading.Thread(target=self.icon.run, daemon=True)
        self.tray_thread.start()
        self.draw()
        self.root.after(100, self.process_events)
        self.root.after(15000, self.periodic_refresh)
        self.root.after(90, self.animate)
        self.submit("status")
        self.submit_plug("status")
        self.submit_energy()
        if show_at_start:
            self.root.after(350, self.show)

    def enqueue_show(self, _icon=None, _item=None):
        self.events.put("show")

    def enqueue_refresh(self, _icon=None, _item=None):
        self.events.put("refresh")

    def enqueue_exit(self, _icon=None, _item=None):
        self.events.put("exit")

    def show(self):
        if self.closed:
            return
        left, top, right, bottom = work_area()
        x = max(left, right - self.view_width - 14)
        y = max(top, bottom - self.view_height - 14)
        self.root.geometry(f"{self.view_width}x{self.view_height}+{x}+{y}")
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.focus_force()
        self.draw()
        if not self.busy and self.plug_dps.get("1") is not False:
            self.submit("status")
        if not self.plug_busy:
            self.submit_plug("status")

    def hide(self):
        self.menu = None
        self.root.withdraw()

    def focus_out(self, _event):
        if not self.preview:
            self.root.after(140, self.hide_if_unfocused)

    def hide_if_unfocused(self):
        if not self.closed and self.root.state() != "withdrawn" and not self.root.focus_displayof():
            self.hide()

    def stop(self):
        self.closed = True
        self.icon.stop()
        self.root.destroy()

    def process_events(self):
        if self.closed:
            return
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            if event == "show":
                if self.root.state() == "withdrawn":
                    self.show()
                else:
                    self.hide()
            elif event == "refresh":
                self.refresh_all()
            elif event == "exit":
                self.stop()
                return
        while True:
            try:
                dps, error = self.results.get_nowait()
            except queue.Empty:
                break
            self.busy = False
            if self.plug_dps.get("1") is False:
                self.dps = {}
                self.updated = None
                self.error = "Ar sem alimentação"
            elif error:
                self.error = error
            else:
                self.dps = dps
                self.error = ""
                self.updated = datetime.now()
                if dps.get("5") not in (None, "strong", "mute"):
                    self.last_normal_fan = dps["5"]
                self.icon.title = f"Elgin AC · {dps.get('2', '--')} °C"
                self.icon.icon = icon_image(dps.get("2"), dps.get("1") is True)
            self.draw()
        while True:
            try:
                dps, error = self.plug_results.get_nowait()
            except queue.Empty:
                break
            self.plug_busy = False
            if error:
                self.plug_error = error
            else:
                self.plug_dps = dps
                self.plug_error = ""
                self.plug_updated = datetime.now()
                if dps.get("1") is False:
                    self.dps = {}
                    self.updated = None
                    self.error = "Ar sem alimentação"
                    self.icon.title = "Elgin AC · sem alimentação"
                    self.icon.icon = icon_image()
            self.draw()
        self.process_cloud_results()
        self.root.after(100, self.process_events)

    def refresh_all(self):
        if self.plug_dps.get("1") is not False:
            self.submit("status")
        self.submit_plug("status")
        self.submit_energy(force=True)

    def submit_energy(self, force=False):
        """Consultas somente leitura; fila independente dos comandos LAN."""
        bridge = getattr(self, 'cloud_energy', None)
        if bridge is None or self.closed or getattr(self, 'cloud_busy', False):
            return
        now = local_now()
        wanted = [(now.year, now.month)]
        year = getattr(self, 'energy_year', now.year)
        month = getattr(self, 'energy_month', now.month) if self.page == 'energy_month' else (now.month if year == now.year else 12)
        selected = (year, month)
        if selected not in wanted:
            wanted.append(selected)
        if force:
            wanted = [selected]
        key = None
        for period in wanted:
            due = time.monotonic() - self.cloud_attempts.get(period, -1e9) >= 60
            if not force and not due:
                continue
            cached = bridge.cached(*period)
            if force or cached is None or cached['stale']:
                key = period
                break
        if key is None:
            return
        self.cloud_busy = True
        self.cloud_attempts[key] = time.monotonic()
        self.draw()

        def work():
            self.cloud_results.put((key, bridge.get_energy_history(*key, force=force)))

        threading.Thread(target=work, daemon=True).start()

    def process_cloud_results(self):
        results = getattr(self, 'cloud_results', None)
        if results is None:
            return
        while True:
            try:
                key, result = results.get_nowait()
            except queue.Empty:
                break
            self.cloud_busy = False
            if result.get('ok'):
                self.cloud_failures.pop(key, None)
                self.cloud_error = result.get('cache_warning', '')
            else:
                self.cloud_error = result.get('error') or 'Falha ao consultar a Tuya Cloud.'
                self.cloud_failures[key] = self.cloud_error
            self.draw()
        # Se o usuário mudou de mês durante uma consulta, busca o mês atual da tela.
        self.submit_energy()

    def cloud_notice(self):
        if getattr(self, 'cloud_busy', False):
            return 'Consultando Tuya Cloud…'
        now = local_now()
        key = ((self.energy_year, self.energy_month) if self.page == 'energy_month' else (now.year, now.month))
        failure = getattr(self, 'cloud_failures', {}).get(key)
        if failure:
            return failure
        return getattr(self, 'cloud_error', '')

    def ac_off_confirmed(self):
        return (self.dps.get("1") is False and not self.error and
                self.updated is not None and
                (datetime.now() - self.updated).total_seconds() < 60)

    def submit_plug(self, command, value=None, *, force_off=False):
        if self.plug_busy or self.closed:
            return
        ac_off = self.ac_off_confirmed()
        if command == "power" and value is False and not (ac_off or force_off):
            self.plug_error = "Confirme o corte de energia antes de desligar"
            self.draw()
            return
        self.plug_busy = True
        self.plug_error = ""
        self.draw()

        def work():
            try:
                result = operar_tomada(command, value,
                                       ac_off_confirmed=ac_off,
                                       force_off=force_off)
                if result[0] is not None and not result[1] and self.energy_store is not None:
                    try:
                        self.energy_store.record(result[0])
                        self.energy_error = ""
                    except (OSError, ValueError, sqlite3.Error):
                        self.energy_error = "Falha ao salvar histórico local"
            except Exception:
                result = (None, "Falha inesperada na comunicação com a tomada")
            self.plug_results.put(result)

        threading.Thread(target=work, daemon=True).start()

    def submit(self, command, value=None):
        if self.busy or self.closed:
            return
        self.busy = True
        self.reconnecting = bool(self.error) or not self.updated
        self.error = ""
        self.draw()

        def work():
            self.results.put(ElginApp.run_operation(command, value))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def periodic_refresh(self):
        if not self.closed:
            if not self.busy and not self.dragging and self.plug_dps.get("1") is not False:
                self.submit("status")
            if not self.plug_busy:
                self.submit_plug("status")
            self.submit_energy()
            self.root.after(15000, self.periodic_refresh)

    def wind_frame_index(self, now=None):
        """Quadro do pulso contínuo do vento (ease-in-out)."""
        frames = getattr(self, "top_on", None) or [None]
        now = time.monotonic() if now is None else now
        t = (1 - math.cos(2 * math.pi * now / WIND_PERIOD)) / 2
        return round(t * (len(frames) - 1))

    def animate(self):
        if self.closed:
            return
        if self.root.state() != "withdrawn" and self.page == "control":
            now = time.monotonic()
            if self.dps.get("1") is True and self.top_item and self.top_on:
                index = self.wind_frame_index(now)
                if index != self.frame_idx:
                    self.frame_idx = index
                    self.canvas.itemconfigure(self.top_item, image=self.top_on[index])
            self.update_beacon(now)
        self.root.after(60, self.animate)

    def update_beacon(self, now):
        """Luz de status pulsante com anel 'ping'."""
        if not self.dot_item:
            return
        scale = getattr(self, "scale", 1.0)
        x, y, radius = STATUS_DOT
        light, ping, _ = self.status_colors
        pulse = math.sin(math.pi * (now % BEACON_PERIOD) / BEACON_PERIOD) ** 2
        r = radius * (1 + 0.15 * pulse)
        self.canvas.coords(self.dot_item, (x - r) * scale, (y - r) * scale,
                           (x + r) * scale, (y + r) * scale)
        if self.ping_item:
            if ping is None:
                self.canvas.itemconfigure(self.ping_item, state="hidden")
                return
            p = (now % PING_PERIOD) / PING_PERIOD
            eased = 1 - (1 - p) ** 3
            r = radius * (1 + eased)
            self.canvas.coords(self.ping_item, (x - r) * scale, (y - r) * scale,
                               (x + r) * scale, (y + r) * scale)
            self.canvas.itemconfigure(self.ping_item, state="normal",
                                      fill=mix(ping, self.footer_bg, 0.75 * (1 - eased)))

    def hit(self, name, bounds, value=None):
        self.hotspots.append((name, bounds, value))

    def rounded(self, bounds, radius, fill, outline=""):
        self.canvas.create_polygon(
            self._rounded_points(*bounds, radius), smooth=True,
            splinesteps=18, fill=fill, outline=outline,
        )

    @staticmethod
    def _rounded_points(x1, y1, x2, y2, r):
        return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
                x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
                x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]

    def font(self, size, weight="normal"):
        """Fonte com tamanho em pixels (negativo no Tk), já na escala da janela."""
        family = FONT
        if weight == "semibold":
            family, weight = f"{FONT} Semibold", "normal"
        return (family, -max(8, round(size * getattr(self, "scale", 1.0))), weight)

    def text_width(self, text, size, weight="normal"):
        """Largura lógica do texto para centralização perfeita."""
        root = getattr(self, "root", None)
        if root is not None:
            key = self.font(size, weight)
            fonts = self.__dict__.setdefault("fonts", {})
            try:
                if key not in fonts:
                    fonts[key] = tkfont.Font(root=root, family=key[0], size=key[1], weight=key[2])
                return fonts[key].measure(text) / getattr(self, "scale", 1.0)
            except tk.TclError:
                pass
        return len(text) * size * 0.52

    def label(self, x, y, text, size, color=TEXT, weight="normal", anchor="nw"):
        return self.canvas.create_text(x, y, text=text, fill=color, anchor=anchor,
                                       font=self.font(size, weight))

    def fit_label(self, x, y, text, size, max_width, color=TEXT, weight="normal", anchor="nw"):
        """Reserva a largura do controle vizinho, sem deixar o texto invadi-lo."""
        if self.text_width(text, size, weight) > max_width:
            while text and self.text_width(text + "…", size, weight) > max_width:
                text = text[:-1]
            text += "…"
        return self.label(x, y, text, size, color, weight, anchor)

    def action_pill(self, box, text, size=11, name=None):
        """Auto-layout horizontal: padding 12, texto, gap 6 e ícone fixo 16."""
        x1, y1, x2, y2 = box
        text_w = self.text_width(text, size, "semibold")
        width = max(x2 - x1, text_w + 6 + 16 + 24)
        x1 = x2 - width
        hovered = name is not None and getattr(self, "hover", None) == name
        self.rounded((x1, y1, x2, y2), (y2 - y1) / 2,
                     "#004f58" if hovered else SURFACE_HIGH, PRIMARY if hovered else OUTLINE_VARIANT)
        cy = (y1 + y2) / 2
        start = x1 + (width - text_w - 22) / 2
        self.label(start, cy, text, size, PRIMARY, "semibold", anchor="w")
        ix = start + text_w + 6
        self.canvas.create_line(ix + 5, cy - 4, ix + 9, cy, ix + 5, cy + 4,
                                fill=PRIMARY, width=1.5)
        return x1

    def metric_value(self, x, y, value, unit, size=32, unit_size=16):
        """Retorna a base real do número para empilhar a legenda sem sobreposição."""
        item = self.label(x, y, value, size, PRIMARY_HERO, "bold")
        self.label(x + self.text_width(value, size, "bold") + 8,
                   y + (size - unit_size), unit, unit_size, SECONDARY, "bold")
        root = getattr(self, "root", None)
        if root is not None:
            return y + (self.canvas.bbox(item)[3] - y) / getattr(self, "scale", 1.0)
        return y + size * 1.35

    def draw_switch(self, x, y, on, name=None):
        """Toggle switch estilo iOS com animação/estado visual."""
        w, h = 50, 26
        bg_col = PRIMARY if on else SURFACE_HIGHEST
        self.rounded((x, y, x + w, y + h), 13, bg_col, outline=PRIMARY if on else OUTLINE_VARIANT)
        if on:
            cx = x + w - 14
            self.canvas.create_oval(cx - 10, y + 3, cx + 10, y + 23, fill="#00363d", outline="")
            # Checkmark vetorial interno
            self.canvas.create_line(cx - 5, y + 13, cx - 1, y + 17, fill=PRIMARY, width=2)
            self.canvas.create_line(cx - 1, y + 17, cx + 5, y + 9, fill=PRIMARY, width=2)
        else:
            cx = x + 14
            self.canvas.create_oval(cx - 10, y + 3, cx + 10, y + 23, fill=OUTLINE, outline="")
        if name:
            self.hit(name, (x, y, x + w, y + h))

    def finish_draw(self):
        focused = getattr(self, "focused_hotspot", None)
        for name, bounds, value in self.hotspots:
            if focused == (name, value):
                self.rounded(bounds, 12, "", PRIMARY)
                break
        scale = getattr(self, "scale", 1.0)
        if scale != 1.0:
            self.canvas.scale("all", 0, 0, scale, scale)

    # ----------------------------------------------------------------------
    # Renderização das Telas
    # ----------------------------------------------------------------------

    def draw(self):
        if self.closed:
            return
        self.transition_generation = getattr(self, "transition_generation", 0) + 1
        self.transitioning = False
        c = self.canvas
        c.delete("all")
        self.hotspots = []
        self.top_item = None
        self.ping_item = None
        self.dot_item = None

        if self.page in ("energy", "energy_month"):
            if getattr(self, "img_blank", None):
                c.create_image(0, 0, image=self.img_blank, anchor="nw")
            if self.page == "energy":
                self.draw_energy()
            else:
                self.draw_energy_month()
            self.finish_draw()
            return

        if self.page == "plug":
            if getattr(self, "img_blank", None):
                c.create_image(0, 0, image=self.img_blank, anchor="nw")
            self.draw_plug()
            self.finish_draw()
            return
        if self.page == "plug_confirm":
            if getattr(self, "img_blank", None):
                c.create_image(0, 0, image=self.img_blank, anchor="nw")
            self.draw_plug_confirm()
            self.finish_draw()
            return
        if self.page == "settings":
            if getattr(self, "img_blank", None):
                c.create_image(0, 0, image=self.img_blank, anchor="nw")
            self.draw_settings()
            self.finish_draw()
            return
        if self.page == "extras":
            if getattr(self, "img_blank", None):
                c.create_image(0, 0, image=self.img_blank, anchor="nw")
            self.draw_extras()
            self.finish_draw()
            return

        # TELA 1: DASHBOARD PRINCIPAL
        if getattr(self, "img_base", None):
            c.create_image(0, 0, image=self.img_base, anchor="nw")
        else:
            self.rounded((0, 0, WIDTH, HEIGHT), 1, BG)

        power = self.dps.get("1") is True
        ambient = self.dps.get("3")
        setpoint = self.pending_temp if self.pending_temp is not None else self.dps.get("2")
        setpoint_val = setpoint if setpoint is not None else 24

        # Topo animado (chassi, fluxo de ar ciano visível apenas quando ligado)
        top_img = None
        if power and getattr(self, "top_on", None):
            idx = min(self.frame_idx, len(self.top_on) - 1)
            top_img = self.top_on[idx]
        elif getattr(self, "top_off", None):
            top_img = self.top_off

        if top_img:
            self.top_item = c.create_image(0, 0, image=top_img, anchor="nw")

        # 1. Cabeçalho Ambiente & ELGIN • CONTROLE LOCAL
        self.label(48, 36, "Ambiente", 14, SLATE_300, "normal")
        self.label(114, 34, f"{ambient}°" if ambient is not None else "--°", 17, PRIMARY_HERO, "bold")
        self.label(24, 60, tracked("ELGIN • CONTROLE LOCAL"), 10, SLATE_400, "bold")
        self.hit("power", POWER_BOX)

        # 2. Visor Digital do Chassi do Split
        unit_temp = str(setpoint) if (power and setpoint is not None) else "--"
        self.label(320, 158, unit_temp, 14, PRIMARY if power else SLATE_500, "bold", anchor="center")

        # 3. Hero Central de Temperatura
        temp_str = str(setpoint) if setpoint is not None else "--"
        t_w = self.text_width(temp_str, 72, "bold")
        total_w = t_w + 3 + self.text_width("°C", 26, "normal")
        start_x = round((WIDTH - total_w) / 2)
        self.label(start_x, 332, temp_str, 72, PRIMARY_HERO, "bold")
        self.label(start_x + t_w + 3, 346, "°C", 26, PRIMARY_DIM, "normal")

        # Indicador ping + legenda TEMPERATURA DESEJADA
        c.create_oval(116, 452, 122, 458, fill=PRIMARY, outline="")
        self.label(130, 447, tracked("TEMPERATURA DESEJADA"), 11, SLATE_300, "bold")

        # 4. Slider de Temperatura e Stepper
        t_clamped = max(MIN_TEMP, min(MAX_TEMP, int(setpoint_val)))
        if getattr(self, "slider_imgs", None):
            s_img = self.slider_imgs[t_clamped - MIN_TEMP]
            c.create_image(SLIDER_BOX[0], SLIDER_BOX[1],
                           image=s_img, anchor="nw")

        self.hit("minus", MINUS_BOX)
        self.hit("plus", PLUS_BOX)
        self.hit("slider", (MINUS_BOX[2], SLIDER_BOX[1], PLUS_BOX[0], SLIDER_BOX[3]))

        # Limites 16° e 32°
        self.label(84, 546, f"{MIN_TEMP}° Mín", 11, SLATE_400, "semibold")
        self.label(306, 546, f"{MAX_TEMP}° Máx", 11, SLATE_400, "semibold", anchor="ne")

        # 5. Card Integrado da Tomada EKAZA
        plug_dps = getattr(self, "plug_dps", {})
        plug_error = getattr(self, "plug_error", "")
        meds = medidas_tomada(plug_dps)
        watts = round(meds["power_w"]) if meds["power_w"] is not None else 0

        if plug_error:
            plug_status_txt = "Sem conexão • verificar rede"
            dot_col = "#fca5a5"
        elif getattr(self, "plug_busy", False) and not plug_dps:
            plug_status_txt = "Sincronizando via LAN..."
            dot_col = SLATE_400
        elif plug_dps.get("1") is True:
            plug_status_txt = f"Ligada • Consumo {watts}W"
            dot_col = TERTIARY
        elif plug_dps.get("1") is False:
            plug_status_txt = "Desligada • Standby"
            dot_col = SLATE_500
        else:
            plug_status_txt = "Aguardando leitura local"
            dot_col = SLATE_400

        # Dot pulsante da tomada
        pill_left = self.action_pill(PLUG_ACTION_BOX, "Medição")
        c.create_oval(80, 584, 88, 592, fill=dot_col, outline="")
        self.fit_label(96, 588, "Tomada EKAZA", 13, pill_left - 108, TEXT, "bold", anchor="w")
        self.fit_label(80, 610, plug_status_txt, 11, pill_left - 92,
                       dot_col if plug_dps.get("1") is True else MUTED, anchor="w")
        self.hit("plug", PLUG_CARD_BOX)

        # 6. Cards Inferiores (Modo, Vento, Funções, Eco)
        mode = MODOS.get(self.dps.get("4"), "--")
        fan = VENTILACAO.get(self.dps.get("5"), "--")
        eco = self.dps.get("11") is True

        if getattr(self, "eco_imgs", None) and len(self.eco_imgs) > 1:
            c.create_image(ECO_BOX[0], ECO_BOX[1],
                           image=self.eco_imgs[1 if eco else 0], anchor="nw")

        cards_data = [
            ("mode", "Modo", mode),
            ("fan", "Vento", fan),
            ("extras", "Funções", "Dormir"),
            ("eco", "Eco", "Ligado" if eco else "Desligado" if "11" in self.dps else "--"),
        ]
        for i, (name, title, val) in enumerate(cards_data):
            x1, y1, x2, y2 = card_box(i)
            is_active = (name == "eco" and eco)
            label_col = PRIMARY if is_active else SLATE_400
            val_col = PRIMARY if is_active else TEXT
            self.label(x1 + 12, y1 + 56, title, 11, label_col, "normal")
            size = 13
            while size > 11 and self.text_width(val, size, "bold") > x2 - x1 - 24:
                size -= 1
            self.fit_label(x1 + 12, y1 + 74, val, size, x2 - x1 - 24, val_col, "bold")
            self.hit(name, (x1, y1, x2, y2))

        # 7. Rodapé de Conexão e Botões de Atalho
        if self.error:
            status_text = "Sem conexão • clique p/ reconectar"
            self.status_colors = STATUS_ERROR
        elif self.busy or getattr(self, "reconnecting", False):
            status_text = "Sincronizando..."
            self.status_colors = STATUS_SYNC
        elif self.updated:
            status_text = f"Conectado • {self.updated:%H:%M}"
            self.status_colors = STATUS_OK
        else:
            status_text = "Conectando..."
            self.status_colors = STATUS_SYNC

        light_col, ping_col, text_col = self.status_colors
        scale = getattr(self, "scale", 1.0)
        sx, sy, sr = STATUS_DOT
        if ping_col:
            self.ping_item = c.create_oval(sx - sr, sy - sr, sx + sr, sy + sr,
                                           fill=ping_col, outline="")
        self.dot_item = c.create_oval(sx - sr, sy - sr, sx + sr, sy + sr,
                                      fill=light_col, outline="")

        self.label(46, 796, status_text, 12, text_col, "normal")
        self.hit("refresh", (20, FOOTER_LINE_Y, 280, HEIGHT))
        self.hit("plug", (295, 782, 338, 826))      # Botão do raio abre telemetria da tomada
        self.hit("settings", (338, 782, 380, 826))  # Botão da engrenagem abre ajustes

        if self.menu:
            self.draw_menu()
        self.finish_draw()

    # ----------------------------------------------------------------------
    # TELA 2: FUNÇÕES DO AR-CONDICIONADO
    # ----------------------------------------------------------------------
    def draw_extras(self):
        c = self.canvas

        # Botão Voltar ‹
        self.rounded((22, 28, 56, 62), 17, SURFACE_CONTAINER, OUTLINE_VARIANT)
        self.label(39, 44, "‹", 22, TEXT, "bold", anchor="center")
        self.hit("back", (20, 24, 65, 68))

        # Título da tela (hierarquia clara: título 28 / apoio 13)
        self.label(24, 76, "Funções", 28, TEXT, "bold")
        self.fit_label(24, 112, "Ajustes do aparelho Elgin", 13, 342, MUTED)

        fan = self.dps.get("5")
        vert = self.dps.get("31") not in (None, "off")
        horiz = self.dps.get("33") is True
        direction = "Ambas" if vert and horiz else "Vertical" if vert else "Horizontal" if horiz else "Fixa"

        rows = [
            ("extra_sleep", "Dormir", "Modo de sono", self.dps.get("25") is True, None),
            ("extra_swing", "Aletas", "Direção do fluxo de ar", None, direction),
            ("extra_mute", "Mudo", "Ventilação sem avisos sonoros", fan == "mute", None),
            ("extra_display", "Display", "Luz do visor do ar", self.dps.get("36") is True, None),
            ("extra_turbo", "Turbo", "Somente no modo Frio", fan == "strong", None),
        ]

        for i, (name, title, subtitle, enabled, badge) in enumerate(rows):
            y1 = 140 + i * 68
            y2 = y1 + 60
            self.rounded((24, y1, 366, y2), 16, SURFACE_CONTAINER)
            self.label(40, y1 + 9, title, 15, TEXT, "bold")
            if name == "extra_swing":
                p_left = self.action_pill((278, y1 + 16, 350, y1 + 44), badge or "Fixa")
                self.fit_label(40, y1 + 33, subtitle, 12, p_left - 52, MUTED)
            else:
                self.draw_switch(300, y1 + 16, enabled)
                self.fit_label(40, y1 + 33, subtitle, 12, 248, MUTED)
            self.hit(name, (24, y1, 366, y2))

        # Timer de desligamento: um único bloco, ação primária única
        self.rounded((24, 492, 366, 660), 16, SURFACE_CONTAINER)
        self.label(40, 508, "Timer de desligamento", 15, TEXT, "bold")
        self.label(40, 530, "Desliga o ar após o tempo escolhido", 12, MUTED)

        chips = [("30 min", "0030"), ("1 hora", "0100"), ("2 horas", "0200"), ("4 horas", "0400")]
        sel_hours = getattr(self, "selected_timer_hours", "0100")
        for idx, (label, val) in enumerate(chips):
            cx1 = 38 + idx * 80
            cx2 = cx1 + 72
            is_sel = (val == sel_hours)
            self.rounded((cx1, 558, cx2, 590), 10, PRIMARY if is_sel else SURFACE_HIGH)
            self.label((cx1 + cx2) / 2, 574, label, 12, "#00363d" if is_sel else TEXT,
                       "bold" if is_sel else "normal", anchor="center")
            self.hit("timer_chip_" + val, (cx1, 558, cx2, 590), val)

        active_timer = self.dps.get("102") is True
        btn_txt = "Cancelar timer" if active_timer else f"Ativar timer de {self.timer_label()}"
        self.rounded((38, 602, 352, 646), 12, SURFACE_HIGH if active_timer else PRIMARY)
        self.label(195, 624, btn_txt, 14, PRIMARY if active_timer else "#00363d", "bold", anchor="center")
        self.hit("extra_timer", (38, 602, 352, 646))

        # Estado real da comunicação
        if self.error:
            foot, foot_col = "Falha de comunicação • atualize e tente de novo", "#fca5a5"
        elif self.busy:
            foot, foot_col = "Sincronizando com o aparelho...", PRIMARY
        elif self.updated:
            foot, foot_col = f"Confirmado pelo aparelho às {self.updated:%H:%M}", MUTED
        else:
            foot, foot_col = "Aguardando o aparelho", MUTED
        self.label(195, 786, foot, 12, foot_col, anchor="center")

        if self.menu:
            self.draw_menu()

    def timer_label(self):
        mapping = {"0030": "30 min", "0100": "1 hora", "0200": "2 horas", "0400": "4 horas"}
        return mapping.get(getattr(self, "selected_timer_hours", "0100"), "1 hora")

    # ----------------------------------------------------------------------
    # TELA 3: TOMADA EKAZA & TELEMETRIA
    # ----------------------------------------------------------------------
    def draw_plug(self):
        c = self.canvas
        dps = getattr(self, "plug_dps", {})
        error = getattr(self, "plug_error", "")
        busy = getattr(self, "plug_busy", False)
        power = dps.get("1")
        meds = medidas_tomada(dps)

        # Botão Voltar ‹ e Badges de Contexto
        self.rounded((22, 28, 56, 62), 17, SURFACE_CONTAINER, OUTLINE_VARIANT)
        self.label(39, 44, "‹", 22, TEXT, "bold", anchor="center")
        self.hit("back", (20, 24, 65, 68))

        self.label(68, 30, "Tomada EKAZA", 20, TEXT, "bold")
        self.fit_label(68, 60, "Alimentação do ar-condicionado", 12, 290, MUTED)

        # Card Master de Controle de Energia da Tomada
        self.rounded((24, 96, 366, 288), 18, SURFACE_CONTAINER, OUTLINE_VARIANT)

        # Disco Tátil Central com Halo
        p_col = PRIMARY if (power is True and not error) else SLATE_500
        if power is True and not error:
            # Halo azul/verde pulsante
            c.create_oval(155, 112, 235, 192, fill="#00363d", outline="")
            c.create_oval(163, 120, 227, 184, fill=SURFACE_HIGH, outline=PRIMARY, width=2)
        else:
            c.create_oval(163, 120, 227, 184, fill=SURFACE_LOW, outline=OUTLINE_VARIANT, width=1)
        # Símbolo vetorial de Power
        c.create_arc(183, 143, 207, 167, start=315, extent=270, style="arc", outline=p_col, width=3)
        c.create_line(195, 139, 195, 153, fill=p_col, width=3)

        # Headings de Estado
        if error:
            badge_txt, badge_col = "FALHA NA REDE", "#fca5a5"
            state_txt, state_col = "Sem conexão", "#fca5a5"
            sub_txt = "Verifique o roteador ou atualize a telemetria"
        elif power is True:
            badge_txt, badge_col = "CIRCUITO ENERGIZADO", PRIMARY
            state_txt, state_col = "Ligada", TERTIARY
            sub_txt = "Alimentando compressor e ventilação"
        elif power is False:
            badge_txt, badge_col = "STANDBY / CORTE ATIVO", SLATE_400
            state_txt, state_col = "Desligada", TEXT
            sub_txt = "Equipamento em standby ou desligado"
        else:
            badge_txt, badge_col = "SINCRONIZANDO", MUTED
            state_txt, state_col = "Aguardando", MUTED
            sub_txt = "Aguardando resposta do protocolo local..."

        self.label(195, 204, badge_txt, 11, badge_col, "bold", anchor="center")
        self.label(195, 236, state_txt, 28, state_col, "bold", anchor="center")
        self.fit_label(195, 272, sub_txt, 12, 310, MUTED, anchor="center")

        # Botão Master de Ligar/Desligar
        enabled = not busy and not error and power in (True, False)
        btn_action = "Desligar tomada" if power is True else "Ligar tomada"
        btn_bg = PRIMARY if (power is True and enabled) else SURFACE_HIGH if enabled else SURFACE_LOW
        btn_fg = "#00363d" if (power is True and enabled) else TEXT if enabled else SLATE_500

        self.rounded((24, 304, 366, 360), 18, btn_bg)
        self.label(195, 332, btn_action, 15, btn_fg, "bold", anchor="center")
        if enabled:
            self.hit("plug_power", (24, 304, 366, 360))

        self.fit_label(195, 380, "O estado só muda após confirmação pela rede local", 11, 342, MUTED, anchor="center")

        # Telemetria instantânea
        self.label(24, 396, "Consumo instantâneo", 15, TEXT, "bold")

        # Três métricas com a mesma altura e hierarquia (valor grande, rótulo curto)
        metrics = [
            ("Potência", meds["power_w"], "W", 0, ""),
            ("Tensão", meds["voltage_v"], "V", 1, ""),
            ("Corrente", meds["current_a"], "A", 2, ""),
        ]
        for i, (title, value, unit, precision, caption) in enumerate(metrics):
            x = 24 + i * 118
            self.rounded((x, 424, x + 106, 524), 16, SURFACE_CONTAINER)
            self.label(x + 16, 440, title, 12, MUTED, "semibold")
            rendered = f"{value:.{precision}f}" if value is not None and not error else "--"
            size = 24
            while size > 17 and self.text_width(rendered, size, "bold") + self.text_width(unit, 12, "bold") + 8 > 74:
                size -= 1
            self.metric_value(x + 16, 470, rendered, unit, size, 12)

        # Consumo de energia fica separado de potência instantânea.
        energy = self.energy_snapshot()
        self.rounded((24, 552, 366, 772), 18, SURFACE_CONTAINER, OUTLINE_VARIANT)
        self.label(40, 568, "Eficiência e Consumo", 14, TEXT, "bold")
        self.fit_label(40, 592, format_source(energy), 11, 310, MUTED)
        self.label(40, 620, "Consumo hoje", 11, MUTED)
        self.metric_value(40, 640, format_kwh(energy["today_kwh"]), "kWh", 28, 14)
        if energy['source'] == 'cloud':
            self.label(350, 620, 'Mês atual', 11, MUTED, anchor='ne')
            self.fit_label(350, 650, format_kwh(energy.get('current_month_kwh')) + ' kWh', 16, 144, PRIMARY_HERO, 'bold', anchor='ne')
            self.label(350, 676, 'Potência • última hora', 10, MUTED, anchor='ne')
        else:
            self.label(350, 628, "Última hora", 11, MUTED, anchor="ne")
        self.draw_recent_energy(energy, (40, 692, 350, 720))
        self.action_pill((40, 732, 350, 760), "Ver detalhamento de consumo", name="energy_detail")
        self.hit("energy_detail", (40, 732, 350, 760))

        self.rounded((24, 784, 366, 824), 18, SURFACE_HIGH, OUTLINE_VARIANT)
        c.create_arc(108, 797, 122, 811, start=30, extent=300, style="arc", outline=PRIMARY, width=1.5)
        self.label(203, 804, "Atualizar telemetria", 12, PRIMARY, "bold", anchor="center")
        self.hit("plug_refresh", (24, 784, 366, 824))
        t_str = ("Sincronizando..." if busy else "Sem conexão • tente atualizar" if error else
                 f"Atualizado • {self.plug_updated:%H:%M}" if getattr(self, "plug_updated", None) else "Aguardando leitura")
        self.label(195, 834, t_str, 11, MUTED, anchor="center")

    # ----------------------------------------------------------------------
    # HISTÓRICO DE ENERGIA
    # ----------------------------------------------------------------------
    def energy_snapshot(self):
        store = getattr(self, "energy_store", None)
        try:
            local = store.snapshot() if store is not None else reference_snapshot()
        except (OSError, ValueError, sqlite3.Error):
            self.energy_error = "Histórico local indisponível"
            local = reference_snapshot()
        bridge = getattr(self, 'cloud_energy', None)
        cloud = bridge.snapshot() if bridge is not None else None
        if cloud:
            cloud['stale'] |= bool(getattr(self, 'cloud_failures', {}).get((local_now().year, local_now().month)))
            return {**local, **cloud, 'reference_date': None}
        return local

    def energy_months(self, year):
        bridge = getattr(self, 'cloud_energy', None)
        if bridge is not None:
            cloud = bridge.monthly(year)
            if cloud is not None:
                if any(key[0] == year for key in getattr(self, 'cloud_failures', {})):
                    cloud = [{**row, 'stale': True} for row in cloud]
                return cloud
            if bridge.snapshot() is not None:
                last = local_now().month if year == local_now().year else 12
                return [{'month': m, 'name': MONTHS[m-1], 'kwh': None, 'source': 'cloud_pending'}
                        for m in range(last, 0, -1)]
        store = getattr(self, "energy_store", None)
        if store is not None:
            try:
                rows = store.monthly(year)
            except (OSError, ValueError, sqlite3.Error):
                self.energy_error = "Histórico local indisponível"
                store = None
        if store is None:
            refs = reference_data()["months"]
            rows = [{"month": m, "name": MONTHS[m-1], "kwh": refs.get(f"{year}-{m:02}"),
                     "source": "reference" if f"{year}-{m:02}" in refs else "empty"} for m in range(12, 0, -1)]
        return [row for row in rows if row["source"] != "empty"]

    def energy_days(self):
        year = getattr(self, "energy_year", 2026)
        month = getattr(self, "energy_month", 10)
        bridge = getattr(self, 'cloud_energy', None)
        if bridge is not None:
            cloud = bridge.daily(year, month)
            if cloud is not None:
                cloud['stale'] |= bool(getattr(self, 'cloud_failures', {}).get((year, month)))
                return cloud
            if bridge.snapshot() is not None:
                import calendar
                return {'source': 'cloud_pending', 'days': [
                    {'day': d, 'date': f'{year}-{month:02}-{d:02}', 'kwh': None}
                    for d in range(1, calendar.monthrange(year, month)[1]+1)]}
        store = getattr(self, "energy_store", None)
        if store is not None:
            try:
                return store.daily(year, month)
            except (OSError, ValueError, sqlite3.Error):
                self.energy_error = "Histórico local indisponível"
        import calendar
        refs = reference_data()["days"]
        days = [{"day": d, "date": f"{year}-{month:02}-{d:02}",
                 "kwh": refs.get(f"{year}-{month:02}-{d:02}")}
                for d in range(1, calendar.monthrange(year, month)[1] + 1)]
        return {"source": "reference" if any(d["kwh"] is not None for d in days) else "empty", "days": days}

    def draw_recent_energy(self, energy, box):
        x1, y1, x2, y2 = box
        recent = [r for r in energy["recent"] if r.get('power_w') is not None]
        if len(recent) < 2:
            self.label((x1+x2)/2, (y1+y2)/2, "Histórico local em formação", 11, MUTED, anchor="center")
            return
        span = max(1, recent[-1]["ts"] - recent[0]["ts"])
        peak = max(1, max(r["power_w"] for r in recent))
        points = [(x1 + (r["ts"] - recent[0]["ts"])/span*(x2-x1),
                   y2 - r["power_w"]/peak*(y2-y1)) for r in recent]
        self.canvas.create_line(*[v for p in points for v in p], fill=PRIMARY, width=1.5, smooth=True)

    def energy_header(self, title, subtitle, back_name):
        self.rounded((24, 28, 60, 64), 18, SURFACE_CONTAINER, OUTLINE_VARIANT)
        self.canvas.create_line(45, 40, 39, 46, 45, 52, fill=PRIMARY, width=1.5)
        self.hit(back_name, (20, 24, 64, 68))
        self.fit_label(76, 36, title, 20, 238, TEXT, "bold")
        self.fit_label(24, 80, subtitle, 11, 342, MUTED)
        if getattr(self, 'cloud_energy', None) is not None:
            self.rounded((326, 28, 366, 64), 16, SURFACE_CONTAINER, OUTLINE_VARIANT)
            self.canvas.create_arc(337, 37, 355, 55, start=40, extent=290, style='arc', outline=PRIMARY, width=1.5)
            self.canvas.create_line(352, 37, 355, 38, 355, 34, fill=PRIMARY, width=1.5)
            self.hit('energy_refresh', (326, 28, 366, 64))

    def draw_monthly_cost(self, x, y, kwh, size, width):
        text = format_brl(monthly_cost(kwh, getattr(self, 'energy_tariff', DEFAULT_TARIFF)))
        while size > 12 and self.text_width(text, size, 'bold') > width:
            size -= 1
        self.fit_label(x, y, text, size, width, PRIMARY_HERO, 'bold')

    def draw_energy(self):
        energy = self.energy_snapshot()
        subtitle = ('Tomada EKAZA • Cloud • ' + datetime.fromtimestamp(energy['updated']).strftime('%d/%m %H:%M')) if energy['source'] == 'cloud' else 'Tomada EKAZA • histórico local'
        self.energy_header("Consumo de energia", subtitle, "energy_back")
        self.rounded((24, 108, 366, 312), 18, SURFACE_CONTAINER, OUTLINE_VARIANT)
        self.canvas.create_arc(40, 132, 172, 264, start=220, extent=-260,
                               style="arc", outline=OUTLINE_VARIANT, width=2)
        self.canvas.create_arc(46, 138, 166, 258, start=220, extent=-260,
                               style="arc", outline="#315964", width=1)
        self.fit_label(106, 193, format_kwh(energy["today_kwh"]), 32, 124, PRIMARY_HERO, "bold", anchor="center")
        self.fit_label(106, 237, "Sem leitura hoje" if energy["today_kwh"] is None else "Hoje (kWh)", 11, 132, MUTED, anchor="center")
        now = local_now()
        current = next((r for r in self.energy_months(now.year) if r['month'] == now.month), None)
        value = current['kwh'] if current else None
        tariff = getattr(self, 'energy_tariff', DEFAULT_TARIFF)
        self.label(192, 144, 'Custo estimado do mês', 11, MUTED)
        self.draw_monthly_cost(192, 174, value, 28, 158)
        self.fit_label(192, 218, f'{MONTHS[now.month-1]} • {format_kwh(value)} kWh', 11, 158, MUTED)
        self.fit_label(192, 244, f'{format_brl(tariff)}/kWh', 11, 158, MUTED)
        source = ('Tuya Cloud • cache desatualizado' if energy.get('stale') else 'Tuya Cloud • consumo registrado') if energy['source'] == 'cloud' else "Referência • 11/10/2026" if energy["source"] == "reference" else "LAN • dia parcial" if energy["source"] == "counter" else "Estimativa local • dia parcial"
        self.fit_label(195, 292, source, 11, 306, MUTED, anchor="center")

        self.rounded((24, 328, 366, 408), 18, SURFACE_CONTAINER, OUTLINE_VARIANT)
        metrics = medidas_tomada(getattr(self, "plug_dps", {}))
        stale = bool(getattr(self, "plug_error", "")) or not getattr(self, "plug_updated", None)
        if not stale:
            stale = (datetime.now()-self.plug_updated).total_seconds() > 60
        if stale:
            metrics = dict.fromkeys(metrics)
        total_name = "Total local" if energy["total_source"] == "estimated" else "Total ref." if energy["total_source"] == "reference" else "Total"
        values = [(metrics["current_a"], 3, "A", "Corrente"), (metrics["power_w"], 1, "W", "Potência"),
                  (metrics["voltage_v"], 1, "V", "Tensão"), (energy["total_kwh"], 2, "kWh", total_name)]
        for i, (value, precision, unit, label) in enumerate(values):
            cx = 24 + (i + .5) * 85.5
            text = f"{value:.{precision}f}" if value is not None else "--"
            self.fit_label(cx, 352, text, 16, 69, TEXT, "bold", anchor="center")
            self.fit_label(cx, 376, f"{label} ({unit})", 10, 77, MUTED, anchor="center")

        year = getattr(self, "energy_year", local_now().year)
        self.label(24, 432, f"Ano {year}", 14, TEXT, "bold")
        if stale:
            self.label(24, 456, "Instantâneas indisponíveis • atualize a tomada", 10, MUTED)
        self.label(284, 432, "kWh", 11, MUTED, anchor="ne")
        years = sorted(set(energy["years"] + [year]))
        if year > years[0]:
            self.energy_chevron(310, 444, -1)
            self.hit("energy_year_prev", (292, 424, 328, 464))
        if year < years[-1]:
            self.energy_chevron(348, 444, 1)
            self.hit("energy_year_next", (330, 424, 366, 464))
        rows = self.energy_months(year)
        offset = min(getattr(self, "energy_month_offset", 0), max(0, len(rows)-1))
        self.energy_month_offset = offset
        for i, row in enumerate(rows[offset:offset+4]):
            y = 480 + i * 80
            self.rounded((24, y, 366, y+72), 18, SURFACE_CONTAINER, OUTLINE_VARIANT)
            self.label(40, y+12, row["name"], 14, TEXT, "semibold")
            src = 'Tuya Cloud • aguardando consulta' if row['source'] == 'cloud_pending' else ('Tuya Cloud • cache' if row.get('stale') else 'Tuya Cloud') if row['source'] == 'cloud' else "Referência Smart Life" if row["source"] == "reference" else "Sem intervalo observado" if row["source"] == "pending" else "Estimativa local" if "estimated" in row["source"] else "Leituras LAN • parcial"
            self.label(40, y+40, src, 11, MUTED)
            self.label(330, y+16, format_kwh(row["kwh"]), 18, PRIMARY_HERO, "bold", anchor="ne")
            self.canvas.create_line(346, y+24, 350, y+28, 346, y+32, fill=PRIMARY, width=1.5)
            self.hit("energy_month", (24, y, 366, y+72), row["month"])
        if not rows:
            self.label(195, 560, "Sem histórico para este ano", 13, MUTED, anchor="center")
        if offset > 0:
            self.energy_chevron(44, 820, -1)
            self.hit("energy_months_prev", (24, 800, 64, 840))
        if offset + 4 < len(rows):
            self.energy_chevron(346, 820, 1)
            self.hit("energy_months_next", (326, 800, 366, 840))
        footer = self.cloud_notice() or getattr(self, "energy_error", "") or f"{min(offset+1,len(rows))}–{min(offset+4,len(rows))} de {len(rows)} meses"
        self.fit_label(195, 820, footer, 11, 250, MUTED, anchor="center")

    def draw_energy_month(self):
        year = getattr(self, "energy_year", 2026)
        month = getattr(self, "energy_month", 10)
        series = self.energy_days()
        self.energy_header(MONTHS[month-1], f"Ano {year} • Unidade: kWh", "energy_month_back")
        row = next((r for r in self.energy_months(year) if r["month"] == month), None)
        self.rounded((24, 108, 366, 232), 18, SURFACE_CONTAINER, OUTLINE_VARIANT)
        self.label(40, 124, "Consumo no mês", 11, MUTED)
        self.metric_value(40, 148, format_kwh(row["kwh"]) if row else "--", "kWh", 32, 14)
        tariff = getattr(self, 'energy_tariff', DEFAULT_TARIFF)
        self.label(208, 124, 'Custo estimado', 11, MUTED)
        self.draw_monthly_cost(208, 153, row['kwh'] if row else None, 24, 142)
        self.fit_label(208, 184, f'{format_brl(tariff)}/kWh', 10, 142, MUTED)
        note = (('Tuya Cloud • cache desatualizado' if series.get('stale') else 'Tuya Cloud • consumo registrado') if series['source'] == 'cloud' else "Referência • barras anteriores aproximadas" if series["source"] == "reference" else
                'Tuya Cloud • aguardando consulta do mês' if series['source'] == 'cloud_pending' else
                "Estimativa local • dias parciais" if series["source"] == "estimated" else
                "Contador LAN • dias parciais / rateados" if series["source"] == "counter" else
                "Sem histórico diário disponível")
        self.fit_label(40, 200, note, 11, 310, MUTED)
        self.rounded((24, 248, 366, 648), 18, SURFACE_CONTAINER, OUTLINE_VARIANT)
        self.label(44, 264, "Consumo diário", 14, TEXT, "bold")
        days = series["days"]
        start = min(getattr(self, "energy_chart_start", 0), max(0, len(days)-8))
        self.energy_chart_start = start
        window = days[start:start+8]
        selected = getattr(self, "energy_selected_day", 1)
        peak = max([d["kwh"] or 0 for d in window] + [1])
        # Escala legível: passos 0.5/1/2/5, nunca dízimas como 0.571429.
        raw_step = peak/5
        magnitude = 10 ** math.floor(math.log10(raw_step))
        tick_step = next(n*magnitude for n in (1, 2, 5, 10) if n*magnitude >= raw_step)
        upper = max(tick_step, math.ceil(peak/tick_step)*tick_step)
        ticks = round(upper/tick_step)
        x1, x2, y1, y2 = 64, 346, 328, 592
        for i in range(ticks+1):
            v = upper*i/ticks
            y = y2 - (y2-y1)*i/ticks
            self.canvas.create_line(x1, y, x2, y, fill=SURFACE_HIGHEST, dash=(3,4))
            self.label(54, y, f"{v:g}", 10, MUTED, anchor="e")
        step = (x2-x1)/8
        for i, day in enumerate(window):
            cx = x1 + (i+.5)*step
            value = day["kwh"]
            active = day["day"] == selected
            color = PRIMARY if active else "#596570"
            if value is not None and value > 0:
                top = y2 - (y2-y1)*value/upper
                self.rounded((cx-10, top, cx+10, y2), 4, color, outline="")
            else:
                top = y2
                self.canvas.create_line(cx-8, y2, cx+8, y2, fill=color if value is not None else SURFACE_HIGHEST, width=2)
            if active:
                self.label(cx, top-20, f"{value:.2f}" if value is not None else "--", 11, PRIMARY, "bold", anchor="center")
            self.label(cx, 620, f"{month:02}-{day['day']:02}", 10, PRIMARY if active else MUTED, anchor="center")
            self.hit("energy_day", (cx-step/2, 280, cx+step/2, 628), day["day"])
        if not any(d["kwh"] is not None for d in days):
            self.label(195, 432, "Histórico diário ainda não disponível", 12, MUTED, anchor="center")
        if start > 0:
            self.energy_chevron(44, 676, -1)
            self.hit("energy_days_prev", (24, 652, 64, 700))
        if start + 8 < len(days):
            self.energy_chevron(346, 676, 1)
            self.hit("energy_days_next", (326, 652, 366, 700))
        self.label(195, 676, f"Dias {window[0]['day']:02}–{window[-1]['day']:02} • {MONTHS[month-1]}", 12, TEXT, anchor="center")
        self.label(40, 724, "Clique em uma barra para selecionar o dia.", 11, MUTED)
        self.label(40, 748, "Use as setas para percorrer o mês.", 11, MUTED)
        self.fit_label(40, 772, self.cloud_notice(), 10, 310, MUTED)
        self.fit_label(40, 796, "Sem barra = sem leitura; 0 = consumo observado zero.", 11, 310, MUTED)

    def energy_scroll(self, event):
        if self.page == "energy":
            self.page_energy_months(4 if event.delta < 0 else -4)

    def page_energy_months(self, step):
        rows = self.energy_months(getattr(self, "energy_year", 2026))
        self.energy_month_offset = max(0, min(max(0, len(rows)-4), getattr(self, "energy_month_offset", 0)+step))
        self.draw()

    def energy_key(self, step):
        if self.page == "energy_month":
            days = self.energy_days()["days"]
            self.energy_selected_day = max(1, min(len(days), self.energy_selected_day+step))
            self.focused_hotspot = ("energy_day", self.energy_selected_day)
            if not self.energy_chart_start < self.energy_selected_day <= self.energy_chart_start+8:
                self.energy_chart_start = max(0, min(len(days)-8, self.energy_selected_day-4))
            self.draw()
        else:
            self.change_temp(step)

    def energy_chevron(self, x, y, direction):
        self.canvas.create_line(x-2*direction, y-5, x+3*direction, y,
                                x-2*direction, y+5, fill=PRIMARY, width=1.5)

    def energy_tab(self, event, step=1):
        if self.page not in ("energy", "energy_month", "plug"):
            return None
        choices = [(n, v) for n, _, v in self.hotspots if n.startswith("energy_")]
        if not choices:
            return None
        focused = getattr(self, "focused_hotspot", None)
        index = choices.index(focused) if focused in choices else (-1 if step > 0 else 0)
        self.focused_hotspot = choices[(index+step) % len(choices)]
        self.canvas.focus_set()
        self.draw()
        return "break"

    def energy_activate(self, _event):
        focused = getattr(self, "focused_hotspot", None)
        if self.page not in ("energy", "energy_month", "plug") or not focused:
            return None
        for name, bounds, value in self.hotspots:
            if (name, value) == focused:
                scale = getattr(self, "scale", 1)
                self.click(SimpleNamespace(x=(bounds[0]+bounds[2])/2*scale,
                                           y=(bounds[1]+bounds[3])/2*scale))
                return "break"

    def navigate_energy(self, page, direction=1, focus=None):
        self.page = page
        self.focused_hotspot = focus
        self.draw()
        self.submit_energy()
        if focus is None:
            choices = [(n, v) for n, _, v in self.hotspots if n.startswith("energy_")]
            self.focused_hotspot = choices[0] if choices else None
        root = getattr(self, "root", None)
        if root is None:
            return
        self.canvas.focus_set()
        generation = self.transition_generation
        scale = getattr(self, "scale", 1)
        offset = 16*scale*direction
        self.canvas.move("all", offset, 0)
        self.transitioning = True
        started = time.monotonic()

        def frame():
            nonlocal offset
            if self.closed or generation != self.transition_generation:
                return
            t = min(1, (time.monotonic()-started)/.18)
            next_offset = 16*scale*direction*(1-t)**3
            self.canvas.move("all", next_offset-offset, 0)
            offset = next_offset
            if t < 1:
                root.after(16, frame)
            else:
                self.transitioning = False
        root.after(16, frame)

    # ----------------------------------------------------------------------
    # TELA DE CONFIRMAÇÃO DO CORTE DA TOMADA
    # ----------------------------------------------------------------------
    def draw_plug_confirm(self):
        # Botão Voltar ‹
        self.rounded((22, 28, 56, 62), 17, SURFACE_CONTAINER, OUTLINE_VARIANT)
        self.label(39, 44, "‹", 22, TEXT, "bold", anchor="center")
        self.hit("plug_cancel_off", (20, 20, 65, 68))

        self.label(24, 76, "Confirmar desligamento", 24, TEXT, "bold")
        self.label(24, 106, "Tomada EKAZA • Proteção do ar-condicionado", 12, MUTED)

        # Card de Alerta
        self.rounded((24, 140, 366, 395), 18, SURFACE_CONTAINER, OUTLINE_VARIANT)
        self.label(42, 165, "⚠  Corte de energia", 20, "#fca5a5", "bold")
        self.label(42, 210, "O ar não está confirmado desligado.", 13, TEXT, "bold")
        self.label(42, 245, "Cortar a energia física agora pode", 12, MUTED)
        self.label(42, 268, "interromper o ciclo do compressor", 12, MUTED)
        self.label(42, 291, "e reduzir a vida útil do aparelho.", 12, MUTED)
        self.label(42, 345, "A tomada só desliga se você confirmar.", 12, SLATE_300, "bold")

        enabled = (not self.plug_busy and not self.plug_error and
                   self.plug_dps.get("1") is True)

        # Botão Desligar mesmo assim (Cobre y=465)
        self.rounded((24, 437, 366, 503), 16, "#93000a" if enabled else SURFACE_LOW,
                     outline="#ffb4ab" if enabled else OUTLINE_VARIANT)
        self.label(195, 470, "Desligar mesmo assim", 15,
                   TEXT if enabled else SLATE_500, "bold", anchor="center")
        if enabled:
            self.hit("plug_confirm_off", (24, 437, 366, 503))

        # Botão Cancelar (Cobre y=545)
        self.rounded((24, 520, 366, 573), 14, SURFACE_HIGH, OUTLINE_VARIANT)
        self.label(195, 546, "Cancelar", 14, TEXT, "semibold", anchor="center")
        self.hit("plug_cancel_off", (24, 520, 366, 573))

        if self.plug_error:
            self.label(195, 600, self.plug_error, 11, "#fca5a5", anchor="center")

    # ----------------------------------------------------------------------
    # TELA DE AJUSTES
    # ----------------------------------------------------------------------
    def draw_settings(self):
        self.rounded((22, 28, 56, 62), 17, SURFACE_CONTAINER, OUTLINE_VARIANT)
        self.label(39, 44, "‹", 22, TEXT, "bold", anchor="center")
        self.hit("back", (20, 20, 65, 68))

        self.label(24, 76, "Ajustes", 24, TEXT, "bold")
        self.label(24, 106, "Ar do quarto • Configurações do painel", 12, MUTED)

        # Card 1: Iniciar com o Windows
        self.rounded((24, 130, 366, 226), 16, SURFACE_CONTAINER, OUTLINE_VARIANT)
        self.label(42, 148, "Abrir com o Windows", 14, TEXT, "bold")
        self.label(42, 178, "Controle disponível na bandeja ao entrar", 11, MUTED)
        enabled = startup_enabled()
        self.draw_switch(304, 156, enabled)
        self.hit("startup", (24, 130, 366, 226))

        # Card 2: Conexão Local
        self.rounded((24, 238, 366, 328), 16, SURFACE_CONTAINER, OUTLINE_VARIANT)
        self.label(42, 256, "Conexão local", 14, TEXT, "bold")
        self.label(42, 286, "TinyTuya LAN • IP redescoberto automaticamente", 11, MUTED)

        # Card 3: Sobre
        self.rounded((24, 340, 366, 430), 16, SURFACE_CONTAINER, OUTLINE_VARIANT)
        self.label(42, 358, "Sobre o painel", 14, TEXT, "bold")
        self.label(42, 388, "Feche para recolher. Saia pelo menu da bandeja.", 11, MUTED)

        if self.startup_error:
            self.label(24, 460, self.startup_error, 11, "#fca5a5")

    # ----------------------------------------------------------------------
    # MENUS DROPDOWN (MODO, VENTO, ALETAS)
    # ----------------------------------------------------------------------
    def draw_menu(self):
        choices = {
            "mode": [("Automático", "auto"), ("Resfriar", "cold"),
                     ("Ventilar", "wind"), ("Secar", "wet")],
            "fan": [("Auto", "auto"), ("Baixa", "low"), ("Média", "middle"),
                    ("Alta", "high")],
            "swing": [("Fixa", "off"), ("Vertical", "vertical"),
                      ("Horizontal", "horizontal"), ("Ambas", "both")],
        }[self.menu]
        height = len(choices) * 38 + 12
        x1, x2 = (24, 190) if self.menu == "mode" else (112, 278) if self.menu == "fan" else (200, 366)
        bottom = 630 if self.page == "control" else 580
        y1 = bottom - height
        self.rounded((x1, y1, x2, bottom), 16, SURFACE_HIGH, PRIMARY)
        for i, (title, value) in enumerate(choices):
            y = y1 + 6 + i * 38
            self.label(x1 + 16, y + 10, title, 12, TEXT, "semibold")
            self.hit("choice", (x1 + 6, y, x2 - 6, y + 36), (self.menu, value))

    def choice_at(self, x, y):
        scale = getattr(self, "scale", 1.0)
        x, y = x / scale, y / scale
        for name, (x1, y1, x2, y2), value in reversed(self.hotspots):
            if x1 <= x <= x2 and y1 <= y <= y2:
                return name, value
        return None, None

    # ----------------------------------------------------------------------
    # INTERAÇÕES DO USUÁRIO
    # ----------------------------------------------------------------------
    def click(self, event):
        if getattr(self, "transitioning", False):
            return
        name, value = self.choice_at(event.x, event.y)
        if name == "choice":
            self.menu = None
            group, selected = value
            if group == "mode":
                self.submit("mode", selected)
            elif group == "fan":
                self.submit("fan", selected)
            elif group == "swing":
                self.set_swing(selected)
            return
        if self.menu:
            self.menu = None
            self.draw()
            return

        if name == 'energy_refresh':
            self.submit_energy(force=True)
            return
        if name == "energy_detail":
            self.energy_year = getattr(self, "energy_year", local_now().year)
            self.energy_month_offset = 0
            self.navigate_energy("energy")
            return
        elif name == "energy_back":
            self.navigate_energy("plug", -1, focus=("energy_detail", None))
            return
        elif name == "energy_month_back":
            self.navigate_energy("energy", -1, focus=("energy_month", self.energy_month))
            return
        elif name == "energy_month":
            self.energy_month = value
            days = self.energy_days()["days"]
            observed = [d["day"] for d in days if d["kwh"] is not None]
            self.energy_selected_day = max(observed) if observed else 1
            self.energy_chart_start = max(0, min(len(days)-8, self.energy_selected_day-8))
            self.navigate_energy("energy_month")
            return
        elif name == "energy_day":
            self.energy_selected_day = value
            self.focused_hotspot = (name, value)
        elif name in ("energy_months_prev", "energy_months_next"):
            self.page_energy_months(-4 if name.endswith("prev") else 4)
            return
        elif name in ("energy_year_prev", "energy_year_next"):
            years = self.energy_snapshot()["years"]
            index = years.index(self.energy_year)
            self.energy_year = years[max(0, min(len(years)-1, index+(-1 if name.endswith("prev") else 1)))]
            self.energy_month_offset = 0
        elif name in ("energy_days_prev", "energy_days_next"):
            days = self.energy_days()["days"]
            step = -8 if name.endswith("prev") else 8
            self.energy_chart_start = max(0, min(len(days)-8, self.energy_chart_start+step))
            window = days[self.energy_chart_start:self.energy_chart_start+8]
            observed = [d["day"] for d in window if d["kwh"] is not None]
            self.energy_selected_day = max(observed) if observed else window[0]["day"]
        elif name == "settings":
            self.page = "settings"
        elif name == "extras":
            self.page = "extras"
        elif name == "plug":
            self.page = "plug"
            if not self.plug_busy:
                self.submit_plug("status")
        elif name == "back":
            self.page = "control"
        elif name == "plug_cancel_off":
            self.page = "plug"
        elif name == "plug_confirm_off":
            if self.plug_dps.get("1") is True and not self.plug_busy and not self.plug_error:
                self.page = "plug"
                self.submit_plug("power", False, force_off=True)
        elif name == "startup":
            try:
                enabled = not startup_enabled()
                set_startup(enabled)
                save_startup_preference(enabled)
                self.startup_error = ""
            except OSError as exc:
                self.startup_error = str(exc)
        elif name == "refresh":
            self.refresh_all()
        elif name == "plug_refresh":
            self.submit_plug("status")
            self.submit_energy(force=True)
        elif name == "plug_power":
            plug_power = self.plug_dps.get("1")
            if plug_power is True and not self.ac_off_confirmed():
                self.page = "plug_confirm"
            elif isinstance(plug_power, bool):
                self.submit_plug("power", not plug_power)
        elif name and name.startswith("timer_chip_"):
            self.selected_timer_hours = value
        elif self.busy or not self.dps:
            return
        elif name == "power":
            self.power()
        elif name == "minus":
            self.change_temp(-1)
        elif name == "plus":
            self.change_temp(1)
        elif name == "slider":
            self.dragging = True
            self.pending_temp = self.temp_at(event.x / getattr(self, "scale", 1.0))
        elif name in ("mode", "fan", "extra_swing"):
            self.menu = "swing" if name == "extra_swing" else name
        elif name == "eco":
            self.submit("protect", self.dps.get("11") is not True)
        elif name == "extra_sleep":
            self.submit("sleep", self.dps.get("25") is not True)
        elif name == "extra_display":
            self.submit("display", self.dps.get("36") is not True)
        elif name == "extra_mute":
            next_fan = None if self.dps.get("5") == "mute" else "mute"
            self.submit("special_fan", (next_fan, self.last_normal_fan))
        elif name == "extra_turbo":
            if self.dps.get("5") != "strong" and self.dps.get("4") != "cold":
                self.error = "Turbo requer modo Frio"
            else:
                next_fan = None if self.dps.get("5") == "strong" else "strong"
                self.submit("special_fan", (next_fan, self.last_normal_fan))
        elif name == "extra_timer":
            self.submit("timer_off_1h", self.dps.get("102") is not True)
        if name in ('energy_year_prev', 'energy_year_next'):
            self.submit_energy()
        self.draw()

    def motion(self, event):
        name, _ = self.choice_at(event.x, event.y)
        if name != self.hover:
            previous = self.hover
            self.hover = name
            self.canvas.configure(cursor="hand2" if name else "")
            if self.page == "plug" and (name == "energy_detail" or previous == "energy_detail"):
                self.draw()

    def drag(self, event):
        if self.dragging:
            self.pending_temp = self.temp_at(event.x / getattr(self, "scale", 1.0))
            self.draw()

    def release(self, _event):
        if self.dragging:
            self.dragging = False
            value = self.pending_temp
            self.pending_temp = None
            self.submit("temp", value)

    @staticmethod
    def temp_at(x):
        return temp_from_x(x)

    def power(self):
        if self.page == "control" and self.dps and not self.busy:
            self.submit("power", self.dps.get("1") is not True)

    def change_temp(self, step):
        if self.page == "control" and self.dps and not self.busy:
            current = int(self.dps.get("2", 23))
            self.submit("temp", max(16, min(32, current + step)))

    def set_swing(self, value):
        vertical = value in ("vertical", "both")
        horizontal = value in ("horizontal", "both")
        self.submit("swing", (vertical, horizontal))


def already_running():
    kernel = ctypes.windll.kernel32
    kernel.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel.CreateMutexW(None, False, "Local\\ElginACTrayMutex")
    if kernel.GetLastError() == 183:
        kernel.OpenEventW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
        kernel.OpenEventW.restype = wintypes.HANDLE
        event = kernel.OpenEventW(0x0002, False, "Local\\ElginACTrayShow")
        if event:
            kernel.SetEvent(event)
            kernel.CloseHandle(event)
        kernel.CloseHandle(handle)
        return True, None
    return False, handle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--preview", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    duplicate, mutex = already_running()
    if duplicate:
        return
    kernel = ctypes.windll.kernel32
    kernel.CreateEventW.argtypes = (ctypes.c_void_p, wintypes.BOOL,
                                     wintypes.BOOL, wintypes.LPCWSTR)
    kernel.CreateEventW.restype = wintypes.HANDLE
    event = kernel.CreateEventW(None, False, False, "Local\\ElginACTrayShow")
    root = tk.Tk()
    app = TrayApp(root, show_at_start=(args.show or args.preview) and not args.background,
                  preview=args.preview)

    def poll_event():
        if app.closed:
            return
        if kernel.WaitForSingleObject(event, 0) == 0:
            app.show()
        root.after(150, poll_event)

    root.after(150, poll_event)
    try:
        root.mainloop()
    finally:
        if not app.closed:
            app.icon.stop()
        kernel.CloseHandle(event)
        kernel.CloseHandle(mutex)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        traceback.print_exc()
        try:
            dialog = tk.Tk()
            dialog.withdraw()
            messagebox.showerror("Elgin AC", f"Não foi possível abrir o controle:\n\n{exc}")
            dialog.destroy()
        except Exception:
            pass
        raise
