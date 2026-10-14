"""Verifica contadores, estimativas e separação de referências sem rede."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tests.fixtures import ENERGY_REFERENCE

from energy_history import EnergyHistory, LOCAL_TZ
import energy_history
READ_REFERENCE_DATA = energy_history.reference_data


class EnergyTests(unittest.TestCase):
    def setUp(self):
        fixture = patch('energy_history.reference_data', return_value=ENERGY_REFERENCE)
        fixture.start()
        self.addCleanup(fixture.stop)
        self.workspace = Path(__file__).resolve().parent
        self.tmp = tempfile.TemporaryDirectory(dir=self.workspace)
        self.path = Path(self.tmp.name) / "history.sqlite3"
        self.start = datetime(2026, 10, 12, 12, tzinfo=LOCAL_TZ)

    def tearDown(self):
        self.assertEqual(Path(self.tmp.name).resolve().parent, self.workspace)
        self.tmp.cleanup()

    def store(self, **config):
        return EnergyHistory(self.path, config={"total_dp": None, **config})

    def test_integrates_power_and_survives_restart(self):
        store = self.store()
        store.record({"19": 10000}, self.start)
        store.record({"19": 10000}, self.start + timedelta(seconds=60))
        fresh = self.store()
        snapshot = fresh.snapshot(self.start + timedelta(seconds=60))
        self.assertAlmostEqual(snapshot["today_kwh"], 1/60)
        self.assertEqual(snapshot["source"], "estimated")
        self.assertEqual(snapshot["coverage_seconds"], 60)

    def test_splits_midnight_in_local_timezone(self):
        store = self.store()
        at = self.start.replace(hour=23, minute=59)
        store.record({"19": 10000}, at)
        store.record({"19": 10000}, at + timedelta(minutes=2))
        series = store.daily(2026, 10)["days"]
        self.assertAlmostEqual(series[11]["kwh"], 1/60)
        self.assertAlmostEqual(series[12]["kwh"], 1/60)

    def test_offline_gap_and_duplicate_do_not_add_energy(self):
        store = self.store()
        store.record({"19": 10000}, self.start)
        self.assertFalse(store.record({"19": 10000}, self.start))
        store.record({"19": 10000}, self.start + timedelta(hours=2))
        snapshot = store.snapshot(self.start + timedelta(hours=2))
        self.assertIsNone(snapshot["today_kwh"])
        self.assertEqual(snapshot["gaps"], 1)

    def test_counter_deltas_and_reset(self):
        store = self.store(total_dp="101", total_scale=3)
        store.record({"19": 0, "101": 100000}, self.start)
        store.record({"19": 0, "101": 100250}, self.start + timedelta(minutes=1))
        store.record({"19": 0, "101": 1000}, self.start + timedelta(minutes=2))
        store.record({"19": 0, "101": 1200}, self.start + timedelta(minutes=3))
        snapshot = store.snapshot(self.start + timedelta(minutes=3))
        self.assertAlmostEqual(snapshot["today_kwh"], .45)
        self.assertEqual(snapshot["total_kwh"], 1.2)
        self.assertEqual(snapshot["gaps"], 1)

    def test_reference_is_not_merged_with_local_readings(self):
        store = self.store()
        self.assertEqual(store.snapshot(self.start)["source"], "reference")
        store.record({"19": 0}, self.start)
        october = next(m for m in store.monthly(2026) if m["month"] == 10)
        september = next(m for m in store.monthly(2026) if m["month"] == 9)
        self.assertIsNone(october["kwh"])
        self.assertEqual(september["kwh"], 7.5)
        series = store.daily(2026, 10)["days"]
        self.assertIsNone(series[10]["kwh"])
        self.assertIsNone(series[11]["kwh"])

    def test_no_samples_today_is_not_zero_and_daily_retains_method(self):
        store = self.store()
        store.record({"19": 10000}, self.start)
        self.assertIsNone(store.snapshot(self.start)["today_kwh"])
        store.record({"19": 10000}, self.start + timedelta(minutes=1))
        series = store.daily(2026, 10)
        self.assertEqual(series["source"], "estimated")
        self.assertEqual(series["days"][11]["method"], "estimated")
        self.assertEqual(series["days"][11]["coverage_seconds"], 60)
        self.assertIsNone(store.snapshot(self.start + timedelta(days=1))["today_kwh"])

    def test_incremental_dp_is_never_treated_as_total(self):
        with self.assertRaises(ValueError):
            self.store(total_dp="17")
        store = self.store()
        store.record({"19": 0, "17": 1}, self.start)
        store.record({"19": 0, "17": 1}, self.start + timedelta(minutes=1))
        self.assertEqual(store.snapshot(self.start)["total_kwh"], 0)

    def test_invalid_power_does_not_create_history(self):
        store = self.store()
        for raw in (None, True, -10, float("nan")):
            self.assertFalse(store.record({"19": raw}, self.start))
        self.assertEqual(store.snapshot(self.start)["source"], "reference")

    def test_checkout_sem_arquivos_privados_inicia_com_historico_vazio(self):
        empty_root = Path(self.tmp.name)
        with (patch('energy_history.ROOT', empty_root),
              patch('energy_history.BASE', empty_root/'src'),
              patch('energy_history.CONFIG_DIR', empty_root/'config'),
              patch('energy_history.reference_data', wraps=READ_REFERENCE_DATA)):
            store = EnergyHistory(self.path)
            snapshot = store.snapshot(self.start)
            self.assertIsNone(store.total_dp)
            self.assertEqual(snapshot['source'], 'empty')
            self.assertIsNone(snapshot['today_kwh'])
            self.assertIsNone(snapshot['total_kwh'])
            self.assertTrue(all(month['kwh'] is None for month in store.monthly(2026)))


if __name__ == "__main__":
    unittest.main()
