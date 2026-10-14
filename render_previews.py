"""Revisão das três telas reais do Tk, com dados ilustrativos e sem rede.

Execute --show para comparar as telas; sem argumentos audita os limites reais
de texto em escala 100% e 80%. Usa os mesmos métodos do app, evitando réplicas
de layout que fiquem desatualizadas quando o painel muda.
"""

import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import tkinter as tk

from PIL import ImageTk

from elgin_art import WIDTH, HEIGHT, render_assets
from elgin_tray import BG, TrayApp
from energy_history import EnergyHistory, local_now


def make_panel(root, page, scale, assets):
    app = TrayApp.__new__(TrayApp)
    app.root, app.page, app.scale = root, page, scale
    app.closed = False
    app.canvas = tk.Canvas(root, width=round(WIDTH * scale), height=round(HEIGHT * scale),
                           bg=BG, highlightthickness=0)
    app.dps = {"1": True, "2": 24, "3": 26, "4": "cold", "5": "auto",
               "11": True, "25": True, "31": "off", "33": False,
               "36": True, "102": False}
    app.plug_dps = {"1": True, "18": 0, "19": 0, "20": 1234}
    app.error = app.plug_error = ""
    app.busy = app.plug_busy = app.reconnecting = False
    app.updated = app.plug_updated = datetime.now()
    app.pending_temp = app.menu = None
    app.frame_idx, app.phase = 7, 0
    app.hotspots, app.fonts = [], {}
    app.selected_timer_hours = "0100"
    app.energy_store = None
    app.energy_year, app.energy_month = 2026, 10
    app.energy_month_offset, app.energy_chart_start = 0, 3
    app.energy_selected_day = 11
    app.img_base = ImageTk.PhotoImage(assets["base"], master=root)
    app.img_blank = ImageTk.PhotoImage(assets["blank"], master=root)
    app.top_off = ImageTk.PhotoImage(assets["top_off"], master=root)
    app.top_on = [ImageTk.PhotoImage(image, master=root) for image in assets["top_on"]]
    app.eco_imgs = [ImageTk.PhotoImage(image, master=root) for image in assets["eco"]]
    app.slider_imgs = [ImageTk.PhotoImage(image, master=root) for image in assets["slider"]]
    return app


def inspect(app):
    texts = []
    for item in app.canvas.find_all():
        if app.canvas.type(item) == "text":
            texts.append((app.canvas.itemcget(item, "text"), app.canvas.bbox(item)))
    outside, overlaps = [], []
    for text, (x1, y1, x2, y2) in texts:
        if x1 < 0 or y1 < 0 or x2 > WIDTH * app.scale or y2 > HEIGHT * app.scale:
            outside.append(text)
    for i, (ta, a) in enumerate(texts):
        for tb, b in texts[i + 1:]:
            if min(a[2], b[2]) - max(a[0], b[0]) > 1 and min(a[3], b[3]) - max(a[1], b[1]) > 1:
                overlaps.append([ta, tb])
    return {"page": app.page, "scale": app.scale, "outside": outside, "overlaps": overlaps}


def review_states(root, scale, output):
    """Fixtures isoladas: nunca escreve no histórico do dispositivo real."""
    import tempfile
    fixture = tempfile.TemporaryDirectory(prefix="energy-review-", dir=output)
    store = EnergyHistory(Path(fixture.name) / "history.sqlite3")
    now = local_now()
    for offset in (2, 1):
        start = (now - timedelta(days=offset)).replace(hour=12, minute=0, second=0, microsecond=0)
        for sample in range(13):
            store.record({"18": 8000, "19": 10000, "20": 1234}, start + timedelta(minutes=5*sample))
    store.record({"18": 0, "19": 0, "20": 1234}, now)
    assets, panels, report = render_assets(scale), [], []
    for state, page in (("Sem leitura hoje", "energy"), ("Estimativa diária", "energy_month"),
                        ("Instantâneas offline", "energy"), ("Foco restaurado", "plug")):
        column = tk.Frame(root, bg=BG)
        column.pack(side="left", padx=4, pady=4)
        tk.Label(column, text=state, bg=BG, fg="#b7c9d9", font=("Segoe UI", 11)).pack(pady=8)
        app = make_panel(root, page, scale, assets)
        app.energy_store = store
        app.energy_year, app.energy_month = now.year, now.month
        app.energy_selected_day = (now - timedelta(days=1)).day
        app.energy_chart_start = max(0, app.energy_selected_day - 7)
        if state == "Instantâneas offline":
            app.plug_error = "Sem conexão"
            app.plug_dps.update({"18": 8000, "19": 10000})
        if state == "Foco restaurado":
            app.focused_hotspot = ("energy_detail", None)
        app.canvas.pack(in_=column)
        app.draw()
        if state == "Foco restaurado":
            # Mesmo caminho de retorno usado pela navegação do app.
            app.navigate_energy("plug", -1, focus=("energy_detail", None))
        report.append({"state": state, **inspect(app)})
        panels.append(app)
    return fixture, panels, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--review-states", action="store_true")
    parser.add_argument('--cloud', action='store_true', help='Renderiza somente o cache Cloud, sem rede.')
    parser.add_argument("--pages", nargs="+", default=["control", "extras", "plug", "energy", "energy_month"],
                        choices=["control", "extras", "plug", "energy", "energy_month"])
    args = parser.parse_args()
    root = tk.Tk()
    root.withdraw()
    root.title("Elgin AC — revisão visual offline")
    root.configure(bg=BG)
    output = Path(__file__).with_name("_ui_review")
    output.mkdir(exist_ok=True)
    if args.review_states:
        fixture, panels, report = review_states(root, args.scale, output)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        root.deiconify()
        root.after(180000, root.destroy)
        root.mainloop()
        fixture.cleanup()
        return
    report, panels = [], []
    cloud = None
    if args.cloud:
        from bridge import EnergyBridge
        from contextlib import closing
        import sqlite3
        with closing(sqlite3.connect(Path(__file__).with_name('energy_history.sqlite3'))) as db:
            row = db.execute('SELECT device_id FROM cloud_energy_cache LIMIT 1').fetchone()
        if row is None:
            raise SystemExit('Faça uma consulta Cloud antes de revisar o cache.')
        cloud = EnergyBridge(row[0], cache_path=Path(__file__).with_name('energy_history.sqlite3'))
    for scale in ([args.scale] if args.show else [1.0, 0.8]):
        assets = render_assets(scale)
        for page in args.pages:
            app = make_panel(root, page, scale, assets)
            if cloud is not None:
                app.cloud_energy = cloud
                app.cloud_error = ''
                app.cloud_failures = {}
                app.cloud_busy = False
                app.submit_energy = lambda *a, **kw: None  # Revisão nunca abre rede.
                app.energy_year, app.energy_month = local_now().year, local_now().month
                app.energy_selected_day = local_now().day
                app.energy_chart_start = max(0, app.energy_selected_day - 8)
                app.plug_error = 'Sem leitura LAN na prévia'
            app.canvas.pack(side="left", padx=4, pady=4)
            app.draw()
            report.append(inspect(app))
            if not args.show:
                for state in ("off", "offline", "full"):
                    app.plug_dps.update({"1": state != "off", "19": 18400 if state == "full" else 0})
                    app.plug_error = "Sem conexão" if state == "offline" else ""
                    app.dps["11"] = state != "off"
                    app.draw()
                    report.append({"state": state, **inspect(app)})
                app.canvas.destroy()
            else:
                panels.append(app)
    output = Path(__file__).with_name("_ui_review")
    output.mkdir(exist_ok=True)
    (output / "native-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.show:
        root.deiconify()
        root.after(180000, root.destroy)
        root.mainloop()
    else:
        root.destroy()
        if any(row["outside"] or row["overlaps"] for row in report):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
