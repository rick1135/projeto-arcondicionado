# Histórico de energia da tomada EKAZA

## Como abrir

O detalhamento exibe **Custo estimado do mês**: kWh do mês atual × **R$ 1,40/kWh**. Ao abrir um mês na lista, o custo estimado corresponde ao período selecionado. A tarifa fica em `price_per_kwh_brl` no `energy_config.json`; reinicie o app após alterá-la. É uma conversão simples do consumo disponível, não uma previsão do fechamento do mês nem a fatura completa: não adiciona cobranças além da tarifa informada. Dados ausentes mostram `R$ --`, e consumo zero confirmado mostra `R$ 0,00`. A origem do consumo (Cloud, cache, estimativa LAN ou referência) continua visível.

No painel do Elgin, abra a vista da tomada EKAZA. Em **Eficiência e Consumo**, escolha **Ver detalhamento de consumo**. O resumo mostra o consumo de hoje, corrente, potência, tensão, total e os meses disponíveis. Selecione um mês para ver o gráfico diário; clique em uma barra para selecionar o dia e use as setas para percorrer janelas de oito dias. A lista mensal do app mostra quatro meses por página. Voltar retorna ao resumo ou à tomada, preservando o contexto e o foco. Tab e Shift+Tab percorrem as ações de energia; Enter ativa a ação focada.

Para carregar esta versão, use **Sair** no menu do ícone da bandeja e execute `Iniciar Elgin.cmd` novamente.

## O que fica salvo

### Consumo registrado na Tuya Cloud

O painel agora prioriza o consumo registrado pela Tuya Cloud: total, hoje, mês atual, totais mensais e dias do mês escolhido. Use a ação de detalhamento na tomada, selecione o ano/mês e clique nas barras. O botão circular de atualizar no cabeçalho consulta novamente a nuvem; “Atualizar telemetria” também atualiza o consumo, além dos sensores LAN.

`energy.py` fornece o cliente e `EnergyBridge`, em `bridge.py`, adapta os dados ao app Tk. O restante de `DeviceAPI` em `bridge.py` pertence ao projeto de referência e depende de `controller.py`; não é usado pelo app atual. A integração usa o **Device ID da tomada em `plug_config.json`**, não o `apiDeviceID` do wizard. As credenciais são lidas exclusivamente de `tinytuya.json` na pasta do projeto. Não foram copiadas para outra configuração ou banco. Esse arquivo e `devices.json` estão ignorados no Git; este diretório não é atualmente um repositório Git.

Endpoints somente leitura, assinados pelo TinyTuya:

- `GET /v1.0/devices/{device_id}/statistics/total`, com `code=add_ele`.
- `GET /v1.0/devices/{device_id}/statistics/months`, com `code=add_ele`, `start_month=AAAAMM`, `end_month=AAAAMM`, no mesmo ano.
- `GET /v1.0/devices/{device_id}/statistics/days`, com `code=add_ele`, `start_day=AAAAMMDD`, `end_day=AAAAMMDD` e `stat_type=sum`.

Os valores Cloud já vêm em kWh: não recebem novamente a escala do DP LAN. Consultas periódicas usam cache de 15 minutos; falhas têm intervalo mínimo de 60 segundos antes de uma nova tentativa automática. A atualização manual força uma consulta do mês da tela. O mês atual também é consultado em segundo plano. Cada operação HTTP tem limites de conexão/leitura; uma fila separada mantém os comandos LAN responsivos.

Somente medições e datas são persistidas na tabela `cloud_energy_cache` do SQLite, isoladas por Device ID e mês. Não são salvos tokens, headers, respostas brutas ou credenciais. O cache continua disponível ao reiniciar/offline e aparece como desatualizado quando expira ou a consulta falha. Hoje/dias não retornados aparecem como `--`, nunca como zero inventado. Um mês Cloud ainda não consultado não é preenchido com barras das fotografias. Antes de existir cache Cloud, a estimativa LAN/referência permanece claramente identificada; nunca é somada ao histórico Cloud.

Se a consulta falhar, confira a conexão, a região do projeto, a validade do IoT Core e a autorização para estatísticas. A interface exibe uma mensagem controlada com o código numérico, sem ecoar a resposta da API. O debug Cloud do TinyTuya é isolado, pois a implementação original pode registrar headers e tokens. Para diagnóstico somente leitura, execute `.venv\Scripts\python.exe -X utf8 energy.py` na pasta do projeto. Também aceita `--year 2026 --month 9`.

Contrato dos parâmetros: [documentação oficial da Tuya](https://developer.tuya.com/en/docs/cloud/device-data-statistic?id=Ka7g7nvnad1rm).

### Estimativa LAN independente

O app salva leituras e totais diários em `energy_history.sqlite3`, na pasta do projeto. A consulta existente ocorre a cada 15 segundos, em segundo plano, enquanto o app está aberto, inclusive com a janela recolhida na bandeja. Leituras bem-sucedidas de atualização manual ou de comandos da tomada também passam pelo registro. Uma operação ainda ocupada pode adiar uma consulta.

Nesta EKAZA, o DP 17 (`add_ele`, escala 3) é incremental, não um contador total. Por isso, `energy_config.json` mantém `total_dp: null`: o app não soma snapshots do DP 17. O consumo local é estimado pela integração da potência em W, usando a média entre duas leituras e convertendo o intervalo para kWh. Intervalos maiores que 300 segundos são excluídos. O histórico é parcial: depende do app e do PC operantes, e não recupera o consumo ocorrido com o PC desligado ou em lacunas excluídas.

Se outro aparelho fornecer um contador **TOTAL confirmado**, seu DP e sua escala podem ser configurados em `energy_config.json`. Nesse modo, o app usa a diferença entre leituras. Uma queda do contador cria uma nova base, sem consumo negativo nem salto fictício. Intervalos que cruzam meia-noite são rateados pelo tempo entre os dias no horário local UTC−03; esse rateio não mede em qual instante a energia foi consumida.

## Como interpretar os valores

- **W, V e A** são métricas instantâneas, apresentadas em três cards equivalentes. No resumo, leituras indisponíveis ou antigas são ocultadas como `--`; o estado offline não transforma a última leitura em uma medição atual.
- **kWh** é consumo acumulado. A Tuya Cloud usa **Total**; sem cache Cloud/contador total, o resumo usa **Total local** para a soma dos intervalos registrados. O contador LAN confirmado usa **Total**. O fallback inicial usa **Total ref.**.
- Hoje sem intervalo monitorado aparece como `--`. Um mês iniciado sem cobertura também mostra `--`, com origem pendente. Sem barra significa ausência de leitura; zero significa consumo observado zero.

## Referências iniciais

`energy_reference.json` contém a referência Smart Life de **11/10/2026**: 1,28 kWh naquele dia, total de 139,54 kWh e os totais mensais transcritos. As demais barras diárias de outubro são aproximações visuais da foto. Essas referências ficam nas tabelas `reference_months` e `reference_days`, separadas das leituras locais, e nunca entram no cálculo de deltas ou na estimativa.

Antes das primeiras leituras, o app pode mostrar a referência datada como dados iniciais. Quando um mês passa a ter histórico local, sua série usa somente os dados locais; os dias ausentes não são preenchidos com a foto. Os HTMLs em `stitch_smart_ac_remote_ui` são prévias interativas com dados de referência e curva ilustrativa, sem acesso ao histórico real do app.

## Verificação desta entrega

O fluxo e a persistência foram cobertos por 45 testes aprovados, incluindo endpoints, cache após reinício, unidades, validação de datas, erros sem vazamento e fila Cloud independente. A consulta real dos três endpoints foi bem-sucedida, retornando total, meses e dias. A revisão anterior cobriu cinco vistas HTML em 320/390/480 px; esta integração preserva essas prévias ilustrativas e usa os componentes reais Tk para mostrar dados Cloud. O painel Tk foi verificado em 100%/80%, com limites de textos e estados offline. A navegação usa entrada horizontal de 180 ms e restaura o foco ao voltar.
