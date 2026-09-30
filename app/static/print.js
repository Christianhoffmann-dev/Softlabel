/* SoftLabel Druckseite: Import, Live-Vorschau, Export PDF/PNG/ZPL/SVG */
(function () {
  'use strict';
  const $ = (s, r) => (r || document).querySelector(s);
  const BASE = location.pathname.replace(/\/drucken\/\d+.*$/, '');
  const api = (p) => BASE + p;
  let rows = [], cur = 0;

  const SAMPLE = {};
  (window.KEYS || []).forEach(k => { SAMPLE[k] = 'BEISPIEL'; });

  function toast(msg) { const t = $('#toast'); t.textContent = msg; t.classList.add('show');
    clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('show'), 2800); }

  function currentRow() {
    if (rows.length) return rows[cur] || rows[0];
    const r = {};
    document.querySelectorAll('#manualFields input[data-key]').forEach(i => { r[i.dataset.key] = i.value; });
    return r;
  }

  async function refreshPreview() {
    const r = await fetch(api('/api/preview/' + window.TID), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ row: currentRow() }) });
    if (!r.ok) return;
    const frag = await r.text();
    const box = $('#preview');
    if (window.LABEL_COUNT > 1 && $('#allSheets') && $('#allSheets').checked === false && !rows.length) {
      box.innerHTML = frag;
    } else {
      box.innerHTML = frag;
    }
    $('#pvInfo').textContent = rows.length ? `Zeile ${cur + 1} von ${rows.length}` : 'Testdaten';
  }

  // ---------- manuelle Felder ----------
  (function buildManual() {
    const wrap = $('#manualFields');
    if (!wrap || !window.KEYS.length) return;
    wrap.innerHTML = window.KEYS.map(k => {
      const id = k.replace(/[^A-Za-z0-9_\-.]/g, '_');
      return `<div class="kv" style="margin-bottom:6px"><label>${k}</label><input id="mf_${id}" data-key="${k}" value="${SAMPLE[k] || ''}"></div>`;
    }).join('');
    wrap.addEventListener('input', refreshPreview);
  })();

  // ---------- Datei-Import ----------
  const drop = $('#drop'), fileIn = $('#file');
  drop.addEventListener('click', () => fileIn.click());
  drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', (e) => {
    e.preventDefault(); drop.classList.remove('over');
    if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]);
  });
  fileIn.addEventListener('change', () => { if (fileIn.files[0]) upload(fileIn.files[0]); });

  async function upload(f) {
    const fd = new FormData(); fd.append('file', f);
    const r = await fetch(api('/api/import'), { method: 'POST', body: fd });
    const j = await r.json();
    if (!r.ok) { toast(j.detail || 'Import fehlgeschlagen'); return; }
    rows = j.rows || [];
    if (j.total > rows.length) toast(`Nur die ersten ${rows.length} Zeilen in der Vorschau — Export nutzt alle ${j.total}.`);
    // Warnung: unbekannte Spaltenköpfe?
    const unknown = (j.headers || []).filter(h => h !== '__index' && !(window.KEYS.includes(h)));
    $('#importNote').innerHTML = `✅ ${j.total} Zeilen · Spalten: ${j.headers.join(', ')}` +
      (unknown.length ? `<br>⚠ Von der Vorlage nicht genutzt: <b>${unknown.join(', ')}</b>` : '');
    cur = 0;
    buildTable();
    $('#rowNav').hidden = !rows.length;
    refreshPreview();
  }

  function buildTable() {
    const t = $('#dtable');
    if (!rows.length) { t.innerHTML = ''; return; }
    const cols = Object.keys(rows[0]).filter(c => c !== '__index');
    t.innerHTML = '<tr>' + cols.map(c => `<th>${c}</th>`).join('') + '</tr>' +
      rows.map((r, i) => '<tr data-i="' + i + '" class="' + (i === cur ? 'active' : '') + '">' +
        cols.map(c => '<td title="' + String(r[c] == null ? '' : r[c]).replace(/"/g, '&quot;') + '">' +
          (r[c] == null ? '' : r[c]) + '</td>').join('') + '</tr>').join('');
    t.querySelectorAll('tr[data-i]').forEach(tr => tr.addEventListener('click', () => {
      cur = parseInt(tr.dataset.i, 10); buildTable(); refreshPreview(); }));
    $('#rowPos').textContent = `${cur + 1} / ${rows.length}`;
  }
  $('#rowPrev').addEventListener('click', () => { cur = Math.max(0, cur - 1); buildTable(); refreshPreview(); });
  $('#rowNext').addEventListener('click', () => { cur = Math.min(rows.length - 1, cur + 1); buildTable(); refreshPreview(); });
  $('#allSheets').addEventListener('change', refreshPreview);

  // ---------- Export ----------
  function payload() {
    const copies = Math.max(1, parseInt($('#copies').value, 10) || 1);
    let out;
    if (rows.length) {
      out = [];
      for (let c = 0; c < copies; c++) out = out.concat(rows.map(r => { const o = Object.assign({}, r); delete o.__index; return o; }));
    } else {
      const r = currentRow();
      out = Array.from({ length: copies }, () => Object.assign({}, r));
    }
    return { rows: out, actor: (document.cookie.match(/(?:^| )sluser=([^;]+)/) || [])[1] || 'web' };
  }

  async function download(fmt) {
    const btn = document.getElementById('exp' + fmt.charAt(0).toUpperCase() + fmt.slice(1));
    const orig = btn ? btn.textContent : '';
    if (btn) { btn.disabled = true; btn.textContent = '…'; }
    try {
    const body = payload();
    if (fmt === 'png' && window.LABEL_COUNT > 1) body.sheet = true;
    if (fmt === 'zpl') body.sheet = undefined;
    const r = await fetch(api(`/api/export/${window.TID}/${fmt}`), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body) });
    if (!r.ok) {
      let d = 'Fehler';
      try { d = (await r.json()).detail || d; } catch (e) {}
      toast(d); return;
    }
    const blob = await r.blob();
    const name = r.headers.get('X-Filename') || `label.${fmt}`;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    if (fmt === 'zpl') showZpl(await blob.text());
    else toast(`${fmt.toUpperCase()} exportiert: ${name}`);
    } catch (err) {
      toast('Export fehlgeschlagen: ' + (err.message || err));
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = orig; }
    }
  }
  $('#expPdf').addEventListener('click', () => download('pdf'));
  $('#expPng').addEventListener('click', () => download('png'));
  $('#expZpl').addEventListener('click', () => download('zpl'));
  $('#expSvg').addEventListener('click', () => download('svg'));

  function showZpl(text) {
    const div = document.createElement('div');
    div.className = 'panel'; div.style.marginTop = '12px';
    div.innerHTML = '<h3>ZPL-Vorschau (in ZPL-Treiber/Weboberfläche einfügen oder „senden“)</h3>' +
      `<pre class="zpl">${text.replace(/</g, '&lt;').slice(0, 4000)}</pre>` +
      '<button class="btn small ghost" id="zplCopy">ZPL kopieren</button>' +
      (navigator.userAgent.includes('Chrome') || navigator.userAgent.includes('Edge')
        ? ' <button class="btn small" id="zplSend">🔌 An lokalen Zebra-Drucker senden (WebSerial)</button>' : '');
    $('#preview').parentNode.appendChild(div);
    $('#zplCopy').addEventListener('click', async () => { await navigator.clipboard.writeText(text); toast('ZPL kopiert'); });
    const send = $('#zplSend');
    if (send) send.addEventListener('click', async () => {
      try {
        const port = await navigator.serial.requestPort();
        await port.open({ baudRate: 9600 });
        const w = port.writable.getWriter();
        await w.write(new TextEncoder().encode(text));
        w.releaseLock(); await port.close();
        toast('An Drucker gesendet');
      } catch (e) { toast('WebSerial: ' + e.message); }
    });
  }

  // ---------- Browser-Druck ----------
  $('#brPrint').addEventListener('click', async () => {
    const r = await fetch(api('/api/preview/' + window.TID), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ row: currentRow() }) });
    const frag = await r.text();
    const copies = Math.max(1, parseInt($('#copies').value, 10) || 1);
    const style = `<style>
      @page { size: ${window.W}mm ${window.H}mm; margin: 0; }
      body { margin:0; font-family:Arial,Helvetica,sans-serif; }
      .lbl { position:relative; background:#fff; overflow:hidden; page-break-after:always; }
      .txt{position:absolute;white-space:pre-wrap}.line,.rect,.img,.bc,.err{position:absolute}
      .bc svg{width:100%;height:100%} .err{color:#b00}
      @media print { .noprint{display:none} }
      </style>`;
    const w = window.open('', '_blank');
    w.document.write(`<html><head><title>Druck</title>${style}</head><body>
      <div class="noprint" style="padding:10px;background:#eef">
        Drucken → Ziel: Zebra/Etikettendrucker → <b>Maßstab 100 % / tatsächliche Größe</b>,
        Ränder & Kopf/Fuß aus. ${frag.match(/width:/) ? '' : ''}</div>
      ${Array.from({length: copies}, () => frag).join('')}</body></html>`);
    w.document.close(); w.focus();
    setTimeout(() => w.print(), 400);
  });

  refreshPreview();
})();
