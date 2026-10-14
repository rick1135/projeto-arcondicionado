"""Histórico local de uma tomada: contadores confirmados ou integração de W.

Referências visuais ficam separadas de leituras e nunca entram nos deltas.
DP 17 (add_ele) não é somado: snapshots repetidos não identificam eventos.
"""

import calendar
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import sqlite3

from ekaza_plug import medidas

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
CONFIG_DIR = ROOT / "config"
LOCAL_TZ = timezone(timedelta(hours=-3), "America/Sao_Paulo")
MONTHS = ("Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
          "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro")


def reference_data():
    for candidate in (CONFIG_DIR / "energy_reference.json", ROOT / "energy_reference.json", BASE / "energy_reference.json"):
        if candidate.is_file():
            return json.loads(candidate.read_text(encoding="utf-8"))
    return {"captured_date": None, "today_kwh": None, "total_kwh": None,
            "months": {}, "days": {}}


def valid_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def local_now():
    return datetime.now(LOCAL_TZ)


def format_kwh(value):
    return "--" if value is None else f"{value:.2f}"


def reference_snapshot(now=None):
    ref = reference_data()
    source = "reference" if ref["total_kwh"] is not None or ref["months"] or ref["days"] else "empty"
    return {"today_kwh": ref["today_kwh"], "total_kwh": ref["total_kwh"],
            "local_total_kwh": 0.0, "source": source, "total_source": source,
            "reference_date": ref["captured_date"], "coverage_seconds": 0,
            "last_reading": None, "recent": [], "years": [(now or local_now()).year], "gaps": 0}


class EnergyHistory:
    def __init__(self, path=None, config=None):
        self.path = Path(path) if path else (ROOT / "data" / "energy_history.sqlite3" if (ROOT / "data").is_dir() else ROOT / "energy_history.sqlite3")
        if config is None:
            config_file = next((p for p in (CONFIG_DIR / "energy_config.json", ROOT / "energy_config.json", BASE / "energy_config.json") if p.is_file()), CONFIG_DIR / "energy_config.json")
            config = (json.loads(config_file.read_text(encoding="utf-8")) if config_file.is_file()
                      else {"total_dp": None, "total_scale": 3, "max_estimation_gap_seconds": 300})
        self.config = config
        self.total_dp = str(config["total_dp"]) if config.get("total_dp") is not None else None
        if self.total_dp == "17":
            raise ValueError("DP 17 é incremental, não um contador total")
        self.scale = int(config.get("total_scale", 3))
        if not 0 <= self.scale <= 6:
            raise ValueError("Escala de energia inválida")
        self.max_gap = max(15, float(config.get("max_estimation_gap_seconds", 300)))
        self.reference = reference_data()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS readings (
                  ts REAL PRIMARY KEY, power_w REAL, voltage_v REAL, current_a REAL,
                  total_kwh REAL, method TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS daily (
                  day TEXT PRIMARY KEY, kwh REAL NOT NULL DEFAULT 0,
                  coverage REAL NOT NULL DEFAULT 0, method TEXT NOT NULL,
                  gaps INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS reference_months (month TEXT PRIMARY KEY, kwh REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS reference_days (day TEXT PRIMARY KEY, kwh REAL NOT NULL);
            """)
            db.executemany("INSERT OR IGNORE INTO reference_months VALUES (?, ?)", self.reference["months"].items())
            db.executemany("INSERT OR IGNORE INTO reference_days VALUES (?, ?)", self.reference["days"].items())

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def record(self, dps, at=None):
        at = at or local_now()
        if at.tzinfo is None:
            at = at.replace(tzinfo=LOCAL_TZ)
        ts, day = at.timestamp(), at.astimezone(LOCAL_TZ).date().isoformat()
        values = medidas(dps)
        watts = values["power_w"]
        counter = dps.get(self.total_dp) if self.total_dp else None
        total = counter / 10 ** self.scale if valid_number(counter) else None
        if not valid_number(watts):
            if total is None:
                return False
            watts = None
        method = "counter" if total is not None else "estimated"
        with closing(self.connect()) as db, db:
            previous = db.execute("SELECT * FROM readings ORDER BY ts DESC LIMIT 1").fetchone()
            if previous and ts <= previous["ts"]:
                return False
            db.execute("INSERT INTO readings VALUES (?, ?, ?, ?, ?, ?)",
                       (ts, watts, values["voltage_v"], values["current_a"], total, method))
            db.execute("INSERT OR IGNORE INTO daily(day, method) VALUES (?, ?)", (day, method))
            if not previous:
                return True
            elapsed = ts - previous["ts"]
            if total is not None and previous["total_kwh"] is not None:
                delta = total - previous["total_kwh"]
                # Reset do contador: nova base; nunca consumo negativo ou salto fictício.
                if delta < 0:
                    db.execute("UPDATE daily SET gaps=gaps+1 WHERE day=?", (day,))
                    return True
            elif method == "estimated" and previous["method"] == "estimated" and elapsed <= self.max_gap:
                delta = (watts + previous["power_w"]) / 2 * elapsed / 3_600_000
            else:
                db.execute("UPDATE daily SET gaps=gaps+1 WHERE day=?", (day,))
                return True
            start = datetime.fromtimestamp(previous["ts"], LOCAL_TZ)
            end = at.astimezone(LOCAL_TZ)
            # Intervalos que cruzam meia-noite são rateados pelo tempo observado.
            while start < end:
                midnight = (start + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                stop = min(end, midnight)
                seconds = (stop - start).total_seconds()
                part = delta * seconds / elapsed
                segment_day = start.date().isoformat()
                db.execute("""INSERT INTO daily(day, kwh, coverage, method) VALUES (?, ?, ?, ?)
                    ON CONFLICT(day) DO UPDATE SET kwh=kwh+excluded.kwh, coverage=coverage+excluded.coverage,
                    method=CASE WHEN method=excluded.method THEN method ELSE 'mixed' END""",
                           (segment_day, part, seconds, method))
                start = stop
        return True

    def snapshot(self, now=None):
        now = now or local_now()
        day = now.astimezone(LOCAL_TZ).date().isoformat()
        with closing(self.connect()) as db:
            last = db.execute("SELECT * FROM readings ORDER BY ts DESC LIMIT 1").fetchone()
            if not last:
                return reference_snapshot(now)
            today = db.execute("SELECT * FROM daily WHERE day=?", (day,)).fetchone()
            local_total = db.execute("SELECT COALESCE(SUM(kwh),0) FROM daily").fetchone()[0]
            recent = db.execute("SELECT ts,power_w FROM readings WHERE ts>=? ORDER BY ts",
                                (now.timestamp() - 3600,)).fetchall()
            years = {2026, now.year}
            years.update(int(r[0][:4]) for r in db.execute("SELECT day FROM daily"))
            return {"today_kwh": today["kwh"] if today and today["coverage"] > 0 else None,
                    "total_kwh": last["total_kwh"] if last["total_kwh"] is not None else local_total,
                    "local_total_kwh": local_total,
                    "source": today["method"] if today else last["method"],
                    "total_source": "counter" if last["total_kwh"] is not None else "estimated",
                    "reference_date": None, "coverage_seconds": today["coverage"] if today else 0,
                    "last_reading": last["ts"], "recent": [dict(r) for r in recent],
                    "years": sorted(years), "gaps": today["gaps"] if today else 0}

    def monthly(self, year):
        with closing(self.connect()) as db:
            live = {r["month"]: dict(r) for r in db.execute(
                "SELECT substr(day,1,7) month,SUM(kwh) kwh,SUM(coverage) coverage,GROUP_CONCAT(DISTINCT method) method FROM daily WHERE day LIKE ? GROUP BY month",
                (f"{year}-%",))}
            refs = dict(db.execute("SELECT month,kwh FROM reference_months WHERE month LIKE ?", (f"{year}-%",)))
        result = []
        for month in range(12, 0, -1):
            key = f"{year}-{month:02}"
            if key in live:
                value = live[key]["kwh"] if live[key]["coverage"] > 0 else None
                source = live[key]["method"] if value is not None else "pending"
            elif key in refs:
                value, source = refs[key], "reference"
            else:
                value, source = None, "empty"
            result.append({"month": month, "name": MONTHS[month-1], "kwh": value, "source": source})
        return result

    def daily(self, year, month):
        prefix = f"{year}-{month:02}"
        with closing(self.connect()) as db:
            live = {r["day"]: dict(r) for r in db.execute("SELECT * FROM daily WHERE day LIKE ?", (prefix + "-%",))}
            refs = dict(db.execute("SELECT day,kwh FROM reference_days WHERE day LIKE ?", (prefix + "-%",)))
        source = ("estimated" if any(r["method"] in ("estimated", "mixed") for r in live.values()) else "counter") if live else "reference" if refs else "empty"
        days = []
        for day in range(1, calendar.monthrange(year, month)[1]+1):
            key = f"{prefix}-{day:02}"
            row = live.get(key)
            value = row["kwh"] if row and row["coverage"] > 0 else None
            if not live:
                value = refs.get(key)
            days.append({"day": day, "date": key, "kwh": value,
                         "method": row["method"] if row else source,
                         "coverage_seconds": row["coverage"] if row else 0})
        return {"source": source, "days": days}


def format_source(snapshot):
    if snapshot['source'] == 'cloud':
        return ('Tuya Cloud • cache desatualizado' if snapshot.get('stale') else
                'Tuya Cloud • aguardando dados de hoje' if snapshot['today_kwh'] is None else
                'Tuya Cloud • consumo registrado')
    if snapshot["today_kwh"] is None:
        return "Sem leitura hoje • aguardando intervalo monitorado"
    if snapshot["source"] == "reference":
        return "Dados iniciais • referência de 11/10/2026"
    if snapshot["source"] == "counter":
        return "Contador LAN • dias parciais / rateio à meia-noite"
    return "Estimativa local • somente períodos monitorados"
