"""
store.py: Persistencia simple en JSON para:
- sesiones por usuario (estado, slots, consentimiento)
- historial conversacional
- cache de idempotencia (message.id) con TTL
"""
import json
import os
import time
import threading
from typing import List, Dict, Any

SESS_FILE = os.path.join(os.path.dirname(__file__), "..", "sessions.json")
_LOCK = threading.Lock()

# Estructura en memoria:
# SESS = {
#   "wa_id": {
#       "state": "WELCOME|INTAKE|EXPECTING_EXAM|ANALYZING|FOLLOW_UP",
#       "consent": bool,
#       "slots": { "age": int|None, "sex": str|None,
#                  "symptoms": [str], "exam_date": str|None, "meds": [str] },
#       "history": [{"role": "user/assistant", "content": "texto"}, ...]
#   },
# }
SESS: Dict[str, Dict[str, Any]] = {}

# Ids de mensajes procesados para idempotencia (con TTL)
PROCESSED: Dict[str, float] = {}

def _load():
    """
    Carga SESS desde sessions.json si existe.
    """
    global SESS
    if os.path.exists(SESS_FILE):
        try:
            with open(SESS_FILE, "r", encoding="utf-8") as f:
                SESS = json.load(f)
        except Exception:
            SESS = {}
    else:
        SESS = {}

def _save():
    """
    Guarda SESS en sessions.json.
    """
    with _LOCK:
        with open(SESS_FILE, "w", encoding="utf-8") as f:
            json.dump(SESS, f, ensure_ascii=False)

def get(wa_id: str) -> Dict[str, Any]:
    """
    Retorna la sesión del usuario (crea una nueva si no existe).
    """
    s = SESS.get(wa_id)
    if not s:
        s = {
            "state": "WELCOME",
            "consent": False,
            "slots": {"age": None, "sex": None, "symptoms": [], "exam_date": None, "meds": []},
            "history": []
        }
        SESS[wa_id] = s
        _save()
    return s

def upsert(wa_id: str, **kwargs):
    """
    Actualiza campos arbitrarios de la sesión y persiste.
    """
    s = get(wa_id)
    s.update({k: v for k, v in kwargs.items() if v is not None})
    SESS[wa_id] = s
    _save()

def set_state(wa_id: str, new_state: str):
    """
    Cambia el estado de la sesión.
    """
    s = get(wa_id)
    s["state"] = new_state
    SESS[wa_id] = s
    _save()

def add_history(wa_id: str, role: str, content: str, maxlen: int = 20):
    """
    Agrega un mensaje al historial (últimos N).
    """
    s = get(wa_id)
    hist = s.get("history", [])
    hist.append({"role": role, "content": content[:2000]})
    s["history"] = hist[-maxlen:]
    SESS[wa_id] = s
    _save()

def get_history(wa_id: str) -> List[Dict[str, str]]:
    return get(wa_id).get("history", [])

def set_slot(wa_id: str, key: str, value):
    """
    Ajusta un slot (edad, sexo, etc.).
    """
    s = get(wa_id)
    slots = s.get("slots", {})
    slots[key] = value
    s["slots"] = slots
    SESS[wa_id] = s
    _save()

def get_slots(wa_id: str) -> Dict[str, Any]:
    return get(wa_id).get("slots", {})

# ---- Idempotencia simple
def was_processed(msg_id: str, ttl_seconds: int = 3600) -> bool:
    """
    Devuelve True si ya procesamos este message.id en la última hora.
    Limpia entradas viejas.
    """
    now = time.time()
    # limpia expirados
    expired = [k for k, v in PROCESSED.items() if now - v > ttl_seconds]
    for k in expired:
        PROCESSED.pop(k, None)
    return msg_id in PROCESSED

def mark_processed(msg_id: str):
    PROCESSED[msg_id] = time.time()

# Carga inicial
_load()
