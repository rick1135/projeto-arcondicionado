import argparse
import json
import queue
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from controller import Controller, MODES, FANS, load_devices

BASE = Path(__file__).resolve().parent


class App:
    def __init__(self, root, demo=False):
        self.root = root
        self.demo = demo
        self.control = Controller(demo=demo)
        self.results = queue.Queue()
        self.busy = False
        self.connected = False
        self.records = []
        self.actions = []
        root.title('Elgin • Controle local' + (' • DEMONSTRAÇÃO' if demo else ''))
        root.geometry('760x760')
        root.minsize(710, 690)
        root.configure(bg='#edf3fa')
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10))
        style.configure('TFrame', background='#edf3fa')
        style.configure('TLabel', background='#edf3fa', foreground='#18314f')
        style.configure('TLabelframe', background='#edf3fa')
        style.configure('TLabelframe.Label', background='#edf3fa', foreground='#18314f', font=('Segoe UI', 11, 'bold'))
        style.configure('TButton', padding=(12, 8))
        style.configure('Title.TLabel', font=('Segoe UI', 23, 'bold'))
        style.configure('Reading.TLabel', font=('Segoe UI', 18, 'bold'))
        main = ttk.Frame(root, padding=20)
        main.pack(fill='both', expand=True)
        ttk.Label(main, text='Seu clima, no computador', style='Title.TLabel').pack(anchor='w')
        ttk.Label(main, text='Elgin Eco Dream • HIFI09C2WA • conexão pela rede local').pack(anchor='w', pady=(4, 14))
        connection = ttk.LabelFrame(main, text='Conexão', padding=10)
        connection.pack(fill='x')
        self.path = tk.StringVar(value='Modo demonstração' if demo else 'Selecione o devices.json')
        ttk.Label(connection, textvariable=self.path, wraplength=600).grid(row=0, column=0, columnspan=3, sticky='w')
        self.browse = ttk.Button(connection, text='Abrir devices.json', command=self.choose_file)
        self.browse.grid(row=1, column=0, sticky='w', pady=6)
        self.device = ttk.Combobox(connection, state='readonly', width=28)
        self.device.grid(row=1, column=1, padx=8)
        self.device.bind('<<ComboboxSelected>>', lambda e: self.select_device())
        self.refresh = ttk.Button(connection, text='Conectar / Atualizar', command=self.read)
        self.refresh.grid(row=1, column=2)
        self.ip = tk.StringVar()
        ttk.Label(connection, text='IP local (vazio = descobrir):').grid(row=2, column=0, sticky='w')
        self.ip_entry = ttk.Entry(connection, textvariable=self.ip, width=22)
        self.ip_entry.grid(row=2, column=1, sticky='w', padx=8)
        self.status_text = tk.StringVar(value='Sem conexão. Nenhum comando foi enviado.')
        ttk.Label(main, textvariable=self.status_text, wraplength=690).pack(anchor='w', pady=10)
        readings = ttk.Frame(main)
        readings.pack(fill='x', pady=(0, 10))
        self.power = tk.StringVar(value='—')
        self.ambient = tk.StringVar(value='Ambiente: —')
        self.target = tk.StringVar(value='Ajustada: —')
        for var in (self.power, self.ambient, self.target):
            ttk.Label(readings, textvariable=var, style='Reading.TLabel').pack(side='left', padx=(0, 22))
        buttons = ttk.Frame(main)
        buttons.pack(fill='x')
        self.button(buttons, 'Ligar', lambda: self.write(1, True)).pack(side='left', padx=(0, 8))
        self.button(buttons, 'Desligar', lambda: self.write(1, False)).pack(side='left')
        self.temp = tk.StringVar(value='24')
        ttk.Label(buttons, text='Temperatura °C:').pack(side='left', padx=(18, 6))
        ttk.Entry(buttons, textvariable=self.temp, width=5).pack(side='left')
        self.button(buttons, 'Aplicar', self.temperature).pack(side='left', padx=8)
        settings = ttk.LabelFrame(main, text='Controles', padding=10)
        settings.pack(fill='x', pady=12)
        self.mode = tk.StringVar()
        self.fan = tk.StringVar()
        self.select_row(settings, 0, 'Modo', self.mode, MODES, 4)
        self.select_row(settings, 1, 'Ventilação', self.fan, FANS, 5)
        toggles = ttk.Frame(settings)
        toggles.grid(row=2, column=0, columnspan=3, sticky='w', pady=(8, 0))
        self.flags = {}
        for dp, label in [(11, 'Folha (Eco/UVC)'), (25, 'Sleep'), (36, 'Display'), (31, 'Oscilação')]:
            var = tk.BooleanVar()
            self.flags[dp] = var
            def toggle(dp=dp, var=var):
                self.write(dp, ('same' if var.get() else 'off') if dp == 31 else var.get())
            widget = ttk.Checkbutton(toggles, text=label, variable=var, command=toggle)
            widget.pack(side='left', padx=(0, 12))
            self.actions.append(widget)
        ttk.Label(settings, text='Sleep e Turbo: somente Refrigerar. Silenciosa não desativa os bipes.', wraplength=650).grid(row=3, column=0, columnspan=3, sticky='w', pady=(10, 0))
        timer_box = ttk.LabelFrame(main, text='Temporizadores • experimental', padding=10)
        timer_box.pack(fill='x')
        ttk.Label(timer_box, text='Intervalo em horas/minutos. ON exige o ar desligado. Confirme o resultado no Smart Life.', wraplength=650).grid(row=0, column=0, columnspan=7, sticky='w', pady=(0, 8))
        self.timers = {}
        for row, kind in enumerate(('ON', 'OFF'), 1):
            h, m = tk.StringVar(value='0'), tk.StringVar(value='0')
            self.timers[kind] = (h, m)
            ttk.Label(timer_box, text='Ligar em' if kind == 'ON' else 'Desligar em').grid(row=row, column=0, sticky='w')
            ttk.Spinbox(timer_box, from_=0, to=23, width=4, textvariable=h).grid(row=row, column=1, padx=5)
            ttk.Label(timer_box, text='h').grid(row=row, column=2)
            ttk.Spinbox(timer_box, from_=0, to=59, width=4, textvariable=m).grid(row=row, column=3, padx=5)
            ttk.Label(timer_box, text='min').grid(row=row, column=4)
            self.button(timer_box, 'Programar', lambda k=kind: self.timer(k, True)).grid(row=row, column=5, padx=8, pady=4)
            self.button(timer_box, 'Cancelar', lambda k=kind: self.timer(k, False)).grid(row=row, column=6)
        self.timer_text = tk.StringVar(value='ON: —  |  OFF: —')
        ttk.Label(timer_box, textvariable=self.timer_text).grid(row=3, column=0, columnspan=7, sticky='w', pady=(6, 0))
        ttk.Label(main, text='A chave fica apenas no seu devices.json. Feche o Smart Life durante o controle local.', wraplength=690).pack(anchor='w', pady=(12, 0))
        self.enable(False)
        if demo:
            self.browse.configure(state='disabled')
            self.ip_entry.configure(state='disabled')
            self.read()
        else:
            candidates = [BASE / 'devices.json', Path.home() / 'elgin-controle' / 'devices.json']
            for candidate in candidates:
                if candidate.is_file():
                    self.load(candidate)
                    break
        root.after(100, self.poll)
        root.after(10000, self.auto_read)

    def button(self, parent, text, command):
        widget = ttk.Button(parent, text=text, command=command)
        self.actions.append(widget)
        return widget

    def select_row(self, parent, row, label, var, mapping, dp):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=4)
        combo = ttk.Combobox(parent, textvariable=var, values=list(mapping), state='readonly', width=27)
        combo.grid(row=row, column=1, sticky='w')
        self.button(parent, 'Aplicar', lambda: self.write(dp, mapping[var.get()]) if var.get() in mapping else None).grid(row=row, column=2, padx=8)

    def enable(self, enabled):
        for widget in self.actions:
            widget.configure(state='normal' if enabled else 'disabled')
        if enabled and self.control.state.get('4') != 'cold':
            # Backend também valida a restrição usando estado lido do aparelho.
            for widget in self.actions:
                if isinstance(widget, ttk.Checkbutton) and widget.cget('text') == 'Sleep':
                    widget.configure(state='disabled')

    def choose_file(self):
        path = filedialog.askopenfilename(title='Selecione seu devices.json', filetypes=[('Arquivo JSON', '*.json')])
        if path:
            self.load(path)

    def load(self, path):
        try:
            self.records = load_devices(path)
            self.path.set(str(path))
            self.device['values'] = [r.get('name', 'Dispositivo') + ' • ' + r['id'][-6:] for r in self.records]
            index = next((i for i, r in enumerate(self.records) if 'air' in r.get('name', '').lower()), 0)
            self.device.current(index)
            self.select_device()
        except (ValueError, OSError) as exc:
            messagebox.showerror('Arquivo inválido', str(exc))

    def select_device(self):
        if self.busy or self.device.current() < 0:
            return
        c = self.records[self.device.current()].copy()
        c.setdefault('version', 3.3)
        self.control = Controller(c)
        self.ip.set(c.get('ip') or '')
        self.connected = False
        self.enable(False)
        self.status_text.set('Dispositivo selecionado. Clique em Conectar / Atualizar.')

    def run(self, fn):
        if self.busy:
            return
        self.busy = True
        self.enable(False)
        self.browse.configure(state='disabled')
        self.device.configure(state='disabled')
        self.refresh.configure(state='disabled')
        self.status_text.set('Comunicando com o aparelho…')
        if self.control.config is not None:
            self.control.config['ip'] = self.ip.get().strip() or 'Auto'
        def worker():
            try:
                self.results.put((True, fn()))
            except Exception as exc:
                # Não imprime credenciais nem traceback com conteúdo do JSON.
                msg = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else 'Não foi possível comunicar com o aparelho. Confira a rede e a configuração.'
                self.results.put((False, msg))
        threading.Thread(target=worker, daemon=True).start()

    def read(self):
        self.run(self.control.status)

    def write(self, dp, value):
        self.run(lambda: self.control.set(dp, value))

    def temperature(self):
        try:
            value = int(self.temp.get())
        except ValueError:
            messagebox.showerror('Temperatura', 'Informe um número inteiro em °C.')
            return
        self.write(2, value)

    def timer(self, kind, enabled):
        h, m = self.timers[kind]
        if enabled and not messagebox.askokcancel('Temporizador experimental', 'Os campos foram mapeados pelo app, mas o envio local e a execução ainda não foram validados. Programar e conferir no Smart Life?'):
            return
        hours, minutes = h.get(), m.get()
        self.run(lambda: self.control.timer(kind, enabled, hours, minutes))

    def poll(self):
        try:
            ok, result = self.results.get_nowait()
        except queue.Empty:
            self.root.after(100, self.poll)
            return
        self.busy = False
        self.browse.configure(state='disabled' if self.demo else 'normal')
        self.device.configure(state='readonly')
        self.refresh.configure(state='normal')
        if ok:
            self.connected = True
            self.render(result)
            self.status_text.set(('DEMONSTRAÇÃO • ' if self.demo else 'Estado recebido • ') + datetime.now().strftime('%H:%M:%S'))
        else:
            self.connected = False
            self.status_text.set(result)
            self.show_error(result)
        self.enable(ok)
        self.root.after(100, self.poll)

    def show_error(self, result):
        messagebox.showerror('Verifique a conexão ou o comando', result)

    def render(self, s):
        self.power.set('Ligado' if s.get('1') is True else 'Desligado' if s.get('1') is False else '—')
        self.ambient.set(f"Ambiente: {s.get('3', '—')} °C")
        self.target.set(f"Ajustada: {s.get('2', '—')} °C")
        # Não sobrescreve a temperatura digitada durante atualização automática.
        for var, mapping, dp in [(self.mode, MODES, '4'), (self.fan, FANS, '5')]:
            var.set(next((k for k, v in mapping.items() if v == s.get(dp)), ''))
        for dp, var in self.flags.items():
            var.set(s.get(str(dp)) == 'same' if dp == 31 else s.get(str(dp)) is True)
        values = []
        for kind, flag, duration in [('ON', '101', '103'), ('OFF', '102', '104')]:
            t = str(s.get(duration, '????'))
            label = f'{t[:2]}h{t[2:]}min' if len(t) == 4 else t
            values.append(f'{kind}: {label}' if s.get(flag) else f'{kind}: desativado')
        self.timer_text.set('  |  '.join(values))

    def auto_read(self):
        if self.connected and not self.busy:
            self.read()
        self.root.after(10000, self.auto_read)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--demo', action='store_true', help='Interface simulada, sem conexão com dispositivos.')
    args = parser.parse_args()
    root = tk.Tk()
    App(root, args.demo)
    root.mainloop()
