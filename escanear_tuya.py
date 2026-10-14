"""Descobre dispositivos Tuya/SmartLife por broadcasts UDP 6666 e 6667."""

import argparse
import json
import select
import socket
import sys
import time

try:
    import tinytuya
except ImportError:
    raise SystemExit("Instale a dependência: python -m pip install tinytuya")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tempo", type=float, default=30, help="segundos de escuta (padrão: 30)")
    parser.add_argument("--id", help="filtra pelo Device ID do ar-condicionado")
    parser.add_argument("--ip", help="filtra pelo IP do ar-condicionado")
    args = parser.parse_args()
    if args.tempo <= 0:
        parser.error("--tempo deve ser maior que zero")

    sockets = []
    vistos = set()
    try:
        for porta in (6666, 6667):
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.bind(("0.0.0.0", porta))
            except OSError:
                sock.close()
                raise
            sockets.append(sock)

        print(f"Escutando broadcasts Tuya em UDP 6666 e 6667 por {args.tempo:g} s...")
        fim = time.monotonic() + args.tempo
        while (restante := fim - time.monotonic()) > 0:
            prontos, _, _ = select.select(sockets, [], [], restante)
            for sock in prontos:
                pacote, origem = sock.recvfrom(65535)
                try:
                    dados = json.loads(tinytuya.decrypt_udp(pacote))
                except Exception:
                    # Outros pacotes UDP ou anúncios inválidos podem chegar às portas.
                    continue

                if not isinstance(dados, dict):
                    continue
                ip = origem[0]
                device_id = dados.get("gwId") or dados.get("devId") or dados.get("id")
                versao = dados.get("version") or "não informada"
                if not device_id or (args.id and device_id != args.id):
                    continue
                if args.ip and ip != args.ip:
                    continue
                if (ip, device_id) in vistos:
                    continue

                vistos.add((ip, device_id))
                print(f"IP: {ip} | Device ID: {device_id} | Protocolo: {versao}")

    except OSError as erro:
        print(f"Erro ao escutar UDP 6666/6667: {erro}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nEscuta interrompida.")
    finally:
        for sock in sockets:
            sock.close()

    if not vistos:
        print("Nenhum dispositivo correspondente foi encontrado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
