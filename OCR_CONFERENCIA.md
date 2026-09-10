# OCR experimental na conferência

O botão de cada item abre um diálogo. “Selecionar ou tirar foto” usa `accept="image/*"`, sem `capture`, preservando as opções de câmera/biblioteca oferecidas pelo navegador. Após escolher a foto, a leitura começa automaticamente. Confirmar apenas altera os três campos do item; o usuário salva pelo fluxo existente. Cancelar não altera o item. Outra foto descarta a sugestão anterior.

A imagem fica em memória, é reduzida para até 2560 pixels e descartada após a leitura. Não há upload, persistência de imagem, endpoint novo ou mudança de banco. O Tesseract e os arquivos de idioma/core são baixados de CDNs. A página `/ocr-teste` usa o mesmo mecanismo e permanece disponível.

## Interpretação

`static/js/ocr_parser.js` expõe `CVOCRParser.parse(text)` e `date(value)`; não depende do DOM. Detecta os rótulos em português/inglês pedidos, inclusive na linha imediatamente seguinte. Remove acentos e aceita substituições restritas nos rótulos (VÁL1DO, VALlDADE, L0TE), sem reescrever valores de lote.

Datas exigem dia/mês com dois dígitos, ano com dois ou quatro e separador consistente `/`, `-` ou `.`. Valida calendário e bissextos. Ano curto: 00–69 significa 2000–2069; 70–99 significa 1970–1999. Regra fixa, sem restringir datas antigas; revise o século na confirmação. Exibição normalizada em dd/mm/aaaa; campos HTML date recebem ISO.

Datas distintas são deduplicadas. Sugere fabricação/validade apenas com contexto explícito não conflitante. Múltiplas datas sempre aparecem em seletores com “Não identificada”; uma sugestão clara pode vir pré-selecionada. “Corrigir” permite digitação manual. Datas iguais para os dois campos são bloqueadas; ordem invertida exige checkbox explícito, invalidado ao editar datas. Ausência de informação mantém a sugestão vazia; confirmar aplica esses vazios ao item também.

Lotes são tokens de 2–40 caracteres com letras, números, hífen ou sublinhado e pelo menos um número, após rótulo explícito. Um candidato é sugerido; vários aparecem em opções sem escolha automática. Edição manual e “Não identificado” sempre disponíveis.

## Testar

Inicie o servidor local como de costume (`venv/bin/python app.py`). Abra uma conferência em andamento no desktop, clique no botão de câmera e selecione uma foto real. Confira o texto recolhido, sugestões, correções e campos preenchidos antes de salvar. Teste `FAB 10/09/26 VAL 15/12/26`, duas datas sem rótulo, datas inválidas e ausência de texto. Cancelar deve preservar os campos.

No celular na mesma rede, acesse o endereço LAN do computador na porta configurada pelo servidor; é necessário que ele escute na rede e que o firewall permita o acesso. Confira as opções oferecidas pelo seletor nativo, orientação e rolagem. Não é necessária permissão de câmera via getUserMedia. Para emulação use 390×844, 360×800, 768×1024 e desktop no DevTools.

Testes isolados (SQLite temporário, sem `.env` real):

```sh
CV_BROWSER_TESTS=1 PYTHONPATH=/private/tmp/cv-mobile-tools PLAYWRIGHT_BROWSERS_PATH=/private/tmp/cv-mobile-browsers venv/bin/python -m unittest discover -s tests -v
```

Os caminhos acima são as dependências Playwright já disponíveis neste computador. Em outro ambiente instale Playwright e seus navegadores e ajuste os caminhos. Os testes de UI simulam a fronteira Tesseract, validando interpretação e fluxo sem depender de CDN/WASM. A qualidade de reconhecimento exige teste adicional com embalagens reais.

Limitações: reflexos, curvatura, desfoque e baixa resolução afetam OCR. HEIC depende da decodificação pelo navegador; JPEG/PNG são mais portáveis. Datas sem dia, mês escrito e lote só alfabético precisam de correção manual. O seletor nativo depende do aparelho/navegador. A primeira leitura requer internet; o processamento pode ser lento e tem timeout. Testes em WebKit/Chromium emulados não substituem teste físico em iPhone/Android.

## Resultado da validação desta implementação

Validação pré-piloto em 10/09/2026: suíte completa com 13 testes aprovados em 106,582 segundos, sem falhas ou testes ignorados. Inclui configuração de produção, servidores Flask/Gunicorn, login, usuários, NF-e, conferência de produtos, navegação mobile, cards do dashboard e de conferências, Salvar e próximo, divergências, diagnóstico OCR, interpretação e confirmação antes do preenchimento. Chromium e WebKit cobrem celular, tablet e desktop, com verificações de overflow e ausência de upload.

Também foi executado o Tesseract real nos dois navegadores, com biblioteca, worker, WASM e idioma carregados das CDNs. Uma imagem sintética gerada apenas em memória contendo `LOTE ABC123`, `FAB 10/09/2026` e `VAL 15/12/2026` foi reconhecida e interpretada corretamente. Em cada navegador foram observadas cinco requisições GET, sem corpo de envio. Nenhuma imagem foi adicionada ao repositório. Essa verificação não substitui a avaliação de câmera, desempenho e precisão com embalagens em aparelhos físicos.

Os testes usaram cópias temporárias da aplicação e bancos SQLite sintéticos. Banco existente, Supabase e modelos não foram alterados. `/ocr-teste` foi preservada. `git diff --check` sem erros.
