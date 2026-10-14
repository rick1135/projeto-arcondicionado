"""Controle local do ar-condicionado Elgin/Tuya.

Exemplos:
    python elgin_ac.py status
    python elgin_ac.py on
    python elgin_ac.py off
    python elgin_ac.py temp 23
    python elgin_ac.py mode cool
"""

import argparse
import json
from pathlib import Path
import sys

if sys.platform == "win32":
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr is not None:
        sys.stderr.reconfigure(encoding="utf-8")

try:
    import tinytuya
except ImportError:
    raise SystemExit("Instale a dependência: python -m pip install tinytuya")


_BASE = Path(__file__).resolve().parent
_CANDIDATES = [
    _BASE.parent / "config" / "config.json",
    _BASE.parent / "config.json",
    _BASE / "config.json",
]
CONFIG = next((c for c in _CANDIDATES if c.is_file()), _BASE.parent / "config" / "config.json")
MODOS = {"auto": "auto", "cool": "cold", "fan": "wind", "dry": "wet"}


def ler_config():
    caminho = CONFIG
    if hasattr(caminho, 'is_file') and not caminho.is_file():
        for c in _CANDIDATES:
            if c.is_file():
                caminho = c
                break
    try:
        config = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        raise RuntimeError(f"Não foi possível ler {caminho}: {erro}") from erro
    for campo in ("ip", "device_id", "local_key", "version"):
        if not config.get(campo):
            raise RuntimeError(f"Campo obrigatório ausente em {caminho}: {campo}")
    return config


def criar_dispositivo(config):
    return tinytuya.Device(
        config["device_id"], config["ip"], config["local_key"],
        version=float(config["version"]), connection_timeout=3,
        connection_retry_limit=1,
    )


def conectar(config):
    """Confere o IP salvo e redescobre o aparelho pelo ID quando necessário."""
    dispositivo = criar_dispositivo(config)
    try:
        dps = ler_status(dispositivo)
        return dispositivo, dps
    except RuntimeError as erro:
        dispositivo.close()
        if "Network Error" not in str(erro) and "Unable to Connect" not in str(erro):
            raise

    encontrados = tinytuya.deviceScan(verbose=False, maxretry=20, poll=False)
    novo_ip = next(
        (ip for ip, info in encontrados.items()
         if info.get("gwId") == config["device_id"]),
        None,
    )
    if not novo_ip:
        raise RuntimeError(f"Dispositivo {config['device_id']} não encontrado na rede local")
    ip_anterior = config["ip"]
    config["ip"] = novo_ip
    dispositivo = criar_dispositivo(config)
    try:
        dps = ler_status(dispositivo)
    except Exception:
        dispositivo.close()
        config["ip"] = ip_anterior
        raise
    if novo_ip != ip_anterior:
        try:
            CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
        except OSError:
            dispositivo.close()
            raise
    return dispositivo, dps


def ler_status(dispositivo):
    resposta = dispositivo.status()
    if not isinstance(resposta, dict) or not isinstance(resposta.get("dps"), dict):
        raise RuntimeError(f"Falha na leitura de status: {resposta!r}")
    return resposta["dps"]


def escrever_dp(dispositivo, dp, valor):
    resposta = dispositivo.set_value(dp, valor)
    if isinstance(resposta, dict) and ("Error" in resposta or "Err" in resposta):
        raise RuntimeError(f"Falha ao escrever DP {dp}: {resposta!r}")
    return ler_status(dispositivo)


def configurar_modo(dispositivo, modo, _eco=None):
    """O DP 11 é Protect, independente do modo; não há Eco confirmado."""
    if modo == "eco":
        raise ValueError("Eco não foi confirmado neste aparelho; DP 11 é Protect")
    return escrever_dp(dispositivo, 4, MODOS[modo])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    comandos = parser.add_subparsers(dest="comando", required=True)
    comandos.add_parser("status", help="mostra temperaturas e estado")
    comandos.add_parser("on", help="liga o ar-condicionado")
    comandos.add_parser("off", help="desliga o ar-condicionado")
    temperatura = comandos.add_parser("temp", help="ajusta o setpoint em °C")
    temperatura.add_argument("graus", type=int, help="temperatura de 16 a 32 °C")
    modo = comandos.add_parser("mode", help="altera o modo de operação")
    modo.add_argument("valor", choices=["auto", "cool", "fan", "dry"])
    protect = comandos.add_parser("protect", help="liga ou desliga Protect")
    protect.add_argument("valor", choices=["on", "off"])
    args = parser.parse_args()

    if args.comando == "temp" and not 16 <= args.graus <= 32:
        parser.error("a temperatura deve estar entre 16 e 32 °C")

    config = ler_config()
    dispositivo, dps_iniciais = conectar(config)
    try:
        if args.comando == "status":
            dps = dps_iniciais
        elif args.comando in ("on", "off"):
            dps = escrever_dp(dispositivo, 1, args.comando == "on")
        elif args.comando == "temp":
            dps = escrever_dp(dispositivo, 2, args.graus)
        elif args.comando == "protect":
            dps = escrever_dp(dispositivo, 11, args.valor == "on")
        else:
            dps = configurar_modo(dispositivo, args.valor)

        print(f"Ligado: {'sim' if dps.get('1') else 'não'}")
        print(f"Temperatura atual: {dps.get('3', '?')} °C")
        print(f"Setpoint: {dps.get('2', '?')} °C")
        print(f"Modo: {dps.get('4', '?')} | Ventilador: {dps.get('5', '?')}")
        print(f"Protect: {'sim' if dps.get('11') else 'não'}")
    finally:
        dispositivo.close()


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        sys.exit(1)
