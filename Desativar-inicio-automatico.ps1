$shortcut = Join-Path ([Environment]::GetFolderPath('Startup')) 'Controle Elgin.lnk'
if (Test-Path -LiteralPath $shortcut) { Remove-Item -LiteralPath $shortcut }
Write-Host 'Inicio automatico desativado. Os atalhos e o aplicativo continuam disponiveis.'
