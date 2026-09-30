"""SoftLabel UI-Test (Playwright/Chromium): Designer + Druckseite.

Nutzung:  python scripts/ui_test.py [base_url]   (Default http://127.0.0.1:8000)
"""
import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
errors = []


def step(name, cond, extra=""):
    mark = "✅" if cond else "❌"
    print(f"  {mark} {name} {extra if not cond else ''}")
    if not cond:
        errors.append(name)


def js_console(page):
    msgs = []
    page.on("console", lambda m: msgs.append((m.type, m.text)))
    page.on("pageerror", lambda e: msgs.append(("pageerror", str(e))))
    return msgs


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    pg = browser.new_page(viewport={"width": 1400, "height": 900})

    # ================= Designer (eigene Wegwerf-Vorlage, Beispiele bleiben heil) =================
    import urllib.request as _ur
    design = [{"id": "u1", "type": "barcode", "subtype": "CODE128", "code": "{{auftrag}}",
               "x": 5, "y": 5, "w": 60, "h": 12, "moduleWidthMm": 0.25, "showText": True,
               "fontSize": 2.4, "barcodeHeightMm": 0, "rotation": 0, "z": 0},
              {"id": "u2", "type": "text", "x": 5, "y": 20, "w": 60, "h": 6, "content": "BASE",
               "fontFamily": "Helvetica", "fontSize": 4, "bold": False, "color": "#000000",
               "align": "left", "valign": "top", "rotation": 0, "z": 1}]
    _b = json.dumps({"template": {"name": "UI-Test-Label", "width_mm": 100, "height_mm": 40,
        "dpi": 300, "label_count": 1, "columns": 1, "rows": 1, "margin_mm": 2,
        "gutter_mm": 3, "design": design}}).encode()
    _r = _ur.Request(f"{BASE}/api/templates", data=_b, headers={"Content-Type": "application/json"})
    tid = json.loads(_ur.urlopen(_r).read())["id"]

    msgs = js_console(pg)
    pg.goto(f"{BASE}/designer/{tid}", wait_until="networkidle")
    step("Designer lädt", pg.locator("#stage").count() == 1)
    step("Bestehende Elemente sichtbar", pg.locator("#stage .el").count() == 2,
         f"-> {pg.locator('#stage .el').count()}")
    barcodes_ok = pg.locator("#stage .el img[src*='api/barcode']").count()
    step("Barcode-Vorschau ( Bilder)", barcodes_ok >= 1, f"-> {barcodes_ok}")
    js_errs = [m for m in msgs if m[0] in ("error", "pageerror")]
    step("Keine JS-Fehler beim Laden", not js_errs, str(js_errs)[:300])

    # Text-Element hinzufügen
    n0 = pg.locator("#stage .el").count()
    pg.click("[data-add='text']")
    n = pg.locator("#stage .el").count()
    step("Text-Element hinzufügen", n == n0 + 1, f"{n0} -> {n}")
    step("Property-Panel offen", pg.locator("#propsBody textarea[data-k='content']").count() == 1)

    # Drag des neuen Elements
    el = pg.locator("#stage .el").nth(n - 1)
    bb = el.bounding_box()
    pg.mouse.move(bb["x"] + 20, bb["y"] + 8)
    pg.mouse.down()
    pg.mouse.move(bb["x"] + 120, bb["y"] + 60, steps=6)
    pg.mouse.up()
    bb2 = el.bounding_box()
    step("Drag bewegt Element", bb2["x"] - bb["x"] > 50, f"dx={bb2['x']-bb['x']:.0f}px")

    # Edit über Property-Panel: Inhalt + Fett
    pg.fill("#propsBody textarea[data-k='content']", "UI-TEST {artnr}")
    pg.click("#propsBody [data-toggle='bold']")
    pg.keyboard.press("Escape")
    step("Textänderung im Element", "UI-TEST" in (el.text_content() or ""))

    # Resize-Handle
    el.click()
    h = pg.locator("#selbox .handle.h-se")
    if h.count():
        w_before = el.bounding_box()["width"]
        hb = h.bounding_box()
        pg.mouse.move(hb["x"] + 5, hb["y"] + 5)
        pg.mouse.down()
        pg.mouse.move(hb["x"] + 105, hb["y"] + 25, steps=5)
        pg.mouse.up()
        w_after = el.bounding_box()["width"]
        step("Resize vergrößert Breite", w_after - w_before > 60, f"dx={w_after-w_before:.0f}")
    else:
        step("Resize-Handle vorhanden", False)

    # Speichern (bleibt im Designer)
    pg.fill("#tplName", "UI-Test-Label")
    pg.click("#btnSave")
    pg.wait_for_selector("#dirtyFlag:text('gespeichert')", timeout=5000)
    step("Speichern OK (dirty-Flag zurückgesetzt)", True)
    # Backend prüft persistiert
    tid = int(pg.evaluate("window.location.pathname.split('/').pop()"))
    data = json.load(urllib.request.urlopen(f"{BASE}/api/templates/{tid}"))
    step("Element persistiert im Backend",
         len(data["design"]) == n and "UI-TEST" in json.dumps(data["design"], ensure_ascii=False),
         f"design has {len(data['design'])} el, expected {n}")
    pg.reload(wait_until="networkidle")
    step("Nach Reload: gleiche Elementzahl", pg.locator("#stage .el").count() == n,
         f"-> {pg.locator('#stage .el').count()} vs {n}")

    # Bogen über Größen-Popover auf 4 Labels (2 Spalten → 2 Zeilen berechnet)
    pg.click("#sizeChip")
    pg.fill("#pCount", "4"); pg.locator("#pCount").press("Tab")
    pg.fill("#pCols", "2"); pg.locator("#pCols").press("Tab")
    guides = pg.locator("#stage .guide").count()
    step("Bogenführungslinien (4 Zellen)", guides == 4, f"-> {guides}")
    pg.fill("#pCount", "1"); pg.locator("#pCount").press("Tab")
    pg.fill("#pCols", "1"); pg.locator("#pCols").press("Tab")
    pg.click("#sizeOk")
    js_errs = [m for m in msgs if m[0] in ("error", "pageerror")][len(js_errs):]

    # ---------- Element-Verknüpfung (Binding) ----------
    n_before = pg.locator("#stage .el").count()
    pg.click("[data-add='field']")                       # Datenfeld
    fld = pg.locator("#stage .el").last
    pg.fill("#propsBody input[data-k='key']", "testfeld")
    pg.locator("#propsBody input[data-k='key']").press("Tab")
    pg.click("[data-add='barcode']")                    # Barcode
    bc_el = pg.locator("#stage .el").last
    pg.select_option("#propsBody select[data-k='srcmode']", "bind")
    opts = pg.locator("#propsBody select[data-k='bindTo'] option").all_inner_texts()
    step("Bind-Auswahl listet Datenfeld", any("testfeld" in o for o in opts), str(opts))
    # Feld als Ziel wählen
    bind_sel = pg.locator("#propsBody select[data-k='bindTo']")
    val = pg.evaluate(f"""() => {{
      const s = document.querySelector('#propsBody select[data-k="bindTo"]');
      const o = [...s.options].find(o => o.text.includes('testfeld'));
      return o ? o.value : null; }}""")
    if val:
        bind_sel.select_option(val)
        pg.wait_for_timeout(400)
    step("Verknüpfungs-Linie sichtbar", pg.locator("#linkLayer line").count() == 1,
         f"-> {pg.locator('#linkLayer line').count()}")
    bc_src = pg.evaluate(f"""() => {{
      const imgs = [...document.querySelectorAll('#stage .el img[src*="api/barcode"]')];
      const last = imgs[imgs.length - 1];
      return last ? decodeURIComponent(last.src) : ''; }}""")
    step("Barcode-Vorschau nutzt gebundenen Wert", "TESTFELD" in bc_src.upper(), bc_src[:160])
    # Speichern + Backend prüfen
    pg.click("#btnSave")
    pg.wait_for_timeout(600)
    data = json.load(urllib.request.urlopen(f"{BASE}/api/templates/{tid}"))
    binds = [d for d in data["design"] if d.get("bindTo")]
    step("bindTo persistiert", len(binds) == 1 and binds[0]["type"] == "barcode",
         json.dumps([b.get("type") for b in binds]))
    keys_html = pg.evaluate("null")  # noop
    import urllib.request as _u2
    page_html = _u2.urlopen(f"{BASE}/drucken/{tid}").read().decode()
    step("Druckseite kennt Feld 'testfeld'", "testfeld" in page_html)

    # ================= Druckseite =================
    msgs2 = js_console(pg)
    pg.goto(f"{BASE}/drucken/{tid}", wait_until="networkidle")
    step("Druckseite lädt", pg.locator("#preview .lbl").count() == 1)
    svg_imgs = pg.locator("#preview .bc svg").count()
    step("Barcode in Vorschau gerendert (SVG)", svg_imgs >= 1, f"-> {svg_imgs}")
    err_marks = pg.locator("#preview .err").count()
    step("Keine Fehlermarken in Vorschau", err_marks == 0)

    # Manuell-Daten ändern -> Live-Vorschau
    art = pg.locator("#manualFields input[data-key='auftrag']")
    if art.count():
        art.fill("MAN-777")
        art.dispatch_event("input")
        pg.wait_for_timeout(350)
        step("Live-Vorschau übernimmt Felddaten", "MAN-777" in (pg.locator("#preview").inner_text() or "") + pg.content())

    # CSV-Import per Dateidialog
    csv_data = "auftrag;empfaenger;adresse;gewicht;tracking;artnr;menge;ean;charge;mhd\nAF-9;ACME AG;Weg 1;20;TRK1;A1;5;4006381333931;C1;01/27\nAF-10;Beta GmbH;Park 2;30;TRK2;B2;6;4006381333931;C2;02/27\n"
    pg.set_input_files("#file", {"name": "test.csv", "mimeType": "text/csv",
                                 "buffer": csv_data.encode("utf-8-sig")})
    pg.wait_for_selector("#dtable tr", timeout=5000)
    rows_n = pg.locator("#dtable tr[data-i]").count()
    step("CSV-Import zeigt Zeilentabelle", rows_n == 2, f"-> {rows_n}")
    step("Zeilenauswahl aktiv", pg.locator("#dtable tr.active").count() == 1)
    # Zweite Zeile anklicken
    pg.click("#dtable tr[data-i='1']")
    pg.wait_for_timeout(400)
    pos = pg.locator("#rowPos").inner_text()
    step("Zeilenwechsel in Vorschau", "2 / 2" in pos, pos)

    # PDF-Download
    with pg.expect_download(timeout=30000) as dl:
        pg.click("#expPdf")
    d = dl.value
    path = d.path()
    head = open(path, "rb").read(4)
    step("PDF-Download", d.suggested_filename.endswith(".pdf") and head == b"%PDF",
         f"{d.suggested_filename} {head!r}")

    # ZPL zeigt Vorschau-Panel
    with pg.expect_download(timeout=30000) as dl:
        pg.click("#expZpl")
    zpl_text = open(dl.value.path(), encoding="utf-8").read()
    step("ZPL-Download mit ^XA", "^XA" in zpl_text and "^XZ" in zpl_text)
    step("ZPL-Vorschau-Panel sichtbar", pg.locator("pre.zpl").count() == 1)

    # PNG-Download
    with pg.expect_download(timeout=30000) as dl:
        pg.click("#expPng")
    png_head = open(dl.value.path(), "rb").read(8)
    step("PNG-Download", png_head[:4] == b"\x89PNG", repr(png_head))

    js_errs2 = [m for m in msgs2 if m[0] in ("error", "pageerror")]
    step("Keine JS-Fehler auf Druckseite", not js_errs2, str(js_errs2)[:300])

    # ================= Home =================
    msgs3 = js_console(pg)
    pg.goto(f"{BASE}/", wait_until="networkidle")
    step("Vorlagenliste zeigt UI-Test-Label", "UI-Test-Label" in pg.content())

    # Aufräumen
    try:
        urllib.request.urlopen(urllib.request.Request(f"{BASE}/api/templates/{tid}", method="DELETE"))
    except Exception:
        pass
    browser.close()

print(f"\nUI-Test: {0 if not errors else len(errors)} Fehler {errors}")
sys.exit(1 if errors else 0)
