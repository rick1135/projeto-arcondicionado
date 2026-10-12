"""Controle LAN: nenhum acesso à API cloud; credenciais ficam no devices.json."""
import json
import time
from pathlib import Path

MODES = {'Automático': 'auto', 'Refrigerar': 'cold', 'Ventilar': 'wind', 'Desumidificar': 'wet'}
FANS = {'Automática': 'auto', 'Baixa': 'low', 'Média': 'middle', 'Alta': 'high', 'Silenciosa': 'mute', 'Turbo': 'strong'}
BOOL_FIELDS = {1, 11, 25, 36}
DEMO_STATE = {'1': True, '2': 24, '3': 26, '4': 'cold', '5': 'auto', '11': False, '25': False, '31': 'off', '36': True, '101': False, '102': False, '103': '0000', '104': '0000'}


def load_devices(path):
    records = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(records, list):
        raise ValueError('O devices.json deve conter uma lista de dispositivos.')
    valid = [r for r in records if isinstance(r, dict) and r.get('id') and r.get('key')]
    if not valid:
        raise ValueError('Nenhum dispositivo com ID e chave foi encontrado.')
    return valid


def encode_time(hours, minutes):
    h, m = int(hours), int(minutes)
    if not 0 <= h <= 23 or not 0 <= m <= 59 or h + m == 0:
        raise ValueError('Informe entre 00h01 e 23h59. Respeite também o limite do app original.')
    return f'{h:02d}{m:02d}'


class Controller:
    def __init__(self, config=None, demo=False, plug_config=None):
        self.config = config
        self.plug_config = plug_config
        self.demo = demo
        self.state = DEMO_STATE.copy() if demo else {}
        self.plug_state = {'1': True, '9': 0, '18': 913, '19': 356, '20': 1226} if demo else {}

    def _device(self):
        return self._make_device(self.config)

    def _plug_device(self):
        return self._make_device(self.plug_config)

    def read_air_status(self):
        """Lê o ar; se o IP salvo mudou, tenta descobri-lo pela LAN uma vez."""
        try:
            response = self.check(self._device().status())
            if not isinstance(response.get('dps'), dict):
                raise RuntimeError('O ar não retornou o estado DPS.')
            return response
        except (RuntimeError, OSError):
            if not self.config or self.config.get('ip') in (None, '', 'Auto'):
                raise
            fallback = dict(self.config, ip='Auto')
            device = self._make_device(fallback)
            response = self.check(device.status())
            if not isinstance(response.get('dps'), dict):
                raise RuntimeError('O ar não retornou o estado DPS.')
            self.config['ip'] = getattr(device, 'address', None) or 'Auto'
            return response

    def _make_device(self, config):
        import tinytuya
        if not config:
            raise ValueError('Selecione o devices.json e um dispositivo.')
        c = config
        d = tinytuya.Device(c['id'], c.get('ip') or 'Auto', c['key'], version=float(c.get('version') or 3.3))
        d.set_socketTimeout(4)
        d.set_socketRetryLimit(1)
        return d

    @staticmethod
    def check(response):
        if not isinstance(response, dict) or response.get('Error') or response.get('Err'):
            # Não reproduz respostas cruas, que podem conter dados de configuração.
            raise RuntimeError('Sem confirmação do aparelho. Confira IP, chave, rede e feche o Smart Life.')
        return response

    def plug_status(self):
        if not self.plug_config:
            return None
        if self.config and self.config['id'] == self.plug_config['id']:
            raise ValueError('Ar e tomada devem ser dispositivos diferentes.')
        response = self.check(self._plug_device().status())
        value = response.get('dps', {}).get('1')
        if type(value) is not bool:
            raise RuntimeError('A tomada não retornou o estado do relé DPS 1.')
        self.plug_state = response['dps'].copy()
        return value

    def read_plug(self):
        if not self.demo:
            if not self.plug_config:
                raise ValueError('Selecione a tomada na área Conexão.')
            self.plug_status()
        return {'_plug_only': True, '_plug_dps': self.plug_state.copy()}

    def set_plug_power(self, enabled):
        if type(enabled) is not bool:
            raise ValueError('Estado da tomada inválido.')
        if self.demo:
            self.plug_state['1'] = enabled
        else:
            current = self.read_plug()['_plug_dps']
            notice = None
            if not enabled and current['1']:
                # É um corte manual de energia. Tenta desligar o ar primeiro, mas não
                # abandona um comando explícito da tomada se o ar estiver sem resposta.
                try:
                    air = self.check(self._device().status()).get('dps', {})
                    if type(air.get('1')) is not bool:
                        raise RuntimeError('O ar não confirmou seu estado.')
                    if air['1']:
                        self.check(self._device().set_value(1, False))
                        if self.check(self._device().status()).get('dps', {}).get('1') is not False:
                            raise RuntimeError('O ar não confirmou que desligou.')
                except (RuntimeError, OSError):
                    notice = 'A tomada foi desligada, mas o ar não confirmou o desligamento antes do corte.'
            self.check(self._plug_device().set_value(1, enabled))
        # Alguns relés respondem à escrita antes de atualizar o estado de leitura.
        # Confirma algumas vezes para não informar sucesso prematuramente.
        for attempt in range(3):
            result = self.read_plug()
            if result['_plug_dps']['1'] is enabled:
                if not self.demo and notice:
                    result['_notice'] = notice
                return result
            if attempt < 2:
                time.sleep(0.4)
        raise RuntimeError('A tomada não confirmou a mudança do relé.')

    def plug_countdown(self, seconds):
        if type(seconds) is not int or not 0 <= seconds <= 86400:
            raise ValueError('Informe de 0 a 86400 segundos (máximo 24 horas).')
        self.read_plug()
        if self.demo:
            self.plug_state['9'] = seconds
        else:
            self.check(self._plug_device().set_value(9, seconds))
        result = self.read_plug()
        value = result['_plug_dps'].get('9')
        if type(value) is not int or (seconds == 0 and value != 0) or (seconds > 0 and not 0 < value <= seconds):
            raise RuntimeError('A tomada não confirmou o temporizador. Confira no Smart Life.')
        return result

    def power_on(self, timeout=90, interval=2):
        if self.plug_config:
            if self.plug_status() is False:
                self.check(self._plug_device().set_value(1, True))
                if self.plug_status() is not True:
                    raise RuntimeError('A tomada não confirmou que ligou. Nenhum comando foi enviado ao ar.')
            deadline = time.monotonic() + timeout
            while True:
                try:
                    response = self.read_air_status()
                    if isinstance(response.get('dps'), dict) and type(response['dps'].get('1')) is bool:
                        break
                except (RuntimeError, OSError):
                    pass
                if time.monotonic() >= deadline:
                    raise RuntimeError('A tomada está ligada, mas o ar não respondeu dentro de 90 segundos. Confira seu IP e Wi-Fi; a tomada foi mantida ligada.')
                time.sleep(min(interval, max(0, deadline - time.monotonic())))
        self.check(self._device().set_value(1, True))
        result = self.status()
        if result.get('1') is not True:
            raise RuntimeError('O ar respondeu, mas não confirmou que ligou.')
        return result

    def status(self):
        if self.demo:
            return self.state.copy()
        plug = self.plug_status()
        if plug is False:
            self.state = {'_plug_power': False, '_ac_available': False}
            return self.state.copy()
        response = self.read_air_status()
        self.state = response['dps'].copy()
        if self.plug_config:
            self.state.update(_plug_power=plug, _ac_available=True)
        return self.state.copy()

    def set(self, dp, value):
        if dp in BOOL_FIELDS:
            if type(value) is not bool:
                raise ValueError('Esse campo requer verdadeiro/falso.')
        elif dp == 2:
            if type(value) is not int or not 1 <= value <= 99:
                raise ValueError('Informe uma temperatura inteira em °C, dentro do limite do Smart Life.')
        elif dp == 4:
            if value not in MODES.values():
                raise ValueError('Modo não mapeado.')
        elif dp == 5:
            if value not in FANS.values():
                raise ValueError('Velocidade não mapeada.')
        elif dp == 31:
            if value not in ('off', 'same'):
                raise ValueError('Oscilação não mapeada.')
        else:
            raise ValueError('DPS não mapeado; escrita bloqueada.')
        if not self.demo and dp == 1 and value is True:
            return self.power_on()
        if self.plug_config and self.plug_status() is False:
            raise ValueError('A tomada está desligada. Clique em Ligar para alimentar o ar primeiro.')
        if (dp == 25 and value is True) or (dp == 5 and value == 'strong'):
            if self.status().get('4') != 'cold':
                raise ValueError('Selecione Refrigerar antes de ativar Sleep ou Turbo.')
        if self.demo:
            self.state[str(dp)] = value
        else:
            self.check(self._device().set_value(dp, value))
        # O estado mostrado ao usuário sempre vem de nova leitura.
        return self.status()

    def timer(self, kind, enabled, hours=0, minutes=0):
        if kind not in ('ON', 'OFF') or type(enabled) is not bool:
            raise ValueError('Temporizador inválido.')
        switch_dp, time_dp = (101, 103) if kind == 'ON' else (102, 104)
        duration = encode_time(hours, minutes) if enabled else None
        current = self.status()
        if current.get('_ac_available') is False:
            raise ValueError('Ligue a alimentação do ar antes de configurar temporizadores.')
        if enabled and kind == 'ON' and current.get('1') is not False:
            raise ValueError('Desligue o ar antes de configurar Timer ON, como no aplicativo.')
        if self.demo:
            self.state[str(switch_dp)] = enabled
            if enabled:
                self.state[str(time_dp)] = duration
        else:
            d = self._device()
            # Desabilita antes de editar para evitar reutilizar um intervalo antigo.
            self.check(d.set_value(switch_dp, False))
            if enabled:
                self.check(d.set_value(time_dp, duration))
                self.check(d.set_value(switch_dp, True))
        return self.status()
