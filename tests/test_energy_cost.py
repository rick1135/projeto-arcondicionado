import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from decimal import Decimal
import unittest
from unittest.mock import Mock
from elgin_tray import TrayApp
from energy_cost import DEFAULT_TARIFF, monthly_cost, format_brl


class EnergyCostTests(unittest.TestCase):
    def test_tariff_and_monthly_amount(self):
        self.assertEqual(DEFAULT_TARIFF, Decimal('1.40'))
        self.assertEqual(monthly_cost(32.98), Decimal('46.17'))
        self.assertEqual(format_brl(monthly_cost(32.98)), 'R$ 46,17')
        self.assertEqual(format_brl(monthly_cost(50.40)), 'R$ 70,56')

    def test_zero_missing_and_invalid(self):
        self.assertEqual(format_brl(monthly_cost(0)), 'R$ 0,00')
        for value in (None, True, -1, 'NaN', 'Infinity', 'invalid'):
            self.assertEqual(format_brl(monthly_cost(value)), 'R$ --')

    def test_rounding_and_brazilian_format(self):
        self.assertEqual(monthly_cost('0.075', '1.40'), Decimal('0.11'))
        self.assertEqual(format_brl(monthly_cost(1000)), 'R$ 1.400,00')

    def test_interface_uses_selected_month_amount(self):
        app = TrayApp.__new__(TrayApp)
        app.closed, app.page = False, 'energy_month'
        app.energy_year, app.energy_month = 2026, 9
        app.energy_selected_day, app.energy_chart_start = 1, 0
        app.energy_months = Mock(return_value=[{'month': 9, 'kwh': 50.40}])
        app.energy_days = Mock(return_value={'source': 'cloud', 'days': [
            {'day': d, 'kwh': 0, 'date': f'2026-09-{d:02}'} for d in range(1, 31)]})
        app.canvas = Mock()
        app.energy_header = app.rounded = app.label = app.fit_label = app.metric_value = app.hit = Mock()
        app.draw_energy_month()
        self.assertTrue(any('R$ 70,56' in call.args for call in app.fit_label.call_args_list))


if __name__ == '__main__':
    unittest.main()
