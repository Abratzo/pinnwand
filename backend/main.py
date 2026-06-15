from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
import sqlite3, json, os
from datetime import datetime

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DB_PATH = os.environ.get("DB_PATH", "/data/pinnwand.db")

def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = get_db()
    con.executescript("""
        CREATE TABLE IF NOT EXISTS boards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
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
    """)
    # Migration: add sort_order if missing
    cols = [r[1] for r in con.execute("PRAGMA table_info(notes)").fetchall()]
    if 'sort_order' not in cols:
        con.execute("ALTER TABLE notes ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
        con.commit()

    # Create default board if none exists
    cur = con.execute("SELECT COUNT(*) FROM boards")
    if cur.fetchone()[0] == 0:
        con.execute("INSERT INTO boards (name, created_at) VALUES (?, ?)", ("Hauptboard", now()))
    con.commit()
    con.close()

def now():
    return datetime.now().isoformat(timespec='seconds')

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

class NoteUpdate(BaseModel):
    text: Optional[str] = None
    color: Optional[str] = None
    author: Optional[str] = None
    tag_ids: Optional[List[int]] = None
    archived: Optional[int] = None
    editor: Optional[str] = None

# ── Boards ───────────────────────────────────────────────
@app.get("/api/boards")
def list_boards():
    con = get_db()
    rows = con.execute("SELECT * FROM boards ORDER BY id").fetchall()
    con.close()
    return [dict(r) for r in rows]

@app.post("/api/boards")
def create_board(b: BoardIn):
    con = get_db()
    cur = con.execute("INSERT INTO boards (name, created_at) VALUES (?, ?)", (b.name, now()))
    con.commit()
    board_id = cur.lastrowid
    con.close()
    return {"id": board_id, "name": b.name}

@app.delete("/api/boards/{board_id}")
def delete_board(board_id: int):
    con = get_db()
    count = con.execute("SELECT COUNT(*) FROM boards").fetchone()[0]
    if count <= 1:
        raise HTTPException(400, "Letztes Board kann nicht gelöscht werden")
    note_ids = [r[0] for r in con.execute("SELECT id FROM notes WHERE board_id=?", (board_id,)).fetchall()]
    for nid in note_ids:
        con.execute("DELETE FROM note_history WHERE note_id=?", (nid,))
        con.execute("DELETE FROM note_tags WHERE note_id=?", (nid,))
    con.execute("DELETE FROM notes WHERE board_id=?", (board_id,))
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
def enrich_notes(rows, con):
    result = []
    for r in rows:
        note = dict(r)
        tag_rows = con.execute(
            "SELECT t.* FROM tags t JOIN note_tags nt ON t.id=nt.tag_id WHERE nt.note_id=?",
            (note["id"],)
        ).fetchall()
        note["tags"] = [dict(t) for t in tag_rows]
        result.append(note)
    return result

@app.get("/api/boards/{board_id}/notes")
def list_notes(board_id: int, archived: int = 0):
    con = get_db()
    rows = con.execute(
        "SELECT * FROM notes WHERE board_id=? AND archived=? ORDER BY sort_order ASC, created_at DESC",
        (board_id, archived)
    ).fetchall()
    result = enrich_notes(rows, con)
    con.close()
    return result

@app.post("/api/boards/{board_id}/notes")
def create_note(board_id: int, n: NoteIn):
    con = get_db()
    ts = now()
    max_order = con.execute("SELECT COALESCE(MIN(sort_order),1)-1 FROM notes WHERE board_id=? AND archived=0", (board_id,)).fetchone()[0]
    cur = con.execute(
        "INSERT INTO notes (board_id, text, color, author, archived, sort_order, created_at, updated_at) VALUES (?,?,?,?,0,?,?,?)",
        (board_id, n.text, n.color, n.author, max_order, ts, ts)
    )
    note_id = cur.lastrowid
    for tid in n.tag_ids:
        con.execute("INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?,?)", (note_id, tid))
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

    if u.text is not None:
        editor = u.editor or u.author
        con.execute("INSERT INTO note_history (note_id, text, author, changed_at) VALUES (?,?,?,?)",
                    (note_id, u.text, editor, now()))

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
    con.execute("DELETE FROM notes WHERE id=?", (note_id,))
    con.commit()
    con.close()
    return {"ok": True}

@app.get("/api/notes/{note_id}/history")
def note_history(note_id: int):
    con = get_db()
    rows = con.execute(
        "SELECT * FROM note_history WHERE note_id=? ORDER BY changed_at DESC",
        (note_id,)
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]

# ── Reorder ──────────────────────────────────────────────
class ReorderIn(BaseModel):
    note_ids: List[int]  # ordered list of note ids

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
