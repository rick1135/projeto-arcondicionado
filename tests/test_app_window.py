import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import app


class WindowTests(unittest.TestCase):
    def test_webview_loads_html_and_closes_api(self):
        api = Mock()
        webview = SimpleNamespace(create_window=Mock(), start=Mock())
        with patch.object(sys, 'argv', ['app.py']), patch.object(app, 'DeviceAPI', return_value=api), patch.dict(sys.modules, {'webview': webview}):
            app.main()
        _, kwargs = webview.create_window.call_args
        self.assertIn('pywebview.api.get_system_status()', kwargs['html'])
        self.assertIs(kwargs['js_api'], api)
        api._shutdown.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
