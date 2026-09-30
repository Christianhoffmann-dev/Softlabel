"""PDF-Renderer (vektor-basiert) + HTML-Vorschau-Fragment.

PDF: Reportlab, 1 pt = 1 mm * 72/25.4. Mehrere Datenzeilen -> Bögen
(Mehrlabels-Layout mit Rand/Abstand), sonst Einzelseite pro Label.
Barcodes werden bei Ziel-DPI gerastert eingebettet (Strichbreiten exakt),
Textvektoren bleiben Vektor.

Vorschau: dasselbe mm-Layout als HTML; lineare Barcodes als inline-SVG.
"""
import base64
import io
import json
import math
from html import escape

from reportlab.lib.units import mm as MM
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas as _canvas

from . import barcode as bc
from . import db as database
from . import elements as el
from . import fonts as fontreg


# ============================================================ PDF
def render_pdf(template: dict, rows: list[dict]) -> tuple[bytes, int]:
    design = json.loads(template["design_json"])
    dpi = int(template.get("dpi", 300)) or 300
    W_mm, H_mm = float(template["width_mm"]), float(template["height_mm"])
    W, H = W_mm * MM, H_mm * MM
    cnt = int(template.get("label_count", 1) or 1)
    cols, rws = _grid(template)
    per_sheet = cols * rws if cnt > 1 else 1
    m = float(template.get("margin_mm", 2))
    g = float(template.get("gutter_mm", 3))
    lw_mm = (W_mm - 2 * m - (cols - 1) * g) / cols if per_sheet > 1 else W_mm
    lh_mm = (H_mm - 2 * m - (rws - 1) * g) / rws if per_sheet > 1 else H_mm

    buf = io.BytesIO()
    c = _canvas.Canvas(buf, pagesize=(W, H))
    rows = rows or [{}]
    total_pages = max(1, math.ceil(len(rows) / per_sheet))
    for page in range(total_pages):
        if page:
            c.showPage()
        start = page * per_sheet
        for slot in range(per_sheet):
            idx = start + slot
            if idx >= len(rows):
                break
            row = rows[idx]
            col, rw = slot % cols, slot // cols
            if per_sheet > 1:
                ox = (m + col * (lw_mm + g)) * MM
                oy = H - (m + rw * (lh_mm + g) + lh_mm) * MM
                c.saveState()
                c.translate(ox, oy)
                c.scale(lw_mm / W_mm, lh_mm / H_mm)
                _draw_label(c, design, row, W, H, dpi)
                c.restoreState()
            else:
                _draw_label(c, design, row, W, H, dpi)
    c.showPage()
    c.save()
    return buf.getvalue(), total_pages


def _grid(template) -> tuple[int, int]:
    cnt = int(template.get("label_count", 1) or 1)
    cols = max(1, int(template.get("columns", 1) or 1))
    rws = max(1, cnt // cols, 1)
    while cols * rws > cnt:
        rws -= 1
    return cols, max(1, rws)


def _draw_label(c, design, row, W, H, dpi):
    for e in sorted(design, key=lambda d: d.get("z", 0)):
        t = e["type"]
        x, y, w, h = e.get("x", 0) * MM, e.get("y", 0) * MM, e.get("w", 0) * MM, e.get("h", 0) * MM
        y_top = H - y - h
        rot = float(e.get("rotation", 0) or 0)
        try:
            if t == "line":
                c.saveState(); _rot(c, x, y_top, w, h, rot)
                c.setLineWidth(max(0.2, float(e.get("lineWidthMm", 0.3))) * MM)
                c.setStrokeColorRGB(*_rgb(e.get("color", "#000000")))
                c.line(x, y_top + h / 2, x + w, y_top + h / 2)
                c.restoreState()
            elif t == "rect":
                c.saveState(); _rot(c, x, y_top, w, h, rot)
                lwpt = max(0.2, float(e.get("lineWidthMm", 0.3))) * MM
                fill, stroke = e.get("fill", ""), e.get("stroke", "#000000")
                if fill and fill not in ("transparent", "none"):
                    c.setFillColorRGB(*_rgb(fill)); c.rect(x, y_top, w, h, stroke=0, fill=1)
                if stroke and stroke not in ("transparent", "none"):
                    c.setStrokeColorRGB(*_rgb(stroke)); c.setLineWidth(lwpt)
                    c.rect(x, y_top, w, h, stroke=1, fill=0)
                c.restoreState()
            elif t in ("text", "field"):
                _draw_text(c, e, row, x, y_top, w, h, rot, design)
            elif t in ("image", "asset"):
                _draw_image(c, e, x, y_top, w, h, rot)
            elif t == "barcode":
                _draw_barcode(c, e, row, x, y_top, w, h, rot, dpi, design)
        except (ValueError, RuntimeError) as exc:
            c.saveState()
            c.setFont("Helvetica", 6)
            c.setFillColorRGB(0.8, 0, 0)
            c.drawString(x, y_top + 4, f"⚠ {str(exc)[:70]}")
            c.restoreState()


def _rgb(hexs):
    hexs = (hexs or "#000000").lstrip("#")
    if len(hexs) == 3:
        hexs = "".join(ch * 2 for ch in hexs)
    return tuple(int(hexs[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _rot(c, x, y, w, h, deg):
    if deg:
        c.translate(x + w / 2, y + h / 2)
        c.rotate(deg)
        c.translate(-(x + w / 2), -(y + h / 2))


def _split_lines(text: str, font: str, size: float, max_w_mm: float) -> list[str]:
    out = []
    for para in str(text).split("\n"):
        line = ""
        for wd in para.split(" "):
            trial = (line + " " + wd).strip()
            if line and pdfmetrics.stringWidth(trial, font, size) / 72 * 25.4 > max_w_mm:
                out.append(line)
                line = wd
            else:
                line = trial
        out.append(line)
    return out


def _draw_text(c, e, row, x, y_top, w, h, rot, design):
    txt = el.resolved_text(e, row, design)
    if not txt:
        return
    font = fontreg.pdf_font(e.get("fontFamily", "Helvetica"), bool(e.get("bold")))
    size = float(e.get("fontSize", 3)) * MM
    lines = _split_lines(txt, font, size, (w / MM) if w else 10 ** 4)
    line_h = size * 1.25
    total = len(lines) * line_h
    if e.get("valign") == "middle":
        y = y_top + (h + total) / 2 - size * 0.8
    elif e.get("valign") == "bottom":
        y = y_top + total - size * 0.8
    else:
        y = y_top + h - size * 0.8 if h else y_top + total - size * 0.8
    c.saveState(); _rot(c, x, y_top, w, h, rot)
    c.setFont(font, size)
    c.setFillColorRGB(*_rgb(e.get("color", "#000000")))
    align = e.get("align", "left")
    for ln in lines:
        if align == "center":
            c.drawCentredString(x + w / 2 if w else x, y, ln)
        elif align == "right":
            c.drawRightString(x + w if w else x, y, ln)
        else:
            c.drawString(x, y, ln)
        y -= line_h
    c.restoreState()


def _draw_image(c, e, x, y_top, w, h, rot):
    path = None
    if e["type"] == "asset":
        a = database.get_asset(int(e.get("assetId", 0) or 0))
        if a:
            path = a["path"]
    if not path:
        return
    try:
        from PIL import Image
        with Image.open(path) as img:
            iw, ih = img.size
        if w <= 0 and h > 0: w = h * iw / ih
        if h <= 0 and w > 0: h = w * ih / iw
        if w > 0 and h > 0:
            c.saveState(); _rot(c, x, y_top, w, h, rot)
            c.drawImage(ImageReader(path), x, y_top, w, h, mask="auto")
            c.restoreState()
    except Exception:
        pass


def _draw_barcode(c, e, row, x, y_top, w, h, rot, dpi, design):
    stype = e.get("subtype", "CODE128")
    code = el.barcode_data(e, row, design)
    if stype == "QRCODE":
        side_mm = min(e.get("w", 15) or 15, e.get("h", 15) or 15)
        px = max(40, round(side_mm * dpi / 25.4))
        png = bc.qr_png(code, px, e.get("ecc", "M"), int(e.get("qrVersion", 0) or 0),
                        int(e.get("quiet", 2) or 2))
        bw = bh = side_mm * MM
    elif stype == "DATAMATRIX":
        side_mm = min(e.get("w", 12) or 12, e.get("h", 12) or 12)
        px = max(40, round(side_mm * dpi / 25.4))
        png = bc.datamatrix_png(code, px)
        bw = bh = side_mm * MM
    else:
        font_pt = float(e.get("fontSize", 2.4) * 2.835) or 7
        bh_mm = float(e.get("barcodeHeightMm", 0) or (e.get("h", 10) - (4 if e.get("showText", True) else 0)))
        png, w_mm, h_mm = bc.linear_png(code, stype, float(e.get("moduleWidthMm", 0.25)),
                                        max(3, bh_mm), bool(e.get("showText", True)), font_pt, dpi)
        bw, bh = w_mm * MM, h_mm * MM
        if w > 0 and bw > w:
            f = w / bw
            bw, bh = bw * f, bh * f
    yy = y_top + max(0, (h - bh) / 2) if h else y_top
    c.saveState(); _rot(c, x, yy, bw, bh, rot)
    c.drawImage(ImageReader(io.BytesIO(png)), x, yy, bw, bh)
    c.restoreState()


# ============================================================ Vorschau (HTML)
def preview_fragment(template: dict, row: dict) -> str:
    design = json.loads(template["design_json"])
    W, H = float(template["width_mm"]), float(template["height_mm"])
    out = [f'<div class="lbl" style="width:{W}mm;height:{H}mm;">']
    for e in sorted(design, key=lambda d: d.get("z", 0)):
        x, y, w, h = e.get("x", 0), e.get("y", 0), e.get("w", 0), e.get("h", 0)
        rot = float(e.get("rotation", 0) or 0)
        style = f"left:{x}mm;top:{y}mm;"
        if w: style += f"width:{w}mm;"
        if h: style += f"height:{h}mm;"
        if rot: style += f"transform:rotate({rot}deg);"
        t = e["type"]
        try:
            if t in ("text", "field"):
                txt = el.resolved_text(e, row, design)
                style += (f"font:{'700' if e.get('bold') else '400'} {e.get('fontSize',3)}mm/1.2 "
                          f"{_css_font(e.get('fontFamily','Helvetica'))};color:{e.get('color','#000')};")
                va = e.get("valign", "top")
                if h:
                    if va == "middle": style += f"display:flex;align-items:center;"
                    elif va == "bottom": style += f"display:flex;align-items:flex-end;"
                al = e.get("align", "left")
                style += f"text-align:{al};"
                out.append(f'<div class="txt" style="{style}">{escape(txt).replace(chr(10), "<br>")}</div>')
            elif t == "line":
                out.append(f'<div class="line" style="{style}height:{e.get("lineWidthMm",0.3)}mm;'
                           f'background:{e.get("color","#000")};"></div>')
            elif t == "rect":
                out.append(f'<div class="rect" style="{style}border:{e.get("lineWidthMm",0.3)}mm solid '
                           f'{e.get("stroke","#000")};background:{e.get("fill","transparent")};"></div>')
            elif t in ("image", "asset"):
                src = f"api/assets/{e.get('assetId')}/raw" if t == "asset" else ""
                out.append(f'<img class="img" style="{style}object-fit:fill;" src="{src}">')
            elif t == "barcode":
                out.append(_preview_barcode(e, row, style, design))
        except (ValueError, RuntimeError) as exc:
            out.append(f'<div class="err" style="{style}">⚠ {escape(str(exc))}</div>')
    out.append("</div>")
    return "".join(out)


def _css_font(fam):
    return {"Helvetica": "Arial,Helvetica,sans-serif", "Times": "Georgia,serif",
            "Courier": "ui-monospace,Consolas,monospace"}.get(fam, "Arial,Helvetica,sans-serif")


def _preview_barcode(e, row, style, design=None) -> str:
    st = e.get("subtype", "CODE128")
    code = el.barcode_data(e, row, design)
    if st == "QRCODE":
        png = bc.qr_png(code, 480, e.get("ecc", "M"), int(e.get("qrVersion", 0) or 0),
                        int(e.get("quiet", 2) or 2))
        src = "data:image/png;base64," + base64.b64encode(png).decode()
        return f'<img class="bc" style="{style}" src="{src}">'
    if st == "DATAMATRIX":
        try:
            png = bc.datamatrix_png(code, 480)
            src = "data:image/png;base64," + base64.b64encode(png).decode()
            return f'<img class="bc" style="{style}" src="{src}">'
        except RuntimeError as exc:
            return f'<div class="err" style="{style}">⚠ {escape(str(exc))}</div>'
    font_pt = float(e.get("fontSize", 2.4) * 2.835) or 7
    bh = float(e.get("barcodeHeightMm", 0) or (e.get("h", 10) - (4 if e.get("showText", True) else 0)))
    svg, _w_mm, _h_mm, _human = bc.linear_svg(code, st, float(e.get("moduleWidthMm", 0.25)),
                                              max(3, bh), bool(e.get("showText", True)), font_pt)
    svg = svg.replace("<svg ", '<svg preserveAspectRatio="xMidYMin meet" '
                      'style="width:100%;height:100%;" ', 1)
    return f'<div class="bc" style="{style}">{svg}</div>'
