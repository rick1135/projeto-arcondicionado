"""Janela HTML nativa para Windows, com ponte local PyWebView."""
import argparse
import ctypes
import os
from pathlib import Path

from bridge import DeviceAPI


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--demo', action='store_true', help='Exibe leituras simuladas sem acessar a rede.')
    args = parser.parse_args()

    mutex = None
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
        kernel.CreateMutexW.restype = ctypes.c_void_p
        mutex = kernel.CreateMutexW(None, False, 'Local\\ElginControlWebview')
        if ctypes.get_last_error() == 183:
            ctypes.windll.user32.MessageBoxW(None, 'O painel já está aberto. Use a janela existente.', 'Elgin', 0)
            return

    import webview
    api = DeviceAPI(demo=args.demo)
    page = Path(__file__).with_name('code.html').read_text(encoding='utf-8')
    webview.create_window('Elgin • Clima e Energia', html=page, js_api=api, width=1280, height=850, min_size=(850, 650), background_color='#070b14')
    try:
        webview.start(gui='edgechromium' if os.name == 'nt' else None)
    finally:
        api._shutdown()
        if mutex:
            ctypes.windll.kernel32.CloseHandle(mutex)


if __name__ == '__main__':
    main()
