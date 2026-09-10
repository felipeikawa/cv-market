(() => {
  'use strict';
  const el = id => document.getElementById(id), dialog = el('ocrDialog'), form = el('ocrConfirmForm');
  let target, busy = false, parsed;
  function error(message) { el('conferenceOCRError').textContent=message; el('conferenceOCRError').hidden=!message; }
  function reset() { form.reset(); form.hidden=true; el('conferenceOCRRaw').textContent=''; el('ocrDateFields').replaceChildren(); error(''); parsed=null; }
  function option(select, value, label) { const o=document.createElement('option'); o.value=value; o.textContent=label; select.append(o); }
  function dates(edit=false) {
    el('ocrDateFields').replaceChildren();
    for (const [kind,label] of [['manufacture','Fabricação'],['expiry','Validade']]) {
      const id='ocr-'+kind, l=document.createElement('label'); l.htmlFor=id; l.textContent=label;
      const input=document.createElement(parsed.dates.length>1 && !edit ? 'select' : 'input'); input.id=id;
      if (input.tagName==='SELECT') { option(input,'','Não identificada'); parsed.dates.forEach(d=>option(input,d.iso,d.value)); input.value=parsed[kind]; }
      else { input.placeholder='dd/mm/aaaa — não identificada'; input.value=parsed[kind] ? parsed[kind].split('-').reverse().join('/') : ''; input.inputMode='numeric'; }
      input.addEventListener('input',()=>{el('ocrAcceptOrder').checked=false; el('ocrOrderWarning').hidden=true; error('');});
      el('ocrDateFields').append(l,input);
    }
  }
  document.querySelectorAll('[data-ocr-item]').forEach(button=>button.addEventListener('click',()=>{
    if(busy) return; target=button.dataset.ocrItem; reset(); el('ocrChoose').textContent='Selecionar ou tirar foto'; dialog.showModal();
  }));
  el('ocrClose').onclick=()=>dialog.close();
  dialog.addEventListener('cancel',event=>{if(busy) event.preventDefault();});
  dialog.addEventListener('close',reset);
  el('ocrChoose').onclick=()=>{if(!busy){reset(); el('conferenceOCRImage').click();}};
  el('ocrLotChoice').onchange=()=>{el('ocrLot').value=el('ocrLotChoice').value; el('ocrNoLot').checked=!el('ocrLotChoice').value; el('ocrLot').disabled=el('ocrNoLot').checked;};
  el('ocrNoLot').onchange=()=>{el('ocrLot').disabled=el('ocrNoLot').checked;};
  el('ocrCorrect').onclick=()=>{
    for(const kind of ['manufacture','expiry']) { const input=el('ocr-'+kind); parsed[kind]=input.tagName==='SELECT'?input.value:(CVOCRParser.date(input.value)?.iso || ''); }
    dates(true); el('ocrAcceptOrder').checked=false; el('ocrOrderWarning').hidden=true; el('ocrNoLot').checked=false; el('ocrLot').disabled=false; el('ocrLot').focus();
  };
  el('conferenceOCRImage').addEventListener('change',async()=>{
    if(busy) return;
    const file=el('conferenceOCRImage').files[0]; el('conferenceOCRImage').value=''; if(!file) return;
    reset(); busy=true; el('ocrChoose').disabled=el('ocrClose').disabled=true; el('conferenceOCRProgress').hidden=false;
    let url, canvas;
    const status=(text,percent)=>{el('conferenceOCRStatus').textContent=text; if(Number.isFinite(percent)) el('conferenceOCRPercent').value=percent; else el('conferenceOCRPercent').removeAttribute('value');};
    status('Preparando imagem…');
    try {
      if(!file.type.startsWith('image/') || file.type==='image/svg+xml' || !file.size || file.size>20*1024*1024) throw Error('Selecione uma foto JPEG, PNG ou WebP de até 20 MB.');
      url=URL.createObjectURL(file); const image=new Image(); image.src=url;
      try {await image.decode();} catch {throw Error('Não foi possível abrir a imagem. Tente JPEG, PNG ou WebP.');}
      const scale=Math.min(1,2560/Math.max(image.naturalWidth,image.naturalHeight)); canvas=document.createElement('canvas'); canvas.width=Math.max(1,Math.round(image.naturalWidth*scale)); canvas.height=Math.max(1,Math.round(image.naturalHeight*scale));
      const ctx=canvas.getContext('2d'); ctx.fillStyle='#fff'; ctx.fillRect(0,0,canvas.width,canvas.height); ctx.drawImage(image,0,0,canvas.width,canvas.height);
      const raw=await CVOCR.recognize(canvas,status); parsed=CVOCRParser.parse(raw); el('conferenceOCRRaw').textContent=raw;
      el('ocrDateHelp').textContent=parsed.dates.length>1?'Encontramos mais de uma data. Confirme qual informação corresponde a cada uma.': (parsed.dates.length ? 'Data encontrada: '+parsed.dates[0].value+'. Revise as sugestões; sem contexto, informe o campo correto em Corrigir.' : 'Nenhuma data identificada. Campos sem identificação ficam em branco.');
      const choice=el('ocrLotChoice'); choice.replaceChildren(); option(choice,'','Não identificado'); parsed.lots.forEach(lot=>option(choice,lot,lot)); choice.value=parsed.lots.length===1?parsed.lots[0]:'';
      el('ocrLot').disabled=false; el('ocrLot').value=choice.value; dates(); form.hidden=false; el('ocrChoose').textContent='Tirar outra foto / escolher imagem';
    } catch(e) {error(e.message || 'Falha ao ler a imagem. Tente outra foto.');}
    finally {if(url) URL.revokeObjectURL(url); if(canvas) canvas.width=canvas.height=0; busy=false; el('ocrChoose').disabled=el('ocrClose').disabled=false; el('conferenceOCRProgress').hidden=true;}
  });
  form.addEventListener('submit',event=>{
    event.preventDefault(); error(''); const values={};
    for(const kind of ['manufacture','expiry']) {
      const input=el('ocr-'+kind), value=input.value.trim();
      values[kind]=input.tagName==='SELECT'?value:(CVOCRParser.date(value)?.iso || '');
      if(value && !values[kind]) {error('Data inválida. Use dd/mm/aaaa e confira os dias do mês.'); input.focus(); return;}
    }
    if(values.manufacture && values.manufacture===values.expiry) {error('Selecione datas diferentes para fabricação e validade ou deixe uma não identificada.');return;}
    if(values.manufacture && values.expiry && values.manufacture>values.expiry && !el('ocrAcceptOrder').checked) {el('ocrOrderWarning').hidden=false; el('ocrAcceptOrder').focus();return;}
    for(const [name,value] of [['lote',el('ocrNoLot').checked?'':el('ocrLot').value.trim()],['fabricacao',values.manufacture],['validade',values.expiry]]) {
      const field=el(name+'_'+target); if(!field || field.disabled) return;
      field.value=value; field.dispatchEvent(new Event('input',{bubbles:true})); field.dispatchEvent(new Event('change',{bubbles:true}));
    }
    dialog.close();
  });
})();
