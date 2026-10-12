"""Histórico Tuya; retorna kWh já escalados, sem somar leituras LAN do DP 17."""
import json
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path


class EnergyClient:
    def __init__(self, config_path, device_id, cloud_factory=None):
        self.config_path = Path(config_path)
        self.device_id = device_id
        self.cloud_factory = cloud_factory
        self.cache = {}

    @staticmethod
    def values(response, key):
        if not isinstance(response, dict) or response.get('success') is not True:
            code = response.get('code', response.get('Err', '?')) if isinstance(response, dict) else '?'
            raise RuntimeError(f'Consulta de consumo recusada pela Tuya (código {code}). Confira as permissões Beta APIs e a validade do IoT Core.')
        raw = response.get('result', {}).get(key)
        if key == 'total':
            raw = {'total': raw}
        if not isinstance(raw, dict):
            raise RuntimeError('A Tuya retornou um histórico em formato inesperado.')
        values = {}
        for period, value in raw.items():
            try:
                number = Decimal(str(value))
                if not number.is_finite() or number < 0:
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                raise RuntimeError('O histórico contém uma medição inválida.') from None
            values[str(period)] = number
        return values

    def history(self, year, month, today=None, force=False):
        today = today or date.today()
        first = date(year, month, 1)
        if first > today:
            raise ValueError('Selecione um mês até a data atual.')
        cache_key = (year, month)
        cached = self.cache.get(cache_key)
        if cached and not force and time.monotonic() - cached[0] < 900:
            return cached[1]
        if self.cloud_factory:
            cloud = self.cloud_factory()
        else:
            import tinytuya
            try:
                config = json.loads(self.config_path.read_text(encoding='utf-8-sig'))
                cloud = tinytuya.Cloud(apiRegion=config['apiRegion'], apiKey=config['apiKey'], apiSecret=config['apiSecret'])
            except (OSError, ValueError, KeyError, TypeError):
                raise ValueError('Selecione o tinytuya.json criado pelo wizard, que contém as credenciais cloud.') from None
        import calendar
        last = min(date(year, month, calendar.monthrange(year, month)[1]), today)
        base = f'/v1.0/devices/{self.device_id}/statistics/'
        total = self.values(cloud.cloudrequest(base+'total', action='GET', query={'code':'add_ele'}), 'total')['total']
        months = self.values(cloud.cloudrequest(base+'months', action='GET', query={'code':'add_ele', 'start_month':f'{year}01', 'end_month':f'{year}{min(12, today.month) if year == today.year else 12:02d}'}), 'months')
        days = self.values(cloud.cloudrequest(base+'days', action='GET', query={'code':'add_ele', 'start_day':first.strftime('%Y%m%d'), 'end_day':last.strftime('%Y%m%d'), 'stat_type':'sum'}), 'days')
        result = {'total':total, 'months':months, 'days':days, 'year':year, 'month':month, 'updated':time.time()}
        self.cache[cache_key] = (time.monotonic(), result)
        return result
