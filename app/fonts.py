"""Schriftarten-Registry: sucht passende System-TTFs (Windows/Linux/macOS)
und meldet sie Reportlab (PDF) und Pillow (PNG) an. Standard-14-PDF-Fonts
dienen als Fallback — ihr Latin-1-Umfang deckt äöüß ab.
"""
import re
import os
from pathlib import Path

# family -> (reguläre Stämme, fette Stämme). Stämme = TTF-Dateistiele ohne Endung,
# verglichen in Kleinbuchstaben ohne Leerzeichen/Bindestriche.
_FAMILIES = {
    "Helvetica": (
        ["arial", "liberationsans", "dejavusans", "helveticaneue", "helvetica"],
        ["arialbold", "liberationsansbold", "dejavusansbold", "helveticaneuebold", "helveticabold"],
    ),
    "Times": (
        ["timesnewroman", "liberationserif", "dejavuserif", "times", "timesroman"],
        ["timesnewromanbold", "liberationserifbold", "dejavuserifbold", "timesbold"],
    ),
    "Courier": (
        ["couriernew", "liberationmono", "dejavusansmono", "courier"],
        ["couriernewbold", "liberationmonobold", "dejavusansmonobold", "courierbold"],
    ),
}

_CANDIDATE_DIRS = [
    Path("C:/Windows/Fonts"),
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype/liberation"),
    Path("/usr/share/fonts/truetype"),
    Path("/usr/share/fonts"),
    Path("/System/Library/Fonts/Supplemental"),
    Path("/Library/Fonts"),
]

_registered: dict | None = None   # {(family, bold): pdf_font_name}
_png_files: dict | None = None    # {(family, bold): ttf_path}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _stem_matches(stem: str, want: str) -> bool:
    """'arialbd' / 'Arial Bold Italic' etc. tolerieren: Stamm beginnt mit dem
    Soll-Namen und der Rest ist nur Stil-Suffix."""
    if stem == want:
        return True
    if not stem.startswith(want):
        return False
    tail = stem[len(want):]
    return bool(tail) and all(t in "bolditalicipregularromanobliquebk" for t in tail)


def _scan() -> dict:
    files: list[Path] = []
    for d in _CANDIDATE_DIRS:
        if not d.is_dir():
            continue
        try:
            for root, _sub, names in os.walk(d):
                files.extend(Path(root) / n for n in names if n.lower().endswith((".ttf", ".ttc")))
        except OSError:
            pass
    stems = {}
    for f in files:
        stems.setdefault(_norm(f.stem), f)

    found: dict = {}
    for family, (reg_stems, bold_stems) in _FAMILIES.items():
        for bold, want_list in ((False, reg_stems), (True, bold_stems)):
            chosen = None
            for want in (_norm(w) for w in want_list):
                if want in stems:
                    chosen = stems[want]
                    break
                for s, f in stems.items():
                    if _stem_matches(s, want):
                        chosen = f
                        break
                if chosen:
                    break
            if chosen:
                found[(family, bold)] = str(chosen)
    return found


def _ensure():
    global _registered, _png_files
    if _registered is not None:
        return _registered, _png_files
    found = _scan()
    _png_files = found
    _registered = {}
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        for (family, bold), path in found.items():
            pdfname = f"SL{family}{'B' if bold else ''}"
            try:
                pdfmetrics.registerFont(TTFont(pdfname, path, subfontIndex=0))
                _registered[(family, bold)] = pdfname
            except Exception:
                pass
    except Exception:
        pass
    return _registered, _png_files


_TYPE1 = {
    ("Helvetica", False): "Helvetica", ("Helvetica", True): "Helvetica-Bold",
    ("Times", False): "Times-Roman", ("Times", True): "Times-Bold",
    ("Courier", False): "Courier", ("Courier", True): "Courier-Bold",
}


def pdf_font(family: str, bold: bool) -> str:
    reg, _ = _ensure()
    return reg.get((family, bool(bold))) or _TYPE1.get((family, bool(bold)), "Helvetica")


def png_font(family: str, bold: bool, size_px: int):
    from PIL import ImageFont
    _, files = _ensure()
    path = files.get((family, bool(bold)))
    size_px = max(2, int(size_px))
    if path:
        try:
            return ImageFont.truetype(path, size_px)
        except Exception:
            pass
    try:
        return ImageFont.truetype("arial.ttf", size_px)
    except Exception:
        try:
            return ImageFont.load_default(size_px)
        except TypeError:  # Pillow < 10.1
            return ImageFont.load_default()
