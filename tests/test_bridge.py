import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from bridge import DeviceAPI


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.preferences = Path(self.directory.name) / 'preferencias.json'
        self.devices = Path(self.directory.name) / 'devices.json'
        self.devices.write_text(json.dumps([
            {'id': 'air-test', 'key': 'private-ac-key', 'name': 'Smart Air', 'version': 3.3, 'ip': '10.0.0.5'},
            {'id': 'plug-test', 'key': 'private-plug-key', 'name': 'tomada ar', 'version': 3.5},
        ]), encoding='utf-8')
        self.api = DeviceAPI(preferences=self.preferences)

    def configure(self):
        result = self.api.save_settings(str(self.devices), '10.0.0.1', '', 'air-test', 'plug-test')
        self.assertTrue(result['ok'], result)

    def test_settings_do_not_return_local_keys_and_select_correct_devices(self):
        self.configure()
        self.assertEqual(self.api.control.config['id'], 'air-test')
        self.assertEqual(self.api.control.plug_config['id'], 'plug-test')
        self.assertEqual(self.api.control.config['ip'], '10.0.0.1')
        self.assertNotIn('private-ac-key', json.dumps(self.api.get_settings()))
        reopened = DeviceAPI(preferences=self.preferences)
        self.assertEqual(reopened.control.plug_config['id'], 'plug-test')

    def test_status_maps_real_dps_and_scales_power(self):
        self.configure()
        c = self.api.control
        c.read_plug = Mock(return_value={'_plug_dps': {'1': True, '9': 0, '18': 904, '19': 354, '20': 1224}})
        c.status = Mock(return_value={'1': True, '2': 23, '3': 26, '4': 'cold', '5': 'middle', '11': True, '25': False, '31': 'same', '36': True})
        status = self.api.get_system_status()
        self.assertEqual(status['ac']['target_temp'], 23)
        self.assertEqual(status['ac']['room_temp'], 26)
        self.assertEqual(status['ac']['mode'], 'cool')
        self.assertEqual(status['ac']['fan'], 'med')
        self.assertTrue(status['ac']['features']['swing'])
        self.assertEqual(status['plug']['watts'], 35.4)
        self.assertEqual(status['plug']['amps'], .904)
        self.assertEqual(status['plug']['volts'], 122.4)

    def test_toggle_plug_uses_measured_state_and_does_not_fake_success(self):
        self.configure()
        c = self.api.control
        c.read_plug = Mock(return_value={'_plug_dps': {'1': True}})
        c.set_plug_power = Mock(side_effect=RuntimeError('Tomada não confirmou desligamento.'))
        result = self.api.toggle_plug_power()
        c.set_plug_power.assert_called_once_with(False)
        self.assertFalse(result['ok'])
        self.assertNotIn('command_ok', result)

    def test_invalid_settings_leave_previous_config_untouched(self):
        self.configure()
        before = self.preferences.read_text(encoding='utf-8')
        result = self.api.save_settings(str(self.devices), '', '', 'air-test', 'air-test')
        self.assertFalse(result['ok'])
        self.assertEqual(self.preferences.read_text(encoding='utf-8'), before)

    def test_empty_ip_uses_discovery_instead_of_stale_wizard_ip(self):
        result = self.api.save_settings(str(self.devices), '', '', 'air-test', 'plug-test')
        self.assertTrue(result['ok'])
        self.assertEqual(self.api.control.config['ip'], 'Auto')


if __name__ == '__main__':
    unittest.main()
