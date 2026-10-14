"""Smoke test do Tk real: inicialização e callbacks com rede lenta simulada."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import threading
import tkinter as tk
import unittest
from unittest.mock import Mock, patch
from elgin_tray import TrayApp, main
from windows_flyout import work_area


class FluentRuntimeTests(unittest.TestCase):
    def test_entrada_demo_executa_e_fecha_sem_dispositivos(self):
        panels = []
        def create(root, **kwargs):
            app = TrayApp(root, **kwargs)
            panels.append(app)
            root.after(650, app.stop)
            return app
        with (patch('sys.argv', ['main.py', '--demo']),
              patch('elgin_tray.TrayApp', side_effect=create)):
            main()
        self.assertEqual(len(panels), 1)
        self.assertTrue(panels[0].closed)
        self.assertTrue(panels[0].offline)

    def test_real_mainloop_responde_enquanto_workers_aguardam(self):
        root = tk.Tk()
        main_thread = threading.get_ident()
        release, ac_started, plug_started = threading.Event(), threading.Event(), threading.Event()
        network_threads, errors, heartbeats = [], [], []
        root.report_callback_exception = lambda *args: errors.append(args)
        def ac(*_):
            network_threads.append(threading.get_ident())
            ac_started.set()
            release.wait(2)
            return {"1": True, "2": 24, "3": 26, "4": "cold", "5": "auto"}, None
        def plug(*_, **__):
            network_threads.append(threading.get_ident())
            plug_started.set()
            release.wait(2)
            return {"1": True, "18": 0, "19": 0, "20": 1234}, None
        with (patch('elgin_tray.ElginApp.run_operation', side_effect=ac),
              patch('elgin_tray.operar_tomada', side_effect=plug),
              patch('elgin_tray.EnergyHistory', return_value=None),
              patch('elgin_tray.EnergyBridge', return_value=None),
              patch('elgin_tray.config_tomada', return_value={'device_id': 'fixture'}),
              patch('elgin_tray.apply_startup_preference'),
              patch('elgin_tray.pystray.Icon', return_value=Mock())):
            app = TrayApp(root)
            try:
                app.show()
                self.assertTrue(ac_started.wait(1))
                self.assertTrue(plug_started.wait(1))
                left, top, right, bottom = work_area(root)
                self.assertEqual((root.winfo_width(), root.winfo_height()), (380, 560))
                self.assertLessEqual(root.winfo_y()+root.winfo_height(), bottom)
                self.assertGreaterEqual(root.winfo_x(), left)
                def pulse():
                    heartbeats.append((app.busy, app.plug_busy))
                    if len(heartbeats) < 5:
                        root.after(20, pulse)
                root.after(10, pulse)
                root.after(140, release.set)
                root.after(500, root.quit)
                root.mainloop()
                self.assertEqual(len(heartbeats), 5)
                self.assertTrue(all(a and p for a, p in heartbeats))
                self.assertFalse(app.busy)
                self.assertFalse(app.plug_busy)
                self.assertEqual(app.dps['2'], 24)
                self.assertTrue(app.plug_dps['1'])
                self.assertTrue(all(t != main_thread for t in network_threads))
                self.assertFalse(errors, errors)
            finally:
                release.set()
                app.stop()

    def test_demo_nao_abre_rede_nem_altera_inicio_automatico(self):
        root = tk.Tk()
        with (patch('elgin_tray.ElginApp.run_operation') as ac,
              patch('elgin_tray.operar_tomada') as plug,
              patch('elgin_tray.EnergyBridge') as cloud,
              patch('elgin_tray.EnergyHistory') as history,
              patch('elgin_tray.apply_startup_preference') as startup):
            app = TrayApp(root, preview=True, offline=True)
            try:
                app.show()
                root.update()
                for mock in (ac, plug, cloud, history, startup):
                    mock.assert_not_called()
                self.assertEqual(app.view_width, 380)
                self.assertEqual(app.view_height, 560)
            finally:
                app.stop()


if __name__ == '__main__':
    unittest.main()
