"""Testes da tomada EKAZA sem enviar comandos reais."""

import unittest
from unittest.mock import Mock, patch

import ekaza_plug


class TestarTomada(unittest.TestCase):
    def test_medidas_respeitam_escala_tuya(self):
        self.assertEqual(
            ekaza_plug.medidas({"18": 125, "19": 432, "20": 1234}),
            {"voltage_v": 123.4, "power_w": 43.2, "current_a": 0.125},
        )

    @patch("ekaza_plug.conectar")
    @patch("ekaza_plug.ler_config", return_value={})
    def test_status_somente_leitura(self, _config, conectar):
        device = Mock()
        conectar.return_value = (device, {"1": False, "19": 0})
        dps, error = ekaza_plug.run_operation("status")
        self.assertIsNone(error)
        self.assertEqual(dps["1"], False)
        device.set_value.assert_not_called()
        device.close.assert_called_once()

    @patch("ekaza_plug.conectar")
    def test_nao_desliga_com_estado_do_ar_desconhecido(self, conectar):
        dps, error = ekaza_plug.run_operation("power", False)
        self.assertIsNone(dps)
        self.assertIn("Desligue o ar", error)
        conectar.assert_not_called()

    @patch("elgin_app.ElginApp.run_operation", return_value=({"1": True}, None))
    @patch("ekaza_plug.conectar")
    def test_reconfirma_o_ar_antes_do_corte(self, conectar, _ac_status):
        dps, error = ekaza_plug.run_operation("power", False,
                                               ac_off_confirmed=True)
        self.assertIsNone(dps)
        self.assertIn("mantida ligada", error)
        conectar.assert_not_called()

    @patch("ekaza_plug.conectar")
    @patch("ekaza_plug.ler_config", return_value={})
    def test_ligar_exige_confirmacao_da_tomada(self, _config, conectar):
        device = Mock()
        device.set_value.return_value = {}
        device.status.return_value = {"dps": {"1": True}}
        conectar.return_value = (device, {"1": False})
        dps, error = ekaza_plug.run_operation("power", True)
        self.assertIsNone(error)
        self.assertTrue(dps["1"])
        device.set_value.assert_called_once_with(1, True)
        device.close.assert_called_once()

    @patch("elgin_app.ElginApp.run_operation", return_value=({"1": False}, None))
    @patch("ekaza_plug.conectar")
    @patch("ekaza_plug.ler_config", return_value={})
    def test_desligar_so_depois_de_confirmar_ar_desligado(self, _config, conectar, _ac_status):
        device = Mock()
        device.set_value.return_value = {}
        device.status.return_value = {"dps": {"1": False}}
        conectar.return_value = (device, {"1": True})
        dps, error = ekaza_plug.run_operation("power", False,
                                               ac_off_confirmed=True)
        self.assertIsNone(error)
        self.assertFalse(dps["1"])
        device.set_value.assert_called_once_with(1, False)

    @patch("elgin_app.ElginApp.run_operation")
    @patch("ekaza_plug.conectar")
    @patch("ekaza_plug.ler_config", return_value={})
    def test_confirmacao_explicita_permite_corte_sem_status_do_ar(self, _config, conectar, ac_status):
        device = Mock()
        device.set_value.return_value = {}
        device.status.return_value = {"dps": {"1": False}}
        conectar.return_value = (device, {"1": True})
        dps, error = ekaza_plug.run_operation("power", False, force_off=True)
        self.assertIsNone(error)
        self.assertFalse(dps["1"])
        device.set_value.assert_called_once_with(1, False)
        ac_status.assert_not_called()


if __name__ == "__main__":
    unittest.main()
