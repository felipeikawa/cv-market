# Protótipo OCR isolado

URL: `/ocr-teste`, disponível para qualquer usuário autenticado. O menu temporário fica em Administração → Teste OCR (visível para administradores).

O navegador abre a imagem, valida MIME/tamanho e decodificação, desenha em canvas e limita o maior lado a 2.560 pixels, preservando proporção. Tesseract.js 6.0.1 usa português (`por`) em Web Worker/WebAssembly. O textarea recebe `data.text` sem interpretação ou preenchimento automático.

Limite: 20 MiB (20 × 1.024 × 1.024 bytes), apresentado como 20 MB na interface. Aceita imagens decodificáveis pelo navegador; SVG é rejeitado. HEIC/HEIF dependem do suporte do aparelho: se falhar, use JPEG. Não há atributo `capture` forçando a câmera: o seletor nativo pode oferecer câmera e biblioteca conforme navegador/SO.

A imagem e o texto ficam somente na memória da página. Nenhuma rota de upload foi adicionada e nenhum arquivo ou resultado é enviado ao Flask ou à CDN. A CDN fornece apenas biblioteca, worker, WebAssembly e idioma. O navegador pode armazenar o idioma em cache, mas a aplicação não persiste fotos/texto. A primeira leitura requer internet; bloqueios de CDN, pouca memória, reflexos, baixa nitidez ou texto curvo podem impedir ou prejudicar a leitura. O prazo máximo de OCR é três minutos, além de até 30 segundos para carregar a biblioteca.

## Testar localmente

Use o ambiente e servidor de desenvolvimento já configurados do projeto. Na porta padrão, faça login e abra `http://127.0.0.1:5000/ocr-teste`. Se o servidor não estiver ativo, o comando usual é `venv/bin/python app.py` (o próprio aplicativo existente executa sua inicialização de desenvolvimento; esta implementação não modifica essa rotina).

Para um aparelho físico na mesma rede Wi-Fi, execute o servidor de desenvolvimento com `venv/bin/python -m flask --app app run --host 0.0.0.0 --port 5000 --no-reload`, em rede confiável. Acesse `http://IP-LOCAL-DO-COMPUTADOR:5000/ocr-teste` e faça login. Não use o servidor de desenvolvimento em exposição pública.

1. Selecione ou tire uma foto real de embalagem. Confira o preview.
2. Toque em Ler texto. Confira progresso, bloqueio dos botões e texto bruto.
3. Selecione o texto para copiar; teste Ler novamente e Escolher outra imagem.
4. Teste imagem inválida, arquivo acima de 20 MB e indisponibilidade de internet antes da primeira leitura.
5. Em DevTools → Network, confira que a leitura baixa somente dependências externas e não envia foto/texto ou requisições POST ao sistema.
6. Confira em iPhone 390×844, Android 360×800, tablet e desktop. Emulação não substitui a validação da câmera e do desempenho em aparelhos físicos.

## Testes

`venv/bin/python -m unittest discover -s tests -p test_ocr.py -v`

Para incluir o teste visual/funcional, instale Playwright e os navegadores Chromium/WebKit no ambiente de testes e defina `CV_BROWSER_TESTS=1`. Nesta máquina, as ferramentas já disponíveis ficam em `/private/tmp/cv-mobile-tools` e os navegadores em `/private/tmp/cv-mobile-browsers`:

```sh
CV_BROWSER_TESTS=1 PYTHONPATH=/private/tmp/cv-mobile-tools PLAYWRIGHT_BROWSERS_PATH=/private/tmp/cv-mobile-browsers venv/bin/python -m unittest discover -s tests -p test_ocr.py -v
```

Os testes copiam a aplicação para um diretório temporário, sem carregar `.env` ou banco reais. Cobrem login, rota somente GET, elementos, ausência de upload, redução proporcional, texto bruto incluindo caracteres de marcação, repetição, falhas, limite, ausência de envio ao backend e ausência de overflow nas quatro dimensões em Chromium/WebKit. O mecanismo Tesseract é simulado nesses testes: precisão real, download de CDN e execução de WASM precisam de validação manual com fotos reais.

Referência da integração: https://github.com/naptha/tesseract.js/blob/v6.0.1/docs/api.md
