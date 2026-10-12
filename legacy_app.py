import argparse
import json
import queue
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from controller import Controller, MODES, FANS, load_devices
from energy import EnergyClient

BASE = Path(__file__).resolve().parent


class App:
    def __init__(self, root, demo=False):
        self.root = root
        self.demo = demo
        self.control = Controller(demo=demo)
        self.results = queue.Queue()
        self.busy = False
        self.pending_operation = None
        self.connected = False
        self.records = []
        self.actions = []
        self.plug_actions = []
        self.energy_client = None
        self.energy_result = None
        self.cloud_path = tk.StringVar()
        root.title('Elgin • Controle local' + (' • DEMONSTRAÇÃO' if demo else ''))
        root.geometry('820x850')
        root.minsize(780, 820)
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
        ttk.Label(connection, text='Tomada de alimentação:').grid(row=3, column=0, sticky='w', pady=6)
        self.plug = ttk.Combobox(connection, state='readonly', width=28, values=['Sem tomada'])
        self.plug.current(0)
        self.plug.grid(row=3, column=1, sticky='w', padx=8)
        self.plug.bind('<<ComboboxSelected>>', lambda e: self.select_plug())
        self.plug_version = tk.StringVar(value='3.5')
        ttk.Combobox(connection, state='readonly', width=6, textvariable=self.plug_version, values=['3.1','3.2','3.3','3.4','3.5']).grid(row=3, column=2)
        self.plug_version.trace_add('write', lambda *a: self.select_plug())
        self.status_text = tk.StringVar(value='Sem conexão. Nenhum comando foi enviado.')
        ttk.Label(main, textvariable=self.status_text, wraplength=690).pack(anchor='w', pady=10)
        self.tabs = ttk.Notebook(main)
        self.tabs.pack(fill='both', expand=True)
        ac_panel = ttk.Frame(self.tabs, padding=10)
        self.plug_panel = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(ac_panel, text='Ar condicionado')
        self.tabs.add(self.plug_panel, text='Tomada e consumo')
        readings = ttk.Frame(ac_panel)
        readings.pack(fill='x', pady=(0, 10))
        self.power = tk.StringVar(value='—')
        self.ambient = tk.StringVar(value='Ambiente: —')
        self.target = tk.StringVar(value='Ajustada: —')
        for var in (self.power, self.ambient, self.target):
            ttk.Label(readings, textvariable=var, style='Reading.TLabel').pack(side='left', padx=(0, 22))
        buttons = ttk.Frame(ac_panel)
        buttons.pack(fill='x')
        self.button(buttons, 'Ligar', lambda: self.write(1, True)).pack(side='left', padx=(0, 8))
        self.button(buttons, 'Desligar', lambda: self.write(1, False)).pack(side='left')
        self.temp = tk.StringVar(value='24')
        ttk.Label(buttons, text='Temperatura °C:').pack(side='left', padx=(18, 6))
        ttk.Entry(buttons, textvariable=self.temp, width=5).pack(side='left')
        self.button(buttons, 'Aplicar', self.temperature).pack(side='left', padx=8)
        settings = ttk.LabelFrame(ac_panel, text='Controles', padding=10)
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
        timer_box = ttk.LabelFrame(ac_panel, text='Temporizadores • experimental', padding=10)
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
        self.build_plug_panel()
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

    def build_plug_panel(self):
        panel = self.plug_panel
        self.plug_reading = tk.StringVar(value='Selecione a tomada na área Conexão.')
        ttk.Label(panel, textvariable=self.plug_reading, wraplength=720, font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=(0, 8))
        commands = ttk.Frame(panel)
        commands.pack(fill='x')
        for label, fn in [('Ligar tomada', lambda: self.run(lambda: self.control.set_plug_power(True), kind='plug', description='Ligando a tomada…')),
                          ('Desligar tomada', self.plug_off),
                          ('Atualizar tomada', lambda: self.run(self.control.read_plug, kind='plug', description='Atualizando a tomada…'))]:
            widget = ttk.Button(commands, text=label, command=fn)
            widget.pack(side='left', padx=(0, 8))
            self.plug_actions.append(widget)
        timer = ttk.LabelFrame(panel, text='Temporizador da tomada', padding=8)
        timer.pack(fill='x', pady=10)
        self.plug_minutes = tk.StringVar(value='10')
        row = ttk.Frame(timer)
        row.pack(fill='x')
        ttk.Label(row, text='Minutos (1–1440):').pack(side='left')
        ttk.Spinbox(row, from_=1, to=1440, textvariable=self.plug_minutes, width=6).pack(side='left', padx=8)
        for label, fn in [('Programar', self.schedule_plug), ('Cancelar', lambda: self.run(lambda: self.control.plug_countdown(0), kind='plug'))]:
            widget = ttk.Button(row, text=label, command=fn)
            widget.pack(side='left', padx=4)
            self.plug_actions.append(widget)
        self.plug_timer_text = tk.StringVar(value='Contagem: —')
        ttk.Label(timer, textvariable=self.plug_timer_text).pack(anchor='w', pady=5)
        ttk.Label(timer, text='O temporizador pertence à tomada e continua com o PC desligado. Ao terminar, pode inverter o relé.', wraplength=710).pack(anchor='w')
        history = ttk.LabelFrame(panel, text='Elétrico • histórico da nuvem em kWh', padding=8)
        history.pack(fill='both', expand=True)
        ttk.Label(history, textvariable=self.cloud_path, wraplength=710).pack(anchor='w')
        options = ttk.Frame(history)
        options.pack(fill='x', pady=5)
        ttk.Button(options, text='Abrir tinytuya.json', command=self.choose_cloud).pack(side='left')
        now = datetime.now()
        self.energy_year = tk.StringVar(value=str(now.year))
        self.energy_month = tk.StringVar(value=str(now.month))
        ttk.Label(options, text='Ano:').pack(side='left', padx=(8, 3))
        ttk.Spinbox(options, from_=2020, to=2100, textvariable=self.energy_year, width=5).pack(side='left')
        ttk.Label(options, text='Mês:').pack(side='left', padx=(8, 3))
        ttk.Spinbox(options, from_=1, to=12, textvariable=self.energy_month, width=3).pack(side='left')
        widget = ttk.Button(options, text='Consultar consumo', command=self.read_energy)
        widget.pack(side='left', padx=8)
        self.plug_actions.append(widget)
        self.energy_summary = tk.StringVar(value='Histórico ainda não consultado. Requer internet e Beta APIs.')
        ttk.Label(history, textvariable=self.energy_summary, wraplength=710).pack(anchor='w', pady=4)
        self.energy_view = tk.StringVar(value='Dias')
        view = ttk.Combobox(history, textvariable=self.energy_view, values=['Dias', 'Meses'], state='readonly', width=10)
        view.pack(anchor='w')
        view.bind('<<ComboboxSelected>>', lambda e: self.draw_energy())
        self.energy_chart = tk.Canvas(history, height=110, bg='white', highlightthickness=0)
        self.energy_chart.pack(fill='x', pady=4)
        self.energy_chart.bind('<Configure>', lambda e: self.draw_energy())
        self.energy_table = ttk.Treeview(history, columns=('period','kwh'), show='headings', height=5)
        self.energy_table.heading('period', text='Período')
        self.energy_table.heading('kwh', text='Consumo (kWh)')
        self.energy_table.column('period', width=210)
        self.energy_table.column('kwh', width=140, anchor='e')
        scroll = ttk.Scrollbar(history, orient='vertical', command=self.energy_table.yview)
        self.energy_table.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.energy_table.pack(fill='both', expand=True)

    def choose_cloud(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(title='Selecione o tinytuya.json do wizard', filetypes=[('Configuração TinyTuya', '*.json')])
        if path:
            self.cloud_path.set(path)
            self.energy_client = None
            if hasattr(self, 'save_preferences'):
                self.save_preferences()

    def plug_off(self):
        self.run(lambda: self.control.set_plug_power(False), kind='plug', description='Desligando a tomada…')

    def schedule_plug(self):
        try:
            minutes = int(self.plug_minutes.get())
            if not 1 <= minutes <= 1440:
                raise ValueError
        except ValueError:
            messagebox.showerror('Temporizador', 'Informe de 1 a 1440 minutos.')
            return
        if not messagebox.askokcancel('Temporizador da tomada', 'A tomada pode inverter o relé ao terminar e cortar a alimentação do ar. Para desligar somente o ar, use o Timer OFF na outra aba. Programar a tomada?'):
            return
        self.run(lambda: self.control.plug_countdown(minutes * 60), kind='plug')

    def render_plug(self, state):
        def reading(dp, divisor, decimals):
            value = state.get(str(dp))
            return f'{value/divisor:.{decimals}f}'.replace('.', ',') if type(value) in (int, float) else '—'
        relay = 'Ligada' if state.get('1') is True else 'Desligada' if state.get('1') is False else '—'
        self.plug_reading.set(f'Tomada: {relay}   •   {reading(19,10,1)} W   •   {reading(18,1000,3)} A   •   {reading(20,10,1)} V')
        seconds = state.get('9')
        self.plug_timer_text.set(f'Contagem: {seconds//3600:02d}h {(seconds%3600)//60:02d}min {seconds%60:02d}s' if type(seconds) is int and seconds > 0 else 'Contagem: desativada' if seconds == 0 else 'Contagem: —')

    def read_energy(self):
        try:
            year, month = int(self.energy_year.get()), int(self.energy_month.get())
            datetime(year, month, 1)
        except ValueError:
            messagebox.showerror('Consumo', 'Informe ano e mês válidos.')
            return
        if self.demo:
            from decimal import Decimal
            self.render_energy({'total':Decimal('12.50'), 'months':{f'{year}{month:02d}':Decimal('12.50')}, 'days':{f'{year}{month:02d}{i:02d}':Decimal(str(i/10)) for i in range(1,6)}, 'year':year, 'month':month, 'updated':datetime.now().timestamp()})
            return
        if not self.control.plug_config:
            messagebox.showerror('Consumo', 'Selecione a tomada na área Conexão.')
            return
        if not self.cloud_path.get():
            candidates = [Path(self.path.get()).parent / 'tinytuya.json', Path.home() / 'elgin-controle' / 'tinytuya.json']
            for path in candidates:
                if path.is_file():
                    self.cloud_path.set(str(path))
                    break
        if not self.cloud_path.get():
            self.choose_cloud()
            if not self.cloud_path.get():
                return
        if self.energy_client is None:
            self.energy_client = EnergyClient(self.cloud_path.get(), self.control.plug_config['id'])
        self.run(lambda: {'_energy':self.energy_client.history(year, month)}, kind='cloud')

    def render_energy(self, data):
        self.energy_result = data
        monthly = data['months'].get(f"{data['year']}{data['month']:02d}")
        label = f'{monthly:.2f} kWh'.replace('.', ',') if monthly is not None else 'sem dado retornado'
        updated = datetime.fromtimestamp(data['updated']).strftime('%d/%m %H:%M')
        self.energy_summary.set(f"Total: {data['total']:.2f} kWh • {data['month']:02d}/{data['year']}: {label} • Consulta: {updated}".replace('.', ',') + (' • DEMONSTRAÇÃO' if self.demo else ''))
        self.draw_energy()

    def draw_energy(self):
        if not self.energy_result:
            return
        months = self.energy_view.get() == 'Meses'
        values = sorted(self.energy_result['months' if months else 'days'].items())
        for item in self.energy_table.get_children():
            self.energy_table.delete(item)
        for period, value in values:
            label = f'{period[4:6]}/{period[:4]}' if months else f'{period[6:8]}/{period[4:6]}/{period[:4]}'
            self.energy_table.insert('', 'end', values=(label, f'{value:.2f}'.replace('.', ',')))
        chart = self.energy_chart
        chart.delete('all')
        if not values:
            chart.create_text(20, 40, text='Sem dados retornados para este período.', anchor='w')
            return
        width = max(100, chart.winfo_width())
        maximum = max(float(v) for _,v in values) or 1
        step = (width-36)/len(values)
        for i,(period,value) in enumerate(values):
            x = 18+i*step
            height = float(value)/maximum*75
            chart.create_rectangle(x, 82-height, x+step*.75, 82, fill='#1671c5', outline='')
            chart.create_text(x+step*.375, 96, text=period[4:6] if months else period[6:8], font=('Segoe UI',8))

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
        if not self.busy and self.control.config:
            for widget in self.actions:
                if isinstance(widget, ttk.Button) and widget.cget('text') == 'Ligar':
                    widget.configure(state='normal')
        for widget in self.plug_actions:
            widget.configure(state='normal' if not self.busy and (self.demo or self.control.plug_config) else 'disabled')
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
            self.plug['values'] = ['Sem tomada'] + [r.get('name', 'Dispositivo') + ' • ' + r['id'][-6:] for r in self.records]
            self.plug.current(0)
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
        self.select_plug()
        self.ip.set(c.get('ip') or '')
        self.connected = False
        self.enable(False)
        self.status_text.set('Dispositivo selecionado. Clique em Conectar / Atualizar.')

    def select_plug(self):
        if self.busy:
            return
        index = self.plug.current() - 1
        if index >= 0 and index < len(self.records):
            c = self.records[index].copy()
            c['version'] = float(self.plug_version.get())
            self.control.plug_config = c
        else:
            self.control.plug_config = None
        self.energy_client = None
        self.energy_result = None
        if hasattr(self, 'plug_reading'):
            self.plug_reading.set('Selecione Atualizar tomada para ler as medições.')
            self.energy_summary.set('Histórico ainda não consultado.')
            for item in self.energy_table.get_children():
                self.energy_table.delete(item)
            self.energy_chart.delete('all')
        self.enable(self.connected and not self.busy)
        if hasattr(self, 'save_preferences'):
            self.save_preferences()

    def run(self, fn, kind='ac', description=None):
        if self.busy:
            if description:
                self.pending_operation = (fn, kind, description)
                self.status_text.set('Há uma atualização em andamento. O comando será enviado em seguida…')
            return
        self.busy = True
        self.operation_kind = kind
        self.enable(False)
        self.browse.configure(state='disabled')
        self.device.configure(state='disabled')
        self.plug.configure(state='disabled')
        self.refresh.configure(state='disabled')
        self.status_text.set(description or 'Comunicando… Ao ligar, pode aguardar até 90 s pelo Wi-Fi do ar.')
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
        self.plug.configure(state='readonly')
        self.refresh.configure(state='normal')
        if ok and '_energy' in result:
            self.render_energy(result['_energy'])
            self.status_text.set('Histórico de consumo recebido da Tuya.')
        elif ok and result.get('_plug_only'):
            self.render_plug(result['_plug_dps'])
            if result['_plug_dps'].get('1') is False:
                self.connected = False
                self.control.state = {'_plug_power':False, '_ac_available':False}
                self.render(self.control.state)
            message = result.get('_notice') or 'Estado da tomada recebido'
            self.status_text.set(message + ' • ' + datetime.now().strftime('%H:%M:%S'))
        elif ok:
            self.connected = result.get("_ac_available", True)
            self.render(result)
            self.status_text.set('Tomada desligada. Clique em Ligar para alimentar e ligar o ar.' if result.get('_plug_power') is False else ('DEMONSTRAÇÃO • ' if self.demo else 'Estado recebido • ') + datetime.now().strftime('%H:%M:%S'))
        else:
            if self.operation_kind == 'ac':
                self.connected = False
            if self.control.plug_state:
                self.render_plug(self.control.plug_state)
            self.status_text.set(result)
            self.show_error(result)
        self.enable(self.connected)
        if self.pending_operation:
            fn, kind, description = self.pending_operation
            self.pending_operation = None
            self.root.after_idle(lambda: self.run(fn, kind=kind, description=description))
        self.root.after(100, self.poll)

    def show_error(self, result):
        messagebox.showerror('Verifique a conexão ou o comando', result)

    def render(self, s):
        if self.control.plug_state:
            self.render_plug(self.control.plug_state)
        self.power.set('Sem alimentação' if s.get('_plug_power') is False else 'Ligado' if s.get('1') is True else 'Desligado' if s.get('1') is False else '—')
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
