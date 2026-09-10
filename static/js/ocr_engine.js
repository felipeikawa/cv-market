/* Shared client-side engine. Images remain in memory; only OCR assets are downloaded. */
window.CVOCR = (() => {
  let libraryPromise = null, activeWorker = null, busy = false;
  function loadLibrary() {
    if (window.Tesseract) return Promise.resolve(window.Tesseract);
    if (!libraryPromise) libraryPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      const timer = setTimeout(() => fail(), 30000);
      function fail() {
        clearTimeout(timer); script.remove(); libraryPromise = null;
        reject(new Error('Não foi possível carregar o OCR. Verifique sua conexão e tente novamente.'));
      }
      script.src = 'https://cdn.jsdelivr.net/npm/tesseract.js@6.0.1/dist/tesseract.min.js';
      script.onload = () => { clearTimeout(timer); resolve(window.Tesseract); };
      script.onerror = fail;
      document.head.appendChild(script);
    });
    return libraryPromise;
  }

  async function recognize(canvas, status) {
    if (busy) throw new Error('Uma leitura já está em andamento.');
    busy = true;
    let timer, expired = false;
    try {
      const Tesseract = await loadLibrary();
      const failure = new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error('Tempo de leitura excedido. Tente novamente com uma foto menor e verifique a conexão.')), 180000);
      });
      let rejectWorker;
      const workerError = new Promise((_, reject) => { rejectWorker = reject; });
      const job = (async () => {
        const worker = await Tesseract.createWorker('por', 1, {
          workerPath: 'https://cdn.jsdelivr.net/npm/tesseract.js@6.0.1/dist/worker.min.js',
          corePath: 'https://cdn.jsdelivr.net/npm/tesseract.js-core@6.0.0',
          langPath: 'https://tessdata.projectnaptha.com/4.0.0',
          errorHandler: () => rejectWorker(new Error('Falha no mecanismo de OCR. Verifique a conexão e tente novamente.')),
          logger: message => {
            if (expired) return;
            const percent = Number.isFinite(message.progress) ? Math.round(message.progress * 100) : undefined;
            const label = message.status === 'recognizing text' ? 'Processando texto...' : 'Lendo imagem... Carregando OCR e idioma.';
            status(label + (percent === undefined ? '' : ` ${percent}%`), percent);
          }
        });
        if (expired) { await worker.terminate(); return; }
        activeWorker = worker;
        return worker.recognize(canvas);
      })();
      return (await Promise.race([job, failure, workerError])).data.text;

    } finally {
      expired = true; clearTimeout(timer);
      if (activeWorker) { activeWorker.terminate().catch(() => {}); activeWorker = null; }
      busy = false;
    }
  }
  window.addEventListener('pagehide', () => { if (activeWorker) activeWorker.terminate().catch(() => {}); });
  return {recognize};
})();
