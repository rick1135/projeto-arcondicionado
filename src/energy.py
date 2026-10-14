"""Histórico Tuya; retorna kWh já escalados, sem somar leituras LAN do DP 17."""
import json
import calendar
from contextlib import closing
import re
import sqlite3
import threading
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import FunctionType


class EnergyError(RuntimeError):
    """Mensagem pública controlada, sem resposta bruta, token ou credenciais."""


def safe_cloud(config):
    """Reusa assinatura/token TinyTuya com transporte limitado e sem debug.

    TinyTuya 1.19 não expõe timeout Cloud e seu debug registra headers.
    Isolamos as dependências dos métodos numa subclasse, sem monkey-patch
    global de requests/logging (o controle LAN continua independente).
    """
    import requests
    import tinytuya

    class Transport:
        Request = requests.Request

        @staticmethod
        def get(*args, **kwargs):
            return requests.get(*args, timeout=(5, 10), **kwargs)

        @staticmethod
        def request(*args, **kwargs):
            return requests.request(*args, timeout=(5, 10), **kwargs)

    class SilentLog:
        def debug(self, *args, **kwargs):
            pass

    def quiet_error(number=None, payload=None):
        return {'Err': str(number), 'Error': 'Falha na Tuya Cloud'}

    methods = {}
    for name, method in vars(tinytuya.Cloud).items():
        if isinstance(method, FunctionType):
            isolated = dict(method.__globals__, requests=Transport, log=SilentLog(), error_json=quiet_error)
            methods[name] = FunctionType(method.__code__, isolated, name,
                                         method.__defaults__, method.__closure__)
            methods[name].__kwdefaults__ = method.__kwdefaults__
    secure_type = type("PrivateEnergyCloud", (tinytuya.Cloud,), methods)
    cloud = secure_type(apiRegion=config['apiRegion'], apiKey=config['apiKey'], apiSecret=config['apiSecret'])
    if not cloud.token:
        raise EnergyError('Não foi possível autenticar na Tuya Cloud. Confira conexão, região e credenciais.')
    return cloud


class EnergyClient:
    def __init__(self, config_path, device_id, cloud_factory=None, cache_path=None):
        self.config_path = Path(config_path)
        self.device_id = device_id
        self.cloud_factory = cloud_factory
        self.cache = {}
        if not isinstance(device_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', device_id):
            raise ValueError('Device ID da tomada inválido.')
        self.cache_path = Path(cache_path) if cache_path else None
        self.lock = threading.RLock()
        self.request_lock = threading.Lock()
        self.cloud = None
        if self.cache_path:
            with closing(self._connect()) as db, db:
                db.execute('''CREATE TABLE IF NOT EXISTS cloud_energy_cache (
                    device_id TEXT, year INTEGER, month INTEGER, payload TEXT NOT NULL,
                    PRIMARY KEY(device_id, year, month))''')

    def _connect(self):
        return sqlite3.connect(self.cache_path, timeout=5)

    @staticmethod
    def period(year, month, today):
        if type(year) is not int or type(month) is not int or not 2000 <= year <= today.year:
            raise ValueError('Ano ou mês inválido.')
        try:
            first = date(year, month, 1)
        except ValueError:
            raise ValueError('Ano ou mês inválido.') from None
        if first > today:
            raise ValueError('Selecione um mês até a data atual.')
        return first

    @staticmethod
    def values(response, key):
        if not isinstance(response, dict) or response.get('success') is not True:
            raw_code = response.get('code', response.get('Err', '?')) if isinstance(response, dict) else '?'
            code = str(raw_code) if re.fullmatch(r'\d{1,10}', str(raw_code)) else '?'
            raise EnergyError(f'Tuya recusou a consulta (código {code}). Confira região, permissões de estatísticas e IoT Core.')
        result = response.get('result')
        raw = result.get(key) if isinstance(result, dict) else None
        if key == 'total':
            raw = {'total': raw}
        if not isinstance(raw, dict):
            raise EnergyError('A Tuya retornou um histórico em formato inesperado.')
        values = {}
        for period, value in raw.items():
            try:
                if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
                    raise InvalidOperation
                number = Decimal(str(value))
                if not number.is_finite() or not 0 <= number <= Decimal('1000000000000'):
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                raise EnergyError('O histórico contém uma medição inválida.') from None
            values[str(period)] = number
        return values

    def _load_cloud(self):
        if self.cloud_factory:
            return self.cloud_factory()
        try:
            config = json.loads(self.config_path.read_text(encoding='utf-8-sig'))
            if not isinstance(config, dict) or not all(isinstance(config.get(k), str) and config[k].strip()
                    for k in ('apiRegion', 'apiKey', 'apiSecret')):
                raise ValueError
            if config['apiRegion'] not in ('us', 'az', 'us-e', 'ue', 'eu', 'eu-w', 'we', 'cn', 'in', 'sg'):
                raise ValueError
        except (OSError, ValueError, TypeError):
            raise EnergyError('Verifique o tinytuya.json local: credenciais Cloud e região obrigatórias.') from None
        try:
            return safe_cloud(config)
        except Exception:
            raise EnergyError('Não foi possível autenticar na Tuya Cloud. Confira conexão, região e credenciais.') from None

    @staticmethod
    def _period_values(values, key, year, month, today):
        filtered = {}
        for period, value in values.items():
            pattern = r'\d{6}' if key == 'months' else r'\d{8}'
            if not re.fullmatch(pattern, period):
                raise EnergyError('A Tuya retornou datas de histórico inválidas.')
            try:
                stamp = date(int(period[:4]), int(period[4:6]), 1 if key == 'months' else int(period[6:]))
            except ValueError:
                raise EnergyError('A Tuya retornou datas de histórico inválidas.') from None
            if stamp.year != year or stamp > today or (key == 'days' and stamp.month != month):
                raise EnergyError('A Tuya retornou dados fora do período solicitado.')
            filtered[period] = value
        return filtered

    def cached(self, year, month, today=None):
        today = today or date.today()
        self.period(year, month, today)
        key = (year, month)
        with self.lock:
            result = self.cache.get(key)
        if result is None and self.cache_path:
            try:
                with closing(self._connect()) as db:
                    row = db.execute('SELECT payload FROM cloud_energy_cache WHERE device_id=? AND year=? AND month=?',
                                     (self.device_id, year, month)).fetchone()
                if row:
                    payload = json.loads(row[0])
                    result = {'total': self.values({'success': True, 'result': {'total': payload['total']}}, 'total')['total'],
                              'year': year, 'month': month, 'updated': float(payload['updated']),
                              'as_of': date.fromisoformat(payload['as_of']).isoformat()}
                    for name in ('months', 'days'):
                        result[name] = self._period_values(self.values({'success': True, 'result': {name: payload[name]}}, name), name, year, month, today)
                    with self.lock:
                        self.cache[key] = result
            except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, EnergyError):
                return None
        if result is None:
            return None
        # Nunca expõe o dicionário mutável interno a consumidores concorrentes.
        return {**result, 'months': dict(result['months']), 'days': dict(result['days']),
                'stale': time.time()-result['updated'] >= 900 or result['as_of'] != today.isoformat()}

    def _save(self, result):
        if self.cache_path:
            # Apenas medições/tempo: nenhuma configuração, token ou resposta bruta.
            payload = {k: result[k] for k in ('year', 'month', 'updated', 'as_of')}
            payload.update(total=str(result['total']), months={k: str(v) for k, v in result['months'].items()},
                           days={k: str(v) for k, v in result['days'].items()})
            try:
                with closing(self._connect()) as db, db:
                    db.execute('INSERT OR REPLACE INTO cloud_energy_cache VALUES (?,?,?,?)',
                               (self.device_id, result['year'], result['month'], json.dumps(payload)))
            except (OSError, sqlite3.Error):
                # Consulta continua disponível na sessão mesmo se cache não puder ser salvo.
                result['cache_warning'] = 'Histórico Cloud não salvo: confira a permissão da pasta.'
        with self.lock:
            self.cache[(result['year'], result['month'])] = result

    def history(self, year, month, today=None, force=False):
        today = today or date.today()
        first = self.period(year, month, today)
        with self.request_lock:
            cached = self.cached(year, month, today)
            if cached and not force and not cached['stale']:
                return cached
            return self._fetch(year, month, first, today)

    def _fetch(self, year, month, first, today):
        last = min(date(year, month, calendar.monthrange(year, month)[1]), today)
        base = f'/v1.0/devices/{self.device_id}/statistics/'
        try:
            if self.cloud is None:
                self.cloud = self._load_cloud()
            cloud = self.cloud
            total = self.values(cloud.cloudrequest(base+'total', action='GET', query={'code':'add_ele'}), 'total')['total']
            months = self.values(cloud.cloudrequest(base+'months', action='GET', query={'code':'add_ele', 'stat_type':'sum', 'start_month':f'{year}01', 'end_month':f'{year}{today.month if year == today.year else 12:02d}'}), 'months')
            days = self.values(cloud.cloudrequest(base+'days', action='GET', query={'code':'add_ele', 'start_day':first.strftime('%Y%m%d'), 'end_day':last.strftime('%Y%m%d'), 'stat_type':'sum'}), 'days')
            months = self._period_values(months, 'months', year, month, today)
            days = self._period_values(days, 'days', year, month, today)
        except EnergyError:
            self.cloud = None
            raise
        except Exception:
            self.cloud = None
            raise EnergyError('Falha de conexão com a Tuya Cloud. Tente atualizar novamente.') from None
        result = {'total':total, 'months':months, 'days':days, 'year':year, 'month':month,
                  'updated':time.time(), 'as_of': today.isoformat(), 'stale': False}
        self._save(result)
        return result


def main():
    """Diagnóstico somente leitura: imprime medições, nunca credenciais."""
    import argparse
    from energy_history import local_now
    parser = argparse.ArgumentParser(description='Consultar consumo EKAZA na Tuya Cloud (kWh).')
    parser.add_argument('--year', type=int)
    parser.add_argument('--month', type=int)
    args = parser.parse_args()
    base, now = Path(__file__).resolve().parent, local_now()
    root = base.parent
    plug_file = next((p for p in (root / 'config' / 'plug_config.json', root / 'plug_config.json', base / 'plug_config.json') if p.is_file()), root / 'config' / 'plug_config.json')
    tuya_file = next((p for p in (root / 'config' / 'tinytuya.json', root / 'tinytuya.json', base / 'tinytuya.json') if p.is_file()), root / 'config' / 'tinytuya.json')
    db_file = root / 'data' / 'energy_history.sqlite3' if (root / 'data').is_dir() else root / 'energy_history.sqlite3'
    try:
        config = json.loads(plug_file.read_text(encoding='utf-8-sig'))
        device_id = config.get('device_id') if isinstance(config, dict) else None
    except (OSError, ValueError):
        print('Não foi possível ler a configuração da tomada.')
        return 1
    try:
        client = EnergyClient(tuya_file, device_id, cache_path=db_file)
        data = client.history(args.year if args.year is not None else now.year,
                              args.month if args.month is not None else now.month, today=now.date(), force=True)
        # Contrato público explícito: não imprime a resposta HTTP nem o objeto Cloud.
        print(json.dumps({'ok': True, 'total_kwh': str(data['total']),
                          'months_kwh': {k: str(v) for k, v in data['months'].items()},
                          'days_kwh': {k: str(v) for k, v in data['days'].items()},
                          'year': data['year'], 'month': data['month']}, ensure_ascii=False, indent=2))
        return 0
    except (EnergyError, ValueError) as exc:
        print(str(exc))
        return 1
    except Exception:
        print('Falha ao consultar a Tuya Cloud; confira conexão e permissões da pasta.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
