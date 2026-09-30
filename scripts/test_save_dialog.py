"""Speichern-Dialog: neue Vorlage -> Zielabfrage; neuer Ordner im Dialog; bestehende speichert direkt."""
import json
import urllib.request

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
fails = []


def step(n, c, x=""):
    print(("✅ " if c else "❌ ") + n + (str(x) if not c else ""))
    if not c:
        fails.append(n)


def api_get(p):
    return json.load(urllib.request.urlopen(BASE + p))


def api_del(p):
    urllib.request.urlopen(urllib.request.Request(BASE + p, method="DELETE"))


with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))

    # 1) Neue Vorlage: Speichern öffnet Ziel-Dialog statt sofort zu speichern
    pg.goto(BASE + "/designer", wait_until="networkidle")
    pg.fill("#tplName", "Dialog-Test-Label")
    pg.click("[data-add='text']")
    pg.click("#btnSave")
    pg.wait_for_timeout(300)
    step("Speichern öffnet Ordner-Dialog", pg.locator("#folderPop.open").count() == 1)
    step("Dialog listet Hauptbereich + Ordner", pg.locator("#folderList button").count() >= 2)
    step("Input für neuen Ordner sichtbar", pg.locator("#newFolderName").is_visible())
    names = [t["name"] for t in api_get("/api/templates?all=1")]
    step("Noch nicht gespeichert", "Dialog-Test-Label" not in names)

    # 2) Neuen Ordner direkt im Dialog anlegen → speichert dort
    pg.fill("#newFolderName", "Kunde Dialogtest")
    pg.click("#newFolderBtn")
    pg.wait_for_timeout(1000)
    names = [t["name"] for t in api_get("/api/templates?all=1")]
    step("Nach Ordnerwahl gespeichert", "Dialog-Test-Label" in names)
    lab = [t for t in api_get("/api/templates?all=1") if t["name"] == "Dialog-Test-Label"][0]
    fid = [f for f in api_get("/api/folders") if f["name"] == "Kunde Dialogtest"][0]["id"]
    step("Label im neuen Ordner", lab["folder_id"] == fid, str(lab["folder_id"]))
    step("Chip zeigt Ordner", "Kunde Dialogtest" in pg.inner_text("#folderChipLabel"))

    # 3) Bestehende Vorlage: Speichern ohne Rückfrage
    pg.goto(f"{BASE}/designer/{lab['id']}", wait_until="networkidle")
    pg.click("[data-add='line']")
    pg.click("#btnSave")
    pg.wait_for_timeout(500)
    step("Bestehende speichert direkt", pg.locator("#folderPop.open").count() == 0)

    # 4) Ziel über Chip wechseln
    pg.click("#folderChip")
    pg.locator("#folderList button", has_text="Hauptbereich").click()
    pg.wait_for_timeout(300)
    pg.click("#btnSave")
    pg.wait_for_timeout(500)
    t2 = api_get(f"/api/templates/{lab['id']}")
    step("Wechsel in Hauptbereich", t2["folder_id"] is None, str(t2["folder_id"]))

    # 5) Save+Print-Flow bei neuer Vorlage mit ?folder= → kein Dialog, direkte Weiterleitung
    pg.goto(f"{BASE}/designer?folder={fid}", wait_until="networkidle")
    pg.fill("#tplName", "Print-Flow-Label")
    pg.click("#btnSavePrint")
    pg.wait_for_timeout(1200)
    step("Direkt auf Drucken-Seite (Ziel war vorgegeben)", "/drucken/" in pg.url, pg.url)

    step("Keine JS-Fehler", not errs, str(errs[:2]))
    b.close()

# Aufräumen
for t in api_get("/api/templates?all=1"):
    if t["name"] in ("Dialog-Test-Label", "Print-Flow-Label"):
        api_del(f"/api/templates/{t['id']}")
for f in api_get("/api/folders"):
    if f["name"] == "Kunde Dialogtest":
        api_del(f"/api/folders/{f['id']}")

print(f"\nErgebnis: {len(fails)} Fehler {fails if fails else ''}")
raise SystemExit(1 if fails else 0)
