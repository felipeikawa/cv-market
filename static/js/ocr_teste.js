(() => {
  'use strict';
  const el = id => document.getElementById(id);
  const input = el('ocrImage'), choose = el('chooseImage'), read = el('readImage');
  const preview = el('imagePreview'), result = el('ocrResult'), raw = el('rawText');
  let busy = false, canvas = null, previewURL = null;

  function setBusy(value) {
    busy = value;
    input.disabled = choose.disabled = value;
    read.disabled = value || !canvas;
    el('ocrProgress').hidden = !value;
    el('imageArea').setAttribute('aria-busy', String(value));
  }
  function status(message, percent) {
    el('ocrStatus').textContent = message;
    if (Number.isFinite(percent)) el('ocrPercent').value = percent;
    else el('ocrPercent').removeAttribute('value');
  }
  function showError(message) {
    el('ocrError').textContent = message;
    el('ocrError').hidden = false;
  }
  function releaseImage() {
    preview.removeAttribute('src');
    if (previewURL) URL.revokeObjectURL(previewURL);
    previewURL = null;
    if (canvas) { canvas.width = canvas.height = 0; canvas = null; }
  }
  choose.addEventListener('click', () => { if (!busy) input.click(); });
  input.addEventListener('change', async () => {
    if (busy) return;
    const file = input.files[0];
    input.value = '';
    if (!file) return;
    releaseImage(); result.hidden = true; raw.value = '';
    el('imageArea').hidden = true; el('ocrError').hidden = true;
    setBusy(true); status('Preparando imagem...');
    let sourceURL;
    try {
      if (!file.type.startsWith('image/') || file.type === 'image/svg+xml')
        throw new Error('Selecione uma foto válida, como JPEG, PNG ou WebP. SVG não é aceito neste teste.');
      if (!file.size || file.size > 20 * 1024 * 1024)
        throw new Error('Selecione uma imagem de até 20 MB e que não esteja vazia.');
      sourceURL = URL.createObjectURL(file);
      const image = new Image();
      image.src = sourceURL;
      try { await image.decode(); }
      catch { throw new Error('Não foi possível abrir essa imagem. Tente uma foto JPEG, PNG ou WebP.'); }
      const scale = Math.min(1, 2560 / Math.max(image.naturalWidth, image.naturalHeight));
      canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
      canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.95));
      if (!blob) throw new Error('Não foi possível preparar a foto. Tente uma imagem menor.');
      previewURL = URL.createObjectURL(blob); preview.src = previewURL;
      el('imageInfo').textContent = `${file.name} — OCR: ${canvas.width} × ${canvas.height} pixels`;
      el('imageArea').hidden = false;
      choose.textContent = 'Escolher outra imagem'; read.textContent = 'Ler texto';
    } catch (error) { releaseImage(); showError(error.message || 'Não foi possível abrir a foto. Tente outra imagem.'); }
    finally { if (sourceURL) URL.revokeObjectURL(sourceURL); setBusy(false); }
  });
  read.addEventListener('click', async () => {
    if (busy || !canvas) return;
    setBusy(true); result.hidden = true; raw.value = ''; el('ocrError').hidden = true;
    status('Lendo imagem... Carregando OCR e idioma.');
    try {
      const response = {data: {text: await CVOCR.recognize(canvas, status)}};
      raw.value = response.data.text;
      el('resultHelp').textContent = raw.value.length ? 'Texto bruto do OCR. Selecione o conteúdo para copiar.' : 'Nenhum texto identificado. Tente uma foto mais próxima, com boa luz e foco.';
      result.hidden = false;
    } catch (error) { showError(error.message || 'Não foi possível ler a imagem. Tente novamente com outra foto.'); }
    finally {
      read.textContent = 'Ler novamente'; setBusy(false);
    }
  });
  window.addEventListener('pagehide', () => {
    releaseImage();
    read.disabled = true;
  });
})();
