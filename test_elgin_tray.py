"""Testes dos atalhos do painel, sem conexão com o ar-condicionado."""

from datetime import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from elgin_tray import TrayApp


class TestarPainel(unittest.TestCase):
    def painel(self, eco):
        app = TrayApp.__new__(TrayApp)
        app.closed = False
        app.canvas = Mock()
        app.rounded = Mock()
        app.label = Mock()
        app.card_icon = Mock()
        app.settings_icon = Mock()
        app.dps = {"1": True, "2": 24, "3": 27, "4": "cold",
                   "5": "auto", "11": eco, "25": False,
                   "31": "off", "33": False, "36": True, "102": False}
        app.pending_temp = None
        app.phase = 0
        app.error = ""
        app.busy = False
        app.updated = None
        app.page = "control"
        app.menu = None
        app.hotspots = []
        app.plug_dps = {"1": False, "18": 0, "19": 0, "20": 1234}
        app.plug_error = ""
        app.plug_busy = False
        app.plug_updated = None
        return app

    def test_cartao_eco_substitui_aletas_e_alterna_dp_confirmado(self):
        for ligado in (False, True):
            with self.subTest(ligado=ligado):
                app = self.painel(ligado)
                app.draw()
                textos = [call.args[2] for call in app.label.call_args_list]
                self.assertIn("Eco", textos)
                self.assertIn("Ligado" if ligado else "Desligado", textos)
                self.assertNotIn("Aletas", textos)
                app.submit = Mock()
                app.draw = Mock()
                app.click(SimpleNamespace(x=330, y=680))
                app.submit.assert_called_once_with("protect", not ligado)

    def test_aletas_continuam_em_funcoes(self):
        app = self.painel(False)
        app.page = "extras"
        app.draw()
        textos = [call.args[2] for call in app.label.call_args_list]
        self.assertIn("Aletas", textos)
        app.draw = Mock()
        app.click(SimpleNamespace(x=50, y=250))
        self.assertEqual(app.menu, "swing")

    def test_cliques_funcionam_com_janela_reduzida(self):
        app = self.painel(True)
        app.scale = 0.8
        app.draw()
        app.submit = Mock()
        app.draw = Mock()
        app.click(SimpleNamespace(x=round(330 * app.scale),
                                  y=round(680 * app.scale)))
        app.submit.assert_called_once_with("protect", False)

    def test_tomada_abre_mesmo_se_ar_esta_offline(self):
        app = self.painel(False)
        app.dps = {}
        app.busy = True
        app.draw()
        app.submit_plug = Mock()
        app.draw = Mock()
        app.click(SimpleNamespace(x=150, y=602))
        self.assertEqual(app.page, "plug")
        app.submit_plug.assert_called_once_with("status")

    def test_tomada_desligada_pode_ser_ligada_sem_status_do_ar(self):
        app = self.painel(False)
        app.dps = {}
        app.page = "plug"
        app.draw()
        app.submit_plug = Mock()
        app.draw = Mock()
        app.click(SimpleNamespace(x=180, y=324))
        app.submit_plug.assert_called_once_with("power", True)

    def test_corte_da_tomada_pede_confirmacao_com_ar_ligado(self):
        app = self.painel(False)
        app.page = "plug"
        app.plug_dps["1"] = True
        app.updated = datetime.now()
        app.draw()
        self.assertIn("plug_power", [name for name, _, _ in app.hotspots])
        app.click(SimpleNamespace(x=180, y=324))
        self.assertEqual(app.page, "plug_confirm")
        app.draw()
        self.assertIn("plug_confirm_off", [name for name, _, _ in app.hotspots])
        app.submit_plug = Mock()
        app.click(SimpleNamespace(x=180, y=465))
        app.submit_plug.assert_called_once_with("power", False, force_off=True)
        self.assertEqual(app.page, "plug")

    def test_cancelar_corte_nao_envia_comando(self):
        app = self.painel(False)
        app.page = "plug_confirm"
        app.plug_dps["1"] = True
        app.draw()
        app.submit_plug = Mock()
        app.click(SimpleNamespace(x=180, y=545))
        self.assertEqual(app.page, "plug")
        app.submit_plug.assert_not_called()

    def test_corte_continua_clicavel_com_status_do_ar_desconhecido(self):
        app = self.painel(False)
        app.page = "plug"
        app.dps = {}
        app.plug_dps["1"] = True
        app.draw()
        self.assertIn("plug_power", [name for name, _, _ in app.hotspots])
        app.click(SimpleNamespace(x=180, y=324))
        self.assertEqual(app.page, "plug_confirm")

    def test_ar_desligado_nao_precisa_de_override(self):
        app = self.painel(False)
        app.page = "plug"
        app.plug_dps["1"] = True
        app.dps["1"] = False
        app.updated = datetime.now()
        app.draw()
        self.assertIn("plug_power", [name for name, _, _ in app.hotspots])
        app.submit_plug = Mock()
        app.click(SimpleNamespace(x=180, y=324))
    def test_navegacao_entre_tres_telas(self):
        # 1. Dashboard -> Subtela Funções -> Dashboard
        app = self.painel(False)
        app.draw()
        app.click(SimpleNamespace(x=240, y=680))
        self.assertEqual(app.page, "extras")
        app.draw()
        app.click(SimpleNamespace(x=35, y=45))
        self.assertEqual(app.page, "control")

        # 2. Dashboard -> Subtela Tomada -> Dashboard
        app.draw()
        app.submit_plug = Mock()
        app.click(SimpleNamespace(x=150, y=602))
        self.assertEqual(app.page, "plug")
        app.draw()
        app.click(SimpleNamespace(x=35, y=45))
        self.assertEqual(app.page, "control")

    def test_chips_do_timer_em_funcoes(self):
        app = self.painel(False)
        app.page = "extras"
        app.draw()
        app.click(SimpleNamespace(x=230, y=558))  # Chip 2 horas (0200)
        self.assertEqual(app.selected_timer_hours, "0200")
        self.assertEqual(app.timer_label(), "2 horas")

    def test_telemetria_tomada_metricas(self):
        app = self.painel(False)
        app.page = "plug"
        app.plug_dps = {"1": True, "18": 6880, "19": 8500, "20": 1234}
        app.draw()
        textos = [call.args[2] for call in app.label.call_args_list]
        self.assertIn("850", textos)
        self.assertIn("123.4", textos)
        self.assertIn("6.88", textos)
        self.assertIn("Ligada", textos)

    def test_detalhamento_abre_offline_e_mes_volta_ao_resumo(self):
        app = self.painel(False)
        app.page = "plug"
        app.busy = True
        app.dps = {}
        app.draw()
        app.click(SimpleNamespace(x=195, y=745))
        self.assertEqual(app.page, "energy")
        app.draw()
        app.click(SimpleNamespace(x=180, y=510))
        self.assertEqual(app.page, "energy_month")
        self.assertEqual(app.energy_month, 10)
        self.assertEqual(app.energy_selected_day, 11)
        app.draw()
        app.click(SimpleNamespace(x=40, y=45))
        self.assertEqual(app.page, "energy")
        self.assertEqual(app.focused_hotspot, ("energy_month", 10))
        app.click(SimpleNamespace(x=40, y=45))
        self.assertEqual(app.page, "plug")
        self.assertEqual(app.focused_hotspot, ("energy_detail", None))
        app.energy_activate(None)
        self.assertEqual(app.page, "energy")

    def test_resumo_nao_exibe_instantaneas_antigas_offline(self):
        app = self.painel(False)
        app.page = "energy"
        app.plug_error = "Sem conexão"
        app.plug_dps = {"1": True, "18": 6880, "19": 8500, "20": 1234}
        app.draw()
        textos = [call.args[2] for call in app.label.call_args_list]
        self.assertNotIn("850.0", textos)
        self.assertNotIn("6.880", textos)
        self.assertIn("Instantâneas indisponíveis • atualize a tomada", textos)


if __name__ == "__main__":
    unittest.main()
