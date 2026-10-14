r"""Painel Windows para controlar o ar-condicionado Elgin pela rede local.

Execute com: .\.venv\Scripts\python.exe .\elgin_app.py
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import math
import queue
import tkinter as tk

from elgin_ac import conectar, configurar_modo, escrever_dp, ler_config, ler_status


MODOS = {"cold": "Resfriar", "wet": "Secar", "wind": "Ventilar", "auto": "Auto", "hot": "Aquecer"}
VENTILACAO = {
    "auto": "Auto", "low": "Baixa", "middle": "Média", "high": "Alta",
    "strong": "Turbo", "mute": "Silencioso",
}
MIN_TEMP, MAX_TEMP = 16, 32
BASE_W, BASE_H = 600, 860


class ElginApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Elgin · Controle do ar-condicionado")
        self.root.geometry("600x860")
        self.root.minsize(520, 750)
        self.root.configure(bg="#090a10")

        self.canvas = tk.Canvas(root, bg="#090a10", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self.draw())
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.root.bind("<r>", lambda _event: self.submit("status"))
        self.root.bind("<R>", lambda _event: self.submit("status"))
        self.root.bind("<space>", self.toggle_power)
        self.root.bind("<Left>", lambda _event: self.change_temp(-1))
        self.root.bind("<Right>", lambda _event: self.change_temp(1))
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.executor = ThreadPoolExecutor(max_workers=1)
        self.results = queue.Queue()
        self.dps = {}
        self.busy = False
        self.error = ""
        self.last_update = None
        self.pending_temp = None
        self.dragging = False
        self.open_menu = None
        self.regions = []
        self.phase = 0.0
        self.scale = 1.0
        self.ox = self.oy = 0.0
        self.closed = False
        self.draw()
        self.root.after(100, self.drain_results)
        self.root.after(90, self.animate)
        self.root.after(15000, self.periodic_refresh)
        self.submit("status")

    def xy(self, x, y):
        return self.ox + x * self.scale, self.oy + y * self.scale

    def font(self, size, weight="normal"):
        return ("Segoe UI", max(8, round(size * self.scale)), weight)

    def rect(self, x1, y1, x2, y2, fill, outline=""):
        a, b = self.xy(x1, y1), self.xy(x2, y2)
        self.canvas.create_rectangle(*a, *b, fill=fill, outline=outline)

    def oval(self, x1, y1, x2, y2, fill, outline="", width=1):
        a, b = self.xy(x1, y1), self.xy(x2, y2)
        self.canvas.create_oval(*a, *b, fill=fill, outline=outline, width=width * self.scale)

    def line(self, points, fill, width=2, smooth=False):
        coords = []
        for x, y in points:
            coords.extend(self.xy(x, y))
        self.canvas.create_line(*coords, fill=fill, width=width * self.scale,
                                smooth=smooth, capstyle="round", joinstyle="round")

    def text(self, x, y, value, size, fill, weight="normal", anchor="nw"):
        self.canvas.create_text(*self.xy(x, y), text=value, fill=fill,
                                font=self.font(size, weight), anchor=anchor)

    def round_rect(self, x1, y1, x2, y2, radius, fill, outline="", width=1):
        r = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
        p = [
            (x1+r,y1), (x2-r,y1), (x2,y1), (x2,y1+r),
            (x2,y2-r), (x2,y2), (x2-r,y2), (x1+r,y2),
            (x1,y2), (x1,y2-r), (x1,y1+r), (x1,y1),
        ]
        coords = []
        for x, y in p:
            coords.extend(self.xy(x, y))
        self.canvas.create_polygon(*coords, smooth=True, splinesteps=20,
                                   fill=fill, outline=outline, width=width*self.scale)

    def region(self, name, x1, y1, x2, y2, payload=None):
        self.regions.append((name, (x1, y1, x2, y2), payload))

    def power_icon(self, x, y, color):
        self.canvas.create_arc(*self.xy(x-15,y-15), *self.xy(x+15,y+15),
                               start=130, extent=280, style="arc", outline=color,
                               width=3*self.scale)
        self.line([(x,y-19),(x,y+2)], color, 3)

    def snow_icon(self, x, y, color):
        for angle in (0, math.pi/3, 2*math.pi/3):
            dx, dy = 14*math.cos(angle), 14*math.sin(angle)
            self.line([(x-dx,y-dy),(x+dx,y+dy)], color, 2)

    def fan_icon(self, x, y, color):
        self.oval(x-3,y-3,x+3,y+3,color)
        for angle in (0, 2*math.pi/3, 4*math.pi/3):
            dx, dy = math.cos(angle), math.sin(angle)
            self.oval(x+4*dx-5,y+4*dy-5,x+4*dx+7,y+4*dy+7,"",color,1.5)

    def wind_icon(self, x, y, color):
        for offset, length in ((-8,27),(0,35),(8,24)):
            self.line([(x,y+offset),(x+length,y+offset)],color,2.5)
            self.oval(x+length-2,y+offset-2,x+length+2,y+offset+2,color)

    def refresh_icon(self, x, y, color):
        self.canvas.create_arc(*self.xy(x-11,y-11), *self.xy(x+11,y+11),
                               start=35, extent=275, style="arc", outline=color,
                               width=2*self.scale)
        self.line([(x+10,y-11),(x+12,y-3),(x+4,y-4)],color,2)

    def draw(self):
        if self.closed:
            return
        w = max(self.canvas.winfo_width(), 520)
        h = max(self.canvas.winfo_height(), 750)
        self.scale = min(w/BASE_W, h/BASE_H)
        self.ox = (w-BASE_W*self.scale)/2
        self.oy = (h-BASE_H*self.scale)/2
        c = self.canvas
        c.delete("all")
        self.regions = []

        self.rect(0,0,BASE_W,BASE_H,"#090a10")
        self.round_rect(9,10,591,850,36,"#141518", "#252830")
        self.round_rect(11,12,589,315,34,"#1b272e")
        self.rect(12,83,588,312,"#1a2025")
        self.round_rect(11,265,589,849,34,"#141518")

        # Cabeçalho e botão principal.
        self.line([(47,66),(47,50),(51,45),(55,50),(55,66)],"#889197",2)
        self.oval(44,62,58,76,"", "#889197",2)
        self.text(78,46,"ELGIN",20,"#f4f6f7","bold")
        ambiente = self.dps.get("3")
        self.text(184,51,f"{ambiente}°C no ambiente" if ambiente is not None else "Conectando...",
                  14,"#aeb9bd")
        ligado = self.dps.get("1") is True
        self.oval(516,28,580,92,"#143c4d" if ligado else "#282e32")
        self.oval(523,35,573,85,"#69d5f8" if ligado else "#40474b")
        self.power_icon(548,59,"#0c2b38" if ligado else "#bdc5c8")
        self.region("power",516,28,580,92)

        # Unidade interna: peça branca e fenda de ventilação.
        self.round_rect(130,149,474,253,28,"#090c0e")
        self.round_rect(126,138,474,244,27,"#edf2f4")
        self.round_rect(132,143,468,229,23,"#f7fafb")
        self.line([(151,206),(446,206)],"#dfe6e8",1)
        self.round_rect(154,223,447,246,9,"#252c31")
        self.round_rect(157,226,444,242,6,"#080c0e")
        self.oval(183,178,188,183,"#cbd4d8")
        valor = self.pending_temp if self.pending_temp is not None else self.dps.get("2")
        self.text(421,176,str(valor) if valor is not None else "--",17,
                  "#6bcaf0" if ligado else "#a6bbc3","bold",anchor="ne")
        self.oval(429,198,433,202,"#6bcaf0" if ligado else "#abb9bf")

        # Correntes de ar se movem apenas quando o aparelho está ligado.
        if ligado:
            for i in range(16):
                start = 164 + i*18
                drift = math.sin(self.phase + i*0.45)*7
                spread = (i-7.5)*4
                shade = ("#36434a", "#35464e", "#2b393f", "#263138")[i%4]
                self.line([(start,248),(start+drift,294),(start+spread+drift,356)],
                          shade,1.4,True)

        # Temperatura e slider.
        if valor is None:
            self.text(43,374,"--",80,"#f5f7f8","bold")
        else:
            self.text(43,374,str(valor),80,"#f5f7f8","bold")
        self.text(157 if valor is not None and valor<10 else 187,394,"°C",29,"#aab2b5")
        self.text(43,468,"Temperatura desejada",14,"#959da2")
        self.oval(40,519,102,581,"#25272b")
        self.line([(60,550),(82,550)],"#d8dde0",3)
        self.oval(498,519,560,581,"#25272b")
        self.line([(519,550),(541,550)],"#d8dde0",3)
        self.line([(530,539),(530,561)],"#d8dde0",3)
        self.region("minus",40,519,102,581)
        self.region("plus",498,519,560,581)
        self.round_rect(121,528,479,571,22,"#292c31")
        if valor is not None:
            knob = 121+(max(MIN_TEMP,min(MAX_TEMP,valor))-MIN_TEMP)/(MAX_TEMP-MIN_TEMP)*358
            self.round_rect(121,528,max(142,knob),571,21,"#409cf1")
            self.oval(knob-24,526,knob+24,574,"#f9fcfd")
        self.region("slider",121,518,479,583)
        self.text(121,586,f"{MIN_TEMP}°",13,"#788187")
        self.text(479,586,f"{MAX_TEMP}°",13,"#788187",anchor="ne")

        # Três controles principais, inspirados nos cartões do vídeo.
        modo = MODOS.get(self.dps.get("4"),"—")
        fan = VENTILACAO.get(self.dps.get("5"),"—")
        self.draw_card(39,635,204,750,"Modo",modo,"snow",False)
        self.draw_card(215,635,380,750,"Ventilação",fan,"fan",False)
        self.draw_card(391,635,561,750,"Protect","Ligado" if self.protect_ativo() else "Desligado",
                       "wind",self.protect_ativo())
        self.region("mode",39,635,204,750)
        self.region("fan",215,635,380,750)
        self.region("protect",391,635,561,750)

        # Aletas ficam acessíveis sem esconder os comandos mais usados.
        self.draw_swing(39,768,287,811,"Aletas verticais",self.dps.get("31") not in (None,"off"))
        self.draw_swing(313,768,561,811,"Aletas horizontais",self.dps.get("33") is True)
        self.region("vertical",39,768,287,811)
        self.region("horizontal",313,768,561,811)

        if self.error:
            footer, color = "Sem conexão · clique para atualizar", "#f6a6a6"
        elif self.busy:
            footer, color = "Enviando...", "#8dcbed"
        elif self.last_update:
            footer, color = f"Atualizado às {self.last_update:%H:%M:%S}", "#9ea7aa"
        else:
            footer, color = "Conectando ao ar-condicionado...", "#9ea7aa"
        self.oval(40,831,49,840,"#6bd2f2" if self.last_update and not self.error else "#838a90")
        self.text(59,826,footer[:48],12,color)
        self.refresh_icon(552,836,"#b9c3c8")
        self.region("refresh",528,816,578,851)
        if self.error:
            self.region("refresh",39,816,510,851)

        if self.open_menu:
            self.draw_menu()

    def draw_card(self,x1,y1,x2,y2,label,value,icon,active):
        self.round_rect(x1,y1,x2,y2,22,"#1d3038" if active else "#222326",
                        "#3c6170" if active else "#33363a")
        color = "#70d2f3" if active else "#a6b0b5"
        if icon == "snow": self.snow_icon(x1+31,y1+31,color)
        elif icon == "fan": self.fan_icon(x1+31,y1+31,color)
        else: self.wind_icon(x1+17,y1+31,color)
        if active:
            self.round_rect(x2-57,y1+18,x2-15,y1+42,12,"#5bc9ee")
            self.oval(x2-39,y1+18,x2-15,y1+42,"#f9fcfd")
        self.text(x1+18,y1+62,label,13,"#aab4b8")
        self.text(x1+18,y1+85,value,19,"#f6f8f9","bold")

    def draw_swing(self,x1,y1,x2,y2,label,active):
        self.round_rect(x1,y1,x2,y2,15,"#1e282d" if active else "#202124",
                        "#33505c" if active else "#303338")
        self.text(x1+14,y1+12,label,13,"#edf1f3" if active else "#b4bbbf")
        self.oval(x2-42,y1+13,x2-21,y1+34,"#5cccf2" if active else "#596166")

    def draw_menu(self):
        if self.open_menu == "mode":
            options = [("Automático","auto"),("Resfriar","cold"),
                       ("Ventilar","wind"),("Secar","wet")]
            x1,y1,x2 = 39,454,204
        else:
            options = [("Auto","auto"),("Baixa","low"),("Média","middle"),
                       ("Alta","high"),("Turbo","strong"),("Silencioso","mute")]
            x1,y1,x2 = 215,371,380
        y2 = y1 + 16 + len(options)*38
        self.round_rect(x1,y1,x2,y2,18,"#2b3034","#45606b")
        for i,(label,value) in enumerate(options):
            y = y1+9+i*38
            selected = self.dps.get("4" if self.open_menu=="mode" else "5")==value
            if selected:
                self.round_rect(x1+7,y,x2-7,y+35,10,"#284653")
            self.text(x1+18,y+8,label,14,"#f4f8fa" if selected else "#c4ced2")
            self.region("choice",x1+7,y,x2-7,y+36,(self.open_menu,value))

    def protect_ativo(self):
        return self.dps.get("11") is True

    def event_position(self,event):
        return (event.x-self.ox)/self.scale, (event.y-self.oy)/self.scale

    def hit(self,x,y):
        for name,(x1,y1,x2,y2),payload in reversed(self.regions):
            if x1<=x<=x2 and y1<=y<=y2:
                return name,payload
        return None,None

    def on_click(self,event):
        self.canvas.focus_set()
        x,y = self.event_position(event)
        name,payload = self.hit(x,y)
        if name == "choice":
            self.open_menu = None
            menu,value = payload
            if menu == "mode":
                self.submit("mode", value)
            else:
                self.submit("fan",value)
            return
        if self.open_menu:
            self.open_menu = None
            self.draw()
            return
        if name == "refresh":
            self.submit("status")
        elif self.busy or not self.dps:
            return
        elif name == "power": self.toggle_power()
        elif name == "minus": self.change_temp(-1)
        elif name == "plus": self.change_temp(1)
        elif name == "slider":
            self.dragging = True
            self.pending_temp = self.temp_from_x(x)
            self.draw()
        elif name in ("mode","fan"):
            self.open_menu = name
            self.draw()
        elif name == "protect": self.submit("protect", not self.protect_ativo())
        elif name == "vertical": self.submit("vertical",self.dps.get("31") in (None,"off"))
        elif name == "horizontal": self.submit("horizontal",self.dps.get("33") is not True)

    def on_drag(self,event):
        if self.dragging:
            x,_ = self.event_position(event)
            self.pending_temp = self.temp_from_x(x)
            self.draw()

    def on_release(self,_event):
        if self.dragging:
            self.dragging = False
            value = self.pending_temp
            self.pending_temp = None
            self.submit("temp",value)

    def temp_from_x(self,x):
        return round(MIN_TEMP + max(0,min(1,(x-121)/358))*(MAX_TEMP-MIN_TEMP))

    def change_temp(self,step):
        if self.busy or not self.dps:
            return
        current = int(self.dps.get("2",23))
        self.submit("temp",max(MIN_TEMP,min(MAX_TEMP,current+step)))

    def toggle_power(self,_event=None):
        if not self.busy and self.dps:
            self.submit("power",self.dps.get("1") is not True)

    def submit(self,command,value=None):
        if self.closed or self.busy:
            return
        self.busy = True
        self.error = ""
        self.draw()
        future = self.executor.submit(self.run_operation,command,value)
        future.add_done_callback(lambda f: self.results.put(f.result()))

    @staticmethod
    def run_operation(command,value):
        try:
            cfg = ler_config()
            device, iniciais = conectar(cfg)
            try:
                def confirmar(dp, esperado):
                    dps = escrever_dp(device, dp, esperado)
                    if dps.get(str(dp)) != esperado:
                        dps = ler_status(device)
                    if dps.get(str(dp)) != esperado:
                        raise RuntimeError(f"O aparelho não confirmou o DP {dp}")
                    return dps

                if command == "status": return iniciais,None
                if command == "power": return escrever_dp(device,1,value),None
                if command == "temp": return escrever_dp(device,2,value),None
                if command == "mode": return configurar_modo(device,{"auto":"auto","cold":"cool","wet":"dry","wind":"fan"}[value]),None
                if command == "fan": return escrever_dp(device,5,value),None
                if command == "protect": return confirmar(11,value),None
                if command == "sleep": return confirmar(25,value),None
                if command == "display": return confirmar(36,value),None
                if command == "special_fan":
                    speed, restore = value
                    if speed == "strong" and iniciais.get("4") != "cold":
                        raise ValueError("Turbo está disponível apenas no modo Frio")
                    return confirmar(5,speed if speed else restore),None
                if command == "timer_off_1h":
                    if value:
                        confirmar(104,"0100")
                    return confirmar(102,value),None
                if command == "vertical": return escrever_dp(device,31,"same" if value else "off"),None
                if command == "horizontal": return escrever_dp(device,33,value),None
                if command == "swing":
                    vertical, horizontal = value
                    dps = iniciais
                    if (dps.get("31") not in (None,"off")) != vertical:
                        dps = escrever_dp(device,31,"same" if vertical else "off")
                    if (dps.get("33") is True) != horizontal:
                        dps = escrever_dp(device,33,horizontal)
                    return dps,None
                raise ValueError(f"Comando desconhecido: {command}")
            finally:
                device.close()
        except Exception as erro:
            return None,str(erro)

    def drain_results(self):
        if self.closed:
            return
        try:
            while True:
                dps,error = self.results.get_nowait()
                self.busy = False
                if error:
                    self.error = error
                else:
                    self.dps = dps
                    self.last_update = datetime.now()
                    self.error = ""
                self.draw()
        except queue.Empty:
            pass
        self.root.after(100,self.drain_results)

    def periodic_refresh(self):
        if self.closed:
            return
        if not self.busy and not self.dragging and not self.open_menu:
            self.submit("status")
        self.root.after(15000,self.periodic_refresh)

    def animate(self):
        if self.closed:
            return
        if self.dps.get("1") is True and not self.busy and not self.dragging:
            self.phase += 0.12
            self.draw()
        self.root.after(90,self.animate)

    def close(self):
        self.closed = True
        self.executor.shutdown(wait=False,cancel_futures=True)
        self.root.destroy()


def main():
    root = tk.Tk()
    ElginApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
