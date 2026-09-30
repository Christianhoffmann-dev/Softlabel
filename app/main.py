"""SoftLabel — FastAPI-Backend: Vorlagen-Designer, Datenimport, Export.

Endpunkte (alle unter optionalem SL_BASE_PATH):
  /                    Vorlagenliste
  /designer/{id?}      Label-Designer (Web-UI)
  /drucken/{id}        Datenimport + Vorschau + Export
  /api/templates...    CRUD, Duplizieren, Archiv
  /api/barcode         Vorschau-SVG eines Barcodes
  /api/preview/{id}    HTML-Vorschau mit Testdaten
  /api/export/{id}.pdf|png|zpl   Export (Zeilen aus CSV/XLSX-Upload oder JSON)
  /api/assets          Upload/Liste
  /api/jobs, /api/audit
"""
import io
import json
import re
import secrets
import time
import base64
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.concurrency import run_in_threadpool
from fastapi.templating import Jinja2Templates

from . import barcode as bc
from . import config
from . import datio
from . import db as database
from . import elements as el
from . import pngrender
from . import render as renderer
from . import zpl as zpl_mod

app = FastAPI(title="SoftLabel", docs_url="/api-docs", openapi_url="/api/openapi.json")
BASE = config.BASE_PATH
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
if config.ASSET_DIR.is_dir():
    app.mount("/assets-dir", StaticFiles(directory=str(config.ASSET_DIR)), name="assetsdir")


@app.on_event("startup")
def _startup():
    database.init_db()


def url(path: str) -> str:
    return f"{BASE}{path}"


# ============================================================ Seiten
@app.get("/", response_class=HTMLResponse)
def page_home(request: Request, folder: int | None = None, q: str = ""):
    items = database.list_templates(folder=folder)
    folders = database.list_folders()
    counts = {"all": database.count_templates(), "root": database.count_templates(0),
              "archived": database.archived_count()}
    if q:
        ql = q.lower()
        items = [t for t in items if ql in t["name"].lower()]
    fname = {f["id"]: f["name"] for f in folders}
    return templates.TemplateResponse(request, "home.html",
                                      {"items": items, "folders": folders, "cur": folder,
                                       "counts": counts, "q": q, "fname": fname, "u": url})


@app.get("/archiv", response_class=HTMLResponse)
def page_archive(request: Request):
    items = database.list_templates(folder=None, only_archived=True)
    return templates.TemplateResponse(request, "archive.html",
                                      {"items": items, "u": url})


@app.get("/drucken/{tid}", response_class=HTMLResponse)
def page_print(request: Request, tid: int):
    t = database.get_template(tid)
    if not t:
        raise HTTPException(404, "Vorlage nicht gefunden")
    design = json.loads(t["design_json"])
    return templates.TemplateResponse(request, "print.html",
                                      {"t": t, "keys": el.keys_in(design), "u": url})


@app.get("/designer", response_class=HTMLResponse)
@app.get("/designer/{tid}", response_class=HTMLResponse)
def page_designer(request: Request, tid: int | None = None):
    t = None
    if tid:
        t = database.get_template(tid)
        if not t:
            raise HTTPException(404, "Vorlage nicht gefunden")
    assets = database.list_assets()
    folders = database.list_folders()
    return templates.TemplateResponse(request, "designer.html",
                                      {"t": t, "tid": tid, "assets": assets, "folders": folders,
                                       "barcode_types": el.BARCODE_TYPES, "u": url})


@app.get("/protokoll", response_class=HTMLResponse)
def page_log(request: Request):
    return templates.TemplateResponse(request, "log.html",
                                      {"jobs": database.list_jobs(),
                                       "audit": database.list_audit(), "u": url})


# ============================================================ API: Ordner
@app.get("/api/folders")
def api_folders():
    return database.list_folders() + database.list_folders(archived=True)


@app.post("/api/folders")
async def api_add_folder(request: Request):
    body = await request.json()
    name = str(body.get("name", "")).strip()
    if not name:
        raise HTTPException(400, "Ordnername fehlt")
    if any(f["name"].lower() == name.lower() for f in database.list_folders() + database.list_folders(archived=True)):
        raise HTTPException(409, f"Ordner „{name}“ existiert bereits.")
    actor = body.get("actor") or request.cookies.get("sluser") or "web"
    return {"id": database.add_folder(name, actor)}


@app.get("/api/folders/{fid}")
def api_folder(fid: int):
    f = database.get_folder(fid)
    if not f:
        raise HTTPException(404)
    f["items"] = database.list_templates(folder=fid)
    return f


@app.post("/api/folders/{fid}/rename")
async def api_rename_folder(fid: int, request: Request):
    body = await request.json()
    name = str(body.get("name", "")).strip()
    if not name:
        raise HTTPException(400, "Ungültiger Name")
    if any(f["id"] != fid and f["name"].lower() == name.lower()
           for f in database.list_folders() + database.list_folders(archived=True)):
        raise HTTPException(409, f"Ordner „{name}“ existiert bereits.")
    if not database.rename_folder(fid, name):
        raise HTTPException(404, "Ordner existiert nicht")
    database.audit(body.get("actor") or request.cookies.get("sluser") or "web",
                   "folder_renamed", f"id={fid} -> {name}")
    return {"ok": True}


@app.delete("/api/folders/{fid}")
def api_delete_folder(fid: int, request: Request):
    if not database.get_folder(fid):
        raise HTTPException(404)
    database.delete_folder(fid, request.cookies.get("sluser") or "web")
    return {"ok": True}


# ============================================================ API: Vorlagen
@app.get("/api/templates")
def api_templates(folder: int | None = None, archived: int = 0, all: int = 0):
    return database.list_templates(include_archived=bool(all), folder=folder,
                                   only_archived=bool(archived))


@app.post("/api/templates")
async def api_save_template(request: Request):
    body = await request.json()
    t = body.get("template") or {}
    actor = (t.get("actor") or request.cookies.get("sluser") or "web")[:60]
    expected_rev = int(t["rev"]) if t.get("id") and t.get("rev") is not None else None
    try:
        tid = await run_in_threadpool(database.save_template, {
            "id": t.get("id") or None,
            "name": (t.get("name") or "Neues Label").strip()[:120],
            "width_mm": float(t.get("width_mm", 100)),
            "height_mm": float(t.get("height_mm", 50)),
            "dpi": int(t.get("dpi", 300)),
            "label_count": max(1, int(t.get("label_count", 1))),
            "columns": max(1, int(t.get("columns", 1))),
            "rows": max(1, int(t.get("rows", 1))),
            "margin_mm": float(t.get("margin_mm", 2)),
            "gutter_mm": float(t.get("gutter_mm", 3)),
            "design_json": json.dumps(t.get("design", [])),
            "folder_id": int(t["folder_id"]) if t.get("folder_id") else None,
            "actor": actor,
        }, expected_rev)
    except database.RevConflict:
        raise HTTPException(409, "Die Vorlage wurde zwischenzeitlich von einer anderen Person geändert.")
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, f"Ungültige Vorlage: {exc}")
    return {"id": tid, "rev": database.get_rev(tid)}


@app.get("/api/templates/{tid}")
def api_template(tid: int):
    t = database.get_template(tid)
    if not t:
        raise HTTPException(404)
    t["design"] = json.loads(t.pop("design_json"))
    return t


@app.post("/api/templates/{tid}/duplicate")
def api_duplicate(tid: int):
    new = database.duplicate_template(tid)
    if not new:
        raise HTTPException(404)
    return {"id": new}


@app.post("/api/templates/{tid}/archive")
def api_archive(tid: int, request: Request, archived: int = 1):
    if not database.get_template(tid):
        raise HTTPException(404)
    database.set_archived(tid, bool(archived), request.cookies.get("sluser") or "web")
    return {"ok": True}


@app.post("/api/templates/{tid}/move")
async def api_move(tid: int, request: Request):
    body = await request.json()
    if not database.get_template(tid):
        raise HTTPException(404)
    fid = body.get("folder_id")
    if fid and not database.get_folder(int(fid)):
        raise HTTPException(400, "Ordner existiert nicht")
    database.move_template(tid, int(fid) if fid else None)
    return {"ok": True}


@app.delete("/api/templates/{tid}")
def api_delete(tid: int):
    if not database.get_template(tid):
        raise HTTPException(404)
    database.delete_template(tid)
    return {"ok": True}


# ============================================================ API: Barcode-Vorschau
@app.get("/api/barcode")
def api_barcode(code: str = "TEST", subtype: str = "CODE128",
                module: float = 0.25, height: float = 10,
                show_text: bool = True, font_pt: float = 7, ecc: str = "M"):
    try:
        if subtype == "QRCODE":
            png = bc.qr_png(code, 240, ecc, 0, 2)
            return Response(png, media_type="image/png")
        if subtype == "DATAMATRIX":
            png = bc.datamatrix_png(code, 240)
            return Response(png, media_type="image/png")
        svg, *_ = bc.linear_svg(code, subtype, module, height, show_text, font_pt)
        return Response(svg, media_type="image/svg+xml")
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(422, str(exc))


# ============================================================ API: Vorschau
@app.post("/api/preview/{tid}")
async def api_preview(tid: int, request: Request):
    t = database.get_template(tid)
    if not t:
        raise HTTPException(404)
    try:
        body = await request.json()
    except Exception:
        body = {}
    row = body.get("row") or _sample_row(t)
    frag = await run_in_threadpool(renderer.preview_fragment, t, row)
    return HTMLResponse(frag)


_SAMPLE_HINTS = {
    "ean": "4006381333931", "ean13": "4006381333931", "gtin": "4006381333931",
    "upc": "042100005264", "itf": "10012345600011", "charge": "C-2291",
    "mhd": "03/2028", "menge": "24", "gewicht": "248,5", "position": "12",
    "artnr": "ART-88420", "artikel": "ART-88420", "auftrag": "AF-2026-1042",
    "kundenauftrag": "KA-555", "tracking": "CV123456789DE",
    "seriennummer": "SN-00123", "empfaenger": "Muster GmbH",
    "adresse": "Beispielstr. 1, 12345 Musterstadt",
}


def _sample_row(t) -> dict:
    keys = el.keys_in(json.loads(t["design_json"]))
    out = {}
    for k in keys:
        low = k.lower().replace(" ", "").replace("-", "").replace("_", "")
        out[k] = next((v for hint, v in _SAMPLE_HINTS.items() if hint in low), f"BEISPIEL-{k}")
    return out


# ============================================================ API: Import
@app.post("/api/import")
async def api_import(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(413, "Datei größer als 20 MB")
    try:
        headers, rows, warnings = await run_in_threadpool(datio.parse_rows, data, file.filename or "")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    for i, r in enumerate(rows):
        r["__index"] = i + 1
    return {"headers": headers, "rows": rows[:500], "total": len(rows),
            "warnings": warnings}


# ============================================================ API: Export
_EXPORT_MEDIA = {
    "pdf": ("application/pdf", "pdf"),
    "png": ("image/png", "png"),
    "zpl": ("text/plain; charset=utf-8", "zpl"),
    "svg": ("image/svg+xml", "svg"),
}


async def _json_body(request: Request) -> dict:
    """JSON-Body tolerant: kaputtes UTF-8/JSON → 400 statt 500."""
    raw = await request.body()
    if not raw:
        return {}
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return json.loads(raw.decode(enc))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise HTTPException(400, "Ungültiges JSON (Kodierung/Format)")


@app.post("/api/export/{tid}/{fmt}")
async def api_export(tid: int, fmt: str, request: Request):
    fmt = fmt.lower()
    if fmt not in _EXPORT_MEDIA:
        raise HTTPException(400, "Format: pdf|png|zpl|svg")
    t = database.get_template(tid)
    if not t:
        raise HTTPException(404, "Vorlage nicht gefunden")
    body = await _json_body(request)
    rows = body.get("rows") or [_sample_row(t)]
    actor = (body.get("actor") or request.cookies.get("sluser") or "web")[:60]
    if fmt == "svg":
        rows = rows[:1]
    fname, payload, media = await run_in_threadpool(_build_export, t, fmt, rows, body)
    database.add_job(tid, fmt, fname, len(rows), 1, actor)
    headers = {
        "Content-Disposition": f'attachment; filename="{fname}"',
        "X-Filename": fname,
    }
    return Response(payload, media_type=media, headers=headers)


def _build_export(t, fmt, rows, body):
    name = re.sub(r"[^\w\-]+", "_", t["name"])[:40]
    ts = time.strftime("%Y%m%d-%H%M%S")
    if fmt == "pdf":
        pdf, pages = renderer.render_pdf(t, rows)
        return f"{name}_{ts}.pdf", pdf, "application/pdf"
    if fmt == "zpl":
        text = zpl_mod.render_zpl(t, rows)
        return f"{name}_{ts}.zpl", text.encode("utf-8"), "text/plain; charset=utf-8"
    if fmt == "png":
        dpi = int(body.get("dpi") or t.get("dpi") or 300)
        if int(t.get("label_count", 1)) > 1 and body.get("sheet"):
            png = pngrender.render_sheet_png(t, rows[0], dpi)
            return f"{name}_{ts}_bogen.png", png, "image/png"
        if len(rows) == 1:
            png = pngrender.render_label_png(t, rows[0], dpi)
            return f"{name}_{ts}.png", png, "image/png"
        png = pngrender.render_grid_png(t, rows[:16], dpi)
        return f"{name}_{ts}_vorschau.png", png, "image/png"
    # svg: Einzelvektor für Webprint-Dienste
    import base64
    svg, *_ = _first_svg(t, rows[0])
    return f"{name}_{ts}.svg", svg, "image/svg+xml"


def _first_svg(t, row):
    """SVG des kompletten Labels (Elemente als Gruppen)."""
    design = json.loads(t["design_json"])
    W, H = float(t["width_mm"]), float(t["height_mm"])
    from . import elements as E
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" '
             f'viewBox="0 0 {W} {H}"><rect width="100%" height="100%" fill="#fff"/>']
    for e in design:
        x, y, w, h = e.get("x", 0), e.get("y", 0), e.get("w", 0), e.get("h", 0)
        rot = e.get("rotation", 0)
        tr = f' transform="rotate({rot} {x + w / 2} {y + h / 2})"' if rot else ""
        if e["type"] in ("text", "field"):
            txt = E.resolved_text(e, row, design)
            size = float(e.get("fontSize", 3))
            anchor = {"left": "start", "center": "middle", "right": "end"}[e.get("align", "left")]
            tx = x + (w / 2 if e.get("align") == "center" else w if e.get("align") == "right" else 0)
            fam = {"Helvetica": "Arial", "Times": "Times New Roman", "Courier": "Courier New"}.get(
                e.get("fontFamily", "Helvetica"), "Arial")
            weight = "bold" if e.get("bold") else "normal"
            parts.append(f'<text x="{tx}" y="{y + size * 0.9}" font-family="{fam}" '
                         f'font-size="{size}" font-weight="{weight}" '
                         f'fill="{e.get("color", "#000")}" text-anchor="{anchor}"{tr}>'
                         f'{_x(txt)}</text>')
        elif e["type"] == "barcode":
            st = e.get("subtype", "CODE128")
            code = E.barcode_data(e, row, design)
            if st == "QRCODE":
                import qrcode, io as _io
                from PIL import Image as _Img
                qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=1,
                                   border=2)
                qr.add_data(code); qr.make(fit=True)
                img = qr.make_image().convert("RGB").resize((400, 400), _Img.NEAREST)
                buf = _io.BytesIO(); img.save(buf, "PNG")
                parts.append(f'<image x="{x}" y="{y}" width="{h or w}" height="{h or w}" '
                             f'href="data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"{tr}/>')
            elif st == "DATAMATRIX":
                try:
                    png = bc.datamatrix_png(code, 400)
                    parts.append(f'<image x="{x}" y="{y}" width="{min(w, h) or 10}" height="{min(w, h) or 10}" '
                                 f'href="data:image/png;base64,{base64.b64encode(png).decode()}"{tr}/>')
                except RuntimeError:
                    pass
            else:
                svg, w_mm, h_mm, _ = bc.linear_svg(
                    code, st, float(e.get("moduleWidthMm", 0.25)),
                    float(e.get("barcodeHeightMm", 0) or (h - (4 if e.get("showText", True) else 0))),
                    bool(e.get("showText", True)), float(e.get("fontSize", 2.4) * 2.835) or 7)
                inner = svg[svg.index("<svg"):]
                inner = inner[inner.index(">") + 1:inner.rindex("</svg>")]
                parts.append(f'<g transform="translate({x} {y})"{tr}>{inner}</g>')
        elif e["type"] == "line":
            parts.append(f'<line x1="{x}" y1="{y}" x2="{x + w}" y2="{y}" stroke="{e.get("color", "#000")}" '
                         f'stroke-width="{e.get("lineWidthMm", 0.3)}"{tr}/>')
        elif e["type"] == "rect":
            parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{e.get("fill", "none")}" '
                         f'stroke="{e.get("stroke", "#000")}" stroke-width="{e.get("lineWidthMm", 0.3)}"{tr}/>')
        elif e["type"] == "asset":
            a = database.get_asset(int(e.get("assetId", 0) or 0))
            if a:
                b64 = base64.b64encode(Path(a["path"]).read_bytes()).decode()
                parts.append(f'<image x="{x}" y="{y}" width="{w}" height="{h}" '
                             f'href="data:image/png;base64,{b64}"{tr}/>')
    parts.append("</svg>")
    return "".join(parts).encode(), None, None, None


def _x(s):
    from xml.sax.saxutils import escape
    return escape(str(s)).replace("\n", "")


# ============================================================ API: Assets
@app.get("/api/assets")
def api_assets():
    return database.list_assets()


@app.post("/api/assets")
async def api_asset_upload(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "Bild größer als 10 MB")
    from PIL import Image
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
        fmt = (img.format or "PNG").upper()
        img = Image.open(io.BytesIO(data))
        w, h = img.size
    except Exception:
        raise HTTPException(422, "Kein gültiges Bild (PNG/JPG/GIF/BMP)")
    data = data  # Bildvalidierung done
    safe = re.sub(r"[^\w.\-]+", "_", file.filename or "asset")[:60]
    ext = {"JPEG": "JPG"}.get(fmt, fmt)[:3].lower()
    fname = f"{int(time.time()*1000)}-{safe}" if safe.endswith(f".{ext}") else f"{int(time.time()*1000)}-{safe}.{ext}"
    path = config.ASSET_DIR / fname
    img.save(path, format={"JPG": "JPEG"}.get(fmt, fmt))
    aid = database.add_asset(safe, str(path), w, h)
    return {"id": aid, "name": safe, "width": w, "height": h}


@app.get("/api/assets/{aid}/raw")
def api_asset_raw(aid: int):
    a = database.get_asset(aid)
    if not a or not Path(a["path"]).is_file():
        raise HTTPException(404)
    return FileResponse(a["path"])


# ============================================================ API: Thumbnails
_THUMB_CACHE: dict[int, tuple[str, bytes]] = {}


@app.get("/api/thumb/{tid}.png")
def api_thumb(tid: int):
    t = database.get_template(tid)
    if not t:
        raise HTTPException(404)
    stamp = t.get("updated_at") or ""
    hit = _THUMB_CACHE.get(tid)
    if hit and hit[0] == stamp:
        return Response(hit[1], media_type="image/png")
    import json as _json
    row = _sample_row(t)
    png = pngrender.render_label_png(t, row, dpi=72)
    _THUMB_CACHE[tid] = (stamp, png)
    if len(_THUMB_CACHE) > 200:
        _THUMB_CACHE.pop(next(iter(_THUMB_CACHE)))
    return Response(png, media_type="image/png")


# ============================================================ API: Jobs / Audit
@app.get("/api/jobs")
def api_jobs():
    return database.list_jobs()


@app.get("/api/audit")
def api_audit():
    return database.list_audit()


# ============================================================ Benutzer
@app.post("/api/whoami")
async def api_whoami(request: Request):
    body = await request.json()
    name = re.sub(r"[^\w\- .äöüÄÖÜß]", "", str(body.get("name", "")))[:40].strip()
    resp = JSONResponse({"name": name or "web"})
    if name:
        resp.set_cookie("sluser", name, max_age=60 * 60 * 24 * 365, samesite="lax")
    else:
        resp.delete_cookie("sluser")
    return resp


# ============================================================ Sonstiges
@app.get("/healthz")
def healthz():
    return {"status": "ok", "app": "softlabel"}
