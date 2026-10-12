"""Controle LAN: nenhum acesso à API cloud; credenciais ficam no devices.json."""
import json
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
    def __init__(self, config=None, demo=False):
        self.config = config
        self.demo = demo
        self.state = DEMO_STATE.copy() if demo else {}

    def _device(self):
        import tinytuya
        if not self.config:
            raise ValueError('Selecione o devices.json e um dispositivo.')
        c = self.config
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

    def status(self):
        if self.demo:
            return self.state.copy()
        response = self.check(self._device().status())
        if not isinstance(response.get('dps'), dict):
            raise RuntimeError('O aparelho não retornou o estado DPS.')
        self.state = response['dps'].copy()
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
