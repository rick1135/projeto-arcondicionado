param(
    [string]$Destino = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'elgin-control-tray')
)

$ErrorActionPreference = 'Stop'
$Fonte = $PSScriptRoot
$Arquivos = @(
    '.gitignore',
    'app.py', 'bridge.py', 'controller.py', 'energy.py', 'legacy_app.py', 'tray.py',
    'code.html', 'elgin.ico', 'requirements.txt',
    'Instalar.ps1', 'Desativar-inicio-automatico.ps1', 'Atualizar-repositorio.ps1',
    'README.md', 'LEIA-ME.md',
    'tests/test_app_window.py', 'tests/test_bridge.py', 'tests/test_controller.py',
    'tests/test_energy.py', 'tests/test_plug.py'
)
$Arquivos = @($Arquivos | ForEach-Object { $_.Replace('\', '/') })
$Permitidos = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
foreach ($item in $Arquivos) { [void]$Permitidos.Add($item) }

if (-not (Test-Path -LiteralPath (Join-Path $Destino '.git'))) {
    throw "Repositório Git não encontrado em '$Destino'. Use -Destino para indicar a pasta correta."
}
$git = (Get-Command git -ErrorAction Stop).Source

# Um .gitignore novo não remove dados que já foram adicionados ao Git.
$nomeSensivel = '(?i)(^|/)(devices[^/]*|snapshot[^/]*|tuya[^/]*|tinytuya[^/]*|preferencias[^/]*|credentials[^/]*|secrets[^/]*|tokens?[^/]*)\.json$|(^|/)(\.env(?:\.[^/]*)?|[^/]+\.(?:pem|key|pfx|p12|log|zip|jpe?g|png|mp4))$'
$rastreados = @(& $git -C $Destino ls-files)
if ($LASTEXITCODE -ne 0) { throw 'Não foi possível verificar os arquivos rastreados pelo Git.' }
$sensivelRastreado = @($rastreados | Where-Object { $_ -match $nomeSensivel })
if ($sensivelRastreado.Count) {
    throw ("Arquivos potencialmente sensíveis já rastreados pelo Git: " + ($sensivelRastreado -join ', ') + '. Remova-os do índice com git rm --cached, preservando os arquivos locais, antes de continuar.')
}
$jaPreparados = @(& $git -C $Destino diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { throw 'Não foi possível inspecionar o índice do Git.' }
$inesperados = @($jaPreparados | Where-Object { -not $Permitidos.Contains($_.Replace('\', '/')) })
if ($inesperados.Count) {
    throw ('Há alterações já preparadas fora dos arquivos do app: ' + ($inesperados -join ', ') + '. Revise-as antes de executar o atualizador.')
}

# Confere apenas os arquivos públicos do pacote; nenhum JSON ou preferência é copiado.
$segredoLiteral = '(?im)\b(?:apiKey|apiSecret|api_key|api_secret|localKey|local_key|access_token|client_id|client_secret|device_id)\b\s*[:=]\s*["''](?=[^"'']{16,}["''])[^"'']+["'']|\b(?:gh[opsu]_[A-Za-z0-9_]{25,}|AKIA[0-9A-Z]{16}|(?:eb|bf)[0-9a-f]{14,20})\b|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'
foreach ($item in $Arquivos) {
    $origem = Join-Path $Fonte ($item.Replace('/', [IO.Path]::DirectorySeparatorChar))
    if (-not (Test-Path -LiteralPath $origem -PathType Leaf)) { throw "Arquivo ausente no pacote: $item" }
    if ($item -ne 'elgin.ico') {
        $conteudo = [IO.File]::ReadAllText($origem)
        if ($conteudo -match $segredoLiteral) { throw "Possível credencial ou ID particular em $item. Revise o arquivo antes de copiar." }
    }
}

$backup = Join-Path $env:TEMP ('ElginControlBackup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$alterados = 0
foreach ($item in $Arquivos) {
    $relativo = $item.Replace('/', [IO.Path]::DirectorySeparatorChar)
    $origem = Join-Path $Fonte $relativo
    $alvo = Join-Path $Destino $relativo
    if ((Test-Path -LiteralPath $alvo -PathType Leaf) -and
        (Get-FileHash -LiteralPath $origem -Algorithm SHA256).Hash -eq (Get-FileHash -LiteralPath $alvo -Algorithm SHA256).Hash) {
        continue
    }
    if (Test-Path -LiteralPath $alvo -PathType Leaf) {
        $copia = Join-Path $backup $relativo
        [void](New-Item -ItemType Directory -Path (Split-Path -Parent $copia) -Force)
        Copy-Item -LiteralPath $alvo -Destination $copia -Force
    }
    [void](New-Item -ItemType Directory -Path (Split-Path -Parent $alvo) -Force)
    Copy-Item -LiteralPath $origem -Destination $alvo -Force
    $alterados++
}

& $git -C $Destino add -- $Arquivos
if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar os arquivos do projeto para o commit.' }
& $git -C $Destino diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'O diff preparado contém problemas de formatação. Revise antes do commit.' }
$preparados = @(& $git -C $Destino diff --cached --name-only)
$inesperados = @($preparados | Where-Object { -not $Permitidos.Contains($_.Replace('\', '/')) -or $_ -match $nomeSensivel })
if ($inesperados.Count) { throw ('Commit contém arquivos inesperados: ' + ($inesperados -join ', ')) }

# Revisa também outros arquivos de texto que já constavam no índice do repositório.
$rastreados = @(& $git -C $Destino ls-files)
foreach ($item in $rastreados) {
    if ($item -notmatch '(?i)\.(?:py|ps1|html|md|txt|json|ya?ml|toml|ini|cfg|sh)$') { continue }
    $texto = @(& $git -C $Destino show (':' + $item)) -join "`n"
    if ($LASTEXITCODE -ne 0) { throw "Não foi possível inspecionar o arquivo rastreado $item." }
    if ($texto -match $segredoLiteral) { throw "Possível credencial ou ID particular no arquivo rastreado $item. Revise antes de commitar." }
}

Write-Host "Atualizados $alterados arquivos em $Destino"
if (Test-Path -LiteralPath $backup) { Write-Host "Cópias dos arquivos substituídos: $backup" }
Write-Host 'Arquivos preparados para commit:'
& $git -C $Destino diff --cached --stat
Write-Host 'Confira o diff com: git diff --cached'
Write-Host 'Depois do seu exame: git commit -m "Atualiza interface e integração Elgin"'
