# Controle Elgin — área de notificação do Windows

Esta versão fica perto do relógio, com um floco azul. O Windows pode colocá-lo na
seta ^ dos ícones ocultos. Não precisa executar BAT e não abre um terminal durante
uso normal. A janela aparece apenas quando você pede para abrir os controles.

## Instalação — uma vez

1. Extraia o ZIP. Abra a pasta que contém Instalar.ps1.
2. Clique com o botão direito no espaço vazio da pasta e escolha Abrir no Terminal.
3. Execute:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\Instalar.ps1"
```

A política Bypass vale somente para esse processo; não muda a política global.
Não precisa executar como administrador. O instalador usa o ambiente Python já
criado em %USERPROFILE%\elgin-venv, instala pystray e Pillow se necessário e copia
os arquivos para %LOCALAPPDATA%\ElginControl. Se o ambiente anterior não existir,
cria um ambiente próprio na pasta instalada. A instalação precisa de internet.

Ele cria Controle Elgin na Área de Trabalho, no menu Iniciar e na pasta de
Inicialização do usuário. Inicia com sua sessão do Windows, não antes de login.
Após instalar, você pode remover a pasta extraída e o ZIP; não apague a pasta
instalada nem o ambiente Python utilizado.

Para instalar sem início automático, acrescente -SemInicializacao ao comando.
Para desativar o início automático depois, execute Desativar-inicio-automatico.ps1
ou desative Controle Elgin nos aplicativos de inicialização do Windows.

## Primeira configuração

O aplicativo procura devices.json em %USERPROFILE%\elgin-controle ou ao lado do
código instalado. Se não encontrar, abra Configurações e informe o caminho.
Selecione o ar e a tomada, deixe o campo IP local vazio para descobrir o endereço
atual do ar, e clique em Salvar & Reconectar. O caminho do arquivo,
IDs selecionados e IP são lembrados para a próxima abertura. A chave não é copiada para
preferencias.json, permanecendo somente no devices.json original.

Feche Smart Life e Elgin Smart para evitar disputar a conexão local. A máquina
precisa estar na mesma rede do ar. Se o IP mudar, abra o controle e deixe IP vazio
para descoberta, ou informe o novo IP.

## Uso

- Clique no floco para abrir a janela (em algumas configurações do Windows é
  necessário duplo clique). Botão direito abre o menu rápido.
- No menu: Ligar/Desligar, temperatura +/-1 °C, modos, velocidades, folha, Sleep,
  Display e Oscilação. A janela completa também permite inserir temperatura e timer.
- Fechar pelo X encerra a janela web. A bandeja continua ativa. Minimizar usa
  o comportamento normal do Windows.
- Para encerrar de verdade: botão direito no ícone > Sair. Ele voltará no próximo
  login, caso o início automático esteja habilitado.
- Abrir o atalho novamente não cria uma segunda janela web.
- Estado atualizado a cada quatro segundos enquanto a janela está aberta; a
  bandeja consulta a cada 10 a 30 segundos. Em falhas, tenta reconectar periodicamente.
  Nenhum comando é enviado para trocar configurações durante a reconexão.
- Windows suspenso ou desligado: o processo não continua funcionando. É um app de
  sessão em segundo plano, não um serviço do Windows.

## Limites conhecidos

Sleep e Turbo são oferecidos apenas em Refrigerar. Temperatura precisa respeitar
os limites oferecidos pelo Smart Life; o intervalo específico não foi identificado.
Silenciosa controla a ventilação e não desliga bipes.
Folha (Eco/UVC) usa DPS 11; o significado físico ainda não foi confirmado.

Temporizadores são EXPERIMENTAIS: campos mapeados por leitura, mas ainda não houve
validação do envio pelo computador, dos limites nem da execução ao término.
A janela avisa antes de programar. ON exige o ar desligado. Confira no Smart Life
após o teste e cancele. Uma falha intermediária pode deixar um timer desativado ou
parcialmente configurado. Não presuma execução enquanto esse recurso não for validado.

Ações locais: energia 1, temperatura 2, modo 4 (auto/cold/wind/wet), ventilação 5
(auto/low/middle/high/mute/strong), folha 11, Sleep 25, oscilação 31 (off/same),
display 36. Timer ON: 101/103; OFF: 102/104; duração como texto HHMM.
Não escrevemos nos DPS ainda não identificados.

## Credenciais e código

Não forneça Access ID nem Access Secret. Não compartilhe devices.json.
O app usa pythonw.exe para executar sem console; não é um EXE independente.
Código editável incluso: tray.py, app.py, bridge.py, code.html, controller.py e instalador PowerShell.
Você pode fixar o atalho no menu Iniciar. O controle permanente fica na área de
notificação; isso é diferente de um botão permanentemente fixado na barra principal.

Testes do controlador: python -m unittest discover -s tests -v.
A lógica foi testada com simulações. Interface da bandeja, instalador e integração
real ainda precisam ser validados no Windows do usuário; este ambiente é Linux.

## Atualização com tomada

Feche a versão anterior pelo ícone > Sair e execute Instalar.ps1 novamente.
Reabra o app. Se o devices.json não mostrar a tomada, use Abrir devices.json e
selecione a versão atualizada pelo wizard. No primeiro seletor escolha o ar e
no campo Tomada de alimentação escolha a tomada. O campo à direita é o protocolo
Tuya da tomada: 3.5 conforme o scanner realizado nesta sessão. Clique em Atualizar.

Ligar liga a tomada e aguarda a rede do ar antes de ligar o aparelho. Desligar
na aba Ar condicionado somente desliga o ar e preserva a alimentação. Na aba
Tomada e consumo, Desligar tomada tenta desligar o ar e corta o relé mesmo se
o ar não responder, pois é um corte manual solicitado pelo usuário.
Timer ON precisa que a tomada permaneça ligada. Teste a sequência no seu Windows.


Atualização: veja no README a seção Consumo cloud e temporizador da tomada.
Feche o app antigo pelo menu Sair antes de executar Instalar.ps1 novamente.
As credenciais permanecem nos JSON externos; o instalador mantém preferencias.json.

## Painel web (PyWebView)

A versão nova abre code.html pelo app.py. Abra Configurações, preencha o caminho
do devices.json, selecione ar e tomada, e informe o protocolo da tomada (3.5
no dispositivo já mapeado). O caminho tinytuya.json é opcional para os botões
locais; ele é usado somente em Consultar Nuvem. O painel lê os dispositivos
a cada quatro segundos e exibe — quando não houver medição confirmada.
O atalho da Área de Trabalho abre o painel; o processo de bandeja continua
independente e também o abre ao clicar no ícone. Fechar a janela encerra suas
consultas; use Sair na bandeja para encerrar o processo da bandeja.
O layout usa Tailwind e Lucide via CDN: os estilos e ícones dependem de internet,
enquanto os comandos LAN seguem locais. Não publique devices.json, tinytuya.json
nem preferencias.json.
Se a tomada mostrar telemetria, mas o ar ficar "Sem resposta do ar", clique em
Reconectar ar após salvar o IP vazio. O comando consulta o ar antes de decidir
se deve ligá-lo ou desligá-lo. Confira se a chave local e o protocolo do ar
correspondem ao dispositivo selecionado caso ele continue sem responder.
