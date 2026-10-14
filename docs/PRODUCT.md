# Elgin AC

<!-- impeccable:product-schema 1 -->

## Platform

Windows desktop (Python/Tkinter).

## Users

O proprietário do ar-condicionado Elgin/Tuya, controlando o aparelho no mesmo computador e rede local.

## Product Purpose

Controlar rapidamente o ar-condicionado e a tomada EKAZA que o alimenta sem abrir o app de celular: ligar/desligar, ajustar temperatura, modo, ventilação, aletas, Dormir, Eco/Protect, Mudo, Display, Turbo, Timer de desligamento de 1 hora e consultar/controlar a tomada.

## Operating Context

O app permanece na bandeja do Windows. Um clique no ícone abre uma janela compacta; clicar fora a recolhe. Deve iniciar com o Windows, conforme solicitado pelo usuário.

## Capabilities and Constraints

- Usa a comunicação LAN existente com `tinytuya`, Device ID e Local Key em `config.json`.
- A EKAZA usa `plug_config.json` local e ignorado pelo controle de versão, com protocolo Tuya 3.5. O DP 1 comanda a tomada; os DPs 18, 19 e 20 informam corrente, potência e tensão.
- Quando o ar está confirmado desligado, o sistema consulta seu estado novamente antes de cortar a energia. Se o ar estiver ligado ou seu estado for desconhecido, o botão da tomada abre uma confirmação explícita de corte; nunca desliga automaticamente. Quando a tomada está desligada, a interface do ar continua acessível, mas seus comandos não fingem sucesso.
- Redescobre o IP por Device ID quando o endereço salvo deixa de responder.
- Mostra somente dados e comandos confirmados para este Elgin; recursos exclusivos do Samsung WindFree não são expostos.
- O DP 11 aparece como Protect no app nativo; o proprietário confirmou que essa função é o modo Eco do aparelho, rótulo usado no atalho principal. Turbo e Mudo são valores especiais da velocidade do ventilador (DP 5). O Timer de 1 hora usa DP 104 = `0100` e DP 102 liga/desliga.
- A interface deve continuar utilizável quando o aparelho está offline, sem simular sucesso de comandos.
- A vista da tomada separa potência/tensão/corrente instantâneas do consumo em kWh e abre o histórico por ano, mês e dia, com barras selecionáveis, paginação e navegação por teclado. Leituras instantâneas indisponíveis ou antigas aparecem como `--` no resumo; os totais históricos mantêm sua origem visível.
- O detalhamento mostra o custo estimado do mês atual e do mês selecionado: consumo em kWh × tarifa de R$ 1,40/kWh, configurável em energy_config.json. Valores monetários usam centavos, arredondamento decimal e formato brasileiro. Ausência de consumo não é apresentada como custo zero; não é previsão do mês completo nem fatura com cobranças adicionais.
- Consumo registrado da tomada é consultado via Tuya Cloud nos endpoints statistics/total, months e days, com code add_ele, usando energy.py/EnergyBridge e o Device ID da tomada de plug_config.json. Tinytuya.json é a única fonte das credenciais Cloud, não é copiado ou registrado em logs e está ignorado no Git. A Cloud tem prioridade na apresentação, cache persistido isolado no SQLite, atualização normalmente a cada 15 minutos e consulta manual pelo cabeçalho. Rede/permissões não bloqueiam o controle LAN; falhas preservam cache identificado como desatualizado. Referências e estimativas LAN nunca são somadas ao consumo Cloud.
- Persiste leituras e totais diários em `energy_history.sqlite3`, na pasta do projeto, a partir das consultas LAN bem-sucedidas do app. A consulta periódica existente ocorre a cada 15 segundos em segundo plano, inclusive com a janela recolhida na bandeja. Nesta EKAZA, o DP 17 (`add_ele`, escala 3) é incremental; `energy_config.json` mantém `total_dp: null` e o app estima kWh integrando potência, excluindo intervalos maiores que 300 segundos. O histórico é parcial, depende do app/PC operantes e não recupera consumo durante desligamento do PC ou lacunas excluídas. Um contador TOTAL confirmado configurado permite usar deltas, tratar reset e ratear intervalos à meia-noite.
- Os dados Smart Life de 11/10/2026 ficam em tabelas de referência separadas e nunca são somados às medições locais. Sem contador, o acumulado é **Total local**; o fallback inicial é **Total ref.**. Hoje e meses pendentes sem cobertura aparecem como `--`, distinguindo ausência de leitura de zero observado. [ENERGY.md](ENERGY.md) descreve o acesso ao detalhe, a persistência e como reiniciar para carregar a versão.

## Brand Commitments

O Quick Settings / Flyout do Windows 11 fornecido no ZIP do Stitch em 14/10/2026 determina a composição compacta, as superfícies escuras e os acentos azuis. A interface segue o pedido explícito: 380 × 560 px, temperatura acima da grade e seis atalhos de Modo, Vento, Eco, Tomada EKAZA, Dormir e Display. Recursos e rótulos permanecem vinculados aos comandos confirmados do Elgin e da EKAZA.
