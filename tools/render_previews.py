"""Renderiza as views Tk reais com fixtures isoladas, sem Tuya nem registro.

Sem argumentos audita texto/limites a 100% e 80%. --capture salva capturas
da janela renderizada; --show mantém a prévia disponível por até 3 minutos.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import argparse
from datetime import datetime, timedelta
import json
import tempfile
import tkinter as tk
from unittest.mock import Mock, patch
from PIL import Image, ImageGrab
from elgin_tray import TrayApp
from fluent_ui import WIDTH, HEIGHT, BG
from energy_history import EnergyHistory, local_now
from windows_flyout import apply_window_style

PAGES = ("control", "extras", "plug", "energy", "energy_month", "settings", "plug_confirm")


def make_panel(root, page="control", scale=1.0, store=None):
    app = TrayApp.__new__(TrayApp)
    app.root, app.page, app.scale = root, page, scale
    app.closed, app.offline = False, True
    app.canvas = tk.Canvas(root, width=round(WIDTH*scale), height=round(HEIGHT*scale),
                           bg=BG, highlightthickness=0, takefocus=True)
    app.dps = {"1": True, "2": 24, "3": 26, "4": "cold", "5": "auto",
               "11": True, "25": False, "31": "off", "33": False, "36": True, "102": False}
    app.plug_dps = {"1": True, "18": 6880, "19": 8500, "20": 1234}
    app.error = app.plug_error = app.startup_error = ""
    app.busy = app.plug_busy = app.dragging = False
    app.updated = app.plug_updated = datetime.now()
    app.pending_temp = app.menu = app.hover = None
    app.hotspots, app.fonts = [], {}
    app.energy_store = store
    app.energy_year, app.energy_month = local_now().year, local_now().month
    app.energy_month_offset = 0
    app.energy_chart_start = max(0, local_now().day-8)
    app.energy_selected_day = local_now().day
    app.submit = app.submit_plug = app.submit_energy = Mock()
    app.draw()
    return app


def inspect(app):
    texts = []
    for item in app.canvas.find_all():
        if app.canvas.type(item) != "text":
            continue
        box = app.canvas.bbox(item)
        if app.menu and "menu_text" not in app.canvas.gettags(item):
            # O menu opaco cobre o conteúdo abaixo; não é sobreposição visível.
            m = [v*app.scale for v in app.menu_bounds]
            if min(box[2], m[2]) > max(box[0], m[0]) and min(box[3], m[3]) > max(box[1], m[1]):
                continue
        texts.append((app.canvas.itemcget(item, "text"), box))
    outside = [text for text, (x1, y1, x2, y2) in texts
               if x1 < 0 or y1 < 0 or x2 > WIDTH*app.scale or y2 > HEIGHT*app.scale]
    overlaps = []
    for i, (a_text, a) in enumerate(texts):
        for b_text, b in texts[i+1:]:
            if min(a[2], b[2])-max(a[0], b[0]) > 1 and min(a[3], b[3])-max(a[1], b[1]) > 1:
                overlaps.append([a_text, b_text])
    hits_outside = [name for name, (x1, y1, x2, y2), _ in app.hotspots
                    if x1 < 0 or y1 < 0 or x2 > WIDTH or y2 > HEIGHT]
    return {"page": app.page, "scale": app.scale, "outside": outside,
            "overlaps": overlaps, "hits_outside": hits_outside}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--pages", nargs="+", choices=PAGES, default=list(PAGES))
    args = parser.parse_args()
    output = Path(__file__).resolve().parent.parent / "_ui_review"
    output.mkdir(exist_ok=True)
    report, captures = [], []
    root = tk.Tk()
    root.withdraw()
    root.overrideredirect(True)
    root.configure(bg=BG)
    root.attributes("-topmost", True)
    now = local_now()
    references = {"captured_date": None, "today_kwh": None, "total_kwh": None,
                  "months": {}, "days": {}}
    for offset in (1, 2, 3, 4):
        year, month0 = divmod(now.year*12 + now.month-1-offset, 12)
        references['months'][f'{year}-{month0+1:02}'] = round(7.25 + offset*2.15, 2)
    with (tempfile.TemporaryDirectory(prefix="fluent-preview-", dir=output) as folder,
          patch('energy_history.reference_data', return_value=references)):
        store = EnergyHistory(Path(folder)/"fixture.sqlite3", config={"total_dp": None})
        for offset in (2, 1, 0):
            start = (now-timedelta(days=offset)).replace(hour=0, minute=0, second=0, microsecond=0)
            for sample in range(13):
                store.record({"18": 6880, "19": 8500, "20": 1234}, start+timedelta(minutes=5*sample))
        for scale in ([args.scale] if args.show else [1.0, .8]):
            for page in args.pages:
                app = make_panel(root, page, scale, store)
                app.canvas.pack()
                root.geometry(f"{round(WIDTH*scale)}x{round(HEIGHT*scale)}+100+100")
                root.update_idletasks()
                report.append(inspect(app))
                if args.capture and scale == 1.0:
                    root.deiconify()
                    root.update()
                    apply_window_style(root)
                    root.update()
                    image = ImageGrab.grab(bbox=(app.canvas.winfo_rootx(), app.canvas.winfo_rooty(),
                                                app.canvas.winfo_rootx()+app.canvas.winfo_width(),
                                                app.canvas.winfo_rooty()+app.canvas.winfo_height()))
                    image.save(output / f"fluent-{page}.png")
                    captures.append((page, image))
                    root.withdraw()
                for state in ("off", "offline", "full", "long_mode", "menu_mode", "menu_fan", "menu_swing"):
                    app.dps.update({"1": state != "off", "4": "wet" if state == "long_mode" else "cold"})
                    app.plug_dps.update({"1": state != "off", "19": 18400 if state == "full" else 8500})
                    app.error = app.plug_error = "Sem conexão" if state == "offline" else ""
                    app.menu = state.removeprefix("menu_") if state.startswith("menu_") and page in ("control", "extras") else None
                    app.draw()
                    report.append({"state": state, **inspect(app)})
                app.canvas.destroy()
        if captures:
            sheet = Image.new("RGB", (WIDTH*3, HEIGHT*2), "#111111")
            for i, (page, capture) in enumerate(captures[:6]):
                sheet.paste(capture, ((i%3)*WIDTH, (i//3)*HEIGHT))
            sheet.save(output/"fluent-views.png")
        if args.show:
            app = make_panel(root, args.pages[0], args.scale, store)
            app.canvas.pack()
            app.canvas.bind("<Button-1>", app.click)
            app.canvas.bind("<Motion>", app.motion)
            root.bind("<Escape>", lambda _e: root.destroy())
            root.deiconify()
            root.after(180000, root.destroy)
            root.mainloop()
        else:
            root.destroy()
    (output/"native-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    failures = [row for row in report if row["outside"] or row["overlaps"] or row["hits_outside"]]
    print(json.dumps({"views_checked": len(report), "failures": failures}, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
