"""Verifikation: Barcode-Breite ziehen = Modulbreite skaliert mit (Browser)."""
import json, urllib.request
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
design = [{"id": "k1", "type": "barcode", "subtype": "CODE128", "code": "TEST1234", "x": 5, "y": 5,
           "w": 40, "h": 12, "moduleWidthMm": 0.25, "showText": True, "fontSize": 2.2,
           "barcodeHeightMm": 0, "rotation": 0, "z": 0}]
b = json.dumps({"template": {"name": "Breiten-Test", "width_mm": 120, "height_mm": 50, "dpi": 300,
    "label_count": 1, "columns": 1, "rows": 1, "margin_mm": 2, "gutter_mm": 3, "design": design}}).encode()
r = urllib.request.Request(BASE + "/api/templates", data=b, headers={"Content-Type": "application/json"})
tid = json.loads(urllib.request.urlopen(r).read())["id"]

ok = True
with sync_playwright() as p:
    br = p.chromium.launch(headless=True)
    pg = br.new_page(viewport={"width": 1440, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"{BASE}/designer/{tid}", wait_until="networkidle")
    pg.wait_for_timeout(900)
    # Auto-Korrektur auf natürliche Symbolbreite abwarten und speichern (Bezugsmaß)
    pg.fill("#tplName", "Breiten-Test"); pg.click("#btnSave"); pg.wait_for_timeout(500)
    pg.click("#stage .el")  # Barcode auswählen
    el = pg.locator("#stage .el")
    h = pg.locator("#selbox .handle.h-e")
    pre = json.load(urllib.request.urlopen(f"{BASE}/api/templates/{tid}"))
    w0, mw0 = pre["design"][0]["w"], pre["design"][0]["moduleWidthMm"]
    w0_px = el.bounding_box()["width"]
    hb = h.bounding_box()
    pg.mouse.move(hb["x"] + 4, hb["y"] + 4)
    pg.mouse.down()
    pg.mouse.move(hb["x"] + 154, hb["y"] + 4, steps=8)   # 150px = 40mm breiter ziehen
    hud = pg.locator("#hud").inner_text()
    pg.mouse.up()
    pg.wait_for_timeout(700)
    print("HUD während Resize:", hud)
    # Modell nach mouseup via Save + Backend prüfen
    pg.click("#btnSave")
    pg.wait_for_timeout(600)
    data = json.load(urllib.request.urlopen(f"{BASE}/api/templates/{tid}"))
    e1 = data["design"][0]
    print(f"w: {w0} -> {e1['w']} mm,  modul: {mw0} -> {e1['moduleWidthMm']} mm")
    # Strichbereich (Box − 5mm Ruhezone) muss proportional zum Modul skaliert sein
    ratio_w = (e1["w"] - 5) / (w0 - 5)
    ratio_m = e1["moduleWidthMm"] / mw0
    if not (e1["w"] > w0 + 5):
        print("❌ Breite nicht gewachsen"); ok = False
    if not abs(ratio_w - ratio_m) < 0.08:
        print("❌ Modul skaliert nicht proportional", round(ratio_w, 3), round(ratio_m, 3)); ok = False
    else:
        print("✅ Breite ziehen skaliert Modulbreite proportional")
    # Boxbreite == natürliche Symbolbreite (Backend-Fetch)
    svg = urllib.request.urlopen(f"{BASE}/api/barcode?code=TEST1234&subtype=CODE128&module={e1['moduleWidthMm']}&height={max(3,e1['h']-4)}&show_text=true&font_pt=6.2").read().decode()
    import re
    nat = float(re.search(r'width="([\d.]+)mm"', svg).group(1))
    print(f"natürliche Symbolbreite: {nat:.1f} mm vs Box {e1['w']} mm")
    if abs(nat - e1["w"]) > 1.5:
        print("❌ Box folgt nicht der Symbolbreite"); ok = False
    if errs:
        print("❌ JS-Fehler:", errs[:2]); ok = False
    br.close()

# Slider-Test (Modulbreite ändert -> Box folgt)
import re
with sync_playwright() as p:
    br = p.chromium.launch(headless=True)
    pg = br.new_page(viewport={"width": 1440, "height": 900})
    pg.goto(f"{BASE}/designer/{tid}", wait_until="networkidle")
    pg.click("#stage .el")
    pg.wait_for_timeout(400)
    pre2 = json.load(urllib.request.urlopen(f"{BASE}/api/templates/{tid}"))
    mw_b = pre2["design"][0]["moduleWidthMm"]; w_before = pre2["design"][0]["w"]
    target = 1.0
    pg.eval_on_selector("#propsBody input[data-k='moduleWidthMm']",
                       f"el => {{ el.value = '{target}'; el.dispatchEvent(new Event('input', {{bubbles:true}})); el.dispatchEvent(new Event('change', {{bubbles:true}})); }}")
    pg.wait_for_timeout(1400)
    pg.click("#btnSave"); pg.wait_for_timeout(600)
    post2 = json.load(urllib.request.urlopen(f"{BASE}/api/templates/{tid}"))
    after = post2["design"][0]["w"]
    print(f"Slider {mw_b}→{target} (Faktor {target/mw_b:.2f}): Box {w_before} → {after} mm")
    exp = (after - 5) / (w_before - 5)
    if not abs(exp - target / mw_b) < 0.1:
        print("❌ Slider skaliert Boxbreite nicht proportional", round(exp, 2)); ok = False
    br.close()

urllib.request.urlopen(urllib.request.Request(f"{BASE}/api/templates/{tid}", method="DELETE"))
print("\nErgebnis:", "OK ✅" if ok else "FEHLER ❌")
