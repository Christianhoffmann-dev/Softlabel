"""SQLite-Schicht: Templates, Assets, Druckjobs, Audit-Log."""
import json
import sqlite3
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS templates(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  width_mm REAL NOT NULL,
  height_mm REAL NOT NULL,
  dpi INTEGER NOT NULL DEFAULT 300,
  label_count INTEGER NOT NULL DEFAULT 1,
  columns INTEGER NOT NULL DEFAULT 1,
  rows INTEGER NOT NULL DEFAULT 1,
  margin_mm REAL NOT NULL DEFAULT 2,
  gutter_mm REAL DEFAULT 0,
  design_json TEXT NOT NULL,
  created_at TEXT, updated_at TEXT,
  archived INTEGER NOT NULL DEFAULT 0,
  rev INTEGER NOT NULL DEFAULT 1,
  last_edited_by TEXT
);
CREATE TABLE IF NOT EXISTS folders(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  created_at TEXT, updated_at TEXT,
  archived INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS assets(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  filename TEXT NOT NULL,
  path TEXT NOT NULL,
  width_px INTEGER, height_px INTEGER,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS print_jobs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  template_id INTEGER,
  format TEXT,
  filename TEXT,
  labels INTEGER,
  rows INTEGER,
  created_by TEXT,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT, actor TEXT, action TEXT, detail TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")       # Leser blockieren Schreiber nicht
    conn.execute("PRAGMA busy_timeout = 8000")      # kurz warten statt Fehler
    conn.execute("PRAGMA synchronous = NORMAL")     # sicher genug mit WAL
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_conn()
    conn.executescript(SCHEMA)
    for ddl in ("ALTER TABLE templates ADD COLUMN rev INTEGER NOT NULL DEFAULT 1",
                "ALTER TABLE templates ADD COLUMN last_edited_by TEXT",
                "ALTER TABLE templates ADD COLUMN folder_id INTEGER",
                "CREATE INDEX IF NOT EXISTS idx_tpl_folder ON templates(folder_id)"):
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError:
            pass  # Spalte/Index existiert schon
    conn.close()
    _seed_examples()


def audit(actor: str, action: str, detail: str = "") -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO audit_log(ts, actor, action, detail) VALUES(?,?,?,?)",
        (now(), actor, action, detail),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------- templates
class RevConflict(Exception):
    """Vorlage wurde zwischenzeitlich von jemand anderem geändert."""


def save_template(t: dict, expected_rev: int | None = None) -> int:
    conn = get_conn()
    cols = ["name", "width_mm", "height_mm", "dpi", "label_count", "columns",
            "rows", "margin_mm", "gutter_mm", "design_json", "folder_id"]
    vals = [t.get(c) for c in cols]
    actor = t.get("actor", "web")
    if t.get("id"):
        sql = (f"UPDATE templates SET {','.join(c+'=?' for c in cols)}, "
               "updated_at=?, last_edited_by=?, rev=rev+1 WHERE id=?")
        args = vals + [now(), actor, t["id"]]
        if expected_rev is not None:
            sql += " AND rev=?"
            args.append(expected_rev)
        cur = conn.execute(sql, args)
        if expected_rev is not None and cur.rowcount == 0:
            conn.close()
            raise RevConflict(t["id"])
        tid = t["id"]
    else:
        cur = conn.execute(
            f"INSERT INTO templates({','.join(cols)},created_at,updated_at,last_edited_by) "
            f"VALUES({','.join('?' * len(cols))},?,?,?)",
            vals + [now(), now(), actor],
        )
        tid = cur.lastrowid
    conn.close()
    audit(actor, "template_saved", f"id={tid} name={t.get('name')}")
    return tid


def get_rev(tid: int) -> int | None:
    conn = get_conn()
    row = conn.execute("SELECT rev FROM templates WHERE id=?", (tid,)).fetchone()
    conn.close()
    return row["rev"] if row else None


def get_template(tid: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM templates WHERE id=?", (tid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_templates(include_archived=False, folder=None, only_archived=False) -> list[dict]:
    """Ordern: folder=None alle, folder=0 nur ohne Ordner, folder=n Ordner n."""
    conn = get_conn()
    q = ("SELECT id,name,width_mm,height_mm,dpi,label_count,updated_at,"
         "last_edited_by,rev,folder_id,archived FROM templates WHERE 1=1")
    if only_archived:
        q += " AND archived=1"
    elif not include_archived:
        q += " AND archived=0"
    if folder == 0:
        q += " AND folder_id IS NULL"
    elif folder:
        q += " AND folder_id=?"
    args = [folder] if folder else []
    rows = conn.execute(q + " ORDER BY updated_at DESC", args).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_archived(tid: int, archived: bool, actor: str = "-") -> None:
    conn = get_conn()
    conn.execute("UPDATE templates SET archived=?, updated_at=? WHERE id=?",
                 (1 if archived else 0, now(), tid))
    conn.commit()
    conn.close()
    audit(actor, "template_archived" if archived else "template_restored", f"id={tid}")


def move_template(tid: int, folder_id: int | None) -> None:
    conn = get_conn()
    if folder_id:
        conn.execute("UPDATE templates SET folder_id=?, archived=0, updated_at=? WHERE id=?",
                     (folder_id, now(), tid))
    else:
        conn.execute("UPDATE templates SET folder_id=NULL, updated_at=? WHERE id=?", (now(), tid))
    conn.commit()
    conn.close()
    audit("-", "template_moved", f"id={tid} folder={folder_id or 'Hauptbereich'}")


def count_templates(folder_id: int | None = None) -> int:
    conn = get_conn()
    if folder_id is None:
        n = conn.execute("SELECT COUNT(*) c FROM templates WHERE archived=0").fetchone()["c"]
    elif folder_id == 0:
        n = conn.execute("SELECT COUNT(*) c FROM templates WHERE archived=0 AND folder_id IS NULL").fetchone()["c"]
    else:
        n = conn.execute("SELECT COUNT(*) c FROM templates WHERE archived=0 AND folder_id=?", (folder_id,)).fetchone()["c"]
    conn.close()
    return n


def archived_count() -> int:
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) c FROM templates WHERE archived=1").fetchone()["c"]
    conn.close()
    return n


# ---------------------------------------------------------------- folders
def add_folder(name: str, actor: str = "-") -> int:
    conn = get_conn()
    cur = conn.execute("INSERT INTO folders(name, created_at, updated_at) VALUES(?,?,?)",
                       (name[:80], now(), now()))
    fid = cur.lastrowid
    conn.commit()
    conn.close()
    audit(actor, "folder_created", f"id={fid} {name}")
    return fid


def list_folders(archived: bool = False) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT f.*, (SELECT COUNT(*) FROM templates t WHERE t.folder_id=f.id AND t.archived=0) AS n"
        " FROM folders f WHERE f.archived=? ORDER BY f.name COLLATE NOCASE", (1 if archived else 0,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_folder(fid: int) -> dict | None:
    conn = get_conn()
    r = conn.execute("SELECT * FROM folders WHERE id=?", (fid,)).fetchone()
    conn.close()
    return dict(r) if r else None


def rename_folder(fid: int, name: str) -> bool:
    conn = get_conn()
    cur = conn.execute("UPDATE folders SET name=?, updated_at=? WHERE id=?", (name[:80], now(), fid))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def delete_folder(fid: int, actor: str = "-") -> None:
    """Ordner löschen: entfällt; die Vorlagen bleiben erhalten und landen im Hauptbereich.
    Vorlagen im Ordner-ARCHIV werden mit archiviert (sie sind ja schon archived)."""
    conn = get_conn()
    conn.execute("UPDATE templates SET folder_id=NULL WHERE folder_id=?", (fid,))
    conn.execute("DELETE FROM folders WHERE id=?", (fid,))
    conn.commit()
    conn.close()
    audit(actor, "folder_deleted", f"id={fid}")


def delete_template(tid: int) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM templates WHERE id=?", (tid,))
    conn.commit()
    conn.close()
    audit("-", "template_deleted", f"id={tid}")


def duplicate_template(tid: int) -> int | None:
    t = get_template(tid)
    if not t:
        return None
    t.pop("id")
    t["name"] = t["name"] + " (Kopie)"
    return save_template(t)


# ---------------------------------------------------------------- assets
def add_asset(filename: str, path: str, w: int, h: int) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO assets(filename, path, width_px, height_px, created_at) VALUES(?,?,?,?,?)",
        (filename, path, w, h, now()),
    )
    conn.commit()
    aid = cur.lastrowid
    conn.close()
    audit("-", "asset_added", f"id={aid} {filename}")
    return aid


def list_assets() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM assets ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_asset(aid: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM assets WHERE id=?", (aid,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ---------------------------------------------------------------- jobs / log
def add_job(template_id, fmt, filename, labels, rows, actor) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO print_jobs(template_id, format, filename, labels, rows, created_by, created_at)"
        " VALUES(?,?,?,?,?,?,?)",
        (template_id, fmt, filename, labels, rows, actor, now()),
    )
    conn.commit()
    conn.close()
    audit(actor, "export_" + fmt, f"{filename} labels={labels} rows={rows}")


def list_jobs(limit=100) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT j.*, t.name AS template_name FROM print_jobs j"
        " LEFT JOIN templates t ON t.id=j.template_id"
        " ORDER BY j.id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_audit(limit=200) -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- Beispieldaten
def _seed_examples() -> None:
    """Stellt die drei Beispielvorlagen wieder her, falls gelöscht (idempotent pro Name).

    Läuft in einer IMMEDIATE-Transaktion, damit zwei gleichzeitig startende
    Worker die Beispiele nicht doppelt anlegen.
    """
    conn = get_conn()

    def text(el_id, x, y, w, h, content="", **kw):
        d = {"id": el_id, "type": "text", "x": x, "y": y, "w": w, "h": h,
             "content": content, "fontFamily": "Helvetica", "fontSize": 3.2,
             "bold": False, "color": "#000000", "align": "left",
             "valign": "middle", "rotation": 0}
        d.update(kw)
        return d

    def field(el_id, x, y, w, h, key, **kw):
        d = {"id": el_id, "type": "field", "x": x, "y": y, "w": w, "h": h,
             "key": key, "label": "", "fontFamily": "Helvetica", "fontSize": 3.0,
             "bold": False, "color": "#000000", "align": "left", "valign": "middle",
             "rotation": 0}
        d.update(kw)
        return d

    def bar(el_id, code, x, y, w, h, symb="CODE128"):
        return {"id": el_id, "type": "barcode", "subtype": symb, "code": code,
                "x": x, "y": y, "w": w, "h": h, "moduleWidthMm": 0.25,
                "showText": True, "fontSize": 2.4, "rotation": 0}

    palet = [
        text("t1", 4, 4, 88, 9, "PALETTEN-LABEL", fontSize=7, bold=True),
        text("t2", 4, 14, 40, 5, "Auftrag:", fontSize=3.2, bold=True),
        field("f1", 42, 14, 50, 5, "auftrag", fontSize=5, bold=True),
        text("t3", 4, 20, 40, 5, "Empfänger:", fontSize=3.2, bold=True),
        field("f2", 42, 20, 50, 9, "empfaenger", fontSize=4.2, bold=True),
        field("f3", 4, 34, 60, 5, "adresse", fontSize=3.4),
        bar("b1", "{{auftrag}}", 4, 46, 90, 13),
        text("t4", 4, 80, 92, 6, "Ladungsträger EUR-1 · Bruttogewicht {{gewicht}} kg",
             fontSize=3.2),
    ]
    send = [
        text("s1", 3, 3, 104, 6, "VERSANDLABEL — PAKET", fontSize=5, bold=True),
        bar("s2", "{{tracking}}", 3, 10, 104, 12),
        text("s3", 3, 24, 20, 5, "Empfänger", fontSize=2.8, bold=True),
        field("s4", 3, 29, 104, 12, "empfaenger", fontSize=3.4, bold=True),
        text("s5", 3, 42, 30, 5, "Art.-Nr.", fontSize=2.6, bold=True),
        field("s6", 34, 42, 73, 5, "artnr", fontSize=3),
        text("s7", 3, 48, 30, 5, "Menge", fontSize=2.6, bold=True),
        field("s8", 34, 48, 73, 5, "menge", fontSize=3),
    ]
    palet2 = [
        text("q1", 2.5, 2.5, 45, 5, "{{artnr}}", fontSize=5, bold=True),
        bar("q2", "{{ean}}", 10, 8, 65, 9, symb="EAN13"),
        text("q3", 2.5, 18, 70, 4, "{{bezeichnung}}", fontSize=2.8),
        text("q4", 2.5, 22, 70, 4, "Charge {{charge}} · MHD {{mhd}}", fontSize=2.6),
    ]

    have = {r["name"] for r in conn.execute("SELECT name FROM templates").fetchall()}
    todo = [(name, w, h, cnt, cols, rws, mg, design) for name, w, h, cnt, cols, rws, mg, design in [
        ("Palettenlabel 100×150 mm (Zebra ZPL)", 100, 150, 1, 1, 1, 0, palet),
        ("Paket-Versandlabel 105×148 mm", 105, 148, 1, 1, 1, 0, send),
        ("Regal-Etikett 70×25 mm", 70, 25, 2, 2, 2, 2, palet2),
    ] if name not in have]
    if todo:
        conn.execute("BEGIN IMMEDIATE")
        try:
            again = {r["name"] for r in conn.execute("SELECT name FROM templates").fetchall()}
            for name, w, h, cnt, cols, rws, mg, design in todo:
                if name in again:
                    continue
                conn.execute(
                    "INSERT INTO templates(name,width_mm,height_mm,dpi,label_count,columns,rows,"
                    "margin_mm,gutter_mm,design_json,created_at,updated_at,last_edited_by,rev) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?, 'system', 1)",
                    (name, w, h, 300, cnt, cols, rws, mg, 3, json.dumps(design), now(), now()))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
    conn.close()
