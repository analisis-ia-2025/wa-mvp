import os
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from .config import DB_PATH
import re
import json

engine = create_engine(f"sqlite:///{DB_PATH}", future=True)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS patients (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wa_id TEXT UNIQUE NOT NULL,
  name TEXT,
  age INTEGER,
  sex TEXT,
  height_cm REAL,
  weight_kg REAL,
  allergies TEXT,
  conditions TEXT,
  meds TEXT,
  last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS encounters (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wa_id TEXT NOT NULL,
  started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  closed_at DATETIME,
  summary TEXT,
  pdf_path TEXT
);

CREATE TABLE IF NOT EXISTS context_kv (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wa_id TEXT NOT NULL,
  k TEXT NOT NULL,
  v TEXT,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(wa_id, k)
);
"""

def init_db():
    # Ejecuta cada sentencia por separado (SQLite no permite múltiples statements en una sola llamada)
    stmts = [s.strip() for s in re.split(r";\s*(?:\r?\n)+", SCHEMA_SQL.strip()) if s.strip()]
    with engine.begin() as conn:
        for s in stmts:
            # Asegura que termine con ';' por si el split lo removió
            if not s.endswith(";"):
                s = s + ";"
            conn.exec_driver_sql(s)

def upsert_patient(wa_id: str, **fields):
    if not fields:
        return
    sets = ", ".join([f"{k}=:{k}" for k in fields.keys()])
    sql = f"""
    INSERT INTO patients (wa_id,{','.join(fields.keys())})
    VALUES (:wa_id,{','.join(':'+k for k in fields.keys())})
    ON CONFLICT(wa_id) DO UPDATE SET {sets}, last_updated=CURRENT_TIMESTAMP
    """
    with engine.begin() as conn:
        conn.execute(text(sql), {"wa_id": wa_id, **fields})

def get_patient(wa_id: str):
    with engine.begin() as conn:
        r = conn.execute(text("SELECT * FROM patients WHERE wa_id=:wa_id"), {"wa_id": wa_id}).mappings().first()
        return dict(r) if r else None

def set_ctx(wa_id: str, k: str, v: str | None):
    with engine.begin() as conn:
        try:
            conn.execute(text("""
                INSERT INTO context_kv (wa_id,k,v) VALUES (:wa_id,:k,:v)
                ON CONFLICT(wa_id,k) DO UPDATE SET v=:v, updated_at=CURRENT_TIMESTAMP
            """), {"wa_id": wa_id, "k": k, "v": v})
        except IntegrityError:
            pass

def get_ctx(wa_id: str, k: str, default=None):
    with engine.begin() as conn:
        r = conn.execute(text("SELECT v FROM context_kv WHERE wa_id=:wa_id AND k=:k"), {"wa_id": wa_id, "k": k}).scalar()
        return r if r is not None else default

def start_encounter(wa_id: str) -> int:
    with engine.begin() as conn:
        r = conn.execute(text("INSERT INTO encounters (wa_id) VALUES (:wa_id)"), {"wa_id": wa_id})
        return r.lastrowid

def close_encounter(enc_id: int, summary: str, pdf_path: str | None):
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE encounters
            SET closed_at=CURRENT_TIMESTAMP, summary=:summary, pdf_path=:pdf
            WHERE id=:id
        """), {"summary": summary, "pdf": pdf_path, "id": enc_id})


MAX_TURNS = 20  # conserva últimas 20 interacciones

def get_chat_history(wa_id: str) -> list[dict]:
    raw = get_ctx(wa_id, "chat_history", "[]")
    try:
        arr = json.loads(raw)
        if isinstance(arr, list):
            return arr[-MAX_TURNS:]
    except Exception:
        pass
    return []

def append_chat(wa_id: str, role: str, content: str):
    arr = get_chat_history(wa_id)
    arr.append({"role": role, "content": content})
    # recorta
    arr = arr[-MAX_TURNS:]
    set_ctx(wa_id, "chat_history", json.dumps(arr, ensure_ascii=False))

def append_chat_media(wa_id: str, role: str, media_url: str, caption: str | None = None):
    """
    Agrega un turno al historial incluyendo una imagen/archivo (media_url público)
    y un caption opcional como 'content'.
    """
    arr = get_chat_history(wa_id)
    arr.append({
        "role": role,
        "content": (caption or "").strip(),
        "media_url": media_url
    })
    arr = arr[-MAX_TURNS:]
    set_ctx(wa_id, "chat_history", json.dumps(arr, ensure_ascii=False))

def clear_chat_history(wa_id: str):
    set_ctx(wa_id, "chat_history", "[]")
    set_ctx(wa_id, "last_pdf_md", None)
    set_ctx(wa_id, "recent_msg_ids", "[]")

def sanitize_history_media_urls(wa_id: str, allowed_base: str):
    arr = get_chat_history(wa_id)
    changed = False
    for m in arr:
        u = m.get("media_url")
        if u and allowed_base and not u.startswith(allowed_base.rstrip("/") + "/media/"):
            # descartamos media inválida para que no rompa llamadas futuras
            m.pop("media_url", None)
            changed = True
    if changed:
        set_ctx(wa_id, "chat_history", json.dumps(arr, ensure_ascii=False))
def append_chat_media_b64(wa_id: str, role: str, mime: str, b64data: str, caption: str | None = None):
    """
    Agrega un turno con media en base64 (data URL).
    Se almacena como {"media_b64": {"mime": "...", "data": "..."}}
    """
    arr = get_chat_history(wa_id)
    arr.append({
        "role": role,
        "content": (caption or "").strip(),
        "media_b64": {"mime": mime, "data": b64data}
    })
    arr = arr[-MAX_TURNS:]
    set_ctx(wa_id, "chat_history", json.dumps(arr, ensure_ascii=False))
