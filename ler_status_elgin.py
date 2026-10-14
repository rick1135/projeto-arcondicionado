"""Lê os Data Points do ar-condicionado Elgin/Tuya pela rede local.

Uso:
    python ler_status_elgin.py
    python ler_status_elgin.py --comparar-eco

Na segunda opção, altere o Eco manualmente no app quando solicitado. O script
apenas lê o estado; ele não envia comandos de controle ao aparelho.
"""

import argparse
import json
import sys
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

try:
    import tinytuya
except ImportError:
    raise SystemExit("Instale a dependência: python -m pip install tinytuya")


from elgin_ac import ler_config


# Identificações confirmadas pelo mapeamento Tuya salvo para este Device ID.
DPS_CONHECIDOS = {
    "1": "Power (ligar/desligar): booleano",
    "2": "Temperatura de setpoint: °C, escala 0 (valor direto)",
    "3": "Temperatura atual: °C, escala 0",
    "4": "Modo: auto, cold=cool, hot=heat, wet=dry, wind=fan",
    "5": "Ventilador: strong, auto, low, middle, high, mute",
    "11": "Ionizador: booleano",
    "12": "Aquecimento auxiliar: booleano",
    "22": "Falhas: bitmap (pode não aparecer no status)",
    "25": "Sleep: booleano (não é Eco)",
    "31": "Aleta vertical: off, same, vane_1..vane_5",
    "33": "Oscilação horizontal: booleano",
    "36": "Display: booleano",
}


def ler_dps(dispositivo):
    resposta = dispositivo.status()
    if not isinstance(resposta, dict) or not isinstance(resposta.get("dps"), dict):
        raise RuntimeError(f"Resposta de status inválida: {resposta!r}")
    return resposta["dps"]


def ordem_dp(dp):
    return (0, int(dp)) if dp.isdigit() else (1, dp)


def mostrar_dps(dps):
    for dp in sorted(dps, key=ordem_dp):
        valor = json.dumps(dps[dp], ensure_ascii=False)
        descricao = DPS_CONHECIDOS.get(dp, "função não confirmada")
        print(f"DP {dp:>3}: {valor:<12} {descricao}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--comparar-eco", action="store_true",
        help="compara duas leituras após você alternar Eco no app",
    )
    args = parser.parse_args()

    config = ler_config()
    dispositivo = tinytuya.Device(
        config["device_id"], config["ip"], config["local_key"], version=float(config["version"]), connection_timeout=3
    )
    try:
        antes = ler_dps(dispositivo)
        print(f"Dispositivo: {config['ip']} | ID: {config['device_id']} | protocolo: {config['version']}")
        mostrar_dps(antes)
        print("\nEco: nenhum DP confirmado pelo mapeamento disponível.")

        if args.comparar_eco:
            input("\nAlterne Eco no app e pressione Enter para ler novamente...")
            time.sleep(2)
            depois = ler_dps(dispositivo)
            alterados = [
                dp for dp in sorted(set(antes) | set(depois), key=ordem_dp)
                if antes.get(dp) != depois.get(dp)
            ]
            if not alterados:
                print("Nenhum DP mudou entre as duas leituras.")
            else:
                print("DPs que mudaram (candidatos a Eco; outras ações podem alterá-los):")
                for dp in alterados:
                    print(f"  DP {dp}: {antes.get(dp)!r} -> {depois.get(dp)!r}")
    finally:
        dispositivo.close()


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        sys.exit(1)
