/* SoftLabel — Wer bin ich? (Name fürs Protokoll, Cookie-basiert) */
(function () {
  const btn = document.querySelector('#whoBtn');
  if (!btn) return;
  // Basispfad aus der eigenen Script-URL ableiten ({BASE}/static/who.js)
  const me = document.currentScript && document.currentScript.getAttribute('src');
  const BASE = me ? me.replace(/\/static\/who\.js.*$/, '') : '';
  function cookie(name) {
    const m = document.cookie.match(new RegExp('(?:^| )' + name + '=([^;]+)'));
    return m ? decodeURIComponent(m[1]) : '';
  }
  function paint() {
    const n = cookie('sluser');
    btn.textContent = n ? '👤 ' + n : '👤 Gast';
  }
  btn.addEventListener('click', async () => {
    const name = prompt('Dein Name (erscheint im Protokoll und bei Exporten):', cookie('sluser'));
    if (name === null) return;
    const r = await fetch(BASE + '/api/whoami', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name })
    });
    if (r.ok) paint();
  });
  paint();
})();
