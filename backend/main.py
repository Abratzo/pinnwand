from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from typing import Optional, List
import sqlite3, os, base64
from datetime import datetime

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DB_PATH = os.environ.get("DB_PATH", "/data/pinnwand.db")

def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con

def now():
    return datetime.now().isoformat(timespec='seconds')

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = get_db()
    con.executescript("""
        CREATE TABLE IF NOT EXISTS boards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            board_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            color TEXT NOT NULL DEFAULT 'gray',
            FOREIGN KEY (board_id) REFERENCES boards(id)
        );
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            board_id INTEGER NOT NULL,
            text TEXT NOT NULL DEFAULT '',
            color TEXT NOT NULL DEFAULT 'yellow',
            author TEXT,
            archived INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (board_id) REFERENCES boards(id)
        );
        CREATE TABLE IF NOT EXISTS note_tags (
            note_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (note_id, tag_id)
        );
        CREATE TABLE IF NOT EXISTS note_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            note_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            author TEXT,
            changed_at TEXT NOT NULL,
            FOREIGN KEY (note_id) REFERENCES notes(id)
        );
        CREATE TABLE IF NOT EXISTS note_boards (
            note_id INTEGER NOT NULL,
            board_id INTEGER NOT NULL,
            PRIMARY KEY (note_id, board_id)
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)
    # Migrations
    cols = [r[1] for r in con.execute("PRAGMA table_info(notes)").fetchall()]
    if 'sort_order' not in cols:
        con.execute("ALTER TABLE notes ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")

    # Default board
    if con.execute("SELECT COUNT(*) FROM boards").fetchone()[0] == 0:
        con.execute("INSERT INTO boards (name, created_at) VALUES (?, ?)", ("Hauptboard", now()))

    con.commit()
    con.close()

init_db()

# ── Models ──────────────────────────────────────────────
class BoardIn(BaseModel):
    name: str

class TagIn(BaseModel):
    name: str
    color: str = "gray"

class NoteIn(BaseModel):
    text: str
    color: str = "yellow"
    author: Optional[str] = None
    tag_ids: List[int] = []
    extra_board_ids: List[int] = []

class NoteUpdate(BaseModel):
    text: Optional[str] = None
    color: Optional[str] = None
    author: Optional[str] = None
    tag_ids: Optional[List[int]] = None
    extra_board_ids: Optional[List[int]] = None
    archived: Optional[int] = None
    editor: Optional[str] = None

class BoardReorderIn(BaseModel):
    board_ids: List[int]

@app.post("/api/boards/reorder")
def reorder_boards(r: BoardReorderIn):
    con = get_db()
    for i, bid in enumerate(r.board_ids):
        con.execute("UPDATE boards SET sort_order=? WHERE id=?", (i, bid))
    con.commit()
    con.close()
    return {"ok": True}

class ReorderIn(BaseModel):
    note_ids: List[int]

# ── Helpers ──────────────────────────────────────────────
def enrich_notes(rows, con):
    result = []
    for r in rows:
        note = dict(r)
        tag_rows = con.execute(
            "SELECT t.* FROM tags t JOIN note_tags nt ON t.id=nt.tag_id WHERE nt.note_id=?",
            (note["id"],)
        ).fetchall()
        note["tags"] = [dict(t) for t in tag_rows]
        board_rows = con.execute(
            "SELECT board_id FROM note_boards WHERE note_id=?", (note["id"],)
        ).fetchall()
        note["extra_board_ids"] = [r[0] for r in board_rows]
        result.append(note)
    return result

# ── Settings / Logo ──────────────────────────────────────
@app.get("/api/settings/logo")
def get_logo():
    con = get_db()
    row = con.execute("SELECT value FROM settings WHERE key='logo'").fetchone()
    con.close()
    if not row:
        raise HTTPException(404, "Kein Logo")
    return {"logo": row[0]}

@app.post("/api/settings/logo")
async def upload_logo(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > 512 * 1024:
        raise HTTPException(400, "Logo zu groß (max 512 KB)")
    mime = file.content_type or "image/png"
    b64 = base64.b64encode(data).decode()
    data_url = f"data:{mime};base64,{b64}"
    con = get_db()
    con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('logo', ?)", (data_url,))
    con.commit()
    con.close()
    return {"logo": data_url}

@app.delete("/api/settings/logo")
def delete_logo():
    con = get_db()
    con.execute("DELETE FROM settings WHERE key='logo'")
    con.commit()
    con.close()
    return {"ok": True}

# ── Boards ───────────────────────────────────────────────
@app.get("/api/boards")
def list_boards():
    con = get_db()
    rows = con.execute("SELECT * FROM boards ORDER BY sort_order ASC, id ASC").fetchall()
    con.close()
    return [dict(r) for r in rows]

@app.post("/api/boards")
def create_board(b: BoardIn):
    con = get_db()
    max_order = con.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM boards").fetchone()[0]
    cur = con.execute("INSERT INTO boards (name, sort_order, created_at) VALUES (?, ?, ?)", (b.name, max_order, now()))
    con.commit()
    board_id = cur.lastrowid
    con.close()
    return {"id": board_id, "name": b.name}

@app.delete("/api/boards/{board_id}")
def delete_board(board_id: int):
    con = get_db()
    if con.execute("SELECT COUNT(*) FROM boards").fetchone()[0] <= 1:
        raise HTTPException(400, "Letztes Board kann nicht gelöscht werden")
    note_ids = [r[0] for r in con.execute("SELECT id FROM notes WHERE board_id=?", (board_id,)).fetchall()]
    for nid in note_ids:
        con.execute("DELETE FROM note_history WHERE note_id=?", (nid,))
        con.execute("DELETE FROM note_tags WHERE note_id=?", (nid,))
        con.execute("DELETE FROM note_boards WHERE note_id=?", (nid,))
    con.execute("DELETE FROM notes WHERE board_id=?", (board_id,))
    con.execute("DELETE FROM note_boards WHERE board_id=?", (board_id,))
    con.execute("DELETE FROM tags WHERE board_id=?", (board_id,))
    con.execute("DELETE FROM boards WHERE id=?", (board_id,))
    con.commit()
    con.close()
    return {"ok": True}

@app.patch("/api/boards/{board_id}")
def rename_board(board_id: int, b: BoardIn):
    con = get_db()
    con.execute("UPDATE boards SET name=? WHERE id=?", (b.name, board_id))
    con.commit()
    con.close()
    return {"ok": True}

# ── Overview board ───────────────────────────────────────
@app.get("/api/notes/overview")
def overview_notes():
    """All non-archived notes across all boards."""
    con = get_db()
    rows = con.execute(
        "SELECT * FROM notes WHERE archived=0 ORDER BY updated_at DESC"
    ).fetchall()
    result = enrich_notes(rows, con)
    # Attach board name
    boards_map = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM boards").fetchall()}
    for n in result:
        n["board_name"] = boards_map.get(n["board_id"], "?")
    con.close()
    return result

# ── Tags ─────────────────────────────────────────────────
@app.get("/api/boards/{board_id}/tags")
def list_tags(board_id: int):
    con = get_db()
    rows = con.execute("SELECT * FROM tags WHERE board_id=? ORDER BY name", (board_id,)).fetchall()
    con.close()
    return [dict(r) for r in rows]

@app.post("/api/boards/{board_id}/tags")
def create_tag(board_id: int, t: TagIn):
    con = get_db()
    cur = con.execute("INSERT INTO tags (board_id, name, color) VALUES (?, ?, ?)", (board_id, t.name, t.color))
    con.commit()
    tag_id = cur.lastrowid
    con.close()
    return {"id": tag_id, "name": t.name, "color": t.color}

@app.delete("/api/boards/{board_id}/tags/{tag_id}")
def delete_tag(board_id: int, tag_id: int):
    con = get_db()
    con.execute("DELETE FROM note_tags WHERE tag_id=?", (tag_id,))
    con.execute("DELETE FROM tags WHERE id=? AND board_id=?", (tag_id, board_id))
    con.commit()
    con.close()
    return {"ok": True}

# ── Notes ────────────────────────────────────────────────
@app.get("/api/boards/{board_id}/notes")
def list_notes(board_id: int, archived: int = 0):
    con = get_db()
    # Primary board notes
    rows = con.execute(
        "SELECT * FROM notes WHERE board_id=? AND archived=? ORDER BY sort_order ASC, created_at DESC",
        (board_id, archived)
    ).fetchall()
    # Also notes assigned to this board via note_boards
    extra_ids = {r[0] for r in con.execute(
        "SELECT note_id FROM note_boards WHERE board_id=?", (board_id,)
    ).fetchall()}
    primary_ids = {dict(r)["id"] for r in rows}
    extra_note_ids = extra_ids - primary_ids
    extra_rows = []
    for nid in extra_note_ids:
        r = con.execute("SELECT * FROM notes WHERE id=? AND archived=?", (nid, archived)).fetchone()
        if r:
            extra_rows.append(r)
    all_rows = list(rows) + extra_rows
    result = enrich_notes(all_rows, con)
    con.close()
    return result

@app.post("/api/boards/{board_id}/notes")
def create_note(board_id: int, n: NoteIn):
    con = get_db()
    ts = now()
    max_order = con.execute(
        "SELECT COALESCE(MIN(sort_order),1)-1 FROM notes WHERE board_id=? AND archived=0", (board_id,)
    ).fetchone()[0]
    cur = con.execute(
        "INSERT INTO notes (board_id, text, color, author, archived, sort_order, created_at, updated_at) VALUES (?,?,?,?,0,?,?,?)",
        (board_id, n.text, n.color, n.author, max_order, ts, ts)
    )
    note_id = cur.lastrowid
    for tid in n.tag_ids:
        con.execute("INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?,?)", (note_id, tid))
    for bid in n.extra_board_ids:
        if bid != board_id:
            con.execute("INSERT OR IGNORE INTO note_boards (note_id, board_id) VALUES (?,?)", (note_id, bid))
    con.execute("INSERT INTO note_history (note_id, text, author, changed_at) VALUES (?,?,?,?)",
                (note_id, n.text, n.author, ts))
    con.commit()
    rows = con.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchall()
    result = enrich_notes(rows, con)
    con.close()
    return result[0]

@app.patch("/api/notes/{note_id}")
def update_note(note_id: int, u: NoteUpdate):
    con = get_db()
    note = con.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
    if not note:
        raise HTTPException(404, "Notiz nicht gefunden")
    fields = {}
    if u.text is not None: fields["text"] = u.text
    if u.color is not None: fields["color"] = u.color
    if u.author is not None: fields["author"] = u.author
    if u.archived is not None: fields["archived"] = u.archived
    if fields:
        fields["updated_at"] = now()
        set_clause = ", ".join(f"{k}=?" for k in fields)
        con.execute(f"UPDATE notes SET {set_clause} WHERE id=?", (*fields.values(), note_id))
    if u.tag_ids is not None:
        con.execute("DELETE FROM note_tags WHERE note_id=?", (note_id,))
        for tid in u.tag_ids:
            con.execute("INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?,?)", (note_id, tid))
    if u.extra_board_ids is not None:
        primary_board = note["board_id"]
        con.execute("DELETE FROM note_boards WHERE note_id=?", (note_id,))
        for bid in u.extra_board_ids:
            if bid != primary_board:
                con.execute("INSERT OR IGNORE INTO note_boards (note_id, board_id) VALUES (?,?)", (note_id, bid))
    if u.text is not None:
        con.execute("INSERT INTO note_history (note_id, text, author, changed_at) VALUES (?,?,?,?)",
                    (note_id, u.text, u.editor or u.author, now()))
    con.commit()
    rows = con.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchall()
    result = enrich_notes(rows, con)
    con.close()
    return result[0]

@app.delete("/api/notes/{note_id}")
def delete_note(note_id: int):
    con = get_db()
    con.execute("DELETE FROM note_history WHERE note_id=?", (note_id,))
    con.execute("DELETE FROM note_tags WHERE note_id=?", (note_id,))
    con.execute("DELETE FROM note_boards WHERE note_id=?", (note_id,))
    con.execute("DELETE FROM notes WHERE id=?", (note_id,))
    con.commit()
    con.close()
    return {"ok": True}

@app.get("/api/notes/{note_id}/history")
def note_history(note_id: int):
    con = get_db()
    rows = con.execute(
        "SELECT * FROM note_history WHERE note_id=? ORDER BY changed_at DESC", (note_id,)
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]

@app.post("/api/boards/{board_id}/notes/reorder")
def reorder_notes(board_id: int, r: ReorderIn):
    con = get_db()
    for i, nid in enumerate(r.note_ids):
        con.execute("UPDATE notes SET sort_order=? WHERE id=? AND board_id=?", (i, nid, board_id))
    con.commit()
    con.close()
    return {"ok": True}

# ── Serve frontend ────────────────────────────────────────
app.mount("/static", StaticFiles(directory="/app/frontend"), name="static")

@app.get("/{full_path:path}")
def serve_frontend(full_path: str):
    return FileResponse("/app/frontend/index.html")
