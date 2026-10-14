"""Leitura e controle LAN da tomada EKAZA ligada ao ar-condicionado."""

import json
from pathlib import Path
import time

import tinytuya


CONFIG = Path(__file__).with_name("plug_config.json")


def ler_config():
    try:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("Não foi possível ler a configuração da tomada") from exc
    if not all(config.get(field) for field in ("device_id", "ip", "local_key", "version")):
        raise RuntimeError("A configuração da tomada está incompleta")
    return config


def criar_dispositivo(config):
    return tinytuya.OutletDevice(
        config["device_id"], config["ip"], config["local_key"],
        version=float(config["version"]), connection_timeout=4,
        connection_retry_limit=1,
    )


def ler_status(device):
    response = device.status()
    dps = response.get("dps") if isinstance(response, dict) else None
    if not isinstance(dps, dict) or not isinstance(dps.get("1"), bool):
        raise RuntimeError("A tomada não retornou um estado válido")
    return dps


def conectar(config):
    """Lê o IP salvo e redescobre pelo ID se a tomada mudou de endereço."""
    device = criar_dispositivo(config)
    try:
        return device, ler_status(device)
    except Exception:
        device.close()

    try:
        found = tinytuya.deviceScan(verbose=False, maxretry=12, poll=False)
    except OSError as exc:
        raise RuntimeError("Tomada sem conexão; descoberta LAN indisponível") from exc
    new_ip = next((ip for ip, info in found.items()
                   if info.get("gwId") == config["device_id"]), None)
    if not new_ip:
        raise RuntimeError("Tomada EKAZA não encontrada na rede local")
    candidate = dict(config, ip=new_ip)
    device = criar_dispositivo(candidate)
    try:
        dps = ler_status(device)
        if new_ip != config["ip"]:
            CONFIG.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
        return device, dps
    except Exception:
        device.close()
        raise


def medidas(dps):
    """Converte as escalas confirmadas no mapeamento Tuya da EKAZA."""
    def scaled(dp, divisor):
        raw = dps.get(dp)
        return raw / divisor if isinstance(raw, (int, float)) and not isinstance(raw, bool) else None

    return {"voltage_v": scaled("20", 10),
            "power_w": scaled("19", 10),
            "current_a": scaled("18", 1000)}


def run_operation(command, value=None, *, ac_off_confirmed=False, force_off=False):
    """Retorna (dps, erro); corte sem ar confirmado requer override explícito."""
    if command not in ("status", "power"):
        return None, "Comando da tomada inválido"
    if command == "power" and not isinstance(value, bool):
        return None, "Estado da tomada inválido"
    if command == "power" and value is False and not (ac_off_confirmed or force_off):
        return None, "Desligue o ar-condicionado antes de cortar a tomada"
    if command == "power" and value is False and not force_off:
        # Confirma outra vez, diretamente no aparelho, antes do corte físico.
        from elgin_app import ElginApp

        ac_dps, ac_error = ElginApp.run_operation("status", None)
        if ac_error or ac_dps is None or ac_dps.get("1") is not False:
            return None, "O ar não foi confirmado desligado; tomada mantida ligada"

    device = None
    try:
        device, dps = conectar(ler_config())
        if command == "power":
            response = device.set_value(1, value)
            if isinstance(response, dict) and ("Error" in response or "Err" in response):
                raise RuntimeError("A tomada recusou o comando")
            for attempt in range(3):
                dps = ler_status(device)
                if dps["1"] is value:
                    break
                if attempt < 2:
                    time.sleep(0.3)
            else:
                raise RuntimeError("O estado da tomada não confirmou o comando")
        return dps, None
    except RuntimeError as exc:
        return None, str(exc)
    except (OSError, ValueError):
        return None, "Falha na comunicação com a tomada"
    finally:
        if device is not None:
            device.close()
