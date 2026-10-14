"""Views Tk Canvas do flyout Fluent. Este módulo não faz chamadas de rede."""

from datetime import datetime

from stitch_assets import draw_stitch_icon
from ekaza_plug import medidas
from energy_cost import DEFAULT_TARIFF, monthly_cost, format_brl
from energy_history import MONTHS, format_kwh, local_now

WIDTH, HEIGHT = 380, 560
MIN_TEMP, MAX_TEMP = 16, 32
SLIDER_BOX = (56, 165, 324, 189)
BG, SURFACE, BORDER = "#202020", "#303030", "#3e3e3e"
TEXT, MUTED = "#f5f5f5", "#cccccc"
ACCENT, TRACK = "#4cc2ff", "#0078d4"
GREEN, ERROR = "#6ddbaa", "#ffb4ab"
MODE_LABELS = {"cold": "Frio", "auto": "Auto", "wind": "Ventilação", "wet": "Desumidificar", "hot": "Aquecer"}
FAN_LABELS = {"auto": "Auto", "low": "Baixa", "middle": "Média", "high": "Alta", "strong": "Turbo", "mute": "Silencioso"}


def temp_from_x(x):
    fraction = max(0, min(1, (x - SLIDER_BOX[0]) / (SLIDER_BOX[2] - SLIDER_BOX[0])))
    return round(MIN_TEMP + fraction * (MAX_TEMP - MIN_TEMP))


class FluentView:
    """Desenha coordenadas lógicas; a escala é aplicada uma vez no fim."""

    def stroke(self, points, color=TEXT, width=1.6):
        return self.canvas.create_line(*points, fill=color, width=width,
                                       capstyle="round", joinstyle="round")

    def draw_icon(self, name, x, y, color=TEXT, size=20):
        return draw_stitch_icon(self, name, x, y, color, size)

    def button(self, name, box, title=None, active=False, value=None):
        hover = getattr(self, "hover", None) == name
        self.rounded(box, 18 if name == "power" else 7, ACCENT if active else ("#3b3b3b" if hover else SURFACE),
                     "" if active else BORDER)
        if title:
            self.label((box[0]+box[2])/2, (box[1]+box[3])/2, title, 13,
                       "#10202a" if active else TEXT, anchor="center")
        self.hit(name, box, value)

    def telemetry(self):
        updated = getattr(self, "plug_updated", None)
        fresh = (updated is not None and not self.plug_error and
                 (datetime.now()-updated).total_seconds() < 60)
        return medidas(self.plug_dps) if fresh else {key: None for key in ("power_w", "voltage_v", "current_a")}

    def footer(self):
        self.canvas.create_rectangle(1, 510, WIDTH-1, HEIGHT-1, fill="#1b1b1b", outline="")
        self.stroke([1, 510, WIDTH-1, 510], "#333333", 1)
        if getattr(self, "offline", False):
            status, color = "Prévia • dados ilustrativos", MUTED
        elif self.error:
            status, color = "Ar sem conexão • atualizar", ERROR
        elif self.busy:
            status, color = "Sincronizando…", ACCENT
        elif self.updated:
            status, color = "Conectado (Tuya LAN)", GREEN
        else:
            status, color = "Conectando ao Elgin…", MUTED
        if self.updated and not self.error and not self.busy and not getattr(self, 'offline', False):
            self.draw_icon('connected', 18, 528, color, 14)
        else:
            self.canvas.create_oval(20, 532, 26, 538, fill=color, outline="")
        self.fit_label(34, 535, status, 12, 270, color, anchor="w")
        self.hit("refresh", (16, 516, 311, 554))
        self.draw_icon("settings", 337, 527, MUTED, 16)
        self.hit("settings", (323, 516, 369, 554))

    def view_header(self, title, subtitle, back="back", refresh=None):
        self.draw_icon("back", 22, 28, TEXT, 22)
        self.hit(back, (12, 16, 58, 65))
        self.label(65, 28, title, 20, TEXT, "semibold")
        self.fit_label(24, 65, subtitle, 12, 332, MUTED)
        if refresh:
            self.draw_icon("refresh", 332, 28, MUTED, 22)
            self.hit(refresh, (320, 16, 369, 62))

    def draw(self):
        if self.closed:
            return
        self.transition_generation = getattr(self, "transition_generation", 0) + 1
        self.transitioning = False
        self.canvas.delete("all")
        self.hotspots = []
        self.rounded((.5, .5, WIDTH-.5, HEIGHT-.5), 9, BG, "#333333")
        renderer = {"control": self.draw_control, "extras": self.draw_extras,
                    "plug": self.draw_plug, "plug_confirm": self.draw_plug_confirm,
                    "settings": self.draw_settings, "energy": self.draw_energy,
                    "energy_month": self.draw_energy_month}
        renderer[self.page]()
        self.footer()
        if self.menu:
            self.draw_menu()
        self.finish_draw()

    def draw_control(self):
        ambient = self.dps.get("3", "--") if not self.error else "--"
        self.label(24, 29, f"Ambiente {ambient}°C • Elgin Local", 14, MUTED, "semibold")
        self.label(24, 53, "Controle do ar-condicionado", 11, MUTED)
        active = self.dps.get("1") is True
        self.button("power", (320, 22, 356, 58), active=active)
        self.draw_icon("power", 330, 32, "#ffffff" if active else MUTED, 16)
        self.stroke([1, 80, WIDTH-1, 80], "#333333", 1)
        temp = self.pending_temp if self.pending_temp is not None else self.dps.get("2", "--")
        mode = MODE_LABELS.get(self.dps.get("4"), "--")
        self.label(190, 116, f"{temp} °C • {mode}", 27, TEXT, "semibold", anchor="center")
        self.label(190, 148, "Temperatura desejada", 11, MUTED, anchor="center")
        self.draw_icon('temperature', 111, 140, MUTED, 16)
        self.stroke([56, 177, 324, 177], "#666666", 4)
        self.hit("slider", SLIDER_BOX)
        self.hit("minus", (17, 157, 53, 197))
        self.hit("plus", (327, 157, 363, 197))
        self.stroke([27, 177, 43, 177], MUTED)
        self.stroke([337, 177, 353, 177], MUTED)
        self.stroke([345, 169, 345, 185], MUTED)
        if isinstance(temp, (int, float)):
            knob = 56 + (max(16, min(32, temp))-16)/16*268
            if knob > 56:
                self.stroke([56, 177, knob, 177], TRACK, 4)
            self.canvas.create_oval(knob-10, 167, knob+10, 187, fill="#eeeeee", outline="")
            self.canvas.create_oval(knob-5, 172, knob+5, 182, fill=TRACK, outline="")
        self.label(56, 196, "16°", 11, MUTED)
        self.label(324, 196, "32°", 11, MUTED, anchor="ne")

        watts = self.telemetry()["power_w"]
        plug = self.plug_dps.get("1")
        plug_status = ("Sem conexão" if self.plug_error else "Desligada" if plug is False
                       else f"Ligada • {watts:.0f} W" if plug is True and watts is not None
                       else "Ligada • -- W" if plug is True else "Conectando…")
        tiles = [("mode", "Modo", mode, "mode", False),
                 ("fan", "Vento", FAN_LABELS.get(self.dps.get("5"), "--"), "fan", False),
                 ("eco", "Eco", self.state_label("11"), "eco", self.dps.get("11") is True),
                 ("plug_power", "Tomada EKAZA", plug_status, "plug", False),
                 ("extra_sleep", "Dormir", self.state_label("25"), "sleep", self.dps.get("25") is True),
                 ("extra_display", "Display", self.state_label("36"), "display", self.dps.get("36") is True)]
        for index, (name, title, status, icon, on) in enumerate(tiles):
            x, y = 24 + (index % 3)*114, 232 + (index//3)*103
            self.button(name, (x, y, x+104, y+52), active=on)
            split = name in ("mode", "fan", "plug_power")
            self.draw_icon(icon, x+(28 if split else 40), y+16, "#10202a" if on else TEXT)
            if split:
                if name == "plug_power":
                    self.stroke([x+74, y+8, x+74, y+44], BORDER, 1)
                    self.hit("plug", (x+75, y, x+104, y+52))
                self.draw_icon("chevron", x+81, y+19, MUTED, 14)
            self.label(x+52, y+67, title, 11, TEXT, "medium", anchor="center")
            self.fit_label(x+52, y+84, status, 10, 108, MUTED,
                           "mono" if name == "plug_power" else "normal", anchor="center")
        self.button("extras", (24, 454, 356, 490))
        self.draw_icon("extras", 37, 463, MUTED, 18)
        self.label(66, 472, "Mais funções", 12, MUTED, anchor="w")
        self.draw_icon("chevron", 330, 465, MUTED, 14)

    def state_label(self, dp):
        value = self.dps.get(dp)
        return "Ligado" if value is True else "Desligado" if value is False else "--"

    def draw_extras(self):
        self.view_header("Funções do Elgin", "Ajustes adicionais do aparelho")
        vertical = self.dps.get("31") not in (None, "off")
        horizontal = self.dps.get("33") is True
        direction = "Ambas" if vertical and horizontal else "Vertical" if vertical else "Horizontal" if horizontal else "Fixa"
        rows = [("extra_swing", "Aletas", "Direção do fluxo de ar", direction),
                ("extra_sleep", "Dormir", "Modo de sono", self.state_label("25")),
                ("extra_display", "Display", "Visor da unidade interna", self.state_label("36")),
                ("extra_mute", "Mudo", "Ventilação silenciosa", "Ligado" if self.dps.get("5") == "mute" else "Desligado"),
                ("extra_turbo", "Turbo", "Disponível no modo Frio", "Ligado" if self.dps.get("5") == "strong" else "Desligado"),
                ("extra_timer", "Timer", "Desligamento em 1 hora", self.state_label("102"))]
        for index, (name, title, subtitle, state) in enumerate(rows):
            y = 98 + index*64
            self.button(name, (24, y, 356, y+56))
            self.label(38, y+10, title, 14, TEXT, "semibold")
            self.label(38, y+32, subtitle, 11, MUTED)
            self.label(340, y+27, state, 12, ACCENT if state == "Ligado" else MUTED, anchor="e")

    def draw_plug(self):
        self.view_header("Tomada EKAZA", "Telemetria pela rede local", refresh="plug_refresh")
        on = self.plug_dps.get("1")
        self.rounded((24, 98, 356, 152), 7, SURFACE)
        self.draw_icon("plug", 38, 115, ACCENT)
        status = "Sem conexão" if self.plug_error else "Ligada" if on is True else "Desligada" if on is False else "Conectando…"
        self.label(70, 124, status, 16, TEXT, "semibold", anchor="w")
        if isinstance(on, bool) and not self.plug_busy and not self.plug_error:
            self.button("plug_power", (250, 109, 344, 141), "Desligar" if on else "Ligar")
        elif self.plug_busy:
            self.label(335, 124, "Enviando…", 12, MUTED, anchor="e")
        values = self.telemetry()
        for i, (key, title, unit, decimals) in enumerate((
                ("power_w", "Potência", "W", 0), ("voltage_v", "Tensão", "V", 1), ("current_a", "Corrente", "A", 2))):
            x = 24+i*114
            self.rounded((x, 172, x+104, 268), 7, SURFACE)
            self.label(x+12, 185, title, 12, MUTED)
            val = values[key]
            self.fit_label(x+12, 210, "--" if val is None else f"{val:.{decimals}f}", 24, 84, TEXT, "semibold")
            self.label(x+12, 246, unit, 11, MUTED)
        energy = self.energy_snapshot()
        self.rounded((24, 288, 356, 397), 7, "#272727")
        today = energy.get("today_kwh") if energy.get("source") != "reference" else None
        self.label(38, 302, "Consumo hoje", 12, MUTED)
        self.label(38, 327, f"{format_kwh(today)} kWh", 21, TEXT, "semibold")
        self.label(202, 302, "Mês atual", 12, MUTED)
        kwh = energy.get("current_month_kwh")
        self.label(202, 329, f"{format_kwh(kwh)} kWh", 17, TEXT, "semibold")
        self.fit_label(38, 375, self.energy_origin(energy), 11, 302, MUTED)
        self.button("energy_detail", (24, 416, 356, 458))
        self.label(38, 437, "Histórico diário e mensal", 13, TEXT, anchor="w")
        self.draw_icon("chevron", 328, 429, MUTED, 16)
        notice = ("Tomada sem conexão • tente atualizar" if self.plug_error else
                  "Leituras indisponíveis • atualize a tomada" if values["power_w"] is None else
                  f"Leitura confirmada às {self.plug_updated:%H:%M:%S}")
        self.fit_label(24, 477, notice, 11, 332, ERROR if self.plug_error else MUTED)

    @staticmethod
    def energy_origin(energy):
        if energy.get("source") == "cloud":
            return "Tuya Cloud • cache desatualizado" if energy.get("stale") else "Consumo registrado • Tuya Cloud"
        if energy.get("source") == "reference":
            return "Referência anterior • sem leitura hoje"
        if energy.get("source") == "counter":
            return "Contador LAN • cobertura parcial"
        if energy.get("source") in ("empty", "cloud_pending"):
            return "Aguardando dados de consumo"
        return "Estimativa local • cobertura parcial"

    def draw_energy(self):
        self.view_header("Histórico de consumo", "Totais em kWh • selecione um mês", "energy_back", "energy_refresh")
        energy = self.energy_snapshot()
        today = energy.get("today_kwh") if energy.get("source") != "reference" else None
        self.label(24, 103, "Hoje", 12, MUTED)
        self.label(24, 126, f"{format_kwh(today)} kWh", 23, TEXT, "semibold")
        self.label(204, 103, "Total ref." if energy.get("total_source") == "reference" else "Total" if energy.get("total_source") == "cloud" else "Total local", 12, MUTED)
        self.label(204, 128, f"{format_kwh(energy.get('total_kwh'))} kWh", 19, TEXT, "semibold")
        self.fit_label(24, 165, self.energy_origin(energy), 11, 332, MUTED)
        current = energy.get("current_month_kwh")
        cost = monthly_cost(current, getattr(self, "energy_tariff", DEFAULT_TARIFF))
        self.label(24, 192, f"Mês atual: {format_kwh(current)} kWh • {format_brl(cost)}", 12, MUTED)
        self.stroke([24, 221, 356, 221], "#333333", 1)
        year = getattr(self, "energy_year", local_now().year)
        self.label(190, 242, str(year), 16, TEXT, "semibold", anchor="center")
        self.draw_icon("back", 26, 231, MUTED)
        self.hit("energy_year_prev", (16, 225, 64, 260))
        self.draw_icon("chevron", 330, 231, MUTED)
        self.hit("energy_year_next", (318, 225, 366, 260))
        rows = self.energy_months(year)
        start = getattr(self, "energy_month_offset", 0)
        for i, row in enumerate(rows[start:start+4]):
            y = 276+i*43
            self.button("energy_month", (24, y, 356, y+37), value=row["month"])
            self.label(36, y+18, row["name"], 13, TEXT, anchor="w")
            self.label(325, y+18, f"{format_kwh(row['kwh'])} kWh", 13, MUTED, anchor="e")
            self.draw_icon("chevron", 331, y+11, MUTED, 14)
        if not rows:
            self.label(190, 340, "Sem histórico para este ano", 13, MUTED, anchor="center")
        if len(rows) > 4:
            self.button("energy_months_prev", (24, 457, 128, 487), "Anteriores")
            self.button("energy_months_next", (252, 457, 356, 487), "Próximos")
        self.fit_label(146, 472, self.cloud_notice() or "", 10, 100, MUTED, anchor="center")

    def draw_energy_month(self):
        year, month = self.energy_year, self.energy_month
        data = self.energy_days()
        days = data["days"]
        self.view_header(f"{MONTHS[month-1]} {year}", "Consumo diário • selecione uma barra", "energy_month_back", "energy_refresh")
        row = next((r for r in self.energy_months(year) if r["month"] == month), {})
        kwh = row.get("kwh")
        self.label(24, 104, f"{format_kwh(kwh)} kWh no mês", 21, TEXT, "semibold")
        cost = monthly_cost(kwh, getattr(self, "energy_tariff", DEFAULT_TARIFF))
        self.label(24, 137, f"Custo estimado: {format_brl(cost)}", 13, MUTED)
        source = self.energy_origin(data)
        self.fit_label(24, 165, source, 11, 332, MUTED)
        start = getattr(self, "energy_chart_start", 0)
        window = days[start:start+8]
        peak = max([d["kwh"] for d in window if d["kwh"] is not None]+[.01])
        selected = getattr(self, "energy_selected_day", 1)
        self.stroke([24, 365, 356, 365], "#444444", 1)
        for i, day in enumerate(window):
            x = 29+i*41
            value = day["kwh"]
            h = max(3, value/peak*146) if value is not None else 3
            self.rounded((x, 365-h, x+28, 365), 3,
                         ACCENT if day["day"] == selected else TRACK if value is not None else "#555555")
            self.label(x+14, 388, str(day["day"]), 12, TEXT if day["day"] == selected else MUTED, anchor="center")
            self.hit("energy_day", (x-3, 204, x+31, 400), day["day"])
        day = next((d for d in days if d["day"] == selected), {})
        self.label(190, 423, f"Dia {selected:02}: {format_kwh(day.get('kwh'))} kWh", 16, TEXT, "semibold", anchor="center")
        self.button("energy_days_prev", (24, 454, 145, 486), "Anteriores")
        self.button("energy_days_next", (235, 454, 356, 486), "Próximos")

    def draw_plug_confirm(self):
        self.view_header("Desligar a tomada?", "O ar não foi confirmado desligado", "plug_cancel_off")
        self.draw_icon("plug", 164, 113, ERROR, 52)
        self.label(190, 192, "O corte interrompe o ar-condicionado.", 15, TEXT, "semibold", anchor="center")
        self.label(190, 224, "Desligue o Elgin antes de cortar a energia", 13, MUTED, anchor="center")
        self.label(190, 248, "para proteger o compressor.", 13, MUTED, anchor="center")
        self.label(190, 300, "A tomada só desliga após sua confirmação.", 12, MUTED, anchor="center")
        enabled = self.plug_dps.get("1") is True and not self.plug_busy and not self.plug_error
        if enabled:
            self.button("plug_confirm_off", (24, 350, 356, 399), "Desligar mesmo assim")
        self.button("plug_cancel_off", (24, 417, 356, 462), "Cancelar")
        if self.plug_error:
            self.fit_label(24, 476, "Sem conexão • tente atualizar", 12, 332, ERROR)

    def draw_settings(self):
        from elgin_tray import startup_enabled
        self.view_header("Configurações", "Painel Elgin e conexão local")
        enabled = False if getattr(self, "offline", False) else startup_enabled()
        self.button("startup", (24, 102, 356, 170))
        self.label(38, 115, "Abrir com o Windows", 14, TEXT, "semibold")
        self.label(38, 143, "Ativado" if enabled else "Desativado", 12, ACCENT if enabled else MUTED)
        self.button("refresh", (24, 186, 356, 250))
        self.label(38, 201, "Reconectar dispositivos", 14, TEXT, "semibold")
        self.label(38, 227, "Atualizar Elgin, tomada e consumo", 12, MUTED)
        self.draw_icon("refresh", 322, 204, MUTED)
        self.label(24, 292, "Controle pela rede local (Tuya LAN)", 13, MUTED)
        self.label(24, 325, "Feche ou pressione Esc para recolher.", 12, MUTED)
        self.label(24, 349, "Para sair, use o menu da bandeja.", 12, MUTED)
        self.label(24, 392, "Aletas, Mudo, Turbo e Timer", 13, TEXT, "semibold")
        self.button("extras", (24, 420, 356, 458), "Abrir funções do Elgin")
        if getattr(self, "startup_error", ""):
            self.fit_label(24, 477, "Falha no início automático • tente novamente", 11, 332, ERROR)

    def draw_menu(self):
        choices = {"mode": [("Frio", "cold"), ("Auto", "auto"), ("Ventilação", "wind"), ("Desumidificar", "wet")],
                   "fan": [("Auto", "auto"), ("Baixa", "low"), ("Média", "middle"), ("Alta", "high")],
                   "swing": [("Fixa", "off"), ("Vertical", "vertical"), ("Horizontal", "horizontal"), ("Ambas", "both")]}[self.menu]
        x = 24 if self.menu == "mode" else 138
        y = 226 if self.page == "control" else 164
        self.menu_bounds = (x, y, x+218, y+170)
        self.rounded(self.menu_bounds, 8, "#2b2b2b", "#555555")
        dp = "4" if self.menu == "mode" else "5"
        for i, (title, value) in enumerate(choices):
            top = y+5+i*40
            self.button("choice", (x+5, top, x+213, top+38), value=(self.menu, value))
            item = self.label(x+18, top+19, title, 13, TEXT, anchor="w")
            self.canvas.addtag_withtag("menu_text", item)
            if self.dps.get(dp) == value:
                self.canvas.create_oval(x+191, top+15, x+199, top+23, fill=ACCENT, outline="")
