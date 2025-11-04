# app/webhook.py
import os
import re
import json
import base64
import mimetypes
import logging
from datetime import datetime
from typing import Optional, Tuple

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, FileResponse

# ---------------------------------
# Heurísticas clínicas
# ---------------------------------
CLINICAL_KEYWORDS = (
    "síntoma", "sintoma", "dolor", "fiebre", "tos", "mareo", "náusea", "nausea", "diarrea",
    "examen", "hemograma", "glucosa", "colesterol", "triglicéridos", "pcr", "radiografía",
    "rx", "tomografía", "ecografía", "saturación", "presión", "presion", "oxígeno", "oxigeno",
    "mg/dl", "mmol/l", "g/dl", "u/l", "mm Hg"
)

SYMPTOM_KEYWORDS = (
    "síntoma", "sintoma", "dolor", "fiebre", "tos", "mareo", "náusea", "nausea",
    "diarrea", "vómito", "vomito", "disnea", "fatiga", "cansancio", "sangrado",
    "erupción", "erupcion", "cefalea", "dolor de cabeza", "congestión", "congestion",
    "secreción", "secrecion", "ardor", "hinchazón", "hinchazon", "inflamación", "inflamacion"
)

INTAKE_PHRASES = (
    "envíame", "enviame", "indícame", "indicame",
    "compárteme", "comparteme", "dime tus", "cuéntame", "cuentame",
    "por favor", "valores y unidades", "edad, sexo", "antecedente", "medicación", "medicacion"
)

ANALYSIS_MARKERS = (
    "diagnóstico", "diagnostico", "interpretación", "interpretacion",
    "recomendaciones", "plan de seguimiento", "señales de alarma", "senales de alarma",
    "# análisis", "# analisis", "hallazgos", "exámenes sugeridos", "examenes sugeridos",
    "conclusión", "conclusion"
)

NUM_UNIT_RE = re.compile(
    r"\b\d+([.,]\d+)?\s?(mg/dl|mmol/l|g/dl|u/l|mm\s?hg|%|x10\^9/l|x10\^3/u?l|k/u?l|mmol|μ?mol/l)\b",
    re.IGNORECASE
)

def _looks_clinical_text(text: str) -> bool:
    """True si el texto del usuario parece aportar información clínica nueva."""
    if not text:
        return False
    t = text.lower()
    if NUM_UNIT_RE.search(t):
        return True
    if any(k in t for k in SYMPTOM_KEYWORDS):
        return True
    if any(k in t for k in CLINICAL_KEYWORDS):
        return True
    return False

def _assistant_looks_like_analysis(reply: str) -> bool:
    """True si la respuesta parece contener análisis (no solo intake)."""
    if not reply:
        return False
    low = reply.lower()
    has_marker = any(m in low for m in ANALYSIS_MARKERS)
    looks_intake = any(p in low for p in INTAKE_PHRASES)
    long_enough = len(low) >= 220
    return has_marker and not looks_intake and long_enough

# ---------------------------------
# Config / Imports internos
# ---------------------------------
from .config import (
    APP_NAME,
    META_WA_VERIFY_TOKEN,
    PUBLIC_BASE_URL,
    PDF_DIR,
    META_WA_ACCESS_TOKEN,
    MEDIA_SAVE_TO_DISK,
    DATA_RETENTION_DAYS,
)

from app.helpers.housekeeping import clean_old_files

from .memory import (
    init_db,
    get_ctx,
    set_ctx,
    start_encounter,
    close_encounter,
    append_chat_media,
    append_chat_media_b64,
    sanitize_history_media_urls,
    clear_chat_history,
    get_chat_history,
)

from .llm import handle_message, render_assessment_markdown
from .pdf_utils import save_markdown_as_pdf
from .wa_api import send_text, send_document_link
from app.helpers.media_bytes import get_media_base64  # puede soportar imágenes; agregamos fallback interno

# ---------------------------------
# App / setup
# ---------------------------------
app = FastAPI(title=APP_NAME or "DR MAX SALUD")
logger = logging.getLogger("webhook")
logging.basicConfig(level=logging.INFO)

os.makedirs(PDF_DIR, exist_ok=True)
BASE_OUT = os.path.dirname(PDF_DIR) if PDF_DIR else os.path.join(os.getcwd(), "out")
MEDIA_DIR = os.path.join(BASE_OUT, "media")
os.makedirs(MEDIA_DIR, exist_ok=True)
MAX_RECENT_IDS = 50

# ---------------------------------
# Utilidades internas (WA media)
# ---------------------------------
async def _wa_fetch_media_url(media_id: str) -> Optional[str]:
    url = f"https://graph.facebook.com/v19.0/{media_id}"
    headers = {"Authorization": f"Bearer {META_WA_ACCESS_TOKEN}"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, headers=headers)
        if r.status_code != 200:
            logger.error(f"❌ WA media meta GET {media_id} -> {r.status_code} {r.text}")
            return None
        data = r.json()
        return data.get("url")

async def _wa_download(url: str) -> Optional[bytes]:
    headers = {"Authorization": f"Bearer {META_WA_ACCESS_TOKEN}"}
    async with httpx.AsyncClient(timeout=None) as client:
        r = await client.get(url, headers=headers)
        if r.status_code != 200:
            logger.error(f"❌ WA media download -> {r.status_code} {r.text}")
            return None
        return r.content

def _sanitize_filename(name: str, default: str = "file") -> str:
    name = (name or default).strip()
    name = re.sub(r"[^\w\.-]+", "_", name, flags=re.UNICODE)
    name = re.sub(r"_+", "_", name)
    return name[:150] or default

def _remember_msg_id(wa_id: str, msg_id: str) -> None:
    key = "recent_msg_ids"
    raw = get_ctx(wa_id, key, "[]")
    try:
        arr = json.loads(raw)
        if not isinstance(arr, list):
            arr = []
    except Exception:
        arr = []
    arr = arr[-MAX_RECENT_IDS:]
    if msg_id not in arr:
        arr.append(msg_id)
    set_ctx(wa_id, key, json.dumps(arr))

def _is_duplicate(wa_id: str, msg_id: str) -> bool:
    raw = get_ctx(wa_id, "recent_msg_ids", "[]")
    try:
        arr = json.loads(raw)
        if isinstance(arr, list) and msg_id in arr:
            return True
    except Exception:
        pass
    return False

async def _save_media_from_message(msg: dict) -> Optional[str]:
    """
    Fallback a disco. Solo se usa si MEDIA_SAVE_TO_DISK=true.
    Guarda en MEDIA_DIR y retorna la ruta.
    """
    if not MEDIA_SAVE_TO_DISK:
        return None

    t = msg.get("type")
    media_id = None
    filename = None
    mime = None

    if t == "image":
        media = msg.get("image", {})
        media_id = media.get("id")
        mime = media.get("mime_type") or "image/jpeg"
        filename = f"image_{msg.get('id','noid')}.jpg"
    elif t == "document":
        media = msg.get("document", {})
        media_id = media.get("id")
        mime = media.get("mime_type") or "application/octet-stream"
        filename = media.get("filename") or f"document_{msg.get('id','noid')}"
    elif t == "audio":
        media = msg.get("audio", {})
        media_id = media.get("id")
        mime = media.get("mime_type") or "audio/ogg"
        filename = f"audio_{msg.get('id','noid')}.ogg"
    elif t == "video":
        media = msg.get("video", {})
        media_id = media.get("id")
        mime = media.get("mime_type") or "video/mp4"
        filename = f"video_{msg.get('id','noid')}.mp4"
    else:
        return None

    if not media_id:
        logger.warning("⚠️ Mensaje media sin media_id (fallback)")
        return None

    url = await _wa_fetch_media_url(media_id)
    if not url:
        return None

    content = await _wa_download(url)
    if content is None:
        return None

    if "." not in (filename or "") and "/" in (mime or ""):
        ext = mime.split("/")[-1]
        filename = f"{filename}.{ext}"

    dest = os.path.join(MEDIA_DIR, _sanitize_filename(filename))
    with open(dest, "wb") as f:
        f.write(content)

    logger.info(f"📥 Media guardada: {dest}")
    return dest

async def _fetch_media_b64_via_graph(msg: dict) -> Optional[Tuple[str, str, str]]:
    """
    Descarga el binario directo desde Graph y retorna (base64, mime, filename).
    Soporta imagen y PDF (document).
    """
    t = msg.get("type")
    if t not in ("image", "document"):
        return None

    node = msg.get(t, {}) or {}
    media_id = node.get("id")
    mime = node.get("mime_type") or ("image/jpeg" if t == "image" else "application/octet-stream")
    filename = node.get("filename") or (f"{t}_{msg.get('id','noid')}")

    if not media_id:
        return None

    url = await _wa_fetch_media_url(media_id)
    if not url:
        return None

    content = await _wa_download(url)
    if content is None:
        return None

    # Limitamos a tipos analizable por LLM: imágenes + PDF
    if not (mime.startswith("image/") or mime == "application/pdf"):
        return None

    b64 = base64.b64encode(content).decode("utf-8")

    # Asegurar extensión
    if "." not in filename:
        if mime.startswith("image/"):
            filename = f"{filename}.{mime.split('/')[-1]}"
        elif mime == "application/pdf":
            filename = f"{filename}.pdf"

    return (b64, mime, filename)

# ---------------------------------
# Lifecycle
# ---------------------------------
@app.on_event("startup")
def _startup():
    init_db()
    try:
        clean_old_files(PDF_DIR, MEDIA_DIR if MEDIA_SAVE_TO_DISK else None, int(DATA_RETENTION_DAYS))
    except Exception as e:
        logger.warning(f"⚠️ Housekeeping al iniciar falló: {e}")
    logger.info("✅ Webhook iniciado y DB lista")

# ---------------------------------
# Health
# ---------------------------------
@app.get("/health")
async def health():
    return {"ok": True}

# ---------------------------------
# WhatsApp Webhook Verification (GET)
# ---------------------------------
@app.get("/webhook")
async def verify_webhook(request: Request):
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == META_WA_VERIFY_TOKEN:
        logger.info("🔐 Webhook verificado con Meta")
        return PlainTextResponse(challenge or "", status_code=200)

    logger.warning("❌ Verificación de webhook fallida")
    return PlainTextResponse("Forbidden", status_code=403)

# ---------------------------------
# WhatsApp Webhook (POST)
# ---------------------------------
@app.post("/webhook")
async def receive_webhook(req: Request):
    body = await req.json()
    logger.info(f"📩 RAW PAYLOAD: {body}")

    try:
        entry = (body.get("entry") or [{}])[0]
        change = (entry.get("changes") or [{}])[0]
        value = change.get("value") or {}
        messages = value.get("messages") or []
        statuses = value.get("statuses") or []

        if statuses:
            logger.info(f"ℹ️ Status update(s): {statuses}")

        if not messages:
            return JSONResponse({"status": "no_messages"}, status_code=200)

        msg = messages[0]
        wa_from = msg.get("from")
        wa_msg_id = msg.get("id") or msg.get("wamid")
        msg_type = msg.get("type")

        # Anti-duplicados
        if wa_msg_id and _is_duplicate(wa_from, wa_msg_id):
            logger.info(f"🔁 Duplicado ignorado: {wa_msg_id}")
            return JSONResponse({"status": "duplicate_ignored"}, status_code=200)
        if wa_msg_id:
            _remember_msg_id(wa_from, wa_msg_id)

        # Normalizar texto / media
        user_text = None

        if msg_type == "text":
            user_text = msg["text"]["body"]

        elif msg_type == "interactive":
            it = msg.get("interactive", {})
            user_text = (
                (it.get("button_reply") or {}).get("title")
                or (it.get("list_reply") or {}).get("title")
                or "OK"
            )

        elif msg_type in ("image", "document", "audio", "video"):
            caption = (msg.get(msg_type, {}) or {}).get("caption") or ""

            # 1) Intento con tu helper (suele manejar imágenes)
            b64, mime = None, None
            try:
                maybe = await get_media_base64(msg)  # puede devolver (b64, mime)
                if isinstance(maybe, (list, tuple)) and len(maybe) >= 2:
                    b64, mime = maybe[0], maybe[1]
            except Exception as e:
                logger.warning(f"⚠️ get_media_base64 fallback: {e}")

            # 2) Si no sirvió o no era imagen, intentamos vía Graph directo (soporta PDF)
            filename = None
            if not b64:
                fetched = await _fetch_media_b64_via_graph(msg)
                if fetched:
                    b64, mime, filename = fetched

            if b64 and mime and (mime.startswith("image/") or mime == "application/pdf"):
                # Guardamos como media en la memoria de chat (base64) para que LLM lo procese
                append_chat_media_b64(wa_from, "user", mime, b64, caption or (filename or ""))
                user_text = caption.strip() or (f"Adjunté un {msg_type}.")
                # (opcional) además guardamos a disco si la flag está activa
                await _save_media_from_message(msg)
            else:
                # Fallback final: guardar a disco (si flag), y si hay PUBLIC_BASE_URL, anexar URL
                p = await _save_media_from_message(msg)
                if p and PUBLIC_BASE_URL:
                    base = os.path.basename(p)
                    media_url = f"{PUBLIC_BASE_URL}/media/{base}"
                    append_chat_media(wa_from, "user", media_url, caption)
                    user_text = caption.strip() or f"Adjunté un {msg_type}."
                elif p:
                    user_text = (
                        f"Adjunté un {msg_type} (no público). Ruta local: {p}. "
                        "Si lo necesitas, te transcribo valores por texto."
                    )
                else:
                    user_text = (
                        f"Recibí tu {msg_type}, pero no pude procesarlo. "
                        "Por favor envía los *valores y unidades* principales como texto, "
                        "o reintenta adjuntando la imagen o PDF."
                    )
        else:
            user_text = "No pude interpretar este mensaje. Envíame texto, por favor."

        # Acciones directas del usuario para PDF
        if isinstance(user_text, str) and user_text.strip().lower() in {
            "generar pdf", "preparar hoja", "preparar pdf", "crear pdf"
        }:
            response = {"type": "action", "action": "generate_pdf", "text": "Preparando tu PDF…"}
        else:
            # Encounter
            if not get_ctx(wa_from, "encounter_id"):
                enc_id = start_encounter(wa_from)
                set_ctx(wa_from, "encounter_id", str(enc_id))

            # Sanitizar URLs antiguas
            if PUBLIC_BASE_URL:
                sanitize_history_media_urls(wa_from, PUBLIC_BASE_URL)

            # Marcar si hubo input clínico nuevo en este turno
            new_clinical = False
            if msg_type in ("image", "video", "document"):
                new_clinical = True
            elif msg_type == "text" and _looks_clinical_text(user_text or ""):
                new_clinical = True
            set_ctx(wa_from, "new_clinical_input", "1" if new_clinical else "0")

            # Conversación con el LLM
            response = handle_message(wa_from, user_text)
            logger.info(f"🤖 handle_message -> {response}")

        # Acción: generar PDF
        if response.get("type") == "action" and response.get("action") == "generate_pdf":
            md = render_assessment_markdown(wa_from)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"CitaMedica_{wa_from}_{ts}.pdf"
            path = save_markdown_as_pdf(
                markdown_text=md,
                out_dir=PDF_DIR,
                filename=filename,
                title="Cita Médica - DR MAX SALUD",
            )
            basename = os.path.basename(path)

            if PUBLIC_BASE_URL:
                file_url = f"{PUBLIC_BASE_URL}/files/{basename}"
                await send_document_link(wa_from, file_url, basename)
            else:
                await send_text(
                    wa_from,
                    "PDF generado. Configura PUBLIC_BASE_URL para recibirlo por WhatsApp. "
                    f"También puedes descargarlo desde /files/{basename}",
                )

            enc_id = int(get_ctx(wa_from, "encounter_id"))
            close_encounter(enc_id, md, path)
            set_ctx(wa_from, "encounter_id", None)
            set_ctx(wa_from, "last_pdf_md", None)
            set_ctx(wa_from, "pdf_offer_done", "0")
            set_ctx(wa_from, "new_clinical_input", "0")

            await send_text(wa_from, "✅ *Cita Médica (PDF) generada*. ¿Puedo ayudarte con algo más?")
            return JSONResponse({"status": "pdf_generated"}, status_code=200)

        # Respuesta normal
        reply_text = response.get("text", "").strip()
        await send_text(wa_from, reply_text or " ")

        # --- Pregunta proactiva por exámenes si detectamos síntomas en texto ---
        # Preguntamos una sola vez por episodio (flag exam_prompted = "1")
        had_new = get_ctx(wa_from, "new_clinical_input", "0") == "1"
        already_prompted = get_ctx(wa_from, "exam_prompted", "0") == "1"
        if msg_type == "text" and _looks_clinical_text(user_text or "") and not already_prompted:
            await send_text(
                wa_from,
                "📎 ¿Tienes *exámenes médicos* (foto o PDF) relacionados que quieras que analice? "
                "Si los envías, puedo complementar la interpretación y darte una mejor guía."
            )
            set_ctx(wa_from, "exam_prompted", "1")

        # Ofrecer PDF solo si: hubo input clínico, respuesta parece análisis y no se ofreció antes
        low = (reply_text or "").lower()
        already_offered = get_ctx(wa_from, "pdf_offer_done", "0") == "1"
        if (had_new
            and "no reemplaza una consulta médica presencial" in low
            and _assistant_looks_like_analysis(reply_text or "")
            and not already_offered):
            await send_text(
                wa_from,
                "🧾 ¿Deseas que *genere tu hoja de cita en PDF* con síntomas, hallazgos y recomendaciones? "
                "Responde: *generar pdf* o *preparar hoja*."
            )
            set_ctx(wa_from, "pdf_offer_done", "1")

        return JSONResponse({"status": "ok"}, status_code=200)

    except Exception as e:
        logger.exception(f"❌ Error en webhook: {e}")
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=200)

# ---------------------------------
# Servir PDFs y Media (solo si guardas a disco)
# ---------------------------------
@app.get("/files/{filename}")
async def serve_file(filename: str):
    path = os.path.join(PDF_DIR, filename)
    if not os.path.isfile(path):
        return PlainTextResponse("Not Found", status_code=404)
    mime, _ = mimetypes.guess_type(path)
    return FileResponse(path, media_type=mime or "application/pdf", filename=filename)

@app.get("/media/{filename}")
async def serve_media(filename: str):
    path = os.path.join(MEDIA_DIR, filename)
    if not os.path.isfile(path):
        return PlainTextResponse("Not Found", status_code=404)
    mime, _ = mimetypes.guess_type(path)
    return FileResponse(path, media_type=mime or "application/octet-stream", filename=filename)

@app.get("/media/list")
async def list_media():
    try:
        files = sorted(os.listdir(MEDIA_DIR))
        return {"dir": MEDIA_DIR, "files": files}
    except Exception as e:
        return {"error": str(e)}

@app.post("/debug/reset/{wa_id}")
async def debug_reset(wa_id: str):
    clear_chat_history(wa_id)
    return {"ok": True, "reset": wa_id}

@app.post("/debug/cleanup")
async def debug_cleanup():
    try:
        result = clean_old_files(PDF_DIR, MEDIA_DIR if MEDIA_SAVE_TO_DISK else None, int(DATA_RETENTION_DAYS))
        return {"ok": True, "result": result, "retention_days": int(DATA_RETENTION_DAYS)}
    except Exception as e:
        logger.exception(f"❌ Error en cleanup: {e}")
        return {"ok": False, "error": str(e)}
