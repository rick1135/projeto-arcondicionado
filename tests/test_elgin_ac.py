"""Testes locais da reconexão, sem enviar comandos ao aparelho."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import json
import unittest
from unittest.mock import MagicMock, patch

import elgin_ac


class DispositivoFalso:
    def __init__(self, ip):
        self.ip = ip
        self.closed = False

    def close(self):
        self.closed = True


class TestarReconexao(unittest.TestCase):
    def test_redescobre_ip_e_salva_so_apos_status_valido(self):
        caminho = MagicMock()
        config = {"ip": "192.168.1.50", "device_id": "id-teste",
                  "local_key": "chave-teste", "version": 3.3}
        dispositivos = []

        def criar(cfg):
            dispositivo = DispositivoFalso(cfg["ip"])
            dispositivos.append(dispositivo)
            return dispositivo

        def status(dispositivo):
            if dispositivo.ip == "192.168.1.50":
                raise RuntimeError("Network Error")
            return {"1": False, "2": 23}

        with (patch.object(elgin_ac, "CONFIG", caminho),
              patch.object(elgin_ac, "criar_dispositivo", side_effect=criar),
              patch.object(elgin_ac, "ler_status", side_effect=status),
              patch.object(elgin_ac.tinytuya, "deviceScan", return_value={
                  "192.168.1.99": {"gwId": "id-teste"}})):
            dispositivo, dps = elgin_ac.conectar(config)

        self.assertEqual(dispositivo.ip, "192.168.1.99")
        self.assertEqual(dps["2"], 23)
        self.assertTrue(dispositivos[0].closed)
        self.assertEqual(json.loads(caminho.write_text.call_args.args[0])["ip"],
                         "192.168.1.99")

    def test_nao_altera_config_se_novo_ip_falhar(self):
        caminho = MagicMock()
        config = {"ip": "192.168.1.50", "device_id": "id-teste",
                  "local_key": "chave-teste", "version": 3.3}

        with (patch.object(elgin_ac, "CONFIG", caminho),
              patch.object(elgin_ac, "criar_dispositivo",
                           side_effect=lambda cfg: DispositivoFalso(cfg["ip"])),
              patch.object(elgin_ac, "ler_status",
                           side_effect=RuntimeError("Network Error")),
              patch.object(elgin_ac.tinytuya, "deviceScan", return_value={
                  "192.168.1.99": {"gwId": "id-teste"}})):
            with self.assertRaises(RuntimeError):
                elgin_ac.conectar(config)

        self.assertEqual(config["ip"], "192.168.1.50")
        caminho.write_text.assert_not_called()


if __name__ == "__main__":
    unittest.main()
