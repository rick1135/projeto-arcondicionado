"""API da janela local. Nunca retorna as chaves do devices.json ao JavaScript."""
import json
import os
import threading
from datetime import date
from pathlib import Path

from energy import EnergyClient, EnergyError
from energy_history import MONTHS, local_now

BASE = Path(__file__).resolve().parent
PREFS = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'ElginControl' / 'preferencias.json'
MODES = {'cool': 'cold', 'dry': 'wet', 'fan': 'wind', 'auto': 'auto'}
FANS = {'quiet': 'mute', 'low': 'low', 'med': 'middle', 'turbo': 'strong'}
FEATURES = {'eco': 11, 'sleep': 25, 'display': 36, 'swing': 31}


def load_devices(path):
    # O controlador do projeto de referência é opcional no app Tk atual.
    from controller import load_devices as load
    return load(path)


class EnergyBridge:
    """Adaptador somente leitura compartilhado com o app Tk atual.

    Nunca usa o apiDeviceID do wizard como alvo: recebe o ID da tomada.
    Não retorna configuração/credenciais, apenas medições normalizadas.
    """
    def __init__(self, device_id, config_path=None, cache_path=None, cloud_factory=None):
        self.client = EnergyClient(config_path or BASE / 'tinytuya.json', device_id,
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


class DeviceAPI:
    def __init__(self, demo=False, preferences=PREFS):
        from controller import Controller
        self.demo = demo
        self.preferences = Path(preferences)
        self.lock = threading.RLock()
        self.closed = False
        self.energy = None
        try:
            self.settings = json.loads(self.preferences.read_text(encoding='utf-8'))
            if not isinstance(self.settings, dict):
                self.settings = {}
        except (OSError, ValueError):
            self.settings = {}
        self.control = Controller(demo=demo)
        if not demo:
            self._configure(self.settings)

    def _configure(self, settings):
        path = Path(settings.get('devices_path') or BASE / 'devices.json').expanduser()
        if not path.is_file():
            path = Path.home() / 'elgin-controle' / 'devices.json'
        if not path.is_file():
            return
        try:
            self.control, _, _, _ = self._apply_devices(path, settings)
            self.settings['devices_path'] = str(path)
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def _apply_devices(self, path, settings):
        from controller import Controller
        records = load_devices(path)
        ac = next((r for r in records if r['id'] == settings.get('device_id')), None)
        if ac is None:
            ac = next((r for r in records if 'air' in r.get('name', '').lower()), records[0])
        plug = next((r for r in records if r['id'] == settings.get('plug_device_id')), None)
        if plug and plug['id'] == ac['id']:
            raise ValueError('O ar e a tomada precisam ser dispositivos diferentes.')
        config = ac.copy()
        # Campo vazio na interface significa descoberta LAN; não reutiliza o IP
        # antigo guardado no devices.json pelo wizard.
        ip = settings['ip'] if 'ip' in settings else ac.get('ip')
        config['ip'] = ip.strip() if isinstance(ip, str) and ip.strip() else 'Auto'
        config['version'] = float(ac.get('version') or 3.3)
        plug_config = plug.copy() if plug else None
        if plug_config:
            plug_config['version'] = float(settings.get('plug_version') or plug.get('version') or 3.5)
        return Controller(config, plug_config=plug_config), records, ac, plug

    def _ready(self):
        if self.closed:
            raise RuntimeError('A janela foi encerrada.')
        if not self.demo and not self.control.config:
            raise ValueError('Selecione um devices.json em Configurações.')

    def _reply(self, action):
        try:
            with self.lock:
                self._ready()
                action()
                result = self._status()
                result['command_ok'] = True
                return result
        except (ValueError, RuntimeError, OSError) as exc:
            return {'ok': False, 'error': str(exc)}
        except Exception:
            return {'ok': False, 'error': 'Falha de comunicação. Confira a rede, o IP e o arquivo de dispositivos.'}

    def _status(self):
        ac, plug, errors = {}, {}, []
        if self.demo:
            ac = self.control.status()
            plug = self.control.read_plug()['_plug_dps']
        else:
            if not self.control.config:
                return {'ok': False, 'error': 'Configure um devices.json para conectar os aparelhos.'}
            if self.control.plug_config:
                try:
                    plug = self.control.read_plug()['_plug_dps']
                except (RuntimeError, OSError, ValueError):
                    errors.append('Não foi possível ler a tomada.')
            if plug.get('1') is False:
                ac = {'_ac_available': False}
            else:
                try:
                    ac = self.control.status() if plug or not self.control.plug_config else self.control.check(self.control._device().status()).get('dps', {})
                except (RuntimeError, OSError, ValueError):
                    errors.append('O ar não respondeu pela rede local. Confira IP, chave local e protocolo em Configurações.')
        def measure(key, scale):
            raw = plug.get(key)
            return round(raw / scale, 3) if type(raw) in (int, float) else None
        return {
            'ok': not errors, 'error': ' '.join(errors) if errors else None,
            'ac': {
                'on': ac.get('1') if type(ac.get('1')) is bool else None,
                'available': ac.get('_ac_available') is not False and bool(ac),
                'room_temp': ac.get('3') if type(ac.get('3')) in (int, float) else None,
                'target_temp': ac.get('2') if type(ac.get('2')) is int else None,
                'mode': next((k for k, v in MODES.items() if ac.get('4') == v), None),
                'fan': next((k for k, v in FANS.items() if ac.get('5') == v), None),
                'features': {key: (ac.get(str(dp)) == 'same' if dp == 31 else ac.get(str(dp)) is True) if str(dp) in ac else None for key, dp in FEATURES.items()},
                'timers': {key: {'enabled': ac.get(str(dp)), 'duration': ac.get(str(dp+2))} for key, dp in [('ON', 101), ('OFF', 102)]},
            },
            'plug': {
                'on': plug.get('1') if type(plug.get('1')) is bool else None,
                'watts': measure('19', 10), 'amps': measure('18', 1000),
                'volts': measure('20', 10), 'countdown': plug.get('9'),
            },
        }

    def get_system_status(self):
        try:
            with self.lock:
                self._ready()
                return self._status()
        except (ValueError, RuntimeError) as exc:
            return {'ok': False, 'error': str(exc)}

    def toggle_ac_power(self):
        def action():
            status = self.control.status()
            current = status.get('1')
            if current is None and status.get('_ac_available') is not False:
                raise RuntimeError('Não foi possível confirmar o estado do ar.')
            self.control.set(1, current is not True)
        return self._reply(action)

    def set_ac_temperature(self, temp):
        def action():
            if type(temp) is not int or not 16 <= temp <= 31:
                raise ValueError('A temperatura deve ser um inteiro entre 16 e 31 °C.')
            self.control.set(2, temp)
        return self._reply(action)

    def set_ac_mode(self, mode):
        return self._reply(lambda: self.control.set(4, MODES[mode] if mode in MODES else mode))

    def set_ac_fan(self, speed):
        return self._reply(lambda: self.control.set(5, FANS[speed] if speed in FANS else speed))

    def toggle_ac_feature(self, feature_name):
        def action():
            if feature_name not in FEATURES:
                raise ValueError('Função desconhecida.')
            current = self.control.status()
            if current.get('_ac_available') is False:
                raise ValueError('Ligue a alimentação do ar primeiro.')
            dp = FEATURES[feature_name]
            if str(dp) not in current:
                raise RuntimeError('O ar não informou o estado desta função.')
            enabled = current[str(dp)] == 'same' if dp == 31 else current[str(dp)] is True
            self.control.set(dp, ('off' if enabled else 'same') if dp == 31 else not enabled)
        return self._reply(action)

    def toggle_plug_power(self):
        def action():
            if not self.demo and not self.control.plug_config:
                raise ValueError('Escolha uma tomada em Configurações.')
            current = self.control.read_plug()['_plug_dps']['1']
            result = self.control.set_plug_power(not current)
            self._plug_notice = result.get('_notice')
        self._plug_notice = None
        result = self._reply(action)
        if result.get('ok') and self._plug_notice:
            result['notice'] = self._plug_notice
        return result

    def set_plug_countdown(self, minutes):
        def action():
            if type(minutes) is not int or not 0 <= minutes <= 1440:
                raise ValueError('Use de 0 a 1440 minutos.')
            self.control.plug_countdown(minutes * 60)
        return self._reply(action)

    def set_ac_timer(self, kind, minutes):
        def action():
            if kind not in ('ON', 'OFF') or type(minutes) is not int or not 0 <= minutes <= 1439:
                raise ValueError('Temporizador inválido.')
            self.control.timer(kind, bool(minutes), minutes // 60, minutes % 60)
        return self._reply(action)

    def get_settings(self):
        with self.lock:
            path = self.settings.get('devices_path') or str(Path.home() / 'elgin-controle' / 'devices.json')
            try:
                records = load_devices(path)
            except (OSError, ValueError):
                records = []
            return {
                'devices_path': path, 'ip': self.settings.get('ip', ''),
                'cloud_path': self.settings.get('cloud_path') or '',
                'device_id': self.settings.get('device_id'), 'plug_device_id': self.settings.get('plug_device_id'),
                'plug_version': self.settings.get('plug_version') or '3.5',
                'devices': [{'id': r['id'], 'name': r.get('name') or 'Dispositivo'} for r in records],
            }

    def list_devices(self, path):
        try:
            records = load_devices(path)
            return {'ok': True, 'devices': [{'id': r['id'], 'name': r.get('name') or 'Dispositivo'} for r in records]}
        except (OSError, ValueError, TypeError):
            return {'ok': False, 'error': 'Não foi possível abrir devices.json. Confira o caminho e o conteúdo.'}

    def save_settings(self, device_json, ip, tinytuya_json, device_id=None, plug_device_id=None, plug_version='3.5'):
        try:
            with self.lock:
                if not isinstance(device_json, str) or not device_json.strip():
                    raise ValueError('Escolha o devices.json.')
                path = Path(device_json).expanduser().resolve(strict=True)
                if path.name.lower() != 'devices.json':
                    raise ValueError('Selecione o arquivo devices.json gerado pelo TinyTuya.')
                if not isinstance(ip, str) or len(ip) > 255:
                    raise ValueError('IP inválido.')
                if tinytuya_json and (not isinstance(tinytuya_json, str) or not Path(tinytuya_json).is_file()):
                    raise ValueError('O tinytuya.json não foi encontrado.')
                if plug_version not in ('3.1', '3.2', '3.3', '3.4', '3.5'):
                    raise ValueError('Protocolo da tomada inválido.')
                settings = {**self.settings, 'devices_path': str(path), 'ip': ip.strip(),
                            'cloud_path': tinytuya_json or '', 'plug_version': plug_version,
                            'device_id': device_id, 'plug_device_id': plug_device_id}
                control, _, ac, plug = self._apply_devices(path, settings)
                settings.update(device_id=ac['id'], plug_device_id=plug['id'] if plug else None)
                if not self.demo:
                    self.preferences.parent.mkdir(parents=True, exist_ok=True)
                    temporary = self.preferences.with_suffix('.tmp')
                    temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')
                    temporary.replace(self.preferences)
                self.settings, self.control, self.energy = settings, control, None
                return {'ok': True, 'settings': self.get_settings()}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return {'ok': False, 'error': str(exc) if isinstance(exc, ValueError) else 'Não foi possível salvar as configurações.'}

    def get_energy_history(self, year=None, month=None):
        try:
            with self.lock:
                now = date.today()
                year, month = year or now.year, month or now.month
                if not self.control.plug_config:
                    raise ValueError('Selecione a tomada em Configurações.')
                if not self.settings.get('cloud_path'):
                    raise ValueError('Selecione o tinytuya.json em Configurações.')
                key = (self.settings['cloud_path'], self.control.plug_config['id'])
                if self.energy is None or self._energy_key != key:
                    self.energy = EnergyClient(*key)
                    self._energy_key = key
                client = self.energy
            # Consulta cloud fora do lock: sensores e comandos LAN continuam responsivos.
            history = client.history(int(year), int(month))
            return {'ok': True, 'total': float(history['total']), 'months': {k: float(v) for k, v in history['months'].items()}, 'days': {k: float(v) for k, v in history['days'].items()}, 'year': history['year'], 'month': history['month']}
        except (OSError, ValueError, RuntimeError) as exc:
            return {'ok': False, 'error': str(exc)}
        except Exception:
            return {'ok': False, 'error': 'Falha ao consultar a nuvem Tuya.'}

    def _shutdown(self):
        with self.lock:
            self.closed = True
            self.energy = None
