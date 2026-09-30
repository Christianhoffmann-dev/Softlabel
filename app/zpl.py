"""ZPL-Export — native Zebra-Sprache (ZPL II).

Label-Elemente werden 1:1 in ^FO/^FD/^BY/^BQ/^BX-Blöcke übersetzt, das Ergebnis
kann direkt an \\printer\Zebra oder über das Zebra-Webinterface gesendet werden.
Enthält Felder und Barcodes; Formen/Bilder als grafische Elemente nur
eingeschränkt (Kommentar Hinweis im Ausgabekopf).
"""
import json

from . import elements as el

_ORIGIN = "^XA^LH0,0^CI28"


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("^", "\\^").replace("~", "\\~")


def render_zpl(template: dict, rows: list[dict]) -> str:
    design = json.loads(template["design_json"])
    dpi = int(template.get("dpi", 300)) or 300
    # Zebra rechnet in Dots; 203/300/600 dpi üblich
    px = dpi / 25.4

    def dots(mm):
        return int(round(float(mm) * px))

    out = []
    for row in (rows or [{}]):
        cmd = [_ORIGIN,
               f"^LL{dots(template['height_mm'])}",
               f"^PW{dots(template['width_mm'])}"]
        for e in sorted(design, key=lambda d: d.get("z", 0)):
            t = e["type"]
            x, y = dots(e.get("x", 0)), dots(e.get("y", 0))
            w, h = dots(e.get("w", 0)), dots(e.get("h", 0))
            if t in ("text", "field"):
                txt = el.resolved_text(e, row, design)
                if not txt:
                    continue
                size = e.get("fontSize", 3)
                height = dots(size * 1.05)
                width = max(1, dots(size * 0.55))
                bold2 = 2 if e.get("bold") else 1
                block = f"^FO{x},{y}^AAN{height},{width * bold2}^FD{_esc(txt)}^FS"
                cmd.append(block)
            elif t == "barcode":
                stype = e.get("subtype", "CODE128")
                code = el.barcode_data(e, row, design)
                if stype == "QRCODE":
                    mag = max(1, dots(e.get("qrModuleDots", 0)) or round(min(w, h) / 25))
                    cmd.append(f"^FO{x},{y}^BQ,2,{mag}^FDLA,{_esc(code)}^FS")
                elif stype == "DATAMATRIX":
                    mag = max(2, round(min(w, h) / 12) or 6)
                    cmd.append(f"^FO{x},{y}^BX,0,{mag}^FD{_esc(code)}^FS")
                else:
                    mod = e.get("moduleWidthMm", 0.25)
                    # ^BY widths: narrow in dots
                    narrow = max(1, dots(mod))
                    wide = int(narrow * 2.5) if stype in ("CODE39", "ITF14") else narrow
                    height_dots = dots(e.get("barcodeHeightMm", 0) or (e.get("h", 10) - 4))
                    hri = "Y" if e.get("showText", True) else "N"
                    sym = {"CODE128": "BC", "CODE128B": "BC", "EAN13": "BE",
                           "EAN8": "BE8", "UPCA": "BU", "CODE39": "B3",
                           "ITF14": "BI", "25IND": "B2", "PHARMA": "BP"}.get(stype, "BC")
                    extra = ""
                    cmd.append(f"^FO{x},{y}^BY{narrow},{wide}"
                               f"^{sym},{height_dots},{hri}{extra}"
                               f"^FD{_esc(code)}^FS")
            elif t == "line":
                lw = max(1, dots(e.get("lineWidthMm", 0.3)))
                cmd.append(f"^FO{x},{y},^GB{max(w,1)},{lw},{lw}^FS")
            elif t == "rect":
                lw = max(1, dots(e.get("lineWidthMm", 0.3)))
                cmd.append(f"^FO{x},{y},^GB{max(w,1)},{max(h,1)},{lw}^FS")
            else:
                cmd.append(f"^FX image/asset {e.get('id','')} nicht in ZPL uebertragen^FS")
        cmd.append("^XZ")
        out.append("\r\n".join(cmd))
    return "\r\n".join(out)
