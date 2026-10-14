"""Controle Elgin na bandeja do Windows. Execute com --show para abrir o painel."""

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime
import json
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

from PIL import Image, ImageDraw, ImageFont
import pystray

from elgin_app import ElginApp
from ekaza_plug import run_operation as operar_tomada
from ekaza_plug import ler_config as config_tomada
from bridge import EnergyBridge
from energy_cost import load_tariff
from energy_history import EnergyHistory, MONTHS, local_now, reference_data, reference_snapshot
from fluent_ui import FluentView, WIDTH, HEIGHT, BG, TEXT, MUTED, ACCENT as PRIMARY, temp_from_x
from windows_flyout import work_area, apply_window_style
from stitch_assets import font_family, icon_image as stitch_icon_image


_BASE = Path(__file__).resolve().parent
_ROOT = _BASE.parent
SETTINGS = next((p for p in (_ROOT / "config" / "settings.json", _ROOT / "settings.json", _BASE / "settings.json") if p.is_file()), _ROOT / "config" / "settings.json")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "Elgin AC Tray"

FONT = "Segoe UI Variable"


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
    draw.rounded_rectangle((4, 5, 60, 59), radius=16, fill="#202020")
    if temperature is None:
        image.alpha_composite(stitch_icon_image('tray', '#4cc2ff', 32), (16, 16))
    else:
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/SegUIVar.ttf", 30)
            variants = font.get_variation_names()
            selected = next((name for name in variants if b'Display' in name and b'Semibold' in name), None)
            if selected is not None:
                font.set_variation_by_name(selected)
        except OSError:
            try:
                font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 30)
            except OSError:
                font = ImageFont.load_default(size=30)
        draw.text((32, 29), str(temperature), font=font, anchor="mm",
                  fill="#4cc2ff" if power else "#f5f5f5")
        draw.line((19, 50, 45, 50), fill="#4cc2ff" if power else "#cccccc", width=3)
    return image


class TrayApp(FluentView):
    def __init__(self, root, show_at_start=False, preview=False, offline=False):
        self.root = root
        self.root.withdraw()
        self.root.title("Elgin AC")
        self.preview = preview
        self.offline = offline
        left, top, right, bottom = work_area(self.root)
        self.scale = min(1.0, (right - left - 24) / WIDTH,
                         (bottom - top - 24) / HEIGHT)
        self.view_width = round(WIDTH * self.scale)
        self.view_height = round(HEIGHT * self.scale)
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
        self.root.bind("<space>", self.activate_or_power)
        self.root.bind("<Left>", lambda _e: self.energy_key(-1))
        self.root.bind("<Right>", lambda _e: self.energy_key(1))
        self.root.bind("<Tab>", self.energy_tab)
        self.root.bind("<Shift-Tab>", lambda e: self.energy_tab(e, -1))
        self.root.bind("<Return>", self.energy_activate)
        self.root.bind("<r>", lambda _e: self.refresh_all())
        self.root.bind("<R>", lambda _e: self.refresh_all())
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
            self.energy_store = None if offline else EnergyHistory()
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
            self.cloud_energy = None if offline else EnergyBridge(config_tomada()['device_id'],
                                             cache_path=_ROOT / 'data' / 'energy_history.sqlite3' if (_ROOT / 'data').is_dir() else _ROOT / 'energy_history.sqlite3')
        except Exception:
            self.cloud_error = 'Cloud indisponível: confira configuração da tomada e pasta.'
        self.energy_year = local_now().year
        self.energy_month = local_now().month
        self.energy_month_offset = 0
        self.energy_chart_start = 0
        self.energy_selected_day = 1
        self.startup_error = ""
        try:
            if not offline:
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
        if offline:
            self.dps = {"1": True, "2": 24, "3": 26, "4": "cold", "5": "auto",
                        "11": True, "25": False, "36": True, "31": "off", "33": False, "102": False}
            self.plug_dps = {"1": True, "18": 6880, "19": 8500, "20": 1234}
            self.updated = self.plug_updated = datetime.now()
        else:
            self.tray_thread = threading.Thread(target=self.icon.run, daemon=True)
            self.tray_thread.start()
        self.draw()
        self.root.after(100, self.process_events)
        self.root.after(15000, self.periodic_refresh)
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
        left, top, right, bottom = work_area(self.root)
        x = max(left, right - self.view_width - 14)
        y = max(top, bottom - self.view_height - 14)
        self.root.geometry(f"{self.view_width}x{self.view_height}{x:+d}{y:+d}")
        self.root.deiconify()
        self.root.update_idletasks()
        apply_window_style(self.root)
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
        if self.closed:
            return
        self.closed = True
        try:
            self.icon.stop()
        finally:
            # Cancela polling/transições antes de destruir o interpretador Tk.
            for callback in self.root.tk.call("after", "info"):
                self.root.after_cancel(callback)
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
            self.root.after(0, self.apply_ac_result, dps, error)
        while True:
            try:
                dps, error, history_error = self.plug_results.get_nowait()
            except queue.Empty:
                break
            self.root.after(0, self.apply_plug_result, dps, error, history_error)
        self.process_cloud_results()
        self.root.after(100, self.process_events)

    def apply_ac_result(self, dps, error):
        """Executado pelo after na thread Tk, inclusive após falhas de rede."""
        if self.closed:
            return
        self.busy = False
        if self.plug_dps.get("1") is False:
            self.dps, self.updated, self.error = {}, None, "Ar sem alimentação"
        elif error:
            self.error = error
        else:
            self.dps, self.error, self.updated = dps, "", datetime.now()
            if dps.get("5") not in (None, "strong", "mute"):
                self.last_normal_fan = dps["5"]
            self.icon.title = f"Elgin AC · {dps.get('2', '--')} °C"
            self.icon.icon = icon_image(dps.get("2"), dps.get("1") is True)
        self.draw()

    def apply_plug_result(self, dps, error, history_error=""):
        if self.closed:
            return
        self.plug_busy = False
        self.energy_error = history_error
        if error:
            self.plug_error = error
        else:
            previous_power = self.plug_dps.get("1")
            self.plug_dps, self.plug_error, self.plug_updated = dps, "", datetime.now()
            if dps.get("1") is False:
                self.dps, self.updated, self.error = {}, None, "Ar sem alimentação"
                self.icon.title, self.icon.icon = "Elgin AC · sem alimentação", icon_image()
            elif previous_power is False:
                # Ao restaurar alimentação, busca novamente o estado real do ar.
                self.submit("status")
        self.draw()

    def refresh_all(self):
        if self.plug_dps.get("1") is not False:
            self.submit("status")
        self.submit_plug("status")
        self.submit_energy(force=True)

    def submit_energy(self, force=False):
        """Consultas somente leitura; fila independente dos comandos LAN."""
        bridge = getattr(self, 'cloud_energy', None)
        if bridge is None or self.closed or getattr(self, 'cloud_busy', False) or getattr(self, "offline", False):
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
        if self.plug_busy or self.closed or getattr(self, "offline", False):
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
            history_error = ""
            try:
                result = operar_tomada(command, value,
                                       ac_off_confirmed=ac_off,
                                       force_off=force_off)
                if result[0] is not None and not result[1] and self.energy_store is not None:
                    try:
                        self.energy_store.record(result[0])
                    except (OSError, ValueError, sqlite3.Error):
                        history_error = "Falha ao salvar histórico local"
            except Exception:
                result = (None, "Falha inesperada na comunicação com a tomada")
            self.plug_results.put((*result, history_error))

        threading.Thread(target=work, daemon=True).start()

    def submit(self, command, value=None):
        if self.busy or self.closed or getattr(self, "offline", False):
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
        """Pilha do Stitch, faces óticas Windows e tamanho em pixels do Tk."""
        available = getattr(self, 'font_families', None)
        if available is None:
            root = getattr(self, 'root', None)
            available = tuple(tkfont.families(root)) if root is not None else ('Segoe UI', 'Consolas')
            self.font_families = available
        family = font_family(available, size, weight)
        tk_weight = 'bold' if weight == 'bold' else 'normal'
        return (family, -max(8, round(size * getattr(self, "scale", 1.0))), tk_weight)

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


    def finish_draw(self):
        focused = getattr(self, "focused_hotspot", None)
        visible_focus = False
        for name, bounds, value in self.hotspots:
            if focused == (name, value):
                self.rounded(bounds, 12, "", PRIMARY)
                visible_focus = True
                break
        if focused and not visible_focus:
            self.focused_hotspot = None
        scale = getattr(self, "scale", 1.0)
        if scale != 1.0:
            self.canvas.scale("all", 0, 0, scale, scale)


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
        now = local_now()
        current_rows = self.energy_months(now.year)
        local['current_month_kwh'] = next((row['kwh'] for row in current_rows if row['month'] == now.month), None)
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


    def energy_tab(self, event, step=1):
        choices = [(n, v) for n, _, v in self.hotspots if not self.menu or n == "choice"]
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
        if not focused:
            return None
        for name, bounds, value in self.hotspots:
            if (name, value) == focused:
                scale = getattr(self, "scale", 1)
                self.click(SimpleNamespace(x=(bounds[0]+bounds[2])/2*scale,
                                           y=(bounds[1]+bounds[3])/2*scale))
                return "break"

    def activate_or_power(self, event):
        if getattr(self, "focused_hotspot", None):
            return self.energy_activate(event)
        self.power()
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
            index = years.index(self.energy_year) if self.energy_year in years else len(years)-1
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
        elif name == "startup" and not getattr(self, "offline", False):
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
            self.hover = name
            self.canvas.configure(cursor="hand2" if name else "")
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
            self.draw()
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
    parser.add_argument("--demo", action="store_true", help="Prévia ilustrativa, sem rede nem alterações nas configurações")
    args = parser.parse_args()
    if args.demo:
        root = tk.Tk()
        app = TrayApp(root, show_at_start=True, preview=True, offline=True)
        root.protocol("WM_DELETE_WINDOW", app.stop)
        root.mainloop()
        return
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
