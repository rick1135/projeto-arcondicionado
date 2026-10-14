"""Estimativa simples: consumo registrado em kWh × tarifa informada."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from pathlib import Path

DEFAULT_TARIFF = Decimal('1.40')


def load_tariff():
    try:
        base = Path(__file__).resolve().parent
        for candidate in (base.parent / 'config' / 'energy_config.json', base.parent / 'energy_config.json', base / 'energy_config.json'):
            if candidate.is_file():
                config = json.loads(candidate.read_text(encoding='utf-8-sig'))
                rate = Decimal(str(config.get('price_per_kwh_brl', '1.40')))
                return rate if rate.is_finite() and rate >= 0 else DEFAULT_TARIFF
        return DEFAULT_TARIFF
    except (OSError, ValueError, TypeError, AttributeError, InvalidOperation):
        return DEFAULT_TARIFF


def monthly_cost(kwh, tariff=DEFAULT_TARIFF):
    if kwh is None or isinstance(kwh, bool):
        return None
    try:
        value, rate = Decimal(str(kwh)), Decimal(str(tariff))
        if not value.is_finite() or not rate.is_finite() or value < 0 or rate < 0:
            return None
        return (value * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return None


def format_brl(value):
    if value is None:
        return 'R$ --'
    number = f'{value:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')
    return 'R$ ' + number
