"""Ponto de entrada principal do Elgin AC Tray."""
import sys
from pathlib import Path

# Adiciona o diretório src/ ao sys.path
SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from elgin_tray import main

if __name__ == "__main__":
    main()
