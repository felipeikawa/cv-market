/* Pure parser. Two-digit years use a fixed pivot: 00–69 => 2000–2069,
   70–99 => 1970–1999. No moving window or future-date restriction. */
(function (root) {
  'use strict';
  function date(value) {
    const m = /^(\d{2})([/.\-])(\d{2})\2(\d{4}|\d{2})$/.exec(value.trim());
    if (!m) return null;
    const day = +m[1], month = +m[3];
    let year = +m[4];
    if (m[4].length === 2) year += year < 70 ? 2000 : 1900;
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    if (year < 1 || month < 1 || month > 12 || day < 1 || day > [31,leap?29:28,31,30,31,30,31,31,30,31,30,31][month-1]) return null;
    const y = String(year).padStart(4,'0');
    return {value:`${m[1]}/${m[3]}/${y}`, iso:`${y}-${m[3]}-${m[1]}`};
  }
  function parse(text) {
    const dates = new Map(), lots = new Set();
    let pending = null;
    // OCR substitutions are limited to known labels; lot values are never rewritten.
    const labels = /\b(BEST BEFORE|BOST BETORA|VAIO ATE|VAL[1IL]DO HASTA|EXPIRATION|EXPIRY|EXP|VENCIMENTO|VENC|VAL[1IL]DO ATE|VAL[1IL]DADE|VALIDADE|VAL|V|FABRICACAO|MANUFACTURED|FABR|FAB|MFG|F|L[O0]TE|LOT|BATCH|L)(?=\b|\d{2}[/.\-])[.:]?/g;
    for (const original of text.split(/\r?\n/)) {
      const line = original.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase();
      if (!line.trim()) { pending = null; continue; }
      const marks = [...line.matchAll(labels)];
      const kind = label => /^(L|LOT|L[O0]TE|BATCH)$/.test(label) ? 'lot' : /^(FAB.*|F|MFG|MANUFACTURED)$/.test(label) ? 'manufacture' : 'expiry';
      const chunks = marks.length ? marks.map((m,i) => ({kind:kind(m[1]), text:line.slice(m.index+m[0].length,marks[i+1]?.index ?? line.length)})) : [{kind:pending,text:line}];
      if (marks.length && marks[0].index > 0) chunks.unshift({kind:null,text:line.slice(0,marks[0].index)});
      pending = null;
      for (const chunk of chunks) {
        // Letters and packaging suffixes may touch dates; numeric continuations may not.
        let foundDate = false;
        for (const m of chunk.text.matchAll(/(?<![\d/.])(?<!\d-)\d{2}([/.\-])\d{2}\1(?:\d{4}|\d{2})(?![\d/.]|-\d)/g)) {
          const d = date(m[0]);
          if (d) { foundDate = true; if (!dates.has(d.iso)) dates.set(d.iso,{...d, contexts:[]});
            if (['manufacture','expiry'].includes(chunk.kind)) dates.get(d.iso).contexts.push(chunk.kind); }
        }
        if (chunk.kind === 'lot') {
          // Only strip a delimited, valid trailing HH:MM; preserve internal lot hyphens.
          const token = chunk.text.trim().replace(/^[:.\-]\s*/, '').split(/[\s|]+/)[0]
            .replace(/-(?:[01]\d|2[0-3]):[0-5]\d$/, '');
          if (token && /^(?=.*\d)[A-Z0-9][A-Z0-9_-]{1,39}$/.test(token)) lots.add(token);
        }
        if (chunk.kind && !chunk.text.trim()) pending = chunk.kind;
        else if (!foundDate && ['expiry','manufacture'].includes(chunk.kind) &&
                 marks.some(m => kind(m[1]) === chunk.kind && m[1].length > 1)) pending = chunk.kind;
      }
    }
    const list = [...dates.values()];
    const suggestion = kind => { const matches = list.filter(d => d.contexts.includes(kind) && !d.contexts.includes(kind==='expiry'?'manufacture':'expiry')); return matches.length===1 ? matches[0].iso : ''; };
    const manufacture = suggestion('manufacture'), expiry = suggestion('expiry');
    return {dates:list, lots:[...lots], manufacture, expiry, reversed:!!(manufacture && expiry && manufacture>expiry)};
  }
  const api = {parse,date};
  if (typeof module !== 'undefined') module.exports = api;
  else root.CVOCRParser = api;
})(globalThis);
