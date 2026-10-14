"""Comportamentos do flyout; todos os transportes de rede são substituídos."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from datetime import datetime, timedelta
from types import SimpleNamespace
import queue
import threading
import unittest
from unittest.mock import Mock, patch
from elgin_tray import TrayApp
from fluent_ui import temp_from_x
from tests.fixtures import ENERGY_REFERENCE


class TestarPainel(unittest.TestCase):
    def setUp(self):
        for target in ('energy_history.reference_data', 'elgin_tray.reference_data'):
            fixture = patch(target, return_value=ENERGY_REFERENCE)
            fixture.start()
            self.addCleanup(fixture.stop)

    def painel(self, eco=False):
        app = TrayApp.__new__(TrayApp)
        app.closed, app.page, app.scale = False, "control", 1.0
        app.canvas, app.rounded, app.label = Mock(), Mock(), Mock()
        app.dps = {"1": True, "2": 24, "3": 27, "4": "cold", "5": "auto",
                   "11": eco, "25": False, "31": "off", "33": False, "36": True, "102": False}
        app.plug_dps = {"1": True, "18": 6880, "19": 8500, "20": 1234}
        app.busy = app.plug_busy = app.dragging = False
        app.error = app.plug_error = ""
        app.updated = app.plug_updated = datetime.now()
        app.pending_temp = app.menu = app.hover = None
        app.hotspots = []
        app.energy_year, app.energy_month = 2026, 10
        app.energy_selected_day, app.energy_chart_start = 1, 0
        app.last_normal_fan = "auto"
        app.submit, app.submit_plug, app.submit_energy = Mock(), Mock(), Mock()
        return app

    def activate(self, app, name, value=None):
        bounds = next(b for n, b, v in app.hotspots if (n, v) == (name, value))
        app.click(SimpleNamespace(x=(bounds[0]+bounds[2])/2*app.scale,
                                  y=(bounds[1]+bounds[3])/2*app.scale))

    def test_seis_atalhos_e_eco_no_dp_confirmado(self):
        for on in (False, True):
            app = self.painel(on)
            app.draw()
            labels = [call.args[2] for call in app.label.call_args_list]
            for title in ("Modo", "Vento", "Eco", "Tomada EKAZA", "Dormir", "Display"):
                self.assertIn(title, labels)
            self.activate(app, "eco")
            app.submit.assert_called_once_with("protect", not on)

    def test_escala_e_mapeamento_slider(self):
        app = self.painel(True)
        app.scale = .8
        app.draw()
        self.activate(app, "eco")
        app.submit.assert_called_once_with("protect", False)
        self.assertEqual([temp_from_x(x) for x in (-999, 56, 190, 324, 999)], [16, 16, 24, 32, 32])

    def test_arrastar_envia_apenas_ao_soltar(self):
        app = self.painel()
        app.draw()
        self.activate(app, "slider")
        app.drag(SimpleNamespace(x=324))
        app.submit.assert_not_called()
        self.assertEqual(app.pending_temp, 32)
        app.release(None)
        app.submit.assert_called_once_with("temp", 32)

    def test_dormir_display_e_energia(self):
        for name, command, target in (("extra_sleep", "sleep", True), ("extra_display", "display", False), ("power", "power", False)):
            app = self.painel()
            app.draw()
            self.activate(app, name)
            app.submit.assert_called_once_with(command, target)

    def test_menu_modo_e_vento(self):
        for name, selected in (("mode", "wet"), ("fan", "middle")):
            app = self.painel()
            app.draw()
            self.activate(app, name)
            self.assertEqual(app.menu, name)
            self.activate(app, "choice", (name, selected))
            app.submit.assert_called_once_with(name, selected)

    def test_seta_telemetria_independente_do_toggle_e_do_ar(self):
        app = self.painel()
        app.dps, app.busy = {}, True
        app.draw()
        self.activate(app, "plug")
        self.assertEqual(app.page, "plug")
        app.submit_plug.assert_called_once_with("status")
        app.submit.assert_not_called()

    def test_ligar_tomada_sem_estado_do_ar(self):
        app = self.painel()
        app.plug_dps["1"], app.dps = False, {}
        app.draw()
        self.activate(app, "plug_power")
        app.submit_plug.assert_called_once_with("power", True)

    def test_corte_exige_confirmacao_com_ar_ligado_ou_desconhecido(self):
        for dps in ({"1": True}, {}):
            app = self.painel()
            app.dps = dps
            app.draw()
            self.activate(app, "plug_power")
            self.assertEqual(app.page, "plug_confirm")
            app.submit_plug.assert_not_called()
            self.activate(app, "plug_confirm_off")
            app.submit_plug.assert_called_once_with("power", False, force_off=True)
            self.assertEqual(app.page, "plug")

    def test_cancelar_corte_nao_envia_comando(self):
        app = self.painel()
        app.page = "plug_confirm"
        app.draw()
        self.activate(app, "plug_cancel_off")
        self.assertEqual(app.page, "plug")
        app.submit_plug.assert_not_called()

    def test_ar_desligado_permite_corte_confirmado(self):
        app = self.painel()
        app.dps["1"] = False
        app.page = "plug"
        app.draw()
        self.activate(app, "plug_power")
        app.submit_plug.assert_called_once_with("power", False)

    def test_telemetria_e_leituras_antigas(self):
        app = self.painel()
        app.page = "plug"
        app.draw()
        labels = [call.args[2] for call in app.label.call_args_list]
        for value in ("850", "123.4", "6.88", "Ligada"):
            self.assertIn(value, labels)
        app.plug_updated = datetime.now()-timedelta(seconds=61)
        self.assertTrue(all(v is None for v in app.telemetry().values()))
        app.plug_updated, app.plug_error = datetime.now(), "Sem conexão"
        self.assertTrue(all(v is None for v in app.telemetry().values()))

    def test_funcoes_preservadas_e_timer_real_uma_hora(self):
        app = self.painel()
        app.draw()
        self.activate(app, "extras")
        self.activate(app, "extra_swing")
        self.assertEqual(app.menu, "swing")
        self.activate(app, "choice", ("swing", "both"))
        app.submit.assert_called_with("swing", (True, True))
        self.activate(app, "extra_timer")
        app.submit.assert_called_with("timer_off_1h", True)

    def test_historico_abre_offline_e_restaura_foco(self):
        app = self.painel()
        app.page, app.dps, app.busy = "plug", {}, True
        app.draw()
        self.activate(app, "energy_detail")
        self.assertEqual(app.page, "energy")
        self.activate(app, "energy_month", 10)
        self.assertEqual(app.page, "energy_month")
        self.assertEqual(app.energy_selected_day, 11)
        self.activate(app, "energy_month_back")
        self.assertEqual(app.focused_hotspot, ("energy_month", 10))
        self.activate(app, "energy_back")
        self.assertEqual(app.focused_hotspot, ("energy_detail", None))
        app.energy_activate(None)
        self.assertEqual(app.page, "energy")

    def test_keyboard_aciona_atalhos_principais(self):
        app = self.painel()
        app.draw()
        app.focused_hotspot = ("eco", None)
        self.assertEqual(app.energy_activate(None), "break")
        app.submit.assert_called_once_with("protect", True)

    def test_worker_nao_bloqueia_tk_e_resultado_volta_por_after(self):
        app = self.painel()
        app.root, app.icon, app.draw = Mock(), Mock(), Mock()
        app.events, app.results, app.plug_results = queue.Queue(), queue.Queue(), queue.Queue()
        app.process_cloud_results = Mock()
        app.closed, app.offline = False, False
        started, release = threading.Event(), threading.Event()
        main_thread = threading.get_ident()
        def network(*_):
            self.assertNotEqual(threading.get_ident(), main_thread)
            started.set()
            release.wait(2)
            return {"1": False, "2": 22}, None
        with patch('elgin_tray.ElginApp.run_operation', side_effect=network):
            TrayApp.submit(app, "temp", 22)
            self.assertTrue(started.wait(1))
            self.assertTrue(app.busy)
            self.assertTrue(app.results.empty())
            release.set()
            app.worker.join(2)
        app.process_events()
        app.root.after.assert_any_call(0, app.apply_ac_result, {"1": False, "2": 22}, None)
        self.assertEqual(app.dps["2"], 24)
        app.apply_ac_result({"1": False, "2": 22}, None)
        self.assertEqual(app.dps["2"], 22)
        self.assertFalse(app.busy)
        app.closed = True
        app.apply_ac_result({"2": 31}, None)
        self.assertEqual(app.dps["2"], 22)


if __name__ == "__main__":
    unittest.main()
