"""Datenimport: CSV/TSV/Excel (Sheet 1) -> Liste von Zeilen-Dicts.

Robust: Semikolon oder Komma als Trenner (BOM, utf-8/latin-1), Leerzeilen
werden verworfen, Header werden stripped.
"""
import csv
import io


def parse_rows(data: bytes, filename: str = "") -> tuple[list[str], list[dict], list[str]]:
    """Gibt (headers, rows, warnings) zurück."""
    warnings: list[str] = []
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        headers, rows = _xlsx(data)
    elif name.endswith(".xls"):
        raise ValueError("Altes .xls-Format nicht unterstützt — bitte als .xlsx oder .csv speichern.")
    else:
        headers, rows = _csv(data)
    if not headers:
        raise ValueError("Keine Kopfzeile / keine Spalten gefunden")
    if not rows:
        warnings.append("Datendatei enthält keine Zeilen.")
    return headers, rows, warnings


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def _csv(data: bytes) -> tuple[list[str], list[dict]]:
    text = _decode(data)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
        delim = dialect.delimiter
    except csv.Error:
        delim = ";" if sample.count(";") >= sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    rows_iter = iter(reader)
    try:
        headers = [h.strip() for h in next(rows_iter)]
    except StopIteration:
        return [], []
    out = []
    for raw in rows_iter:
        if not any(str(c).strip() for c in raw):
            continue
        raw = raw + [""] * (len(headers) - len(raw))
        out.append({headers[i]: str(raw[i]).strip() for i in range(len(headers))})
    return headers, out


def _xlsx(data: bytes) -> tuple[list[str], list[dict]]:
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        first = next(rows_iter)
    except StopIteration:
        wb.close()
        return [], []
    headers = [str(h).strip() if h is not None else f"spalte_{i+1}" for i, h in enumerate(first)]
    out = []
    for raw in rows_iter:
        if raw is None or not any(str(c).strip() for c in raw if c is not None):
            continue
        vals = list(raw) + [None] * (len(headers) - len(raw))
        out.append({headers[i]: _xstr(vals[i]) for i in range(len(headers))})
    wb.close()
    return headers, out


def _xstr(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()
