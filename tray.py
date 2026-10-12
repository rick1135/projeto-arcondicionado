"""Windows tray entry point. UI callbacks are queued onto the Tk main thread."""
import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
import pystray
from PIL import Image, ImageDraw
from legacy_app import App
from controller import MODES, FANS

PREFS = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'ElginControl' / 'preferencias.json'


def icon_image():
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, 62, 62), radius=14, fill='#1671c5')
    draw.line((32, 11, 32, 53), fill='white', width=4)
    draw.line((14, 21, 50, 43), fill='white', width=4)
    draw.line((14, 43, 50, 21), fill='white', width=4)
    for pts in [(24, 16, 32, 23, 40, 16), (24, 48, 32, 41, 40, 48)]:
        draw.line(pts, fill='white', width=3)
    return image


class TrayApp(App):
    def __init__(self, root):
        self.commands = queue.Queue()
        self.icon = None
        self._ready = False
        self._last_error = None
        self._quitting = False
        self.snapshot = {}
        try:
            self.prefs = json.loads(PREFS.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            self.prefs = {}
        super().__init__(root)
        root.title('Elgin • Controle local')
        try:
            root.iconbitmap(str(Path(__file__).with_name('elgin.ico')))
        except tk.TclError:
            pass
        self.apply_preferences()
        self._ready = True
        self._prefs_mtime = PREFS.stat().st_mtime_ns if PREFS.is_file() else None
        root.protocol('WM_DELETE_WINDOW', self.hide)
        root.bind('<Unmap>', self.minimized)
        self.icon = pystray.Icon('ElginControl', icon_image(), 'Elgin • Controle local', self.menu())
        threading.Thread(target=self.icon.run, daemon=True).start()
        root.after(150, self.dispatch)
        root.withdraw()
        if self.control.config:
            root.after(350, self.read)

    def save_preferences(self):
        if not self._ready or not self.control.config:
            return
        PREFS.parent.mkdir(parents=True, exist_ok=True)
        prefs = {'devices_path': self.path.get(), 'device_id': self.control.config['id'], 'ip': self.ip.get().strip(), 'plug_device_id': (self.control.plug_config or {}).get('id'), 'plug_version': self.plug_version.get(), 'cloud_path': self.cloud_path.get()}
        try:
            PREFS.write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding='utf-8')
            self._prefs_mtime = PREFS.stat().st_mtime_ns
        except OSError:
            pass

    def apply_preferences(self):
        saved = self.prefs.get('devices_path')
        if saved and Path(saved).is_file():
            self.load(saved)
            index = next((i for i, r in enumerate(self.records) if r['id'] == self.prefs.get('device_id')), self.device.current())
            self.device.current(index)
            self.select_device()
            self.ip.set(self.prefs.get('ip', self.ip.get()))
            plug_index = next((i + 1 for i, r in enumerate(self.records) if r['id'] == self.prefs.get('plug_device_id')), 0)
            self.plug.current(plug_index)
            if plug_index:
                self.plug_version.set(str(self.prefs.get('plug_version', self.records[plug_index-1].get('version') or '3.5')))
            self.select_plug()
        self.cloud_path.set(self.prefs.get('cloud_path', ''))

    def reload_preferences_if_changed(self):
        if not PREFS.is_file() or self.busy:
            return
        mtime = PREFS.stat().st_mtime_ns
        if mtime == self._prefs_mtime:
            return
        try:
            incoming = json.loads(PREFS.read_text(encoding='utf-8'))
            if not isinstance(incoming, dict):
                return
            self.prefs = incoming
            self._ready = False
            self.apply_preferences()
            self._prefs_mtime = mtime
        except (OSError, ValueError):
            pass
        finally:
            self._ready = True

    def select_device(self):
        super().select_device()
        self.save_preferences()

    def run(self, fn, kind='ac', description=None):
        self.reload_preferences_if_changed()
        super().run(fn, kind=kind, description=description)

    def show_error(self, result):
        if self.root.state() == 'withdrawn':
            if self.icon and result != self._last_error:
                self._last_error = result
                try:
                    self.icon.notify(result, 'Elgin • Verifique a conexão')
                except Exception:
                    pass
        else:
            messagebox.showerror('Verifique a conexão ou o comando', result)

    def render(self, state):
        super().render(state)
        self.snapshot = state.copy()
        self._last_error = None
        if self.icon:
            self.icon.title = f"Elgin • {'Ligado' if state.get('1') else 'Desligado'} • {state.get('2', '—')} °C"
            self.icon.update_menu()

    def send(self, fn):
        def action(icon, item):
            self.commands.put(fn)
        return action

    def available(self, item):
        return self.connected and not self.busy

    def dispatch(self):
        try:
            fn = self.commands.get_nowait()
            fn()
        except queue.Empty:
            pass
        if not self._quitting:
            self.root.after(150, self.dispatch)

    def auto_read(self):
        if hasattr(self, '_prefs_mtime'):
            self.reload_preferences_if_changed()
        if self.control.config and not self.busy:
            self.read()
        self.root.after(30000 if not self.connected else 10000, self.auto_read)

    def hide(self):
        self.root.withdraw()

    def minimized(self, event):
        if event.widget is self.root and self.root.state() == 'iconic':
            self.root.after(50, self.hide)

    def show(self):
        subprocess.Popen([sys.executable, str(Path(__file__).with_name('app.py'))], cwd=str(Path(__file__).resolve().parent))

    def show_plug(self):
        self.show()

    def quit_app(self):
        self._quitting = True
        if self.icon:
            self.icon.stop()
        self.root.destroy()

    def change_temp(self, delta):
        value = self.snapshot.get('2')
        if type(value) is int:
            self.write(2, value + delta)

    def toggle(self, dp):
        state = self.snapshot
        value = ('off' if state.get('31') == 'same' else 'same') if dp == 31 else not bool(state.get(str(dp)))
        self.write(dp, value)

    def menu(self):
        Item, Menu = pystray.MenuItem, pystray.Menu
        modes = Menu(*[Item(label, self.send(lambda value=value: self.write(4, value)), enabled=self.available,
                            checked=lambda item, value=value: self.snapshot.get('4') == value, radio=True)
                       for label, value in MODES.items()])
        fans = Menu(*[Item(label, self.send(lambda value=value: self.write(5, value)),
                           enabled=lambda item, value=value: self.available(item) and (value != 'strong' or self.snapshot.get('4') == 'cold'),
                           checked=lambda item, value=value: self.snapshot.get('5') == value, radio=True)
                      for label, value in FANS.items()])
        toggles = [Item(label, self.send(lambda dp=dp: self.toggle(dp)),
                        checked=lambda item, dp=dp: self.snapshot.get(str(dp)) == 'same' if dp == 31 else bool(self.snapshot.get(str(dp))),
                        enabled=lambda item, dp=dp: self.available(item) and (dp != 25 or self.snapshot.get('4') == 'cold'))
                   for dp, label in [(11,'Folha (Eco/UVC)'),(25,'Sleep'),(36,'Display'),(31,'Oscilação')]]
        return Menu(
            Item('Abrir controle', self.send(self.show), default=True),
            Item(lambda item: f"{'Tomada desligada' if self.snapshot.get('_plug_power') is False else 'Ligado' if self.snapshot.get('1') else 'Desligado'} • Ajustada {self.snapshot.get('2', '—')} °C • Ambiente {self.snapshot.get('3', '—')} °C", None, enabled=False),
            Menu.SEPARATOR,
            Item('Ligar ar (alimenta a tomada)', self.send(lambda: self.write(1, True)), enabled=lambda item: bool(self.control.config) and not self.busy),
            Item('Desligar', self.send(lambda: self.write(1, False)), enabled=self.available),
            Item('Temperatura +1 °C', self.send(lambda: self.change_temp(1)), enabled=self.available),
            Item('Temperatura −1 °C', self.send(lambda: self.change_temp(-1)), enabled=self.available),
            Item('Modo', modes), Item('Ventilação', fans),
            *toggles,
            Menu.SEPARATOR,
            Item('Tomada / Consumo', self.send(self.show_plug)),
            Item('Temporizadores / Configurações', self.send(self.show)),
            Item('Reconectar / Atualizar', self.send(self.read), enabled=lambda item: not self.busy),
            Menu.SEPARATOR,
            Item('Sair', self.send(self.quit_app)))


if __name__ == '__main__':
    mutex = None
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
        kernel.CreateMutexW.restype = ctypes.c_void_p
        mutex = kernel.CreateMutexW(None, False, 'Local\\ElginControlTray')
        if ctypes.get_last_error() == 183:
            ctypes.windll.user32.MessageBoxW(None, 'O controle já está aberto. Procure o floco azul perto do relógio (ou na seta ^).', 'Elgin', 0)
            raise SystemExit(0)
    root = tk.Tk()
    TrayApp(root)
    root.mainloop()
