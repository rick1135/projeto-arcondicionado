# Fontes e ícones do Stitch

Os SVGs em `icons/` foram extraídos como dados do `code.html` fornecido pelo usuário. Preservam as geometrias, espessuras de traço e acabamentos originais. `manifest.json` identifica a pilha de fontes do HTML e distingue os ícones originais dos complementos Dormir e Atualizar. Voltar reutiliza o chevron original rotacionado.

O HTML usa `Segoe UI Variable` e, como alternativa, `Segoe UI`. O ZIP não contém arquivos de fonte. O aplicativo seleciona as faces nativas Small, Text e Display disponíveis no Windows, incluindo Semibold; a leitura de watts usa Consolas como a pilha monoespaçada da referência. As fontes do Windows não são copiadas nem redistribuídas.

Os PNGs transparentes de 192 × 192 px são derivados dos SVGs e acompanham o aplicativo. Pillow adapta a imagem à dimensão e cor do controle, com cache para evitar rasterização repetida durante a interação. Não há nova dependência no aplicativo nem acesso à rede para carregar assets.

Para importar uma referência novamente, execute `tools/import_stitch_assets.py caminho-do-zip` e depois `tools/render_stitch_icons.cjs` com Node e o pacote `sharp` disponível. Esses utilitários são usados apenas na preparação dos assets.
