/* SoftLabel Designer — visuelle Bearbeitung: ziehen,大小 über 8 Anfasser, drehen,
   Snap-Führungslinien, Lineale, Maß-HUD. Keine x/y/breite/höhe-Zahlenfelder. */
(function () {
  'use strict';
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const BASE = location.pathname.replace(/\/(designer)(\/.*)?$/, '');
  const api = (p) => BASE + p;
  const SAMPLE = { auftrag: 'AF-2026-1042', empfaenger: 'Muster GmbH', adresse: 'Beispielstr. 1, 12345 Musterstadt',
    gewicht: '248,5', tracking: 'CV123456789DE', artnr: 'ART-88420', menge: '24', ean: '4006381333931',
    charge: 'C-2291', mhd: '03/2028', gtin: '4006381333931', artikel: 'ART-88420', seriennummer: 'SN-00123',
    kundenauftrag: 'KA-555', position: '12', feld: 'BEISPIEL' };

  let tpl = { id: window.TPL_ID || null, name: '', width_mm: 100, height_mm: 80, dpi: 300,
    label_count: 1, columns: 1, rows: 1, margin_mm: 2, gutter_mm: 3, design: [],
    folder_id: window.FOLDER_ID || null };
  // folder_id: null = Hauptbereich, Zahl = Kunde/Ordner. window.FOLDER_ID (aus ?folder=) zählt als gewählt.
  let folderChosen = !!window.TPL_ID || !!window.FOLDER_ID;
  let sel = null, dirty = false, uid = 1, zoom = 1, snapOn = true;

  // ---------- History (Undo/Redo) ----------
  const hist = []; let hix = -1, histLock = false;
  function snapshot() {
    if (histLock) return;
    const st = JSON.stringify({ design: tpl.design, w: tpl.width_mm, h: tpl.height_mm,
      lc: tpl.label_count, cols: tpl.columns, rows: tpl.rows, mg: tpl.margin_mm, gt: tpl.gutter_mm });
    if (hix >= 0 && hist[hix] === st) return;
    hist.splice(hix + 1);
    hist.push(st);
    if (hist.length > 60) hist.shift();
    hix = hist.length - 1;
  }
  function restore(st) {
    const j = JSON.parse(st);
    tpl.design = j.design; tpl.width_mm = j.w; tpl.height_mm = j.h; tpl.label_count = j.lc;
    tpl.columns = j.cols; tpl.rows = j.rows; tpl.margin_mm = j.mg; tpl.gutter_mm = j.gt;
    if (sel && !tpl.design.find(x => x.id === sel)) sel = null;
    histLock = true; render(); histLock = false; markDirty();
  }
  function undo() { if (hix > 0) { hix--; restore(hist[hix]); } }
  function redo() { if (hix < hist.length - 1) { hix++; restore(hist[hix]); } }

  const stage = $('#stage');
  const LABELS = { CODE128: 'Code 128', EAN13: 'EAN-13', EAN8: 'EAN-8', UPCA: 'UPC-A',
    CODE39: 'Code 39', ITF14: 'ITF-14', '25IND': '2 interleave 5', PHARMA: 'Pharmacode',
    QRCODE: 'QR-Code', DATAMATRIX: 'DataMatrix' };

  // ---------- utils ----------
  function toast(msg) {
    const t = $('#toast'); t.textContent = msg; t.classList.add('show');
    clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('show'), 2600);
  }
  function markDirty() { dirty = true; snapshot(); const f = $('#dirtyFlag'); if (f) { f.textContent = 'ungespeichert'; f.style.color = 'var(--warn)'; } }
  function setSaved(msg) { const f = $('#dirtyFlag'); if (f) { f.textContent = msg || 'gespeichert'; f.style.color = 'var(--ok)'; } }
  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function num(v, d) { const n = parseFloat(v); return isNaN(n) ? d : n; }
  function r1(v) { return Math.round(v * 10) / 10; }

  // ---------- Elemente ----------
  function mkEl(type) {
    const ls = labelSize();
    const base = { id: 'e' + (uid++), type, x: 5, y: 5, w: 40, h: 8, rotation: 0, z: tpl.design.length };
    if (type === 'text') Object.assign(base, { content: 'Text', fontFamily: 'Helvetica', fontSize: 4, bold: false, color: '#000000', align: 'left', valign: 'top' });
    if (type === 'field') Object.assign(base, { key: 'feld', label: '', fontFamily: 'Helvetica', fontSize: 3.5, bold: true, color: '#000000', align: 'left', valign: 'top', uppercase: false });
    if (type === 'barcode') Object.assign(base, { subtype: 'CODE128', code: '{{auftrag}}', w: Math.min(80, ls.w - 10), h: 15, moduleWidthMm: 0.25, showText: true, barcodeHeightMm: 0, fontSize: 2.4 });
    if (type === 'line') Object.assign(base, { w: 60, h: 0, color: '#000000', lineWidthMm: 0.4 });
    if (type === 'rect') Object.assign(base, { w: 40, h: 20, stroke: '#000000', fill: '', lineWidthMm: 0.4 });
    if (type === 'asset') Object.assign(base, { assetId: null, w: 25, h: 25 });
    base.x = Math.min(base.x, Math.max(0, ls.w - base.w - 2));
    base.y = Math.min(base.y, Math.max(0, ls.h - base.h - 2));
    return base;
  }
  function labelSize() {
    if (tpl.label_count > 1) {
      const lw = (tpl.width_mm - 2 * tpl.margin_mm - (tpl.columns - 1) * tpl.gutter_mm) / tpl.columns;
      const lh = (tpl.height_mm - 2 * tpl.margin_mm - (tpl.rows - 1) * tpl.gutter_mm) / tpl.rows;
      return { w: lw, h: lh };
    }
    return { w: tpl.width_mm, h: tpl.height_mm };
  }

  // ---------- Variablen / Bindings (Server-Logik gespiegelt) ----------
  function substitute(s) {
    return String(s || '').replace(/\{\{\s*([\wäöüÄÖÜß.\- ]+?)\s*(?:\|\s*(upper|lower))?\s*\}\}/g,
      (m, k, mode) => {
        let v = SAMPLE[k.trim()] || k.trim().toUpperCase();
        return mode === 'upper' ? v.toUpperCase() : (mode === 'lower' ? v.toLowerCase() : v);
      });
  }
  function materialOf(e) {
    if (e.type === 'field') {
      let v = SAMPLE[e.key] || String(e.key || '').toUpperCase();
      if (e.uppercase) v = v.toUpperCase();
      return (e.label ? e.label + ' ' : '') + v;
    }
    return substitute(e.content);
  }
  function resolveEl(e) {
    let cur = e, seen = {}, d = 0;
    while (cur.bindTo && d < 10) {
      const t = tpl.design.find(x => x.id === cur.bindTo);
      if (!t || seen[t.id] || t.type === 'barcode') break;
      seen[t.id] = 1; cur = t; d++;
    }
    return materialOf(cur);
  }
  function barCodeData(e) {
    let v = '';
    if (e.bindTo) {
      const t = tpl.design.find(x => x.id === e.bindTo);
      if (t) {
        if (t.type === 'field') { v = SAMPLE[t.key] || String(t.key || '').toUpperCase(); if (t.uppercase) v = v.toUpperCase(); }
        else v = substitute(t.content);
      }
    } else v = substitute(e.code);
    if (!String(v).trim()) v = '[leer]';
    return v;
  }

  // ---------- Maßstab ----------
  function px(mm) { return mm * 96 / 25.4 * zoom; }
  function mmFromPx(pxv) { return pxv * 25.4 / 96 / zoom; }

  // ---------- Rendering (inkrementell: DOM bleibt erhalten, nichts flackert) ----------
  function stageSig() {
    return [zoom, tpl.width_mm, tpl.height_mm, tpl.label_count, tpl.columns, tpl.rows,
            tpl.margin_mm, tpl.gutter_mm].join('|');
  }
  function render(force) {
    let inner = document.getElementById('lblInner');
    if (!inner || force || inner.dataset.sig !== stageSig()) {
      buildStage();
      inner = document.getElementById('lblInner');
    } else {
      syncEls(inner);
    }
    renderLinks();
    renderSelbox();
    renderRulers();
    renderProps();
    markActiveTool();
    updateChip();
  }
  function buildStage() {
    const ls = labelSize();
    // Gerüst: Stage-Größe + Guides bleiben, nur lblInner-Inhalt erneuern wenn nötig
    stage.style.width = px(tpl.width_mm) + 'px';
    stage.style.height = px(tpl.height_mm) + 'px';
    stage.querySelectorAll('.guide').forEach(g => g.remove());
    if (tpl.label_count > 1) {
      const cols = tpl.columns, rws = tpl.rows, m = tpl.margin_mm, g = tpl.gutter_mm;
      for (let r = 0; r < rws; r++) for (let c = 0; c < cols; c++) {
        const d = document.createElement('div'); d.className = 'guide';
        d.style.left = px(m + c * (ls.w + g)) + 'px'; d.style.top = px(m + r * (ls.h + g)) + 'px';
        d.style.width = px(ls.w) + 'px'; d.style.height = px(ls.h) + 'px';
        stage.appendChild(d);
      }
    }
    let inner = document.getElementById('lblInner');
    if (!inner) {
      inner = document.createElement('div');
      inner.id = 'lblInner';
      stage.appendChild(inner);
      const sbDiv = document.createElement('div'); sbDiv.id = 'selbox'; inner.appendChild(sbDiv);
      const ll = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      ll.id = 'linkLayer';
      ll.style.cssText = 'position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;overflow:visible;z-index:4;';
      inner.appendChild(ll);
    }
    if (tpl.label_count > 1) {
      inner.style.cssText = `position:absolute;left:${px(tpl.margin_mm)}px;top:${px(tpl.margin_mm)}px;` +
        `width:${px(ls.w)}px;height:${px(ls.h)}px;outline:1px solid var(--border2);background:#fff`;
      inner.dataset.w = ls.w; inner.dataset.h = ls.h;
    } else {
      inner.style.cssText = 'position:absolute;left:0;top:0;width:100%;height:100%';
      delete inner.dataset.w; delete inner.dataset.h;
    }
    inner.dataset.sig = stageSig();
    // vorhandene Element-Divs verwerfen nur wenn Stage-Größe/Zoom sich änderte:
    inner.querySelectorAll('.el').forEach(d => d.remove());
    tpl.design.forEach((e) => inner.appendChild(renderEl(e)));
  }
  function syncEls(inner) {
    const have = {};
    inner.querySelectorAll('.el').forEach(d => { have[d.dataset.id] = d; d.dataset.dead = '1'; });
    tpl.design.forEach((e) => {
      let d = have[e.id];
      if (!d) { d = renderEl(e); inner.appendChild(d); }
      else { paintEl(e, d); d.dataset.dead = ''; }
    });
    Object.keys(have).forEach(id => { if (have[id].dataset.dead) have[id].remove(); });
    // Ebenenreihenfolge (z) spiegeln
    tpl.design.slice().sort((a, b) => (a.z || 0) - (b.z || 0)).forEach((e, i) => {
      const d = inner.querySelector(`.el[data-id="${e.id}"]`);
      if (d) d.style.zIndex = i + 1;
    });
  }

  function paintEl(e, d) {
    d.classList.toggle('selected', sel === e.id);
    d.style.left = px(e.x) + 'px';
    d.style.top = px(e.y) + 'px';
    if (e.w != null) d.style.width = px(e.w) + 'px';
    if (e.type === 'line') { d.style.height = '0px'; boxLine(d, e); }
    else if (e.h != null) d.style.height = px(Math.max(e.h, 0.5)) + 'px';
    applyRot(d, e);
    if (e.type === 'text' || e.type === 'field') {
      const fam = { Helvetica: 'Arial', Times: 'Georgia', Courier: 'Consolas' }[e.fontFamily || 'Helvetica'] || 'Arial';
      d.style.font = `${e.bold ? '700 ' : ''}${px(e.fontSize || 3)}px ${fam}`;
      d.style.color = e.color || '#000';
      d.style.textAlign = e.align || 'left';
      d.textContent = (e.type === 'field' && !e.bindTo)
        ? ((e.label ? e.label + ' ' : '') + '{{' + (e.key || 'feld') + '}}')
        : resolveEl(e);
    } else if (e.type === 'rect') {
      d.style.border = `${Math.max(1, px(e.lineWidthMm || 0.3))}px solid ${e.stroke || '#000'}`;
      d.style.background = e.fill && e.fill !== 'none' ? e.fill : 'transparent';
    } else if (e.type === 'asset') {
      const a = (window.ASSETS || []).find(x => x.id === e.assetId);
      const img = d.querySelector('img');
      if (a && img && img.dataset.aid !== String(a.id)) { img.src = api('/api/assets/' + a.id + '/raw'); img.dataset.aid = String(a.id); }
      d.style.width = px(e.w || 20) + 'px'; d.style.height = px(e.h || 20) + 'px';
      if (img) { img.style.width = '100%'; img.style.height = '100%'; }
    } else if (e.type === 'barcode') {
      const img = d.querySelector('img');
      if (e.subtype === 'QRCODE' || e.subtype === 'DATAMATRIX') {
        const qs = new URLSearchParams({ code: barCodeData(e), subtype: e.subtype, ecc: e.ecc || 'M' });
        const key = qs.toString();
        d.style.width = px(e.w) + 'px'; d.style.height = px(e.h) + 'px';
        if (img) {
          if (img.dataset.key !== key) { img.src = api('/api/barcode?' + key); img.dataset.key = key; }
          img.style.width = px(e.w) + 'px'; img.style.height = px(e.h) + 'px';
        }
      } else {
        const key = barQs(e).toString();
        if (_natW[key] != null) { if (Math.abs((e.w || 0) - _natW[key]) > 0.3) e.w = r1(_natW[key]); }
        else if (!_natW['req:' + key]) {
          _natW['req:' + key] = 1;
          fetch(api('/api/barcode?' + key)).then(r => r.text()).then(svg => {
            const m = /width="([\d.]+)mm"/.exec(svg);
            if (m) { _natW[key] = parseFloat(m[1]); if (tpl.design.find(x => x.id === e.id)) syncEls(document.getElementById('lblInner')); }
          }).catch(() => {});
        }
        if (img) {
          if (img.dataset.key !== key) { img.src = api('/api/barcode?' + key); img.dataset.key = key; }
          img.style.width = px(e.w) + 'px'; img.style.height = px(Math.max(3, e.h)) + 'px';
        }
      }
    }
    const badge = d.querySelector('.linkbadge');
    if (e.bindTo && !badge) d.insertAdjacentHTML('beforeend', '<div class="linkbadge">🔗</div>');
    if (!e.bindTo && badge) badge.remove();
  }

  function renderEl(e) {
    const d = document.createElement('div');
    d.className = 'el' + (sel === e.id ? ' selected' : '');
    d.dataset.id = e.id;
    d.style.left = px(e.x) + 'px';
    d.style.top = px(e.y) + 'px';
    if (e.w != null) d.style.width = px(e.w) + 'px';
    if (e.type === 'line') { d.style.height = '0px'; d.style.padding = '1px 0'; boxLine(d, e); }
    else if (e.h != null) d.style.height = px(Math.max(e.h, 0.5)) + 'px';
    applyRot(d, e);
    d.style.zIndex = (e.z || 0) + 1;

    if (e.type === 'text' || e.type === 'field') {
      const fam = { Helvetica: 'Arial', Times: 'Georgia', Courier: 'Consolas' }[e.fontFamily || 'Helvetica'] || 'Arial';
      d.style.font = `${e.bold ? '700 ' : ''}${px(e.fontSize || 3)}px ${fam}`;
      d.style.color = e.color || '#000';
      d.style.textAlign = e.align || 'left';
      d.textContent = (e.type === 'field' && !e.bindTo)
        ? ((e.label ? e.label + ' ' : '') + '{{' + (e.key || 'feld') + '}}')
        : resolveEl(e);
      d.style.opacity = e.type === 'field' ? .92 : 1;
    } else if (e.type === 'rect') {
      d.style.border = `${Math.max(1, px(e.lineWidthMm || 0.3))}px solid ${e.stroke || '#000'}`;
      d.style.background = e.fill && e.fill !== 'none' ? e.fill : 'transparent';
    } else if (e.type === 'asset') {
      const a = (window.ASSETS || []).find(x => x.id === e.assetId);
      d.innerHTML = a ? `<img data-aid="${a.id}" src="${api('/api/assets/' + a.id + '/raw')}">`
        : `<div style="color:#c33;font-size:12px;padding:4px;outline:1.5px dashed #d99;border-radius:6px;height:100%;display:grid;place-items:center">Bild wählen…</div>`;
      d.style.width = px(e.w || 20) + 'px'; d.style.height = px(e.h || 20) + 'px';
      const img = d.querySelector('img'); if (img) { img.style.width = '100%'; img.style.height = '100%'; }
    } else if (e.type === 'barcode') {
      if (e.subtype === 'QRCODE' || e.subtype === 'DATAMATRIX') {
        const qs = new URLSearchParams({ code: barCodeData(e), subtype: e.subtype, ecc: e.ecc || 'M' });
        d.innerHTML = `<img data-key="${qs.toString()}" src="${api('/api/barcode?' + qs)}" style="width:${px(e.w)}px;height:${px(e.h)}px">`;
      } else {
        const qs = barQs(e);
        const key = qs.toString();
        // Modell: Boxbreite == natürliche Symbolbreite (autokorrigieren)
        if (_natW[key] != null) { if (Math.abs((e.w || 0) - _natW[key]) > 0.3) e.w = r1(_natW[key]); }
        else if (!_natW['req:' + key]) {
          _natW['req:' + key] = 1;
          fetch(api('/api/barcode?' + key)).then(r => r.text()).then(svg => {
            const m = /width="([\d.]+)mm"/.exec(svg);
            if (m) { _natW[key] = parseFloat(m[1]); const cur = tpl.design.find(x => x.id === e.id); if (cur) render(); }
          }).catch(() => {});
        }
        d.innerHTML = `<img data-key="${key}" src="${api('/api/barcode?' + key)}" style="height:${px(Math.max(3, e.h))}px;width:${px(e.w)}px">`;
        d.style.display = 'flex'; d.style.alignItems = 'flex-start';
      }
    }

    if (e.bindTo) d.insertAdjacentHTML('beforeend', '<div class="linkbadge">🔗</div>');
    return d;
  }
  function boxLine(d, e) {
    d.style.borderTop = `${Math.max(1, px(e.lineWidthMm || 0.3))}px solid ${e.color || '#000'}`;
  }
  function applyRot(d, e) {
    if (e.rotation) {
      const cx = px(e.w || 0) / 2, cy = px(e.type === 'line' ? 1 : (e.h || 0)) / 2;
      d.style.transform = `rotate(${e.rotation}deg)`;
      d.style.transformOrigin = `${cx}px ${cy}px`;
    } else d.style.transform = '';
  }

  function renderSelbox() {
    const inner = $('#lblInner'); if (!inner) return;
    let sb = $('#selbox');
    if (!sb) { sb = document.createElement('div'); sb.id = 'selbox'; inner.appendChild(sb); }
    const e = tpl.design.find(x => x.id === sel);
    if (!e) { sb.style.display = 'none'; sb.innerHTML = ''; return; }
    const wpx = Math.max(8, px(e.w || 0));
    const hpx = e.type === 'line' ? 8 : Math.max(8, px(e.h || 0));
    const yo = e.type === 'line' ? -(hpx - Math.max(1, px(e.lineWidthMm || 0.3))) / 2 : 0;
    sb.style.display = 'block';
    sb.style.left = px(e.x) + 'px';
    sb.style.top = (px(e.y) + yo) + 'px';
    sb.style.width = wpx + 'px';
    sb.style.height = hpx + 'px';
    if (e.rotation) { sb.style.transform = `rotate(${e.rotation}deg)`; sb.style.transformOrigin = 'center center'; }
    else sb.style.transform = '';
    let h = '<div class="sb-frame"></div>';
    const corners = e.type === 'line' ? [] : ['nw', 'ne', 'sw', 'se'];
    const edges = e.type === 'line' ? ['w', 'e'] : ['n', 's', 'w', 'e'];
    corners.forEach(c => h += `<div class="handle h-${c}" data-h="${c}"></div>`);
    edges.forEach(c => h += `<div class="handle h-${c}" data-h="${c}"></div>`);
    h += '<div class="rot-stem"></div><div class="handle rot-handle" data-h="rot" title="Drehen (Shift = 15°-Raster)"></div>';
    h += `<div class="sb-size">${r1(e.w || 0)} × ${r1(e.h || 0)}</div>`;
    sb.innerHTML = h;
  }

  // ---------- Lineale ----------
  let rulerSig = null;
  function renderRulers() {
    const sig = stageSig();
    if (sig === rulerSig) return;
    rulerSig = sig;
    const W = tpl.width_mm, H = tpl.height_mm;
    drawRuler($('#rulerTop'), W, px, 'x');
    drawRuler($('#rulerLeft'), H, px, 'y');
  }
  function drawRuler(el, mmTotal, pxf, axis) {
    const size = Math.ceil(pxf(mmTotal)) + 1;
    const stepChoices = [1, 2, 5, 10, 20, 25, 50, 100];
    let step = stepChoices.find(s => pxf(s) >= 48) || 100;
    const minor = step / (step >= 20 ? 4 : step >= 10 ? 5 : (step === 5 ? 5 : 2));
    let svg = `<svg width="${axis === 'x' ? size : 24}" height="${axis === 'x' ? 24 : size}" style="display:block">`;
    svg += `<rect width="100%" height="100%" fill="#fff"/>`;
    for (let v = 0; v <= mmTotal + 0.001; v += minor) {
      const p = px(fix(v)); if (p > size) break;
      const isMajor = Math.abs(v / step - Math.round(v / step)) < 1e-6;
      const len = isMajor ? 9 : 4.5;
      svg += axis === 'x'
        ? `<line x1="${p}" y1="${24 - len}" x2="${p}" y2="24" stroke="${isMajor ? '#94a3b8' : '#cbd5e1'}"/>`
        : `<line x1="${24 - len}" y1="${p}" x2="24" y2="${p}" stroke="${isMajor ? '#94a3b8' : '#cbd5e1'}"/>`;
      if (isMajor) {
        const lbl = Math.round(v);
        svg += axis === 'x'
          ? `<text x="${p + 2}" y="10" font-size="8.5" fill="#64748b">${lbl}</text>`
          : `<text x="2" y="${p + 8}" font-size="8.5" fill="#64748b" >${lbl}</text>`;
      }
    }
    svg += `</svg>`;
    el.innerHTML = svg;
    el.style.width = (axis === 'x' ? size : 24) + 'px';
    el.style.height = (axis === 'x' ? 24 : size) + 'px';
  }
  function fix(v) { return Math.round(v * 100) / 100; }
  function px(v) { return v * 96 / 25.4 * zoom; }

  // ---------- Snap ----------
  function snapCandidates(skip) {
    const ls = labelSize();
    const xs = [0, ls.w], ys = [0, ls.h];
    if (ls.w > 4) xs.push(ls.w / 2);
    if (ls.h > 4) ys.push(ls.h / 2);
    tpl.design.forEach((e) => {
      if (e.id === skip) return;
      xs.push(e.x, e.x + (e.w || 0));
      ys.push(e.y, e.y + (e.h || 0));
      xs.push(e.x + (e.w || 0) / 2);
      ys.push(e.y + (e.h || 0) / 2);
    });
    return { xs, ys };
  }
  function snapVal(v, cands, tolPx) {
    let best = null, bestD = 999;
    for (const c of cands) {
      const dpx = Math.abs(c - v) * 96 / 25.4 * zoom;
      if (dpx <= tolPx && dpx < bestD) { bestD = dpx; best = c; }
    }
    return best;
  }
  let snapEls = [];
  function showSnap(vLines, hLines) {
    snapEls.forEach(n => n.remove()); snapEls = [];
    const inner = $('#lblInner'); if (!inner) return;
    const add = (cls, style) => {
      const n = document.createElement('div'); n.className = 'snapline ' + cls; n.style.cssText = style;
      inner.appendChild(n); snapEls.push(n);
    };
    vLines.forEach(x => add('', `left:${px(x)}px;top:-6px;bottom:-6px;width:1px`));
    hLines.forEach(y => add('', `top:${px(y)}px;left:-6px;right:-6px;height:1px`));
  }

  // ---------- HUD ----------
  function hud(text, xpx, ypx) {
    const h = $('#hud');
    if (!text) { h.style.display = 'none'; return; }
    h.textContent = text; h.style.display = 'block';
    const outer = $('#stageOuter').getBoundingClientRect();
    h.style.left = (xpx - outer.left + 14) + 'px';
    h.style.top = (ypx - outer.top + 18) + 'px';
  }

  // ---------- Interaktion ----------
  stage.addEventListener('dblclick', (ev) => {
    const elDiv = ev.target.closest('.el');
    if (!elDiv) return;
    const e = tpl.design.find(x => x.id === elDiv.dataset.id);
    if (!e || (e.type !== 'text' && e.type !== 'field')) return;
    if (e.type === 'field' && e.bindTo) return;
    sel = e.id; render();
    const box = stage.querySelector(`.el[data-id="${e.id}"]`);
    box.contentEditable = 'true';
    box.style.outline = '2px solid var(--accent)';
    box.style.cursor = 'text'; box.style.zIndex = 60;
    box.focus();
    document.execCommand && document.getSelection().selectAllChildren(box);
    const commit = () => {
      const txt = box.innerText.replace(/\n+$/, '');
      box.contentEditable = 'false';
      if (e.type === 'text') e.content = txt; else e.key = txt.replace(/[{}]/g, '').trim() || e.key;
      render(); markDirty();
      box.removeEventListener('blur', commit);
    };
    box.addEventListener('blur', commit);
    box.addEventListener('keydown', (k) => {
      if (k.key === 'Enter' && !k.shiftKey) { k.preventDefault(); box.blur(); }
      if (k.key === 'Escape') { box.contentEditable = 'false'; render(); }
    });
    ev.preventDefault();
  });

  let drag = null;
  stage.addEventListener('mousedown', (ev) => {
    const hb = ev.target.closest('.handle');
    const elDiv = ev.target.closest('.el');
    const selE = tpl.design.find(x => x.id === sel);

    if (hb && selE) {
      drag = { e: selE, sx: ev.clientX, sy: ev.clientY, ox: selE.x, oy: selE.y,
        ow: selE.w || 0, oh: selE.h || 0, omw: selE.moduleWidthMm || 0.25,
        handle: hb.dataset.h, moved: false, ls: labelSize() };
      if (selE.type === 'barcode' && selE.subtype !== 'QRCODE' && selE.subtype !== 'DATAMATRIX') {
        const key = barQs(selE).toString();
        if (_natW[key] == null) fetch(api('/api/barcode?' + key)).then(r => r.text())
          .then(svg => { const m = /width="([\d.]+)mm"/.exec(svg); if (m) _natW[key] = parseFloat(m[1]); }).catch(() => {});
      }
      ev.preventDefault();
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
      return;
    }
    if (!elDiv) { if (sel) { sel = null; render(); } return; }
    const id = elDiv.dataset.id;
    const e = tpl.design.find(x => x.id === id);
    if (!e) return;

    // Alt+Klick = verknüpfen: ausgewähltes Element wird an angeklicktes gebunden
    if (ev.altKey && sel && sel !== id && e.type !== 'barcode') {
      const s = tpl.design.find(x => x.id === sel);
      if (s && (s.type === 'barcode' || s.type === 'text' || s.type === 'field')) {
        s.bindTo = e.id;
        render(); markDirty();
        toast(`🔗 verknüpft mit „${e.key || e.content || e.id}“`);
        ev.preventDefault(); return;
      }
    }
    if (sel !== id) sel = id;
    drag = { e, sx: ev.clientX, sy: ev.clientY, ox: e.x, oy: e.y, ow: e.w || 0, oh: e.h || 0,
      omw: e.moduleWidthMm || 0.25, handle: null, moved: false, ls: labelSize() };
    if (e.type === 'barcode' && e.subtype !== 'QRCODE' && e.subtype !== 'DATAMATRIX') {
      const key = barQs(e).toString();
      if (_natW[key] == null) fetch(api('/api/barcode?' + key)).then(r => r.text())
        .then(svg => { const m = /width="([\d.]+)mm"/.exec(svg); if (m) _natW[key] = parseFloat(m[1]); }).catch(() => {});
    }
    ev.preventDefault();
    renderSelbox(); renderProps();
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  });

  function onMove(ev) {
    if (!drag) return;
    const e = drag.e, ls = drag.ls;
    const dx = mmFromPx(ev.clientX - drag.sx), dy = mmFromPx(ev.clientY - drag.sy);
    drag.moved = drag.moved || Math.abs(dx) > .05 || Math.abs(dy) > .05;
    const tolPx = 6;

    if (drag.handle === 'rot') {
      const d = stage.querySelector(`.el[data-id="${e.id}"]`);
      const b = d.getBoundingClientRect();
      const cx = b.left + b.width / 2, cy = b.top + b.height / 2;
      let ang = Math.atan2(ev.clientX - cx, -(ev.clientY - cy)) * 180 / Math.PI;
      if (ev.shiftKey) ang = Math.round(ang / 15) * 15;
      e.rotation = Math.round(ang * 10) / 10;
      const div = stage.querySelector(`.el[data-id="${e.id}"]`);
      applyRot(div, e);
      renderSelbox();
      hud(`${e.rotation}°`, ev.clientX, ev.clientY);
      return;
    }

    if (drag.handle) {
      resizeStep(e, ev, dx, dy, ls);
    } else {
      // Verschieben mit Snap (linke Kante/Mitte/rechte Kante, analog y)
      let nx = drag.ox + dx, ny = drag.oy + dy;
      const c = snapCandidates(e.id);
      let snappedX = null, snappedY = null;
      for (const key of ['l', 'c', 'r']) {
        const probe = nx + (key === 'c' ? e.w / 2 : key === 'r' ? e.w : 0);
        const s = snapVal(probe, c.xs, tolPx);
        if (s !== null) { nx = s - (key === 'c' ? e.w / 2 : key === 'r' ? e.w : 0); snappedX = s; break; }
      }
      for (const key of ['t', 'vc', 'b']) {
        const probe = ny + (key === 'vc' ? e.h / 2 : key === 'b' ? e.h : 0);
        const s = snapVal(probe, c.ys, tolPx);
        if (s !== null) { ny = s - (key === 'vc' ? e.h / 2 : key === 'b' ? e.h : 0); snappedY = s; break; }
      }
      if (!snappedX && snapOn) nx = Math.round(nx * 2) / 2;
      if (!snappedY && snapOn) ny = Math.round(ny * 2) / 2;
      nx = Math.max(-e.w + 2, Math.min(ls.w - 1, nx));
      ny = Math.max(-e.h + 1, Math.min(ls.h - 1, ny));
      e.x = r1(nx); e.y = r1(ny);
      showSnap(snappedX !== null ? [snappedX] : [], snappedY !== null ? [snappedY] : []);
      hud(`${r1(e.x)} × ${r1(e.y)} mm  ·  ↕ ${r1(e.w)} × ${r1(e.h)}`, ev.clientX, ev.clientY);
    }
    positionEl(e);
    renderSelbox();
    renderLinks();
  }

  function resizeStep(e, ev, dx, dy, ls) {
    const h = drag.handle;
    let x0 = drag.ox, y0 = drag.oy, x1 = drag.ox + drag.ow, y1 = drag.oy + drag.oh;
    if (h === 'w' || h === 'nw' || h === 'sw') x0 = drag.ox + dx;
    if (h === 'e' || h === 'ne' || h === 'se') x1 = drag.ox + drag.ow + dx;
    if (h === 'n' || h === 'nw' || h === 'ne') y0 = drag.oy + dy;
    if (h === 's' || h === 'sw' || h === 'se') y1 = drag.oy + drag.oh + dy;

    const c = snapCandidates(e.id);
    if (h.includes('w')) { const s = snapVal(x0, c.xs, 6); x0 = s !== null ? s : Math.round(x0 * 2) / 2; }
    if (h.includes('e')) { const s = snapVal(x1, c.xs, 6); x1 = s !== null ? s : Math.round(x1 * 2) / 2; }
    if (h.startsWith('n')) { const s = snapVal(y0, c.ys, 6); y0 = s !== null ? s : Math.round(y0 * 2) / 2; }
    if (h.startsWith('s')) { const s = snapVal(y1, c.ys, 6); y1 = s !== null ? s : Math.round(y1 * 2) / 2; }

    let w = Math.max(e.type === 'line' ? 0.5 : 1, Math.abs(x1 - x0));
    let hh = (e.type === 'line' || h === 'w' || h === 'e') ? drag.oh : Math.max(0.8, Math.abs(y1 - y0));
    if (e.type === 'line') hh = 0;
    if ((e.subtype === 'QRCODE' || e.subtype === 'DATAMATRIX' || e.type === 'asset') && h.length === 2) {
      hh = w;  // Quadrat/Bild-Seitenverhältnis erhalten
    }
    e.x = r1(Math.min(x0, x1)); e.y = r1(Math.min(y0, y1));
    e.w = r1(w); if (e.type !== 'line') e.h = r1(hh);
    // Linearer Barcode: Breite ziehen = Modulbreite mitziehen (Symbol füllt die Box)
    if (e.type === 'barcode' && e.subtype !== 'QRCODE' && e.subtype !== 'DATAMATRIX'
        && (h === 'e' || h === 'w' || h === 'ne' || h === 'nw' || h === 'se' || h === 'sw')
        && drag.ow > 0) {
      // Ruhezone fix 2×2,5 mm → bars = ow−5; neues Modul = omw·(neueBreite−5)/bars
      const bars = Math.max(1, drag.ow - 5);
      e.moduleWidthMm = Math.min(3, Math.max(0.12, Math.round(drag.omw * (e.w - 5) / bars * 1000) / 1000));
      hud(`${r1(e.w)} × ${r1(e.h)} mm · Modul ${e.moduleWidthMm.toFixed(2)} mm`, ev.clientX, ev.clientY);
    } else {
      hud(`${r1(e.w)} × ${r1(e.h)} mm`, ev.clientX, ev.clientY);
    }
    const v = [], hv = [];
    if (h.includes('w')) v.push(e.x);
    if (h.includes('e')) v.push(e.x + e.w);
    if (h.startsWith('n')) hv.push(e.y);
    if (h.startsWith('s')) hv.push(e.y + e.h);
    showSnap(v, hv);
  }

  function positionEl(e) {
    const div = stage.querySelector(`.el[data-id="${e.id}"]`);
    if (!div) return;
    div.style.left = px(e.x) + 'px'; div.style.top = px(e.y) + 'px';
    if (e.w != null) div.style.width = px(e.w) + 'px';
    if (e.type !== 'line' && e.h != null) div.style.height = px(Math.max(e.h, 0.5)) + 'px';
    applyRot(div, e);
    const img = div.querySelector('img');
    if (img && e.type === 'barcode') {
      if (e.subtype === 'QRCODE' || e.subtype === 'DATAMATRIX') {
        img.style.width = px(e.w) + 'px'; img.style.height = px(e.h) + 'px';
      } else {
        img.style.width = px(e.w) + 'px';   // Lineal: live strecken, neu gerastert wird auf mouseup
      }
    } else if (img && e.type === 'asset') {
      img.style.width = px(e.w) + 'px'; img.style.height = px(e.h) + 'px';
    }
  }

  function onUp(ev) {
    const e = drag && drag.e;
    const wasGeom = drag && drag.moved;
    const hadHandle = drag && drag.handle;
    drag = null;
    showSnap([], []); hud(null);
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
    if (wasGeom) markDirty();
    if (wasGeom && e && e.type === 'barcode' && e.subtype !== 'QRCODE' && e.subtype !== 'DATAMATRIX') {
      // Boxbreite == Symbolbreite: render() autokorrigiert über _natW-Cache
      const key = barQs(e).toString();
      if (_natW[key] != null) e.w = r1(_natW[key]);
      else syncBarWidth(e);
      render();
    } else if (wasGeom && e && e.type === 'barcode') { render(); }
    if (wasGeom) { renderSelbox(); renderProps(); }
  }

  // ---------- Links ----------
  function renderLinks() {
    const ll = document.getElementById('linkLayer');
    if (!ll) return;
    while (ll.firstChild) ll.removeChild(ll.firstChild);
    tpl.design.forEach((e) => {
      if (!e.bindTo) return;
      const t = tpl.design.find(x => x.id === e.bindTo);
      if (!t) return;
      const a = center(e), b = center(t);
      const hi = (sel === e.id || sel === t.id) ? '#4f6ef7' : '#f59e0b';
      ll.insertAdjacentHTML('beforeend',
        `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="${hi}" stroke-width="1.6" stroke-dasharray="5 3"/>` +
        `<circle cx="${b.x}" cy="${b.y}" r="4" fill="${hi}"/>` +
        `<path d="M ${a.x - 4} ${a.y - 7} L ${a.x + 4} ${a.y} L ${a.x - 4} ${a.y + 7} Z" fill="${hi}"/>`);
    });
  }
  function center(e) { return { x: px(e.x + (e.w || 0) / 2), y: px(e.y + (e.h || 0) / 2) }; }

  function markActiveTool() {
    const e = tpl.design.find(x => x.id === sel);
    const map = { text: 'text', field: 'field', line: 'line', rect: 'rect', asset: 'asset' };
    let key = e ? (e.type === 'barcode' ? (e.subtype === 'QRCODE' ? 'qr' : 'barcode') : map[e.type]) : null;
    $$('[data-add]').forEach(b => b.classList.toggle('active', b.dataset.add === key));
  }

  // ---------- Tastatur ----------
  document.addEventListener('keydown', (ev) => {
    if (/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) return;
    const K = ev.key;
    if ((ev.ctrlKey || ev.metaKey) && K.toLowerCase() === 'z') { (ev.shiftKey ? redo : undo)(); ev.preventDefault(); return; }
    if ((ev.ctrlKey || ev.metaKey) && K.toLowerCase() === 'y') { redo(); ev.preventDefault(); return; }
    if ((ev.ctrlKey || ev.metaKey) && K.toLowerCase() === 's') { save(); ev.preventDefault(); return; }
    const e = tpl.design.find(x => x.id === sel);
    if (!e) return;
    const step = ev.shiftKey ? 1 : 0.2;
    if (K === 'Delete' || K === 'Backspace') { delEl(e); ev.preventDefault(); }
    else if (K === 'Escape') { sel = null; render(); }
    else if (K === 'ArrowLeft') { e.x = r1(e.x - step); render(); markDirty(); ev.preventDefault(); }
    else if (K === 'ArrowRight') { e.x = r1(e.x + step); render(); markDirty(); ev.preventDefault(); }
    else if (K === 'ArrowUp') { e.y = r1(e.y - step); render(); markDirty(); ev.preventDefault(); }
    else if (K === 'ArrowDown') { e.y = r1(e.y + step); render(); markDirty(); ev.preventDefault(); }
    else if (K === '[') { e.z = Math.max(0, (e.z || 0) - 1); rez(); ev.preventDefault(); }
    else if (K === ']') { e.z = (e.z || 0) + 1; rez(); ev.preventDefault(); }
    else if ((ev.ctrlKey || ev.metaKey) && K.toLowerCase() === 'b' && (e.type === 'text' || e.type === 'field')) {
      e.bold = !e.bold; render(); markDirty(); ev.preventDefault();
    }
    else if ((ev.ctrlKey || ev.metaKey) && K.toLowerCase() === 'd') {
      const c = JSON.parse(JSON.stringify(e)); c.id = 'e' + (uid++); c.x = r1(c.x + 3); c.y = r1(c.y + 3); c.z = tpl.design.length;
      tpl.design.push(c); sel = c.id; render(); markDirty(); ev.preventDefault();
    }
    else if ((ev.ctrlKey || ev.metaKey) && K.toLowerCase() === 's') { save(); ev.preventDefault(); }
    else if ((ev.ctrlKey || ev.metaKey) && K.toLowerCase() === 'z') { (ev.shiftKey ? redo : undo)(); ev.preventDefault(); }
    else if ((ev.ctrlKey || ev.metaKey) && K.toLowerCase() === 'y') { redo(); ev.preventDefault(); }
  });
  function delEl(e) { tpl.design = tpl.design.filter(x => x.id !== e.id); sel = null; render(); markDirty(); }
  function rez() { tpl.design.sort((a, b) => (a.z || 0) - (b.z || 0)); render(); markDirty(); }

  // ---------- Elemente hinzufügen ----------
  $$('[data-add]').forEach(b => b.addEventListener('click', () => {
    let type = b.dataset.add;
    if (type === 'asset') { openAssetDialog(); return; }
    const e = mkEl(type === 'qr' ? 'barcode' : type);
    if (type === 'qr') { e.subtype = 'QRCODE'; e.w = 20; e.h = 20; }
    tpl.design.push(e); sel = e.id; render(); markDirty();
  }));

  // ---------- Property-Panel (ohne Geometrie-Zahlen) ----------
  function renderProps() {
    const body = $('#propsBody');
    const kind = $('#selKind');
    const e = tpl.design.find(x => x.id === sel);
    if (!e) {
      kind.textContent = '';
      markActiveTool();
      body.innerHTML = '<p class="hint">Kein Element ausgewählt — klicke eines auf der Fläche an.<br><br>' +
        'Größe &amp; Position änderst du direkt durch Ziehen an den blauen Punkt­kanten, Drehen am oberen Punkt. ' +
        'Die Lineale zeigen dir mm.</p>';
      return;
    }
    markActiveTool();
    kind.textContent = e.type === 'barcode' ? (LABELS[e.subtype] || e.subtype) : ({ text: 'Text', field: 'Datenfeld', line: 'Linie', rect: 'Rahmen', asset: 'Bild' }[e.type] || e.type);
    const isTxt = e.type === 'text' || e.type === 'field';
    let h = '';

    h += `<div class="grp row gap" style="margin-bottom:6px"><span class="hint">📐 <b>${r1(e.w||0)} × ${r1(e.h||0)} mm</b> @ ${r1(e.x)}, ${r1(e.y)} · gedreht ${r1(e.rotation||0)}°</span></div>`;

    /* ---------- INHALT ---------- */
    h += '<div class="sect">Inhalt</div>';
    if (e.type === 'text') {
      h += `<div class="grp"><label>Text <span style="opacity:.55">({{feld}} erlaubt)</span></label><textarea data-k="content">${esc(e.content)}</textarea></div>`;
      h += `<div class="grp"><label>🔗 Daten übernehmen von</label><select data-k="bindTo">${bindOptionsHtml(e)}</select></div>`;
    }
    if (e.type === 'field') {
      h += `<div class="grp"><label>CSV/Excel-Spalte</label><input data-k="key" value="${esc(e.key)}"></div>` +
        `<div class="grp"><label>Vortext (optional)</label><input data-k="label" value="${esc(e.label)}"></div>` +
        `<label class="chk"><input type="checkbox" data-k="uppercase" ${e.uppercase ? 'checked' : ''}> Großbuchstaben</label>` +
        `<div class="grp" style="margin-top:10px"><label>🔗 Wert übernehmen von</label><select data-k="bindTo">${bindOptionsHtml(e)}</select></div>`;
    }
    if (e.type === 'barcode') {
      h += `<div class="grp"><label>Typ</label><select data-k="subtype">` +
        (window.BARCODE_TYPES || ['CODE128']).map(t => `<option value="${t}" ${e.subtype === t ? 'selected' : ''}>${LABELS[t] || t}</option>`).join('') + '</select></div>';
      const mode = e.bindTo ? 'bind' : (e.code && e.code.includes('{{') ? 'feld' : 'fest');
      h += `<div class="grp"><label>Datenquelle</label><select data-k="srcmode">
              <option value="feld" ${mode === 'feld' ? 'selected' : ''}>CSV/Excel-Feld {{…}}</option>
              <option value="fest" ${mode === 'fest' ? 'selected' : ''}>Fester Text</option>
              <option value="bind" ${mode === 'bind' ? 'selected' : ''}>🔗 Anderer Baustein</option>
            </select></div>`;
      if (mode !== 'bind') {
        h += `<div class="grp"><input data-k="code" value="${esc(e.code)}" placeholder="{{artnr}}"></div>`;
      } else {
        h += `<div class="grp"><select data-k="bindTo">${bindOptionsHtml(e)}</select>` +
          (e.bindTo ? `<div class="hint">kodiert live: <b>${esc(barCodeData(e))}</b></div>` : '') + '</div>';
      }
    }
    if (e.type === 'asset') {
      h += `<div class="grp"><button class="btn small ghost" id="pickAsset"><i data-ic="image"></i> Bild wählen…</button></div>`;
    }

    /* ---------- TEXT & FARBE ---------- */
    if (isTxt) {
      h += '<div class="sect">Darstellung</div>';
      h += `<div class="grp"><label>Schrift</label><select data-k="fontFamily">` +
        ['Helvetica', 'Times', 'Courier'].map(f => `<option ${e.fontFamily === f ? 'selected' : ''}>${f}</option>`).join('') + '</select></div>';
      h += `<div class="grp"><label>Schriftgröße (mm)</label>` +
        `<input type="range" min="1.2" max="14" step="0.2" data-k="fontSize" value="${num(e.fontSize, 3)}"><span class="hint" id="fsEcho"></span></div>`;
      // Ausrichtungs-Toolbar: Fett | links/zentriert/rechts | oben/mitte/unten
      const AL = { left: 'alL', center: 'alC', right: 'alR' };
      const VA = { top: 'vT', middle: 'vM', bottom: 'vB' };
      h += `<div class="grp"><label>Ausrichtung</label><div class="seg icons" style="width:100%">` +
        `<button data-toggle="bold" class="${e.bold ? 'on' : ''}" title="Fett (Ctrl+B)"><i data-ic="bold"></i></button>` +
        Object.keys(AL).map(a => `<button data-align="${a}" class="${(e.align || 'left') === a ? 'on' : ''}" title="Text ${({left:'links',center:'zentriert',right:'rechts'})[a]}"><i data-ic="${AL[a]}"></i></button>`).join('') +
        `<span style="width:1px;background:var(--border);margin:6px 3px"></span>` +
        Object.keys(VA).map(v => `<button data-valign="${v}" class="${(e.valign || 'top') === v ? 'on' : ''}" title="${({top:'oben',middle:'mittig',bottom:'unten'})[v]}"><i data-ic="${VA[v]}"></i></button>`).join('') +
        `</div><div class="hint">Zentriert = Text mittig <b>im Kasten</b>. Position/Größe änderst du direkt auf der Fläche.</div></div>`;
      const SW = ['#000000', '#333333', '#767676', '#b91c1c', '#c2410c', '#a16207', '#15803d', '#0f766e', '#1d4ed8', '#6d28d9'];
      h += `<div class="grp"><label>Farbe</label><div class="swatches">` +
        SW.map(c => `<button class="swatch${(e.color || '#000000').toLowerCase() === c ? ' on' : ''}" data-color="${c}" style="background:${c}" title="${c}"></button>`).join('') +
        `</div><div style="display:flex;gap:6px;align-items:center;margin-top:6px">
          <input data-k="color" type="color" value="${(e.color || '#000000').slice(0, 7)}" style="width:44px" title="Eigene Farbe">
          <span class="hint">${SW.some(c => c === (e.color || '#000000').toLowerCase()) ? '' : 'eigene Farbe'}</span></div></div>`;
    }
    if (e.type === 'line' || e.type === 'rect') {
      h += '<div class="sect">Darstellung</div>';
      h += `<div class="grp"><label>Linienstärke (mm)</label><input type="range" min="0.1" max="3" step="0.1" data-k="lineWidthMm" value="${num(e.lineWidthMm, 0.3)}"><span class="hint" id="lwEcho"></span></div>`;
      if (e.type === 'line') h += `<div class="grp"><label>Farbe</label><input data-k="color" type="color" value="${(e.color || '#000000').slice(0, 7)}"></div>`;
      else h += `<div class="grp two"><div><label>Rahmen</label><input data-k="stroke" type="color" value="${(e.stroke || '#000000').slice(0, 7)}"></div>` +
        `<div><label>Füllung</label><input data-k="fill" type="color" value="${(e.fill && e.fill !== 'none' ? e.fill : '#ffffff').slice(0, 7)}"></div></div>` +
        `<label class="chk"><input type="checkbox" id="fillOn" ${e.fill && e.fill !== 'none' ? 'checked' : ''}> Füllung aktiv</label>`;
    }
    if (e.type === 'barcode' && e.subtype !== 'QRCODE' && e.subtype !== 'DATAMATRIX') {
      h += '<div class="sect">Darstellung</div>';
      h += `<div class="grp"><label>Modulbreite (mm — dünnster Strich)</label>` +
        `<input type="range" min="0.15" max="1" step="0.01" data-k="moduleWidthMm" value="${num(e.moduleWidthMm, 0.25)}"><span class="hint" id="mwEcho"></span></div>`;
      h += `<label class="chk"><input type="checkbox" data-k="showText" ${e.showText ? 'checked' : ''}> Lesetext unter Barcode</label>`;
      h += `<div class="hint">Tipp: <span class="kbd">Alt+Klick</span> auf einen Text/Baustein verknüpft ihn mit diesem Barcode.</div>`;
    } else if (e.type === 'barcode' && e.subtype === 'QRCODE') {
      h += '<div class="sect">Darstellung</div>';
      h += `<div class="grp"><label>Fehlerkorrektur</label><select data-k="ecc"><option ${e.ecc === 'L' ? 'selected' : ''}>L – wenig</option><option ${(!e.ecc || e.ecc === 'M') ? 'selected' : ''}>M – Standard</option><option ${e.ecc === 'Q' ? 'selected' : ''}>Q</option><option ${e.ecc === 'H' ? 'selected' : ''}>H – max</option></select></div>`;
    }

    /* ---------- ELEMENT ---------- */
    h += '<div class="sect">Element</div>';
    h += `<div class="grp row gap" style="flex-wrap:wrap">
      <button class="btn small ghost" id="dupEl" style="flex:1"><i data-ic="copy"></i> Duplizieren</button>
      <button class="btn small danger" id="delEl" style="flex:1">Löschen</button>
      <button class="btn small ghost" id="frontEl" title="nach vorne (])"><i data-ic="front"></i> vorne</button>
      <button class="btn small ghost" id="backEl" title="nach hinten ([)"><i data-ic="back"></i> hinten</button></div>`;
    body.innerHTML = h;

    $$('[data-k]', body).forEach(inp => {
      inp.addEventListener('change', () => applyProp(e, inp.dataset.k, inp));
      if (inp.type === 'range' || inp.type === 'color')
        inp.addEventListener('input', () => { applyProp(e, inp.dataset.k, inp); echo(e, body); });
    });
    $$('[data-align]', body).forEach(b => b.addEventListener('click', () => {
      e.align = b.dataset.align; render(); markDirty();
    }));
    $$('[data-toggle="bold"]', body).forEach(b => b.addEventListener('click', () => {
      e.bold = !e.bold; render(); markDirty();
    }));
    $$('[data-valign]', body).forEach(b => b.addEventListener('click', () => {
      e.valign = b.dataset.valign; render(); markDirty();
    }));
    $$('[data-color]', body).forEach(b => b.addEventListener('click', () => {
      e.color = b.dataset.color; render(); markDirty();
    }));
    echo(e, body);

    const srcSel = $('select[data-k="srcmode"]', body);
    if (srcSel) srcSel.addEventListener('change', () => {
      const m = srcSel.value;
      if (m === 'bind') {
        e.bindTo = e.bindTo || (tpl.design.find(x => x.id !== e.id && (x.type === 'field' || x.type === 'text')) || {}).id || '';
        if (!e.bindTo) delete e.bindTo;
      } else {
        delete e.bindTo;
        if (m === 'feld' && !String(e.code || '').includes('{{'))
          e.code = '{{' + (String(e.code || 'feld').replace(/[^\w\-. ]/g, '') || 'feld') + '}}';
      }
      render(); markDirty();
    });
    $('#delEl', body)?.addEventListener('click', () => delEl(e));
    $('#dupEl', body)?.addEventListener('click', () => {
      const c = JSON.parse(JSON.stringify(e)); c.id = 'e' + (uid++); c.x = r1(c.x + 3); c.y = r1(c.y + 3); c.z = tpl.design.length;
      tpl.design.push(c); sel = c.id; render(); markDirty();
    });
    $('#pickAsset', body)?.addEventListener('click', () => openAssetDialog(e.id));
    $('#fillOn', body)?.addEventListener('change', (ev) => { e.fill = ev.target.checked ? (e.fill || '#ffffff') : ''; render(); markDirty(); });
    $('#frontEl', body)?.addEventListener('click', () => { e.z = 999; rez(); });
    $('#backEl', body)?.addEventListener('click', () => { e.z = -999; rez(); });
  }
  function echo(e, body) {
    const fs = $('#fsEcho', body), mw = $('#mwEcho', body), lw = $('#lwEcho', body);
    if (fs) fs.textContent = r1(num(e.fontSize, 3)).toFixed(1) + ' mm';
    if (mw) mw.textContent = num(e.moduleWidthMm, 0.25).toFixed(2) + ' mm';
    if (lw) lw.textContent = num(e.lineWidthMm, 0.3).toFixed(1) + ' mm';
  }

  const _natW = {};
  function barQs(e) {
    return new URLSearchParams({
      code: barCodeData(e), subtype: e.subtype, module: e.moduleWidthMm || 0.25,
      height: e.barcodeHeightMm > 0 ? e.barcodeHeightMm : Math.max(3, e.h - (e.showText ? 4 : 0)),
      show_text: e.showText ? 'true' : 'false', font_pt: (e.fontSize || 2.4) * 2.835
    });
  }
  function syncBarWidth(e) {
    const key = barQs(e).toString();
    if (_natW[key] != null) { e.w = r1(_natW[key]); render(); markDirty(); return; }
    fetch(api('/api/barcode?' + key)).then(r => r.text()).then(svg => {
      const m = /width="([\d.]+)mm"/.exec(svg);
      if (m) { _natW[key] = parseFloat(m[1]); if (tpl.design.find(x => x.id === e.id)) { e.w = r1(_natW[key]); render(); markDirty(); } }
    }).catch(() => {});
  }

  function bindOptionsHtml(e) {
    const cand = tpl.design.filter(x => x.id !== e.id && (x.type === 'text' || x.type === 'field'));
    let o = '<option value="">— keine —</option>';
    cand.forEach(x => {
      const nm = x.type === 'field' ? ('Datenfeld: ' + (x.key || '?')) : ('Text: „' + (x.content || '').slice(0, 20) + '“');
      o += `<option value="${x.id}" ${e.bindTo === x.id ? 'selected' : ''}>${esc(nm)}</option>`;
    });
    return o;
  }

  function applyProp(e, k, inp) {
    let v = inp.value;
    if (inp.type === 'number' || inp.type === 'range') v = num(v, 0);
    if (inp.type === 'checkbox') v = inp.checked;
    if (k === 'bold' || k === 'showText') { v = v === '1' || v === true; }
    if (k === 'bindTo') v = v || null;
    const cur = e[k];
    if (cur === v) return;
    if (k === 'bindTo' && !v) delete e[k]; else e[k] = v;
    if (k === 'code') delete e.bindTo;
    if (k === 'subtype' && (v === 'QRCODE' || v === 'DATAMATRIX')) { e.w = e.w || 20; e.h = e.h || 20; }
    if (k === 'moduleWidthMm' && e.type === 'barcode' && e.subtype !== 'QRCODE' && e.subtype !== 'DATAMATRIX') {
      // Slider = echte Druckauflösung: Symbolbox folgt der natürlichen Breite
      syncBarWidth(e);
    }
    render(); markDirty();
  }

  // ---------- Bildauswahl ----------
  let assetTarget = null;
  function openAssetDialog(targetId) {
    assetTarget = targetId || sel;
    const list = $('#assetList');
    list.innerHTML = (window.ASSETS || []).map(a =>
      `<div class="card" style="padding:8px;cursor:pointer" data-asset="${a.id}">
         <img src="${api('/api/assets/' + a.id + '/raw')}" style="width:100%;max-height:70px;object-fit:contain;background:#fff;border-radius:6px">
         <div style="font-size:11px;color:var(--dim);margin-top:4px;overflow:hidden;text-overflow:ellipsis">${esc(a.filename)}</div></div>`).join('') ||
      '<p class="hint">Noch keine Bilder — bitte hochladen.</p>';
    $('#assetDlg').showModal();
  }
  $('#assetList').addEventListener('click', (ev) => {
    const c = ev.target.closest('[data-asset]');
    if (!c) return;
    const e = tpl.design.find(x => x.id === assetTarget);
    if (e) {
      e.assetId = parseInt(c.dataset.asset, 10);
      const a = (window.ASSETS || []).find(x => x.id === e.assetId);
      if (a && e.h) { const ar = a.width_px / a.height_px; if (ar) e.w = e.h * ar; }
      render(); markDirty();
    }
    $('#assetDlg').close();
  });
  $('#assetFile').addEventListener('change', async (ev) => {
    const f = ev.target.files[0]; if (!f) return;
    const fd = new FormData(); fd.append('file', f);
    const r = await fetch(api('/api/assets'), { method: 'POST', body: fd });
    if (r.ok) {
      const j = await r.json();
      window.ASSETS.unshift({ id: j.id, filename: j.name, width_px: j.width, height_px: j.height, path: '' });
      toast('Bild hochgeladen'); openAssetDialog(assetTarget);
    } else toast('Upload fehlgeschlagen');
  });
  $('#assetClose').addEventListener('click', () => $('#assetDlg').close());

  // ---------- Größen-Popover (einmal mm eingeben) ----------
  const chip = $('#sizeChip'), pop = $('#sizePop');
  function updateChip() {
    const ls = labelSize();
    const extra = tpl.label_count > 1 ? ` · ${tpl.columns}×${tpl.rows} Bogen` : '';
    $('#sizeChipLabel').textContent = tpl.label_count > 1
      ? `${r1(ls.w)} × ${r1(ls.h)} mm · ${tpl.columns}×${tpl.rows}`
      : `${r1(tpl.width_mm)} × ${r1(tpl.height_mm)} mm`;
    $('#popDims').textContent = `Papier: ${r1(tpl.width_mm)} × ${r1(tpl.height_mm)} mm · ${tpl.dpi} dpi`;
  }
  chip.addEventListener('click', (ev) => {
    const r = chip.getBoundingClientRect();
    pop.style.left = Math.max(8, r.left) + 'px';
    pop.style.top = (r.bottom + window.scrollY + 6) + 'px';
    pop.classList.toggle('open');
    ev.stopPropagation();
  });
  document.addEventListener('click', (ev) => {
    if (pop.classList.contains('open') && !pop.contains(ev.target) && !chip.contains(ev.target))
      pop.classList.remove('open');
  });
  $('#sizeOk').addEventListener('click', () => { pop.classList.remove('open'); });
  ['pW', 'pH', 'pDpi', 'pCount', 'pCols', 'pMargin', 'pGutter'].forEach(id => {
    $('#' + id).addEventListener('change', () => {
      tpl.width_mm = num($('#pW').value, tpl.width_mm);
      tpl.height_mm = num($('#pH').value, tpl.height_mm);
      tpl.dpi = parseInt($('#pDpi').value, 10);
      tpl.label_count = Math.max(1, parseInt($('#pCount').value, 10) || 1);
      tpl.columns = Math.max(1, parseInt($('#pCols').value, 10) || 1);
      tpl.rows = Math.max(1, Math.floor(tpl.label_count / tpl.columns));
      tpl.margin_mm = num($('#pMargin').value, 2);
      tpl.gutter_mm = num($('#pGutter').value, 3);
      render(); markDirty();
    });
  });
  $('#snapBtn').addEventListener('click', () => {
    snapOn = !snapOn;
    $('#snapBtn').classList.toggle('on', snapOn);
  });
  $('#snapBtn').classList.toggle('on', snapOn);
  $('#zoomSel').addEventListener('change', () => { zoom = parseFloat($('#zoomSel').value); render(); });

  // ---------- Ordner-Chip (wohin speichern) ----------
  let FOLDERS = (window.FOLDERS || []).map(f => ({ id: f.id, name: f.name }));
  const fChip = $('#folderChip'), fPop = $('#folderPop');

  function folderName(fid) {
    if (!fid) return 'Hauptbereich';
    const f = FOLDERS.find(x => x.id == fid);
    return f ? f.name : 'Hauptbereich';
  }
  function updateChipFolder() {
    const lbl = $('#folderChipLabel');
    if (lbl) lbl.textContent = folderName(tpl.folder_id);
  }
  function folderListHtml() {
    let h = `<button class="tool${!tpl.folder_id ? ' active' : ''}" data-f="">🏠 Hauptbereich</button>`;
    FOLDERS.forEach(f => {
      h += `<button class="tool${String(tpl.folder_id) === String(f.id) ? ' active' : ''}" data-f="${f.id}">🗀 ${esc(f.name)}</button>`;
    });
    $('#folderList').innerHTML = h;
  }
  function openFolderPop(askToSave) {
    folderListHtml();
    const r = fChip.getBoundingClientRect();
    fPop.style.left = Math.max(8, r.left) + 'px';
    fPop.style.top = (r.bottom + window.scrollY + 6) + 'px';
    fPop.classList.add('open');
    fPop._saveAfter = !!askToSave;
    fPop._goPrint = false;
    $('#newFolderName').focus();
  }
  fChip.addEventListener('click', (ev) => {
    ev.stopPropagation();
    if (fPop.classList.contains('open')) fPop.classList.remove('open');
    else openFolderPop(false);
  });
  // Auswahl im Popover
  $('#folderList').addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-f]'); if (!b) return;
    tpl.folder_id = b.dataset.f ? parseInt(b.dataset.f, 10) : null;
    folderChosen = true;
    fPop.classList.remove('open');
    updateChipFolder();
    if (fPop._saveAfter) save().then(id => { if (id && fPop._goPrint) location.href = api('/drucken/' + id); });
    else markDirty();
    fPop._saveAfter = false;
  });
  // Neuer Ordner aus dem Popover
  async function createFolderInline() {
    const name = $('#newFolderName').value.trim();
    if (!name) return;
    const r = await fetch(api('/api/folders'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }) });
    if (r.status === 409) { toast('Ordner existiert schon — bitte unten auswählen'); }
    if (!r.ok) { toast('Ordner konnte nicht angelegt werden'); return; }
    const j = await r.json();
    FOLDERS.push({ id: j.id, name });
    tpl.folder_id = j.id; folderChosen = true;
    $('#newFolderName').value = '';
    updateChipFolder(); folderListHtml();
    if (fPop._saveAfter) { fPop._saveAfter = false; save().then(id => { if (id && fPop._goPrint) location.href = api('/drucken/' + id); }); }
    toast('Ordner „' + name + '“ angelegt');
  }
  $('#newFolderBtn').addEventListener('click', createFolderInline);
  $('#newFolderName').addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter') { ev.preventDefault(); createFolderInline(); }
  });
  $('#newFolderName').addEventListener('click', ev => ev.stopPropagation());
  document.addEventListener('click', (ev) => {
    if (fPop.classList.contains('open') && !fPop.contains(ev.target) && !fChip.contains(ev.target))
      fPop.classList.remove('open');
  });
  updateChipFolder();

  // ---------- Speichern ----------
  async function save(ev) {
    // Neue Vorlage, Ziel unbekannt → erst fragen, wohin
    if (!tpl.id && !folderChosen) {
      openFolderPop(true);
      if (ev) ev.stopPropagation();   // sonst schließt der Dokument-Click das Popover sofort
      return null;
    }
    tpl.name = $('#tplName').value.trim() || tpl.name || 'Neues Label';
    const r = await fetch(api('/api/templates'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template: Object.assign({}, tpl, { design: tpl.design, actor: (document.cookie.match(/(?:^| )sluser=([^;]+)/) || [])[1] || 'web' }) })
    });
    if (r.status === 409) {
      const d = await r.json().catch(() => ({}));
      if (confirm((d.detail || 'Vorlage wurde zwischenzeitlich geändert.') + '\n\nFremde Änderungen laden? (OK = laden, Abbrechen = hier fortfahren und überschreiben)')) {
        if (confirm('Nicht gespeicherte eigene Änderungen gehen dabei verloren. Neu laden?')) location.reload();
      }
      return null;
    }
    if (!r.ok) { toast('Fehler beim Speichern'); return null; }
    const j = await r.json();
    tpl.rev = j.rev;
    tpl.id = j.id; history.replaceState(null, '', api('/designer/' + j.id));
    folderChosen = true; updateChipFolder();
    dirty = false; setSaved();
    toast('Vorlage gespeichert');
    return j.id;
  }
  $('#btnSave').addEventListener('click', (ev) => save(ev));
  $('#btnSavePrint').addEventListener('click', (ev) => {
    if (!tpl.id && !folderChosen) {
      openFolderPop(true); fPop._goPrint = true; ev.stopPropagation(); return;
    }
    (async () => { const id = await save(ev); if (id && !location.pathname.includes('/drucken/')) location.href = api('/drucken/' + id); })();
  });
  window.addEventListener('beforeunload', (ev) => { if (dirty) { ev.preventDefault(); ev.returnValue = ''; } });

  // ---------- Init ----------
  (async function init() {
    window.BARCODE_TYPES = ['CODE128','EAN13','EAN8','UPCA','CODE39','ITF14','25IND','PHARMA','QRCODE','DATAMATRIX'];
    if (window.TPL_ID) {
      const r = await fetch(api('/api/templates/' + window.TPL_ID));
      if (r.ok) {
        const j = await r.json();
        tpl = { id: j.id, name: j.name, width_mm: j.width_mm, height_mm: j.height_mm, dpi: j.dpi,
          label_count: j.label_count, columns: j.columns, rows: j.rows, margin_mm: j.margin_mm,
          gutter_mm: j.gutter_mm, rev: j.rev, design: j.design || [],
          folder_id: j.folder_id || window.FOLDER_ID || null };
        folderChosen = true;
        tpl.design.forEach(e => { const n = parseInt(String(e.id).replace(/\D/g, ''), 10) || 0; if (n >= uid) uid = n + 1; });
        $('#tplName').value = j.name;
      }
    }
    $('#pW').value = tpl.width_mm; $('#pH').value = tpl.height_mm; $('#pDpi').value = tpl.dpi;
    $('#pCount').value = tpl.label_count; $('#pCols').value = tpl.columns;
    $('#pMargin').value = tpl.margin_mm; $('#pGutter').value = tpl.gutter_mm;
    render();
    hist.push(JSON.stringify({ design: tpl.design, w: tpl.width_mm, h: tpl.height_mm,
      lc: tpl.label_count, cols: tpl.columns, rows: tpl.rows, mg: tpl.margin_mm, gt: tpl.gutter_mm }));
    hix = 0;
  })();
})();
