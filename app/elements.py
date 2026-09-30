"""Gemeinsame Element-Logik: Variablen-Platzhalter {{feld}} und {{feld|upper}},
Element-Verknüpfungen (bindTo: Barcode/Text übernimmt den Wert eines anderen
Bausteins), Datensatz-Auflösung und Felderkennung in der Vorlage.
"""
import re

_VAR_RE = re.compile(r"\{\{\s*([\wäöüÄÖÜß.\- ]+?)\s*(?:\|\s*(upper|lower))?\s*\}\}")
_KEY_RE = re.compile(r"\{\{\s*([\wäöüÄÖÜß.\- ]+)")

BARCODE_TYPES = ["CODE128", "EAN13", "EAN8", "UPCA", "CODE39", "ITF14", "25IND", "PHARMA",
                 "QRCODE", "DATAMATRIX"]

_MAX_BIND_DEPTH = 10


def keys_in(design: list[dict]) -> list[str]:
    """Alle von der Vorlage referenzierten Datenfelder, in Reihenfolge.

    Erfasst {{feld}}-Platzhalter UND die key-Werte von Datenfeld-Elementen;
    bei Verknüpfungen wird das Feld am Ende der Bindungskette erfasst.
    """
    out, seen = [], set()

    def add(k):
        k = str(k).strip() if k else ""
        if k and k not in seen:
            seen.add(k)
            out.append(k)

    by_id = {e.get("id"): e for e in design if e.get("id")}
    for el in design:
        if el.get("bindTo"):
            cur, seenb, d = el, set(), 0
            while cur.get("bindTo") and d < _MAX_BIND_DEPTH:
                t = by_id.get(cur["bindTo"])
                if t is None or t.get("id") in seenb:
                    break
                seenb.add(t["id"])
                cur = t
                d += 1
            if cur.get("type") == "field":
                add(cur.get("key"))
        blob = " ".join(str(el.get(k, "")) for k in ("content", "code", "label"))
        for m in _KEY_RE.finditer(blob):
            add(m.group(1))
        if el.get("type") == "field" and not el.get("bindTo"):
            add(el.get("key"))
    return out


def subst(value: str, row: dict) -> str:
    if not value:
        return ""
    def rep(m):
        v = str(row.get(m.group(1).strip(), ""))
        if m.group(2) == "upper":
            v = v.upper()
        elif m.group(2) == "lower":
            v = v.lower()
        return v
    return _VAR_RE.sub(rep, value)


def _find_target(el: dict, by_id: dict) -> dict | None:
    tid = el.get("bindTo")
    if not tid or not by_id:
        return None
    return by_id.get(tid)


def _index(design) -> dict:
    if isinstance(design, dict):
        return design
    return {e.get("id"): e for e in (design or []) if e.get("id")}


def resolved_text(el: dict, row: dict, design=None, raw: bool = False) -> str:
    """Endgültiges Textmaterial eines text/field-Elements für eine Datenzeile.

    Mit bindTo übernimmt das Element den Wert des verknüpften Bausteins
    (Text oder Datenfeld); {{feld}}-Platzhalter werden dabei aufgelöst.
    raw=True liefert Datenfeldwerte ohne Vortext (für Barcode-Inhalte).
    """
    by_id = _index(design)
    seen = set()
    cur, depth = el, 0
    while depth < _MAX_BIND_DEPTH:
        tgt = _find_target(cur, by_id)
        if tgt is None or tgt.get("id") in seen or tgt.get("type") == "barcode":
            break
        seen.add(tgt["id"])
        cur = tgt
        depth += 1
    return _material(cur, row, raw)


def _material(el: dict, row: dict, raw: bool = False) -> str:
    """Rohmaterial eines Elements ohne weitere Bindings auflösen."""
    if el.get("type") == "field":
        val = str(row.get(el.get("key", ""), ""))
        if el.get("uppercase"):
            val = val.upper()
        if raw:
            return val
        label = subst(el.get("label", ""), row)
        return (label + " " + val).strip() if label else val
    return subst(el.get("content", ""), row)


def bind_name(el: dict, design) -> str:
    """Anzeigename des Verknüpfungsziels oder ''."""
    by_id = _index(design)
    tgt = _find_target(el, by_id)
    if not tgt:
        return ""
    if tgt.get("type") == "field":
        return tgt.get("key") or tgt.get("label") or tgt.get("id")
    return (tgt.get("content") or tgt.get("label") or tgt.get("id") or "")[:24]


def barcode_data(el: dict, row: dict, design=None) -> str:
    """Barcode-Inhalt: verknüpfter Wert, {{feld}}-Ausdruck oder fester Text.

    Leere Ergebnisse -> Platzhalter, damit der Renderer nicht mit leerem Code läuft.
    """
    if el.get("bindTo"):
        val = resolved_text(el, row, design)
    else:
        val = subst(el.get("code", ""), row)
    if not val:
        key = re.search(r"\{\{\s*([\w\-]+)", str(el.get("code", "")) or el.get("key", ""))
        src = key.group(1) if key else "Daten"
        val = f"[{src}]"
    return val
