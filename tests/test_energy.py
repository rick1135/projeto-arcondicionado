import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import Mock
from energy import EnergyClient


class EnergyTests(unittest.TestCase):
    def make(self):
        cloud = Mock()
        cloud.cloudrequest.side_effect = [
            {'success':True, 'result':{'total':'139.54'}},
            {'success':True, 'result':{'months':{'202610':'28.65'}}},
            {'success':True, 'result':{'days':{'20261011':'1.28'}}},
        ]
        return EnergyClient('unused.json', 'test-plug', cloud_factory=lambda:cloud), cloud

    def test_history_keeps_scaled_kwh_and_caches(self):
        client, cloud = self.make()
        result = client.history(2026,10,today=date(2026,10,11))
        self.assertEqual(result['total'],Decimal('139.54'))
        self.assertEqual(result['days']['20261011'],Decimal('1.28'))
        self.assertEqual(result['months']['202610'],Decimal('28.65'))
        self.assertIs(client.history(2026,10,today=date(2026,10,11)), result)
        self.assertEqual(cloud.cloudrequest.call_count,3)
        self.assertEqual(cloud.cloudrequest.call_args.kwargs['query']['end_day'],'20261011')

    def test_missing_day_is_not_invented_as_zero(self):
        values=EnergyClient.values({'success':True,'result':{'days':{'20261011':'0.00'}}},'days')
        self.assertNotIn('20261010',values)
        self.assertEqual(values['20261011'],0)

    def test_api_error_never_returns_zero_consumption(self):
        with self.assertRaises(RuntimeError):
            EnergyClient.values({'success':False,'code':1106,'msg':'private detail'},'days')

    def test_invalid_energy_is_rejected(self):
        for value in ['NaN','Infinity','-2',None]:
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                EnergyClient.values({'success':True,'result':{'total':value}},'total')

    def test_future_month_does_not_call_cloud(self):
        client, cloud = self.make()
        with self.assertRaises(ValueError):
            client.history(2026,11,today=date(2026,10,11))
        cloud.cloudrequest.assert_not_called()
