"""Cloud sem rede e sem credenciais reais: assinatura, dados e integração Tk."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from contextlib import closing
from datetime import date, datetime
from decimal import Decimal
import io
import json
import logging
from pathlib import Path
import queue
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from bridge import EnergyBridge
from energy import EnergyClient, EnergyError, safe_cloud
from energy_history import LOCAL_TZ
from elgin_tray import TrayApp

NOW = datetime(2026, 10, 13, 12, tzinfo=LOCAL_TZ)


class FakeCloud:
    def __init__(self):
        self.calls = []
        self.fail = False

    def cloudrequest(self, url, action, query):
        self.calls.append((url, action, query))
        if self.fail:
            return {'success': False, 'code': 28841101, 'msg': 'NEVER_EXPORT_SECRET'}
        name = url.rsplit('/', 1)[-1]
        values = {'total': '139.54', 'months': {'202610': '28.65', '202609': '50.40'},
                  'days': {'20261011': '1.28', '20261013': '0.00'}}
        return {'success': True, 'result': {name: values[name]}}


class CloudTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.fake = FakeCloud()
        self.cache_path = Path(self.temp.name) / 'history.sqlite3'
        self.client = EnergyClient(Path(self.temp.name) / 'unused.json', 'plug-test',
                                   cloud_factory=lambda: self.fake, cache_path=self.cache_path)

    def test_endpoints_periods_and_units(self):
        data = self.client.history(2026, 10, today=NOW.date())
        self.assertEqual(data['total'], Decimal('139.54'))
        self.assertEqual(data['days']['20261011'], Decimal('1.28'))
        self.assertEqual([u for u, _, _ in self.fake.calls], [
            '/v1.0/devices/plug-test/statistics/' + k for k in ('total', 'months', 'days')])
        self.assertTrue(all(action == 'GET' and q['code'] == 'add_ele' for _, action, q in self.fake.calls))
        self.assertEqual(self.fake.calls[1][2]['end_month'], '202610')
        self.assertEqual(self.fake.calls[2][2]['end_day'], '20261013')
        self.assertEqual(self.fake.calls[2][2]['stat_type'], 'sum')

    def test_cache_force_and_restart(self):
        self.client.history(2026, 10, today=NOW.date())
        self.client.history(2026, 10, today=NOW.date())
        self.assertEqual(len(self.fake.calls), 3)
        self.client.history(2026, 10, today=NOW.date(), force=True)
        self.assertEqual(len(self.fake.calls), 6)
        restored = EnergyClient('missing', 'plug-test', cache_path=self.cache_path,
                                cloud_factory=lambda: self.fail('Cache deveria evitar rede'))
        self.assertEqual(restored.history(2026, 10, today=NOW.date())['total'], Decimal('139.54'))
        other = EnergyClient('missing', 'other-plug', cache_path=self.cache_path)
        self.assertIsNone(other.cached(2026, 10, today=NOW.date()))
        with closing(sqlite3.connect(self.cache_path)) as db:
            payload = db.execute('SELECT payload FROM cloud_energy_cache').fetchone()[0]
        for forbidden in ('apiKey', 'apiSecret', 'access_token', 'NEVER_EXPORT_SECRET'):
            self.assertNotIn(forbidden, payload)

    def test_errors_are_sanitized_and_keep_last_good_data(self):
        self.client.history(2026, 10, today=NOW.date())
        self.fake.fail = True
        with self.assertRaises(EnergyError) as error:
            self.client.history(2026, 10, today=NOW.date(), force=True)
        self.assertIn('28841101', str(error.exception))
        self.assertNotIn('NEVER_EXPORT_SECRET', str(error.exception))
        self.assertEqual(self.client.cached(2026, 10, today=NOW.date())['total'], Decimal('139.54'))
        self.assertTrue(self.client.cached(2026, 10, today=date(2026, 10, 14))['stale'])

    def test_invalid_device_dates_and_values(self):
        for year, month in ((2027, 1), (2026, 11), (2026, 0), (True, 1), (2026, True)):
            with self.assertRaises(ValueError):
                self.client.history(year, month, today=NOW.date())
        self.assertFalse(self.fake.calls)
        with self.assertRaises(ValueError):
            EnergyClient('missing', 'plug/other')
        for value in ('NaN', 'Infinity', '-1', None, True, {}, 'secret'):
            with self.assertRaises(EnergyError):
                EnergyClient.values({'success': True, 'result': {'total': value}}, 'total')
        with self.assertRaises(EnergyError) as error:
            EnergyClient.values({'success': False, 'code': 'NEVER_EXPORT_SECRET'}, 'total')
        self.assertNotIn('NEVER_EXPORT_SECRET', str(error.exception))

    def test_previous_year_and_leap_month_boundaries(self):
        self.fake.cloudrequest = Mock(side_effect=[
            {'success': True, 'result': {'total': '2'}},
            {'success': True, 'result': {'months': {'202402': '2'}}},
            {'success': True, 'result': {'days': {'20240229': '2'}}}])
        self.client.history(2024, 2, today=NOW.date())
        calls = self.fake.cloudrequest.call_args_list
        self.assertEqual(calls[1].kwargs['query']['end_month'], '202412')
        self.assertEqual(calls[2].kwargs['query']['end_day'], '20240229')

    def test_bad_period_and_empty_response_not_fabricated(self):
        self.fake.cloudrequest = Mock(side_effect=[
            {'success': True, 'result': {'total': '2'}},
            {'success': True, 'result': {'months': {'202609': '2'}}},
            {'success': True, 'result': {'days': {'20260901': '2'}}}])
        with self.assertRaises(EnergyError):
            self.client.history(2026, 10, today=NOW.date())
        self.assertIsNone(self.client.cached(2026, 10, today=NOW.date()))
        self.fake.cloudrequest = Mock(side_effect=[
            {'success': True, 'result': {'total': '0'}},
            {'success': True, 'result': {'months': {}}},
            {'success': True, 'result': {'days': {}}}])
        data = self.client.history(2026, 10, today=NOW.date())
        self.assertEqual(data['days'], {})

    def test_missing_credentials_safe_and_never_required_for_cache(self):
        client = EnergyClient(Path(self.temp.name) / 'missing.json', 'plug-test')
        with self.assertRaises(EnergyError):
            client.history(2026, 10, today=NOW.date())

    def test_private_transport_bounded_and_no_debug_even_on_errors(self):
        token = {'success': True, 'result': {'access_token': 'SYNTHETIC_TOKEN'}}
        response = Mock(status_code=200, text=json.dumps(token), content=json.dumps(token).encode())
        stream, handler = io.StringIO(), logging.StreamHandler()
        handler.setStream(stream)
        logger = logging.getLogger()
        old_level = logger.level
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        self.addCleanup(logger.removeHandler, handler)
        self.addCleanup(logger.setLevel, old_level)
        with patch('requests.get', return_value=response) as get:
            cloud = safe_cloud({'apiRegion': 'us', 'apiKey': 'SYNTHETIC_KEY', 'apiSecret': 'SYNTHETIC_SECRET'})
            self.assertEqual(get.call_args.kwargs['timeout'], (5, 10))
            response.text, response.content = 'invalid SYNTHETIC_TOKEN', b'invalid SYNTHETIC_TOKEN'
            cloud.cloudrequest('/v1.0/devices/plug-test/statistics/total', query={'code': 'add_ele'})
        for secret in ('SYNTHETIC_TOKEN', 'SYNTHETIC_KEY', 'SYNTHETIC_SECRET'):
            self.assertNotIn(secret, stream.getvalue())

    @patch('bridge.local_now', return_value=NOW)
    def test_bridge_and_ui_prefer_cloud_without_adding_lan_or_references(self, _now):
        bridge = EnergyBridge('plug-test', cache_path=self.cache_path, cloud_factory=lambda: self.fake)
        self.assertTrue(bridge.get_energy_history()['ok'])
        self.assertEqual(bridge.snapshot()['today_kwh'], 0)
        self.assertEqual(bridge.snapshot()['current_month_kwh'], 28.65)
        self.assertEqual(bridge.monthly(2026)[0]['source'], 'cloud')
        daily = bridge.daily(2026, 10)
        self.assertEqual(daily['days'][10]['kwh'], 1.28)
        self.assertIsNone(daily['days'][11]['kwh'])
        app = TrayApp.__new__(TrayApp)
        app.cloud_energy = bridge
        app.energy_store = Mock()
        app.energy_store.snapshot.return_value = {'source': 'estimated', 'today_kwh': 1000, 'recent': []}
        app.energy_year, app.energy_month = 2026, 10
        with patch('elgin_tray.local_now', return_value=NOW):
            self.assertEqual(app.energy_snapshot()['total_kwh'], 139.54)
            self.assertEqual(app.energy_snapshot()['today_kwh'], 0)
            self.assertEqual(app.energy_months(2026)[0]['kwh'], 28.65)
            self.assertEqual(app.energy_days()['source'], 'cloud')
            app.cloud_failures = {(2026, 10): 'Consulta indisponível'}
            self.assertTrue(app.energy_snapshot()['stale'])
            self.assertTrue(app.energy_days()['stale'])
            self.assertTrue(app.energy_months(2026)[0]['stale'])
            app.energy_month = 9
            # Nunca preenche um mês Cloud pendente com barras locais/de referência.
            pending = app.energy_days()
            self.assertEqual(pending['source'], 'cloud_pending')
            self.assertTrue(all(day['kwh'] is None for day in pending['days']))
            app.energy_store.daily.assert_not_called()

    @patch('elgin_tray.local_now', return_value=NOW)
    def test_queue_handles_navigation_and_failure_without_blocking_lan(self, _now):
        app = TrayApp.__new__(TrayApp)
        app.closed = False
        app.cloud_energy = Mock()
        app.cloud_busy = False
        app.cloud_error = ''
        app.cloud_attempts, app.cloud_failures = {}, {}
        app.cloud_results = queue.Queue()
        app.page, app.energy_year, app.energy_month = 'energy_month', 2026, 9
        app.draw = Mock()
        app.cloud_energy.cached.return_value = {'stale': False}
        app.cloud_energy.get_energy_history.return_value = {'ok': True}
        with patch('elgin_tray.threading.Thread') as thread:
            thread.return_value.start.side_effect = lambda: thread.call_args.kwargs['target']()
            app.submit_energy(force=True)
            app.cloud_energy.get_energy_history.assert_called_once_with(2026, 9, force=True)
            app.process_cloud_results()
            self.assertFalse(app.cloud_busy)
        app.cloud_results.put(((2026, 9), {'ok': False, 'error': 'Tuya recusou a consulta.'}))
        app.process_cloud_results()
        self.assertIn((2026, 9), app.cloud_failures)


if __name__ == '__main__':
    unittest.main()
