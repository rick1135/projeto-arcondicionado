param([switch]$SemInicializacao)
$ErrorActionPreference = 'Stop'
$dest = Join-Path $env:LOCALAPPDATA 'ElginControl'
New-Item -ItemType Directory -Force -Path $dest | Out-Null
if ([IO.Path]::GetFullPath($PSScriptRoot) -ne [IO.Path]::GetFullPath($dest)) {
    Get-ChildItem -LiteralPath $PSScriptRoot -File | Copy-Item -Destination $dest -Force
}
$python = Join-Path $env:USERPROFILE 'elgin-venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $venv = Join-Path $dest '.venv'
    $python = Join-Path $venv 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        & py -m venv $venv
        if ($LASTEXITCODE -ne 0) { throw 'Não foi possível criar o ambiente Python.' }
    }
}
& $python -m pip install -r (Join-Path $dest 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependências.' }
& $python -c 'import tkinter, tinytuya, pystray, webview; from PIL import Image'
if ($LASTEXITCODE -ne 0) { throw 'Dependências ou Tcl/Tk indisponíveis.' }
$pythonw = Join-Path (Split-Path -Parent $python) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw)) { throw 'pythonw.exe não encontrado.' }
$wshell = New-Object -ComObject WScript.Shell
$script = Join-Path $dest 'tray.py'
function Write-Shortcut([string]$Path, [string]$Entry) {
    $link = $wshell.CreateShortcut($Path)
    $link.TargetPath = $pythonw
    $link.Arguments = '"' + (Join-Path $dest $Entry) + '"'
    $link.WorkingDirectory = $dest
    $link.IconLocation = (Join-Path $dest 'elgin.ico') + ',0'
    $link.Description = 'Controle local do ar Elgin na área de notificação'
    $link.Save()
}
Write-Shortcut (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Controle Elgin.lnk') 'app.py'
$startMenu = Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs\Controle Elgin.lnk'
Write-Shortcut $startMenu 'app.py'
$startup = Join-Path ([Environment]::GetFolderPath('Startup')) 'Controle Elgin.lnk'
if (-not $SemInicializacao) { Write-Shortcut $startup 'tray.py' }
Write-Host 'Instalado. Procure o floco azul perto do relógio ou na seta ^.'
Start-Process -FilePath $pythonw -ArgumentList ('"' + $script + '"') -WorkingDirectory $dest
