"""Testa o mapeamento dos controles sem conectar ao ar-condicionado."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import unittest
from unittest.mock import patch

import elgin_app


class DispositivoFalso:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class TestarControles(unittest.TestCase):
    def setUp(self):
        self.device = DispositivoFalso()
        self.dps = {"1": True, "4": "cold", "5": "high",
                    "11": True, "25": True, "36": False,
                    "102": False, "104": "0100"}
        self.calls = []
        self.config_patch = patch.object(elgin_app, "ler_config", return_value={})
        self.connect_patch = patch.object(elgin_app, "conectar",
                                          return_value=(self.device, self.dps))
        self.write_patch = patch.object(elgin_app, "escrever_dp",
                                        side_effect=self.escrever)
        for item in (self.config_patch, self.connect_patch, self.write_patch):
            item.start()
            self.addCleanup(item.stop)

    def escrever(self, _device, dp, value):
        self.calls.append((dp, value))
        self.dps[str(dp)] = value
        return self.dps.copy()

    def test_botoes_extras_usam_dps_confirmados(self):
        for command, value, expected in (
            ("protect", False, (11, False)),
            ("sleep", False, (25, False)),
            ("display", True, (36, True)),
            ("special_fan", ("mute", "high"), (5, "mute")),
            ("special_fan", ("strong", "high"), (5, "strong")),
        ):
            with self.subTest(command=command, value=value):
                dps, error = elgin_app.ElginApp.run_operation(command, value)
                self.assertIsNone(error)
                self.assertEqual(self.calls[-1], expected)
                self.assertIsNotNone(dps)

    def test_turbo_exige_frio(self):
        self.dps["4"] = "auto"
        dps, error = elgin_app.ElginApp.run_operation("special_fan",
                                                       ("strong", "auto"))
        self.assertIsNone(dps)
        self.assertIn("Frio", error)
        self.assertEqual(self.calls, [])

    def test_timer_uma_hora_e_cancelamento(self):
        dps, error = elgin_app.ElginApp.run_operation("timer_off_1h", True)
        self.assertIsNone(error)
        self.assertEqual(self.calls, [(104, "0100"), (102, True)])
        self.assertTrue(dps["102"])
        self.calls.clear()
        dps, error = elgin_app.ElginApp.run_operation("timer_off_1h", False)
        self.assertIsNone(error)
        self.assertEqual(self.calls, [(102, False)])
        self.assertFalse(dps["102"])

    def test_nao_afirma_sucesso_sem_confirmacao(self):
        with (patch.object(elgin_app, "escrever_dp", return_value=self.dps.copy()),
              patch.object(elgin_app, "ler_status", return_value=self.dps.copy())):
            dps, error = elgin_app.ElginApp.run_operation("display", True)
        self.assertIsNone(dps)
        self.assertIn("não confirmou", error)


if __name__ == "__main__":
    unittest.main()
