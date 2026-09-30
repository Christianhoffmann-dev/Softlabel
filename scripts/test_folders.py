"""SoftLabel Ordner-/Archiv-Flow im Browser (Playwright) — End-to-End."""
import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
errors = []


def step(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name} {extra if not cond else ''}")
    if not cond:
        errors.append(name)


def api(path, data=None, method=None):
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(BASE + path, data=body, method=method or ("POST" if body else "GET"),
                               headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(r, timeout=30)
    raw = resp.read()
    return resp.status, json.loads(raw) if raw[:1] in (b"[", b"{") else raw


status, folders = api("/api/folders")
pre = {f["name"] for f in folders}
with sync_playwright() as p:
    br = p.chromium.launch(headless=True)
    pg = br.new_page(viewport={"width": 1440, "height": 900})
    pgerr = []
    pg.on("pageerror", lambda e: pgerr.append(str(e)))

    # ---------- Ordner anlegen ----------
    # prompt()-Dialoge mit Werteschlange beantworten
    answers = ["Kunde A", "Kunde A umbenannt"]
    def on_dialog(d):
        if d.type == "prompt":
            d.accept(answers.pop(0) if answers else None)
        else:
            d.accept()
    pg.on("dialog", on_dialog)
    pg.goto(BASE + "/", wait_until="networkidle")
    pg.click("text=＋ Neuer Ordner")
    pg.wait_for_timeout(1200)
    step("Ordner 'Kunde A' angelegt", "Kunde A" in pg.inner_text("body"))
    fid_a = [f for f in api("/api/folders")[1] if f["name"] == "Kunde A"][0]["id"]

    # ---------- Neues Label direkt in Ordner ----------
    pg.goto(f"{BASE}/designer?folder={fid_a}", wait_until="networkidle")
    pg.fill("#tplName", "Kunden-A-Label")
    pg.click("[data-add='text']")
    pg.click("#btnSave")
    pg.wait_for_timeout(800)
    tid = int(pg.evaluate("location.pathname.split('/').pop()"))
    t = api(f"/api/templates/{tid}")[1]
    step("Neues Label landet im Ordner", t.get("folder_id") == fid_a, str(t.get("folder_id")))

    # ---------- Label verschieben ----------
    pg.goto(BASE + "/", wait_until="networkidle")
    step("Kunde A sichtbar + Zähler", "Kunde A" in pg.inner_text(".folders"))
    pg.goto(f"{BASE}/?folder={fid_a}", wait_until="networkidle")
    step("Label im Ordner gelistet", "Kunden-A-Label" in pg.inner_text("#tplGrid"))
    # Musterlabel herholen & verschieben
    pg.goto(BASE + "/", wait_until="networkidle")
    card = pg.locator(".card", has_text="Palettenlabel").first
    card.locator("button", has_text="Verschieben").click()
    pg.wait_for_timeout(300)
    step("Verschieben-Popover offen", pg.locator("#movePop.open").count() == 1)
    pg.locator("#movePop .tool", has_text="Kunde A").click()
    pg.wait_for_timeout(900)
    t2 = api("/api/templates/1")[1] if api("/api/templates")[1][0]["name"].startswith("Paletten") else None
    palet = [x for x in api("/api/templates")[1] if x["name"].startswith("Paletten")][0]
    step("Verschieben persistiert", palet["folder_id"] == fid_a, str(palet))

    # ---------- Umbenennen ----------
    pg.hover(".folders a[data-fid]")
    pg.locator(".folders a[data-fid] button[title='Umbenennen']").first.click()
    pg.wait_for_timeout(900)
    step("Ordner umbenannt", "Kunde A umbenannt" in pg.inner_text(".folders"))
    fid_a = [f for f in api("/api/folders")[1] if f["name"] == "Kunde A umbenannt"][0]["id"]

    # ---------- Archivieren / Wiederholen / Löschen ----------
    pg.goto(BASE + "/", wait_until="networkidle")
    kcard = pg.locator(".card", has_text="Kunden-A-Label").first
    kcard.locator("button", has_text="Archiv").click()
    pg.wait_for_timeout(900)
    step("Aus Liste verschwunden nach Archiv", "Kunden-A-Label" not in pg.inner_text("#tplGrid"))
    pg.goto(BASE + "/archiv", wait_until="networkidle")
    step("Archiv zeigt Label + Thumbnail", "Kunden-A-Label" in pg.inner_text("body")
         and pg.locator("#archiv, table img").count() >= 1)
    # Endgültig löschen
    pg.locator("button", has_text="Endgültig löschen").first.click()
    pg.wait_for_timeout(900)
    gone = all(x["id"] != tid for x in api("/api/templates")[1])
    step("Endgültig gelöscht", gone)
    # Palettenlabel: archivieren und wiederholen
    palet = [x for x in api("/api/templates")[1] if x["name"].startswith("Paletten")][0]
    api(f"/api/templates/{palet['id']}/archive?archived=1", method="POST")
    pg.goto(BASE + "/archiv", wait_until="networkidle")
    step("Archivseite zeigt Palettenlabel", "Palettenlabel" in pg.inner_text("body"))
    pg.locator("button", has_text="Wiederholen").first.click()
    pg.wait_for_timeout(900)
    restored = [x for x in api("/api/templates")[1] if x["name"].startswith("Paletten")][0]
    step("Wiederhergestellt im richtigen Ordner", restored["archived"] == 0
         and restored["folder_id"] == fid_a, str(restored))

    # ---------- Ordner löschen: Labels → Hauptbereich ----------
    status, _ = api(f"/api/folders/{fid_a}", method="DELETE")
    step("Ordner gelöscht (200)", status == 200)
    moved = [x for x in api("/api/templates")[1] if x["name"].startswith("Paletten")][0]
    step("Labels bleiben im Hauptbereich erhalten", moved["folder_id"] is None and moved["archived"] == 0)

    step("Keine JS-Fehler", not pgerr, str(pgerr[:2]))
    br.close()

# Aufräumen: Testsystem auf Ausgangszustand
for f in api("/api/folders")[1]:
    if f["name"] not in pre:
        api(f"/api/folders/{f['id']}", method="DELETE")
print(f"\nOrdner-Test: {len(errors)} Fehler {errors if errors else ''}")
sys.exit(1 if errors else 0)
