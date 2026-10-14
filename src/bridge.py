"""Adaptador de consumo Tuya Cloud para a interface Tk, sem expor credenciais."""
from pathlib import Path

from energy import EnergyClient, EnergyError
from energy_history import MONTHS, local_now

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
DEFAULT_TINYTUYA = next((p for p in (ROOT / 'config' / 'tinytuya.json', ROOT / 'tinytuya.json', BASE / 'tinytuya.json') if p.is_file()), ROOT / 'config' / 'tinytuya.json')


class EnergyBridge:
    """Adaptador somente leitura compartilhado com o app Tk atual.

    Nunca usa o apiDeviceID do wizard como alvo: recebe o ID da tomada.
    Não retorna configuração/credenciais, apenas medições normalizadas.
    """
    def __init__(self, device_id, config_path=None, cache_path=None, cloud_factory=None):
        self.client = EnergyClient(config_path or DEFAULT_TINYTUYA, device_id,
                                   cloud_factory=cloud_factory, cache_path=cache_path)

    def get_energy_history(self, year=None, month=None, force=False):
        now = local_now()
        year = now.year if year is None else year
        month = now.month if month is None else month
        try:
            history = self.client.history(year, month, today=now.date(), force=force)
            return {'ok': True, **self.public(history)}
        except (EnergyError, ValueError) as exc:
            return {'ok': False, 'error': str(exc)}
        except Exception:
            return {'ok': False, 'error': 'Falha ao consultar a Tuya Cloud.'}

    @staticmethod
    def public(history):
        return {'total': float(history['total']),
                'months': {k: float(v) for k, v in history['months'].items()},
                'days': {k: float(v) for k, v in history['days'].items()},
                'year': history['year'], 'month': history['month'],
                'updated': history['updated'], 'stale': history.get('stale', False),
                'cache_warning': history.get('cache_warning', '')}

    def cached(self, year, month):
        try:
            result = self.client.cached(year, month, today=local_now().date())
            return self.public(result) if result else None
        except (OSError, ValueError):
            return None

    def snapshot(self):
        now = local_now()
        result = self.cached(now.year, now.month)
        if result is None:
            return None
        return {'today_kwh': result['days'].get(now.strftime('%Y%m%d')),
                'total_kwh': result['total'], 'current_month_kwh': result['months'].get(now.strftime('%Y%m')),
                'source': 'cloud', 'total_source': 'cloud', 'updated': result['updated'],
                'stale': result['stale'], 'years': list(range(2020, now.year+1))}

    def monthly(self, year):
        # Uma consulta de qualquer mês do ano já traz sua série mensal.
        now = local_now()
        candidates = range(min(12, now.month) if year == now.year else 12, 0, -1)
        cached_rows = [cached for m in candidates if (cached := self.cached(year, m))]
        result = max(cached_rows, key=lambda r: r['updated']) if cached_rows else None
        if not result:
            return None
        rows = []
        for month in range(now.month if year == now.year else 12, 0, -1):
            key = f'{year}{month:02}'
            rows.append({'month': month, 'name': MONTHS[month-1], 'kwh': result['months'].get(key),
                         'source': 'cloud', 'stale': result['stale']})
        return rows

    def daily(self, year, month):
        import calendar
        result = self.cached(year, month)
        if result is None:
            return None
        return {'source': 'cloud', 'stale': result['stale'], 'updated': result['updated'],
                'days': [{'day': d, 'date': f'{year}-{month:02}-{d:02}',
                          'kwh': result['days'].get(f'{year}{month:02}{d:02}')}
                         for d in range(1, calendar.monthrange(year, month)[1]+1)]}
