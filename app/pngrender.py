"""PNG-Renderer: Label und Etikettenbögen bei Ziel-DPI.

Nutzt dieselben mm-Koordinaten wie PDF/HTML. Jedes Element wird in ein
eigenes RGBA-Teilbild gerendert (Rotation möglich) und auf die Basis geklebt.
Lineare Barcodes kommen aus dem bei Druck-DPI gerasterten Vektor-SVG, QR
pixelgenau, Texte über Pillow-TTFs.
"""
import io
import json
import math

from PIL import Image, ImageDraw

from . import barcode as bc
from . import db as database
from . import elements as el
from . import fonts as fontreg


# ============================================================ öffentliche API
def render_label_png(template: dict, row: dict, dpi: int | None = None) -> bytes:
    """Ein einzelnes Label in Originalgröße bei dpi."""
    design = json.loads(template["design_json"])
    dpi = _dpi(template, dpi)
    w_px = _px(float(template["width_mm"]), dpi)
    h_px = _px(float(template["height_mm"]), dpi)
    img = Image.new("RGB", (w_px, h_px), "#ffffff")
    _paint(img, design, row, dpi, dpi / 25.4, 0, 0)
    return _save(img, dpi)


def render_sheet_png(template: dict, row: dict, dpi: int | None = None) -> bytes:
    """Erster Bogen: alle Zellen des Templates mit derselben Datenzeile."""
    design = json.loads(template["design_json"])
    dpi = _dpi(template, dpi)
    W_px = _px(float(template["width_mm"]), dpi)
    H_px = _px(float(template["height_mm"]), dpi)
    img = Image.new("RGB", (W_px, H_px), "#ffffff")
    cols, rws = _grid(template)
    m = float(template.get("margin_mm", 2))
    g = float(template.get("gutter_mm", 3))
    lw_mm = (float(template["width_mm"]) - 2 * m - (cols - 1) * g) / cols
    lh_mm = (float(template["height_mm"]) - 2 * m - (rws - 1) * g) / rws
    for rw in range(rws):
        for col in range(cols):
            ox = _px(m + col * (lw_mm + g), dpi)
            oy = _px(m + rw * (lh_mm + g), dpi)
            cw, ch = _px(lw_mm, dpi), _px(lh_mm, dpi)
            cell = Image.new("RGB", (cw, ch), "#ffffff")
            _paint(cell, design, row, dpi, dpi / 25.4, 0, 0)
            img.paste(cell, (ox, oy))
    return _save(img, dpi)


def render_grid_png(template: dict, rows: list[dict], dpi: int | None = None) -> bytes:
    """Mehrere Datenzeilen auf einem Raster nebeneinander (für CSV-Vorschau)."""
    design = json.loads(template["design_json"])
    dpi = min(_dpi(template, dpi), 120)  # Vorschauauflösung
    n = max(1, len(rows))
    cols = min(4, n)
    rws = math.ceil(n / cols)
    lw_px = _px(float(template["width_mm"]), dpi)
    lh_px = _px(float(template["height_mm"]), dpi)
    pad = 8
    img = Image.new("RGB", (cols * (lw_px + pad) + pad, rws * (lh_px + pad) + pad), "#e5e7eb")
    for i, row in enumerate(rows):
        x = pad + (i % cols) * (lw_px + pad)
        y = pad + (i // cols) * (lh_px + pad)
        cell = Image.new("RGB", (lw_px, lh_px), "#ffffff")
        _paint(cell, design, row, dpi, dpi / 25.4, 0, 0)
        img.paste(cell, (x, y))
    return _save(img, 72)


# ============================================================ intern
def _dpi(template, override) -> int:
    return int(override or template.get("dpi") or 300)


def _px(mm: float, dpi: int) -> int:
    return max(1, round(mm / 25.4 * dpi))


def _grid(template) -> tuple[int, int]:
    cnt = int(template.get("label_count", 1) or 1)
    cols = max(1, int(template.get("columns", 1) or 1))
    rws = max(1, int(template.get("rows", 1) or 1))
    while cols * rws > cnt:
        rws -= 1
    return cols, rws


def _save(img: Image.Image, dpi: int) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(dpi, dpi))
    return buf.getvalue()


def _paint(base: Image.Image, design, row, dpi, u, ox, oy):
    """Alle Elemente auf Basisbild malen. u = px pro mm."""
    for e in sorted(design, key=lambda d: d.get("z", 0)):
        x, y = ox + e.get("x", 0) * u, oy + e.get("y", 0) * u
        w, h = e.get("w", 0) * u, e.get("h", 0) * u
        rot = float(e.get("rotation", 0) or 0)
        t = e["type"]
        part = None
        try:
            if t in ("text", "field"):
                part = _text_img(e, row, u, dpi, design)
                pw, ph = (w or part.width), max(h, part.height)
            elif t == "line":
                part = _line_img(e, w, h, u)
                pw, ph = part.size
            elif t == "rect":
                part = _rect_img(e, w, h, u)
                pw, ph = part.size
            elif t in ("image", "asset"):
                part = _asset_img(e)
                if part is None:
                    continue
                iw, ih = part.size
                if w <= 0 and h > 0: w = h * iw / ih
                if h <= 0 and w > 0: h = w * ih / iw
                if w > 0 and h > 0:
                    part = part.resize((max(1, round(w)), max(1, round(h))), Image.LANCZOS)
                pw, ph = part.size
            elif t == "barcode":
                part = _barcode_img(e, row, dpi, u, design)
                if part is None:
                    continue
                pw, ph = part.size
                if w > 0 and pw > w:
                    f = w / pw
                    part = part.resize((max(1, round(pw * f)), max(1, round(ph * f))), Image.LANCZOS)
                    pw, ph = part.size
            else:
                continue
        except (ValueError, RuntimeError) as exc:
            part = _error_img(str(exc), u, dpi)
            pw, ph = part.size
        if part is None or pw <= 0 or ph <= 0:
            continue
        if rot:
            pad = round(max(pw, ph) * 0.1) + 2
            canvas = Image.new("RGBA", (pw + 2 * pad, ph + 2 * pad), (0, 0, 0, 0))
            canvas.paste(part, (pad, pad))
            canvas = canvas.rotate(-rot, expand=True, resample=Image.BICUBIC)
            cx, cy = x + (w or pw) / 2, y + (h or ph) / 2
            base.paste(canvas, (int(cx - canvas.width / 2), int(cy - canvas.height / 2)), canvas)
        else:
            valign = e.get("valign", "top")
            yy = y
            if h > 0 and ph < h and t in ("text", "field"):
                if valign == "middle": yy = y + (h - ph) / 2
                elif valign == "bottom": yy = y + h - ph
            base.paste(part, (int(x), int(round(yy))), part)


def _text_img(e, row, u, dpi, design=None) -> Image.Image:
    txt = el.resolved_text(e, row, design)
    fam = e.get("fontFamily", "Helvetica")
    bold = bool(e.get("bold"))
    size_px = max(2, round(float(e.get("fontSize", 3)) * dpi / 25.4))
    font = fontreg.png_font(fam, bold, size_px)
    color = e.get("color", "#000000")
    max_w = max(1, round(e.get("w", 0) * u)) if e.get("w") else 10 ** 6
    lines = _wrap(txt, font, max_w)
    lh = round(size_px * 1.25)
    w = max([round(_tl(ln, font)) for ln in lines] + [1])
    h = max(1, lh * len(lines))
    img = Image.new("RGBA", (w + 2, h + 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    align = e.get("align", "left")
    yy = 1
    for ln in lines:
        lw_px = _tl(ln, font)
        xx = 1 if align == "left" else ((w - lw_px) / 2 + 1 if align == "center" else w - lw_px + 1)
        d.text((xx, yy), ln, font=font, fill=color)
        yy += lh
    return img


def _wrap(text, font, max_w: int) -> list[str]:
    out = []
    for para in str(text or "").split("\n"):
        line = ""
        for wd in para.split(" "):
            trial = (line + " " + wd).strip()
            if line and _tl(trial, font) > max_w:
                out.append(line)
                line = wd
            else:
                line = trial
        out.append(line)
    return out or [""]


def _tl(s, font) -> float:
    try:
        return font.getlength(s)
    except Exception:
        try:
            l, t, r, b = font.getbbox(s)
            return r - l
        except Exception:
            return len(s) * 6


def _line_img(e, w, h, u) -> Image.Image:
    lw = max(1, round(float(e.get("lineWidthMm", 0.3)) * u))
    img = Image.new("RGBA", (max(1, round(w)), max(1, round(h) + lw * 2)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.line([(0, lw // 2), (img.width, lw // 2)], fill=e.get("color", "#000000"), width=lw)
    return img


def _rect_img(e, w, h, u) -> Image.Image:
    lw = max(1, round(float(e.get("lineWidthMm", 0.3)) * u))
    img = Image.new("RGBA", (max(1, round(w) + lw), max(1, round(h) + lw)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    box = [0, 0, img.width - 1, img.height - 1]
    fill = e.get("fill", "")
    stroke = e.get("stroke", "#000000")
    if fill and fill not in ("transparent", "none"):
        d.rectangle(box, fill=fill)
    if stroke and stroke not in ("transparent", "none"):
        d.rectangle(box, outline=stroke, width=lw)
    return img


def _asset_img(e):
    path = None
    if e.get("type") == "asset":
        a = database.get_asset(int(e.get("assetId", 0) or 0))
        if a:
            path = a["path"]
    if not path:
        return None
    try:
        return Image.open(path).convert("RGBA")
    except Exception:
        return None


def _barcode_img(e, row, dpi, u, design=None):
    stype = e.get("subtype", "CODE128")
    code = el.barcode_data(e, row, design)
    if stype == "QRCODE":
        w_mm = e.get("w") or e.get("h") or 15
        h_mm = e.get("h") or e.get("w") or 15
        size = round(min(w_mm, h_mm) * dpi / 25.4)
        return Image.open(io.BytesIO(bc.qr_png(
            code, size, e.get("ecc", "M"),
            int(e.get("qrVersion", 0) or 0), int(e.get("quiet", 2) or 2)))).convert("RGBA")
    if stype == "DATAMATRIX":
        size = round(min(e.get("w", 12), e.get("h", 12)) * dpi / 25.4)
        return Image.open(io.BytesIO(bc.datamatrix_png(code, max(20, size)))).convert("RGBA")
    font_pt = float(e.get("fontSize", 2.4) * 2.835) or 7
    bh_mm = float(e.get("barcodeHeightMm", 0) or (e.get("h", 10) - (4 if e.get("showText", True) else 0)))
    png, w_mm, h_mm = bc.linear_png(code, stype, float(e.get("moduleWidthMm", 0.25)),
                                    max(3, bh_mm), bool(e.get("showText", True)), font_pt, dpi)
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    # Zielgröße in px nach aktuellem mm-Maßstab u (bei Bögen < dpi)
    tw, th = round(w_mm * u), round(h_mm * u)
    if (tw, th) != img.size:
        img = img.resize((max(1, tw), max(1, th)), Image.LANCZOS)
    return img


def _error_img(msg, u, dpi) -> Image.Image:
    size = max(9, round(2.2 * dpi / 25.4))
    font = fontreg.png_font("Helvetica", False, size)
    msg = ("⚠ " + msg)[:70]
    w = max(60, round(_tl(msg, font) + 8))
    img = Image.new("RGBA", (w, size + 8), (255, 240, 240, 255))
    ImageDraw.Draw(img).text((4, 3), msg, font=font, fill="#b00000")
    return img
