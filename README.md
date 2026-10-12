# Elgin Control Tray

Mini aplicativo para Windows que controla um ar-condicionado compatível com Tuya
pela rede local, com menu na área de notificação e janela de configurações.
Projeto independente, sem vínculo com Elgin ou Tuya. Mapeado a partir de um
Elgin Eco Dream HIFI09C2WA; outros modelos e firmwares não foram validados.

## Recursos

- Liga/desliga, temperatura, modos e velocidades de ventilação.
- Ventilação silenciosa, Turbo, Sleep, Display e Oscilação.
- Ícone de folha (Eco/UVC): campo identificado; significado físico ainda incerto.
- Inicialização com a sessão do Windows e execução sem console usando pythonw.exe.
- Temporizadores experimentais: campos mapeados, envio e execução ainda não validados.

## Instalação

Requisitos: Windows, Python com Tcl/Tk, rede local compartilhada com o ar e
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

Selecione seu `devices.json` na interface e conecte. Fechar/minimizar mantém
o processo ativo; botão direito no ícone > Sair encerra.
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

## Desenvolvimento

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe app.py --demo
```

Para iniciar a bandeja manualmente: `.\.venv\Scripts\pythonw.exe tray.py`.
Código: `controller.py` (protocolo), `app.py` (Tkinter), `tray.py` (bandeja)
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
