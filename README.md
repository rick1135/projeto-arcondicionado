# Elgin Control Tray

Aplicativo para Windows que controla um ar-condicionado Elgin compatível com
Tuya pela rede local. A interface é exibida em uma janela PyWebView e também
fica disponível na área de notificação do Windows.

O projeto foi desenvolvido e testado com um Elgin Eco Dream Inverter
HIFI09C2WA e uma tomada inteligente EKAZA. Outros modelos podem exigir ajustes
nos códigos DPS e no protocolo de comunicação.

<p align="center">
  <img
    src="docs/images/painel.png"
    alt="Painel do Elgin Control Tray"
    width="1000"
  >
</p>

## Funcionalidades

### Ar-condicionado

- Ligar e desligar o aparelho.
- Ajustar a temperatura entre 16 °C e 31 °C.
- Selecionar os modos frio, seco, ventilação e automático.
- Alterar a velocidade para silenciosa, baixa, média ou turbo.
- Ativar Eco/UVC, Sleep, Display e Oscilação.
- Configurar os temporizadores de ligar e desligar do aparelho.
- Detectar o estado alterado pelo controle remoto físico ou pelo aplicativo.
- Redescobrir automaticamente o endereço IP local quando necessário.

### Tomada inteligente

- Ligar e desligar o relé da tomada.
- Ligar o ar depois de confirmar que a tomada está energizada.
- Exibir potência, corrente e tensão em tempo real.
- Configurar uma contagem regressiva em minutos.
- Consultar o consumo total, mensal e diário em kWh.
- Visualizar o histórico em gráfico, com detalhes ao passar o mouse ou clicar
  em um dia ou mês.

## Estrutura do projeto

| Arquivo | Responsabilidade |
|---|---|
| `app.py` | Inicia a janela PyWebView e conecta o HTML à API Python. |
| `bridge.py` | Expõe à interface as funções de controle, configuração e consulta. |
| `controller.py` | Controla o ar e a tomada pela rede local usando TinyTuya. |
| `energy.py` | Consulta o histórico de consumo nas APIs cloud da Tuya. |
| `code.html` | Interface do painel e lógica JavaScript. |
| `tray.py` | Mantém o aplicativo na área de notificação do Windows. |
| `legacy_app.py` | Interface auxiliar usada pela bandeja e pelas configurações. |
| `Instalar.ps1` | Instala dependências e cria os atalhos do aplicativo. |
| `Desativar-inicio-automatico.ps1` | Remove o início automático com o Windows. |
| `tests/` | Testes automatizados do controlador, da ponte e do histórico. |

## Requisitos

- Windows 10 ou posterior.
- Python 3.10 ou posterior.
- WebView2 Runtime.
- Python com suporte a Tcl/Tk para o ícone da bandeja.
- Ar-condicionado e computador conectados à mesma rede local.
- `devices.json` gerado pelo TinyTuya.
- `tinytuya.json` gerado pelo wizard do TinyTuya para consultar o consumo cloud.

## Instalação

Abra o PowerShell na pasta do projeto e execute:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\Instalar.ps1"
```

O instalador cria um ambiente virtual, instala as dependências e cria atalhos
na Área de Trabalho, no menu Iniciar e na inicialização do Windows.

Para instalar sem iniciar automaticamente com o Windows:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\Instalar.ps1" -SemInicializacao
```

## Configuração

1. Abra o aplicativo pelo atalho criado pelo instalador.
2. Abra **Configurações**.
3. Selecione o `devices.json` gerado pelo TinyTuya.
4. Escolha o dispositivo do ar e, se aplicável, o dispositivo da tomada.
5. Informe o protocolo da tomada. O modelo testado usa o protocolo `3.5`.
6. Para consultar o consumo, selecione também o `tinytuya.json`.
7. Deixe o campo de IP do ar vazio para usar a descoberta automática na rede.
8. Salve as configurações.

Os comandos do ar e da tomada usam a rede local. O histórico de consumo usa a
API cloud da Tuya e precisa de internet e de um `tinytuya.json` válido.

## Execução manual

Para abrir o painel diretamente:

```powershell
python app.py
```

Para iniciar somente a bandeja:

```powershell
pythonw tray.py
```

O painel pode ser reaberto pelo ícone na bandeja. Para encerrar completamente
o aplicativo, use **Sair** no menu do ícone.

## Desenvolvimento e testes

Crie o ambiente virtual e instale as dependências:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Execute os testes:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Os testes usam dispositivos simulados e não precisam das chaves ou dos
arquivos de configuração do usuário.

## Limitações conhecidas

- O mapeamento dos DPS foi validado no HIFI09C2WA e pode variar em outros
  aparelhos.
- Sleep e Turbo ficam disponíveis somente no modo frio nesse modelo.
- Os temporizadores do aparelho dependem do firmware e ainda são tratados como
  recurso experimental.
- A tomada deve ser compatível com a carga elétrica do ar-condicionado. O app
  não substitui a verificação da instalação elétrica.
