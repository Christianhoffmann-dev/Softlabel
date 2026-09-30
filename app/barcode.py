"""Barcode-Rendering.

Lineare Symbole: python-barcode liefert die Bitmuster (build()), daraus entsteht
ein eigenes SVG in mm — Modulbreiten exakt wie vorgegeben, identisch in
Vorschau (inline-SVG), PNG (bei Druck-DPI gerastert) und PDF.
QR: qrcode-Bibliothek, pixelgenau. DataMatrix: optional (pylibdmtx /
python-datamatrix), sonst saubere Fehlermeldung im Label.
"""
import io
import itertools
import re

try:
    from barcode import Code128, Code39, EAN13, EAN8, UPCA
    from barcode.itf import ITF
    BARCODE_LIB = True
except ImportError:  # pragma: no cover
    BARCODE_LIB = False

LINEAR_TYPES = ("CODE128", "EAN13", "EAN8", "UPCA", "CODE39", "ITF14", "25IND", "PHARMA")


def _clean(code: str) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", "", code or "").strip()


def ean13_check_digit(digits12: str) -> str:
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(digits12))
    return str((10 - total % 10) % 10)


def itf14_check_digit(digits13: str) -> str:
    weights = [3, 1] * 6 + [3]
    total = sum(int(d) * w for d, w in zip(digits13, weights))
    return str((10 - total % 10) % 10)


def pharmacode_bits(n: int) -> str:
    """GS1 Pharmacode: Full-Bar=3 Module, Narrow-Bar=2, Trennung=1 (links=MSB-Ende)."""
    seq = []
    while n > 1:
        seq.append(1 if n % 2 == 0 else 0)  # 1 = full bar, 0 = narrow bar
        n = (n - 2) // 2 if n % 2 == 0 else (n - 1) // 2
    seq.reverse()
    seq = seq[1:]  # höchstwertige Ziffer wird nicht kodiert
    return "".join(("111" if s else "11") + "0" for s in seq)


def _encode(symb: str, code: str):
    """→ (bitstring, menschenlesbarer Text). Validiert Daten je Symbologie."""
    if not BARCODE_LIB:
        raise RuntimeError("python-barcode fehlt im Container (requirements prüfen)")
    code = _clean(code)
    if not code:
        raise ValueError("Barcode: keine Daten")
    digits = re.sub(r"\D", "", code)
    try:
        if symb in ("CODE128", "CODE128B", "GS1-128"):
            obj = Code128(code)
        elif symb == "EAN13":
            if len(digits) == 12:
                digits += ean13_check_digit(digits)
            if len(digits) == 8:
                obj = EAN8(digits)
                return "".join(obj.build()), obj.get_fullcode()
            if len(digits) != 13 or digits == "0" * 13:
                raise ValueError(f"EAN-13 braucht 12/13 Ziffern, bekommen: {len(digits)} Ziffern")
            obj = EAN13(digits)
        elif symb == "EAN8":
            if len(digits) == 7:
                obj = EAN8(digits)
            elif len(digits) == 8:
                obj = EAN8(digits)
            else:
                raise ValueError("EAN-8 braucht 7/8 Ziffern")
        elif symb == "UPCA":
            if len(digits) == 12:
                digits += ean13_check_digit(digits)
            if len(digits) != 13:
                raise ValueError("UPC-A braucht 11/12 Ziffern")
            obj = UPCA(digits[1:])
        elif symb == "CODE39":
            allowed = re.sub(r"[^0-9A-Z\-.\s$/+%]", "", code.upper()).replace("*", "")
            if not allowed:
                raise ValueError("CODE39: keine gültigen Zeichen (0-9, A-Z, - . / $ + % und Leerzeichen)")
            obj = Code39(allowed)
        elif symb == "ITF14":
            if len(digits) == 13:
                digits += itf14_check_digit(digits)
            if len(digits) != 14:
                raise ValueError("ITF-14 braucht 13/14 Ziffern")
            obj = ITF(digits)
        elif symb == "25IND":
            if not digits:
                raise ValueError("Code 2interleaved 5 braucht Ziffern")
            if len(digits) % 2:
                digits = "0" + digits
            obj = ITF(digits)
        elif symb == "PHARMA":
            if not digits or len(digits) > 4:
                raise ValueError("Pharmacode: Zahl mit 1–4 Ziffern")
            return pharmacode_bits(int(digits)), digits
        else:
            raise ValueError(f"Unbekanntes Symbol: {symb}")
        return "".join(obj.build()), str(obj.get_fullcode())
    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise ValueError(f"Barcode {symb}: {exc}") from exc


def _runs(bits: str) -> list[int]:
    """'11001…' → [2,2,1,…] Moduleinheiten (Strich, Lücke, Strich, …)."""
    return [len(list(g)) for _k, g in itertools.groupby(bits)]


def linear_svg(code: str, symb: str, module_mm: float, height_mm: float,
               show_text: bool, font_pt: float, quiet_mm: float = 2.5):
    """SVG-Zeichenkette mit mm-Einheiten. → (svg, breite_mm, höhe_mm, human)"""
    bits, human = _encode(symb, code)
    module = max(0.1, float(module_mm))
    bar_h = max(4.0, float(height_mm))
    text_h = max(2.0, float(font_pt) * 0.3528 * 1.3) if show_text else 0.0
    runs = _runs(bits)
    if runs and bits[0] == "0":
        runs = [0] + runs  # Sicherheitsabstand vor erstem Strich
    bars_w = sum(runs) * module
    quiet = max(quiet_mm, 1.0)
    total_w = bars_w + 2 * quiet

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w:.4f}mm" '
             f'height="{bar_h + text_h:.4f}mm" viewBox="0 0 {total_w:.4f} {bar_h + text_h:.4f}">',
             f'<rect width="100%" height="100%" fill="#ffffff"/>']
    x = quiet
    for i, u in enumerate(runs):
        if i % 2 == 0:  # gerader Lauf = Strich
            parts.append(f'<rect x="{x:.4f}" y="0" width="{u * module:.4f}" height="{bar_h:.4f}" fill="#000000"/>')
        x += u * module
    if show_text and human:
        fmm = float(font_pt) * 0.3528
        parts.append(f'<text x="{total_w / 2:.3f}" y="{bar_h + fmm:.3f}" text-anchor="middle" '
                     f'font-family="Arial,Helvetica,sans-serif" font-size="{fmm:.3f}" '
                     f'fill="#000000">{_esc(human)}</text>')
    parts.append("</svg>")
    return "".join(parts), total_w, bar_h + text_h, human


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def linear_png(code: str, symb: str, module_mm: float, height_mm: float,
               show_text: bool, font_pt: float, dpi: int):
    """PNG bei Ziel-DPI. → (png_bytes, breite_mm, höhe_mm)"""
    svg, w_mm, h_mm, _ = linear_svg(code, symb, module_mm, height_mm, show_text, font_pt)
    from .vector import rasterize_svg
    png, _w, _h = rasterize_svg(svg.encode("utf-8"), dpi)
    return png, w_mm, h_mm


# ---------------------------------------------------------------- QR-Code
def qr_png(text: str, size_px: int, ecc: str = "M", version: int = 0,
           border: int = 2) -> bytes:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q
    from PIL import Image
    level = {"L": ERROR_CORRECT_L, "M": ERROR_CORRECT_M, "Q": ERROR_CORRECT_Q,
             "H": ERROR_CORRECT_H}.get((ecc or "M").upper(), ERROR_CORRECT_M)
    qr = qrcode.QRCode(version=version or None, error_correction=level,
                       box_size=1, border=border)
    qr.add_data(_clean(text) or " ")
    qr.make(fit=True)
    matrix = qr.get_matrix()
    n = len(matrix)
    scale = max(1, round(size_px / n))
    img = Image.new("1", (n * scale, n * scale), 1)
    px = img.load()
    for r, row in enumerate(matrix):
        for c, v in enumerate(row):
            if v:
                for dy in range(scale):
                    y = r * scale + dy
                    for dx in range(scale):
                        px[c * scale + dx, y] = 0
    img = img.convert("RGB")
    if img.width != size_px:
        img = img.resize((size_px, size_px), Image.NEAREST)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------- DataMatrix (optional)
def datamatrix_png(text: str, size_px: int) -> bytes:
    t = _clean(text)
    from PIL import Image
    try:
        from pylibdmtx.pylibdmtx import encode as dmtx_encode
        enc = dmtx_encode(t.encode("utf-8"))
        img = Image.frombytes("L", (enc.width, enc.height), enc.pixels).convert("RGB")
        img = img.resize((size_px, size_px), Image.NEAREST)
        buf = io.BytesIO(); img.save(buf, format="PNG"); return buf.getvalue()
    except Exception:
        pass
    try:
        import datamatrix as dm
        m = dm.encode.DataMatrix(t).matrix
        n = len(m)
        scale = max(1, size_px // n)
        img = Image.new("1", (n * scale, n * scale), 1)
        px = img.load()
        for r in range(n):
            for c in range(n):
                if m[r][c]:
                    for dy in range(scale):
                        for dx in range(scale):
                            px[c * scale + dx, r * scale + dy] = 0
        img = img.convert("RGB")
        if img.width != size_px:
            img = img.resize((size_px, size_px), Image.NEAREST)
        buf = io.BytesIO(); img.save(buf, format="PNG"); return buf.getvalue()
    except Exception as exc:
        raise RuntimeError(
            "DataMatrix-Renderer fehlt (pylibdmtx/libdmtx oder python-datamatrix). "
            "In requirements.txt freischalten oder QR/Code128 verwenden.") from exc
