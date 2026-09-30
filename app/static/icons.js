/* SoftLabel — Inline-SVG-Icons (feder-light) */
(function () {
  const P = {
    folderI: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    text: '<path d="M4 7V4h16v3M12 4v16M9 20h6"/>',
    field: '<rect x="3" y="7" width="18" height="10" rx="2"/><path d="M7 12h6"/><path d="M17 10v4"/>',
    barcode: '<path d="M3 5v14M6.5 5v14M10 5v10M10 19v0M13 5v14M17 5v14M21 5v14"/>',
    qr: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3M21 21v.01M17 21v.01"/>',
    line: '<path d="M4 12h16"/>',
    rect: '<rect x="4" y="6" width="16" height="12" rx="1.5"/>',
    image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="1.7"/><path d="M21 16l-4.5-4.5L7 20"/>',
    save: '<path d="M5 3h11l5 5v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M8 3v6h8V3M8 21v-7h8v7"/>',
    print: '<path d="M7 8V3h10v5"/><rect x="4" y="8" width="16" height="8" rx="2"/><path d="M7 13h10v8H7z"/>',
    ruler: '<rect x="2.5" y="8" width="19" height="8" rx="1.5" transform="rotate(0)"/><path d="M6.5 8v3M10.5 8v4M14.5 8v3M18.5 8v4"/>',
    grid: '<path d="M3 9h18M3 15h18M9 3v18M15 3v18"/>',
    trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
    copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 4H6a2 2 0 0 0-2 2v10"/>',
    alL: '<path d="M4 6h16M4 12h10M4 18h13"/>',
    alC: '<path d="M4 6h16M7 12h10M6 18h12"/>',
    alR: '<path d="M4 6h16M10 12h10M7 18h13"/>',
    vT: '<path d="M4 4h16"/><rect x="8" y="8" width="8" height="12" rx="1"/>',
    vM: '<path d="M4 12h16"/><rect x="8" y="4" width="8" height="16" rx="1"/>',
    vB: '<path d="M4 20h16"/><rect x="8" y="4" width="8" height="12" rx="1"/>',
    front: '<rect x="7" y="7" width="10" height="10" rx="1.5"/><path d="M4 15V5a1 1 0 0 1 1-1h10"/>',
    back: '<rect x="4" y="4" width="10" height="10" rx="1.5"/><path d="M20 9v10a1 1 0 0 1-1 1H9"/>',
    bold: '<path d="M7 5h6a3.5 3.5 0 0 1 0 7H7zm0 7h7a3.5 3.5 0 0 1 0 7H7z"/>',
    center: '<path d="M4 6h16M8 12h8M6 18h12"/><circle cx="12" cy="12" r="9" stroke-dasharray="3 3" opacity=".35"/>',
  };
  window.ic = function (name, size) {
    size = size || 19;
    return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" ` +
      `stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${P[name] || ''}</svg>`;
  };
  // <i data-ic="name"></i> automatisch füllen
  function hydrate() {
    document.querySelectorAll('i[data-ic]').forEach((el) => {
      if (el.dataset.done) return;
      el.dataset.done = 1;
      const sz = el.closest('.rail') ? 19 : (el.closest('.btn') ? 15 : 16);
      el.innerHTML = window.ic(el.dataset.ic, sz);
    });
  }
  const mo = new MutationObserver(hydrate);
  document.addEventListener('DOMContentLoaded', () => { hydrate(); mo.observe(document.body, { childList: true, subtree: true }); });
  hydrate();
})();
