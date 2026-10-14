@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Python do projeto nao encontrado.
    echo Crie o ambiente e instale as dependencias:
    echo py -m venv .venv
    echo .venv\Scripts\python.exe -m pip install tinytuya
    pause
    exit /b 1
)
echo Abrindo controle Elgin...
".venv\Scripts\python.exe" -c "import tkinter, tinytuya, pystray, PIL"
if errorlevel 1 (
    echo.
    echo Faltam dependencias. Instale com:
    echo .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "elgin_tray.py" --show
