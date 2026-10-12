# Elgin Control Tray

Mini aplicativo para Windows que controla um ar-condicionado compatível com Tuya
pela rede local, com painel HTML em PyWebView e menu na área de notificação.
Projeto independente, sem vínculo com Elgin ou Tuya. Mapeado a partir de um
Elgin Eco Dream HIFI09C2WA; outros modelos e firmwares não foram validados.

## Recursos

- Liga/desliga, temperatura, modos e velocidades de ventilação.
- Ventilação silenciosa, Turbo, Sleep, Display e Oscilação.
- Ícone de folha (Eco/UVC): campo identificado; significado físico ainda incerto.
- Tomada: ligar/desligar, contagem regressiva e medições de W/A/V.
- Histórico cloud: total, meses do ano e dias do mês, com gráfico e tabela em kWh.
- Painel web nativo atualizado a cada 4 segundos; mostra mudanças feitas no controle físico.
- Inicialização com a sessão do Windows e execução sem console usando pythonw.exe.
- Temporizadores experimentais: campos mapeados, envio e execução ainda não validados.

## Instalação

Requisitos: Windows com WebView2 Runtime, Python com Tcl/Tk para a bandeja, rede local compartilhada com o ar e
`devices.json` gerado pelo [TinyTuya](https://github.com/jasonacox/tinytuya).

Na pasta do projeto, execute uma vez no PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\Instalar.ps1"
```

O instalador copia o app para `%LOCALAPPDATA%\ElginControl`, instala dependências
e cria atalhos na Área de Trabalho, no menu Iniciar e na Inicialização.
Para não iniciar com o Windows, acrescente `-SemInicializacao`.
Não precisa de administrador. Bypass vale somente para esse processo.
Feche uma versão anterior pelo menu Sair antes de atualizar.

Selecione seu `devices.json` em Configurações, escolha o ar e a tomada e salve.
Deixe IP local vazio para descobrir o endereço atual do ar na LAN; o campo vazio
não reutiliza o endereço antigo registrado pelo wizard em `devices.json`.
O atalho abre o painel web. Fechar a janela encerra o painel; a bandeja continua
em segundo plano quando iniciada com o Windows. Clique no ícone para reabrir.
Botão direito no ícone > Sair encerra a bandeja.
Veja [LEIA-ME.md](LEIA-ME.md) para detalhes, limites e solução de problemas.

## Dados privados

**Nunca publique `devices.json`: ele contém a chave local do aparelho.**
Mantenha credenciais fora do repositório, por exemplo em
`%USERPROFILE%\elgin-controle`, e selecione esse caminho na interface.
O app não precisa de Access ID nem Access Secret para controlar pela LAN.

O `.gitignore` exclui arquivos TinyTuya, preferências, ambientes, certificados,
caches, logs e capturas. Isso não remove arquivos já versionados ou histórico.
Revise `git diff --cached` antes de publicar. Não exponha tokens, chaves, IDs
pessoais ou capturas de credenciais em commits, issues ou documentação.
O código não inclui uma chave nem um dispositivo pessoal fixado.

## Atualizar o repositório local no Windows

Extraia o pacote atualizado e, na pasta que contém `Atualizar-repositorio.ps1`,
execute no PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\Atualizar-repositorio.ps1"
```

O destino padrão é a pasta `elgin-control-tray` em Documentos do usuário atual.
Se ela estiver em outro local, use `-Destino "C:\caminho\elgin-control-tray"`.
O script exige um repositório Git existente, copia somente os arquivos públicos
do projeto, preserva `.git` e os JSON locais, faz backup dos arquivos substituídos
em `%TEMP%` e prepara os arquivos copiados com `git add`. Ele interrompe a
atualização se detectar arquivos de credenciais já rastreados ou alterações
inesperadas previamente preparadas. Confira o resultado antes do commit:

```powershell
git -C "$HOME\Documents\elgin-control-tray" diff --cached
git -C "$HOME\Documents\elgin-control-tray" status --short
```

O script não cria o commit nem publica o repositório. Um `.gitignore` novo
também não apaga segredos que tenham entrado em commits anteriores.

## Desenvolvimento

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe app.py --demo
```

Para iniciar a bandeja manualmente: `.\.venv\Scripts\pythonw.exe tray.py`.
Código: `controller.py` (protocolo), `bridge.py` (API local da janela),
`app.py` e `code.html` (PyWebView), `legacy_app.py` e `tray.py` (bandeja)
e `Instalar.ps1` (instalação). Testes simulados não usam credenciais.

## Mapeamento

| DPS | Função | Valores |
|---|---|---|
| 1 | Energia | booleano |
| 2 | Temperatura configurada | inteiro em °C |
| 3 | Temperatura ambiente, compatível com leituras observadas | leitura |
| 4 | Modo | auto, cold, wind, wet |
| 5 | Ventilação | auto, low, middle, high, mute, strong |
| 11 | Ícone de folha (Eco/UVC) | booleano |
| 25 | Sleep | booleano |
| 31 | Oscilação | off, same |
| 36 | Display | booleano |
| 101 / 103 | Habilitação / duração Timer ON | booleano / texto HHMM |
| 102 / 104 | Habilitação / duração Timer OFF | booleano / texto HHMM |

Energia e temperatura foram testadas por comando local no aparelho do usuário.
Outros campos foram identificados por comparação de estados no Smart Life.
Sleep/Turbo só aparecem em cold; Timer ON só aparece com o ar desligado.
O app mantém essas restrições. Campos não identificados não são escritos.
Intervalos de temperatura e timer específicos do firmware ainda não validados.

Testes do controlador passaram no Linux. Interface, instalador e bandeja ainda
precisam de validação no Windows do usuário.

## Tomada de alimentação (EKAZA / Tuya)

O seletor de conexão distingue o ar da tomada, usando dois registros do mesmo
`devices.json`. Atualize esse arquivo com `tinytuya wizard` antes de configurar.
Selecione o ar no primeiro seletor e a tomada no campo Tomada de alimentação.
Informe o protocolo da tomada conforme o scanner (3.5 no caso testado).
A preferência é salva localmente; nenhum ID pessoal é fixado no código.

Ligar ar consulta a tomada, ativa seu DPS 1 se estiver desligada, confirma o relé,
aguarda o ar responder pela LAN por aproximadamente 90 segundos e envia o DPS 1
para ligar o ar. O prazo pode incluir o tempo de descoberta de IP. Falhas são
mostradas ao usuário e não causam corte automático de alimentação.
Desligar ar mantém a tomada ligada. Na aba Tomada e consumo, Desligar tomada
primeiro tenta desligar o ar e então corta a alimentação. Por ser um comando
explícito para o relé, ele ainda corta a tomada se o ar não responder; nesse
caso a tela informa que não houve confirmação do ar.
Com a tomada desligada, o app informa Sem alimentação e mantém Ligar habilitado.
A conexão a dois dispositivos usa seus respectivos protocolos e chaves.

O relé foi observado desligado/ligado por consulta local; a sequência completa
foi testada com dispositivos simulados, não no equipamento real. A compatibilidade
elétrica da tomada com o ar-condicionado ainda não foi verificada. O nome de
produto 10A na plataforma não basta para confirmar essa compatibilidade.
Timer ON no aparelho exige alimentação contínua; não liga uma tomada desligada.

## Consumo cloud e temporizador da tomada

Abra a aba **Tomada e consumo**. Selecione a tomada EKAZA na área Conexão
e protocolo 3.5. Atualizar tomada consulta o relé, corrente, potência, tensão
e contagem regressiva. Ligar tomada alimenta o ar, sem ligá-lo automaticamente;
Ligar ar mantém a sequência coordenada de alimentação e espera pelo Wi-Fi.

O temporizador escreve o DP 9 em segundos: de 1 a 1440 minutos. Cancelar envia
zero sem mudar o relé. Ele é executado pela tomada mesmo com o PC desligado.
Foi validado no equipamento que uma tomada desligada liga ao terminar;
a inversão de ligada para desligada ainda requer validação no aparelho.
O programa informa essa limitação antes de programar. Use o Timer OFF do ar
quando quiser desligar somente o aparelho sem interromper sua alimentação.

Para consumo, selecione **Abrir tinytuya.json** (arquivo do wizard, diferente
de devices.json), escolha ano/mês e clique **Consultar consumo**. O app busca
esse arquivo também junto ao devices.json ou em %USERPROFILE%\elgin-controle.
Beta APIs deve estar autorizada e IoT Core válido. O histórico exige internet;
os controles continuam pela LAN. O arquivo guarda API Key/Secret e não deve
ser publicado. As preferências guardam somente seu caminho, sem copiar chaves.

As APIs /statistics/total, /statistics/months e /statistics/days para add_ele
foram verificadas no dispositivo: os valores retornados já estão em kWh.
O DP 17 local é incremento escalado, e não é somado por polling. Dado ausente
fica ausente (não é substituído por zero). O mês em andamento é parcial;
os dias são consultados até a data local do PC. O PC deve usar o fuso correto.
A consulta de um mesmo mês usa cache em memória de 15 minutos.

Esta versão passou em 28 testes simulados e na verificação de sintaxe.
Interface e bandeja não foram executadas neste ambiente; a validação final
de instalação e uso deve ocorrer no Windows.
