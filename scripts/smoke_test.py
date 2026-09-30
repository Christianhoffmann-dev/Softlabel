"""SoftLabel Smoke-Test: prüft API + alle Exportpfade gegen einen laufenden Server.

Nutzung:  python scripts/smoke_test.py [base_url]   (Default http://127.0.0.1:8000)
"""
import io
import json
import sys
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✅ {name}")
    else:
        fail += 1
        print(f"  ❌ {name} {extra}")


def req(path, data=None, method=None, headers=None, raw=False):
    url = BASE + path
    body = json.dumps(data).encode() if isinstance(data, (dict, list)) else data
    m = method or ("POST" if data is not None else "GET")
    r = urllib.request.Request(url, data=body, method=m)
    if headers:
        for k, v in headers.items():
            r.add_header(k, v)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            content = resp.read()
            return resp.status, content, {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, e.read(), {k.lower(): v for k, v in e.headers.items()}


print("SoftLabel Smoke-Test auf", BASE)

# Seiten
for p in ["/", "/designer", "/drucken/1", "/protokoll", "/healthz"]:
    s, b, _ = req(p)
    check(f"GET {p}", s == 200, f"-> {s}")

s, b, _ = req("/healthz")
check("healthz JSON", json.loads(b).get("app") == "softlabel")

# Barcode-Vorschau für alle Symbologien (lineare als SVG, QR als PNG)
for st, code, mime in [("CODE128", "AF-2026-1042", "image/svg"), ("EAN13", "400638133393", "image/svg"),
                       ("EAN8", "96385074", "image/svg"), ("UPCA", "042100005264", "image/svg"),
                       ("CODE39", "HELLO-123", "image/svg"), ("ITF14", "1001234560001", "image/svg"),
                       ("25IND", "08123456789", "image/svg"), ("PHARMA", "742", "image/svg"),
                       ("QRCODE", "https://example.com/x", "image/png")]:
    s, b, h = req(f"/api/barcode?code={code}&subtype={st}")
    check(f"barcode {st}", s == 200 and mime in h.get("content-type", ""), f"-> {s} {h.get('content-type')}")

# Fehlerfall: EAN13 mit Unsinn
s, _, _ = req("/api/barcode?code=ABC&subtype=EAN13")
check("barcode Fehlerfall 422", s == 422)

# Vorlage anlegen
design = [
    {"id": "x1", "type": "text", "x": 4, "y": 4, "w": 60, "h": 8, "content": "TESTLABEL",
     "fontFamily": "Helvetica", "fontSize": 5, "bold": True, "color": "#000000", "align": "left", "valign": "top", "rotation": 0, "z": 0},
    {"id": "x2", "type": "field", "x": 4, "y": 14, "w": 72, "h": 6, "key": "artnr", "label": "Art.",
     "fontFamily": "Helvetica", "fontSize": 3, "bold": False, "color": "#000000", "align": "left", "valign": "top", "rotation": 0, "uppercase": True, "z": 1},
    {"id": "x3", "type": "barcode", "subtype": "CODE128", "code": "{{artnr}}", "x": 4, "y": 22,
     "w": 72, "h": 10, "moduleWidthMm": 0.3, "showText": True, "fontSize": 2.2, "barcodeHeightMm": 0, "rotation": 0, "z": 2},
    {"id": "x4", "type": "barcode", "subtype": "QRCODE", "code": "{{seriennr}}", "x": 78, "y": 4,
     "w": 18, "h": 18, "ecc": "M", "qrVersion": 0, "quiet": 2, "rotation": 0, "z": 3},
    {"id": "x5", "type": "line", "x": 4, "y": 34, "w": 92, "h": 0, "color": "#000000", "lineWidthMm": 0.4, "rotation": 0, "z": 4},
]
tid = None
s, b, _ = req("/api/templates", {"template": {"name": "Smoke-Test", "width_mm": 100, "height_mm": 40,
    "dpi": 300, "label_count": 1, "columns": 1, "rows": 1, "margin_mm": 2, "gutter_mm": 3, "design": design}})
check("template anlegen", s == 200 and json.loads(b).get("id"), b[:200])
if s == 200:
    tid = json.loads(b)["id"]

if tid:
    # Vorschau
    s, b, h = req(f"/api/preview/{tid}", {"row": {"artnr": "a-99", "seriennr": "SN12345"}})
    check("preview HTML", s == 200 and b"lbl" in b)
    check("preview mit Variablen", b"a-99" in b" ".join([b]) or b"A-99" in b, b[:300])

    rows = [{"artnr": f"ART-{i}", "seriennr": f"SN{i}"} for i in range(1, 26)]
    # PDF
    s, b, h = req(f"/api/export/{tid}/pdf", {"rows": rows, "actor": "smoke"})
    check("export PDF", s == 200 and b[:4] == b"%PDF", f"{s} {b[:60]}")
    try:
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(b))
        check("PDF Seitenzahl = Zeilenzahl", len(r.pages) == 25, len(r.pages))
        box = r.pages[0].mediabox
        mm_w = float(box.width) / 72 * 25.4
        check("PDF Format mm (100)", abs(mm_w - 100) < 0.6, mm_w)
    except Exception as e:
        check("PDF lesbar", False, str(e))

    # PNG
    s, b, h = req(f"/api/export/{tid}/png", {"rows": rows[:1], "actor": "smoke"})
    check("export PNG", s == 200 and b[:8] == b"\x89PNG\r\n\x1a\n", f"{s}")
    if b[:4] == b"\x89PNG":
        from PIL import Image
        img = Image.open(io.BytesIO(b))
        # 100mm bei 300dpi = 1181px
        check("PNG Größe 300dpi", abs(img.width - 1181) <= 2 and abs(img.height - 472) <= 2, img.size)
        check("PNG DPI-Meta", img.info.get("dpi", (0, 0))[0] >= 299, img.info.get("dpi"))

    # ZPL
    s, b, h = req(f"/api/export/{tid}/zpl", {"rows": rows[:3], "actor": "smoke"})
    zpl = b.decode()
    check("export ZPL", s == 200 and zpl.count("^XA") == 3 and zpl.count("^XZ") == 3)
    check("ZPL Barcode + QR + Feld", "^BC" in zpl and "^BQ" in zpl and "ART-1" in zpl, zpl[:200])

    # SVG
    s, b, h = req(f"/api/export/{tid}/svg", {"rows": rows[:1], "actor": "smoke"})
    check("export SVG", s == 200 and b"<svg" in b and b"mm" in b)

    # Bogen-Export (12er auf A4)
    s, b, _ = req("/api/templates", {"template": {"name": "Smoke-Bogen", "width_mm": 210, "height_mm": 297,
        "dpi": 300, "label_count": 12, "columns": 3, "rows": 4, "margin_mm": 5, "gutter_mm": 4,
        "design": design}})
    bid = json.loads(b)["id"]
    s, b, h = req(f"/api/export/{bid}/pdf", {"rows": [{"artnr": "B1", "seriennr": "S1"}] * 5, "actor": "smoke"})
    ok_pdf = s == 200 and b[:4] == b"%PDF"
    check("Bogen-PDF", ok_pdf)
    if ok_pdf:
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(b))
        check("Bogen A4 Hochformat", abs(float(r.pages[0].mediabox.height) / 72 * 25.4 - 297) < 1)
    s, b, h = req(f"/api/export/{bid}/png", {"rows": [{"artnr": "B1", "seriennr": "S1"}], "sheet": True, "actor": "smoke"})
    ok_png = s == 200 and b[:8] == b"\x89PNG\r\n\x1a\n"
    check("Bogen-PNG", ok_png)
    if ok_png:
        from PIL import Image
        img = Image.open(io.BytesIO(b))
        check("Bogen-PNG A4@300", abs(img.width - 2480) <= 3, img.size)

    # Optimistische Sperre: falsche rev -> 409, korrekte rev -> ok
    cur = json.loads(req(f"/api/templates/{tid}")[1])
    bad = dict(cur); bad["rev"] = 99999; bad["name"] = cur["name"] + "X"
    s, b, _ = req("/api/templates", {"template": bad})
    check("rev-Konflikt -> 409", s == 409, f"{s} {b[:150]}")
    good = dict(cur); good["rev"] = cur["rev"]
    s, b, _ = req("/api/templates", {"template": good})
    check("rev ok -> speichert", s == 200 and json.loads(b).get("rev", 0) >= 2, f"{s} {b[:120]}")
    # actor aus Template-Feld gelangt ins Protokoll
    s, b, _ = req("/api/templates", {"template": dict(good, rev=json.loads(b)["rev"], actor="alice")})
    s, b, _ = req("/api/audit")
    check("Aktor im Audit", s == 200 and any(a["actor"] == "alice" for a in json.loads(b)))

    # Duplizieren / Archiv / Delete
    s, b, _ = req(f"/api/templates/{tid}/duplicate", data={}, headers={"Content-Type": "application/json"})
    s2 = 200 if s == 200 else s
    check("duplizieren", s2 == 200 and json.loads(b).get("id"))
    dup = json.loads(b)["id"] if s2 == 200 else None
    if dup:
        s, _, _ = req(f"/api/templates/{dup}/archive?archived=1", data={}, headers={"Content-Type": "application/json"})
        check("archivieren", s == 200)
        s, _, _ = req(f"/api/templates/{dup}", method="DELETE")
        check("löschen", s == 200)

# CSV-Import (Trenner Semikolon, Umlaute)
csv_bytes = "artnr;bezeichnung;menge\nART-1;Fräse Ø8;10\nART-2;Bohrer · HSS;5\n".encode("cp1252")
bound = "----smoke"
mpart = (f"--{bound}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"test.csv\"\r\n"
         f"Content-Type: text/csv\r\n\r\n").encode() + csv_bytes + f"\r\n--{bound}--\r\n".encode()
s, b, _ = req("/api/import", data=mpart, method="POST",
              headers={"Content-Type": f"multipart/form-data; boundary={bound}"})
if s == 200:
    j = json.loads(b)
    check("CSV-Import Spalten", j["headers"][:3] == ["artnr", "bezeichnung", "menge"], j)
    check("CSV-Import Zeilen+Umlaute", j["total"] == 2 and j["rows"][1]["bezeichnung"] == "Bohrer · HSS", j)
    check("__index ergänzt", j["rows"][0].get("__index") == 1)
else:
    check("CSV-Import", False, f"{s} {b[:200]}")

# Excel-Import
try:
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active
    ws.append(["artnr", "menge"]); ws.append(["X1", 3]); ws.append(["X2", 7])
    buf = io.BytesIO(); wb.save(buf); xbytes = buf.getvalue()
    mpart = (f"--{bound}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"test.xlsx\"\r\n"
             f"Content-Type: application/vnd.ms-excel\r\n\r\n").encode() + xbytes + f"\r\n--{bound}--\r\n".encode()
    s, b, _ = req("/api/import", data=mpart, method="POST",
                  headers={"Content-Type": f"multipart/form-data; boundary={bound}"})
    j = json.loads(b)
    check("XLSX-Import", s == 200 and j["total"] == 2 and j["rows"][0]["artnr"] == "X1", f"{s} {b[:150]}")
except ImportError:
    print("  ⚠ openpyxl fehlt – XLSX-Test übersprungen")

# Jobs/Audit gefüllt?
s, b, _ = req("/api/jobs")
check("Export-Jobs protokolliert", s == 200 and len(json.loads(b)) >= 4)
s, b, _ = req("/api/audit")
check("Audit-Log", s == 200 and any("export" in a["action"] for a in json.loads(b)))

# ---------- Ordner & Archiv ----------
s, b, _ = req("/api/folders", {"name": "Smoke-Kunde"}, method="POST")
check("Ordner anlegen", s == 200 and json.loads(b).get("id"), f"{s} {b[:120]}")
fid = json.loads(b)["id"] if s == 200 else None
if fid:
    s, b, _ = req("/api/folders", method="GET")
    fl = json.loads(b)
    check("Ordnerliste mit Zähler", s == 200 and any(f["id"] == fid and f["n"] == 0 for f in fl))
    s, b, _ = req(f"/api/folders/{fid}/rename", {"name": "Smoke-Kunde2"})
    check("Ordner umbenennen", s == 200)
    # Label in Ordner verschieben
    t_new = req("/api/templates", {"template": {"name": "Ordner-Test-Label", "width_mm": 50,
        "height_mm": 30, "dpi": 300, "label_count": 1, "columns": 1, "rows": 1,
        "margin_mm": 1, "gutter_mm": 0, "design": []}})
    oid = json.loads(t_new[1])["id"]
    s, _, _ = req(f"/api/templates/{oid}/move", {"folder_id": fid})
    check("Label verschieben", s == 200)
    t = json.loads(req(f"/api/templates/{oid}")[1])
    check("folder_id gesetzt", t.get("folder_id") == fid, str(t.get("folder_id")))
    # Archivieren -> nur im Archiv sichtbar
    s, _, _ = req(f"/api/templates/{oid}/archive?archived=1", method="POST", data={})
    check("archivieren", s == 200)
    act = json.loads(req("/api/templates")[1])
    check("archiviert nicht in aktiver Liste", all(x["id"] != oid for x in act))
    arc = json.loads(req("/api/templates?archived=1")[1])
    check("Archivliste enthält Label", any(x["id"] == oid for x in arc))
    s, _, _ = req(f"/api/templates/{oid}/archive?archived=0", method="POST", data={})
    act2 = json.loads(req("/api/templates")[1])
    check("widderhergestellt", s == 200 and any(x["id"] == oid for x in act2))
    # Ordner löschen -> Label im Hauptbereich
    s, _, _ = req(f"/api/folders/{fid}", method="DELETE")
    t = json.loads(req(f"/api/templates/{oid}")[1])
    check("Ordner löschen, Label bleibt (Hauptbereich)", s == 200 and t.get("folder_id") is None)
    # Ungültiger Ordner als Ziel
    s, _, _ = req(f"/api/templates/{oid}/move", {"folder_id": 999999})
    check("move in fremden Ordner -> 400", s == 400)
    req(f"/api/templates/{oid}", method="DELETE")
    req(f"/api/folders/{fid}", method="DELETE")

# Home/Archiv-Seiten
for pth in ["/", "/archiv", "/?folder=1"]:
    s, b, _ = req(pth)
    check(f"GET {pth}", s == 200, f"-> {s}")

print(f"\nErgebnis: {ok} ok, {fail} Fehler")
sys.exit(1 if fail else 0)
