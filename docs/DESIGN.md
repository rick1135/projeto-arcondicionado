# Direção visual — Elgin AC na bandeja

- Painel alto de 390 × 844 px, sem moldura, alinhado ao canto inferior direito da área útil do Windows e reduzido proporcionalmente quando a tela é menor. Coordenadas são escaladas uma vez; fontes e imagens usam a mesma escala.
- Fundo em gradiente azul-noite, texto branco suave, acentos ciano nos controles ativos e verde no estado conectado. A imagem de referência do usuário define a composição.
- Cabeçalho com temperatura ambiente e energia; ar-condicionado claro e fluxo de ar luminoso no centro; setpoint grande centralizado; barra horizontal com botões − e +; quatro cartões independentes de Modo, Vento, Funções e Eco.
- Entre o ajuste de temperatura e os cartões, uma linha discreta apresenta o estado da tomada EKAZA e abre sua vista própria sem competir com os controles do ar.
- A vista da tomada mantém o fundo azul-noite, mostra o estado em destaque, potência/tensão/corrente confirmadas pela rede e uma ação explícita. O botão de desligar permanece acionável; quando o ar não está confirmado desligado, abre uma segunda vista com aviso e confirmação antes do corte.
- Eco mostra o estado do DP 11 (Protect no app nativo). A vista Funções reúne Dormir, Aletas, Mudo, Display, Turbo e Timer de desligamento, com estados retornados pelo aparelho.
- Estado de conexão sempre visível no rodapé. Feedback de comando e falha sem ocultar o estado anterior.
- Configuração de início com o Windows acessível em uma segunda vista do mesmo painel.
- O arquivo HTML e a captura fornecidos em outubro de 2026 são referências visuais para a vista principal; não copiar controles sem suporte no Elgin, como WindFree, umidade, filtro ou consumo.

## Craft & Polish das três telas

- O painel Tk usa espaçamento de 4/8/12/16/20/24 px, cards com raio de 18 px e borda sutil comum, textos secundários legíveis e foco de teclado visível.
- A pílula Medição usa conteúdo medido, padding de 12 px, gap de 6 px e chevron de 16 px que não encolhe. Ícone, status e nome da tomada ficam em um bloco separado alinhado verticalmente.
- Valores de telemetria e legendas são empilhados com intervalos explícitos. A posição da legenda usa a altura real da fonte.
- Cards e badges suportam textos longos sem invadir ações vizinhas. O painel Windows é verificado em 100% e 80% com estado ligado, desligado, sem conexão e carga cheia.
- `tools/render_previews.py` renderiza os componentes reais do app com dados ilustrativos, sem comunicação com os aparelhos. Os protótipos HTML não fazem parte do aplicativo distribuído.
