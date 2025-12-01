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


def _looks_clinical_text(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    if any(k in t for k in SYMPTOM_KEYWORDS):
        return True
    if any(k in t for k in CLINICAL_KEYWORDS):
        return True
    return False


def _assistant_looks_like_analysis(reply: str) -> bool:
    if not reply:
        return False
    low = reply.lower()
    has_marker = any(m in low for m in ANALYSIS_MARKERS)
    looks_intake = any(p in low for p in INTAKE_PHRASES)
    long_enough = len(low) >= 220
    return has_marker and not looks_intake and long_enough


# -------------------------------------------------------------------
# Helpers de seguridad para uso sensible (D)
# -------------------------------------------------------------------
def _should_redirect_to_urgency(text: str) -> bool:
    if not text:
        return False
    t = text.lower()

    emergency_keywords = [
        "dolor en el pecho",
        "dolor torácico",
        "dolor toracico",
        "falta de aire",
        "no puedo respirar",
        "dificultad para respirar",
        "ahogo",
        "ahogándome",
        "ahogandome",
        "desmayo",
        "se desmayó",
        "se desmayo",
        "convulsión",
        "convulsion",
        "convulsiones",
        "parálisis",
        "paralisis",
        "cara chueca",
        "boca chueca",
        "no mueve un brazo",
        "no puede mover un brazo",
        "sangrado abundante",
        "mucho sangrado",
        "hemorragia",
        "dolor abdominal muy fuerte",
        "dolor abdominal intenso",
        "dolor muy fuerte",
        "peor dolor de mi vida",
    ]

    for kw in emergency_keywords:
        if kw in t:
            return True
    return False


def _looks_radiology_request(text: str) -> bool:
    if not text:
        return False
    t = text.lower()

    imaging_keywords = [
        "radiografía",
        "radiografia",
        "rayos x",
        "rx",
        "tac",
        "scanner",
        "escáner",
        "escaner",
        "tomografía",
        "tomografia",
        "resonancia",
        "rmn",
        "rm",
        "ecografía",
        "ecografia",
        "eco doppler",
    ]
    for kw in imaging_keywords:
        if kw in t:
            return True
    return False


def _looks_non_medical(text: str) -> bool:
    """
    Detecta preguntas claramente NO médicas (películas, series, música, finanzas, programación, etc.)
    para responder con un mensaje fijo sin llamar al LLM.
    """
    if not text:
        return False
    t = text.lower()

    non_medical_keywords = [
        # ocio / entretenimiento
        "pelicula", "película", "peliculas", "películas",
        "serie", "series", "netflix", "hbo", "disney", "prime video", "amazon prime",
        "anime", "manga", "videojuego", "videojuegos", "juego de pc", "juego de play", "juego de xbox",
        "musica", "música", "cancion", "canción", "canciones", "spotify", "podcast",
        "libro", "libros", "novela", "novelas",

        # plata / finanzas / trabajo
        "dinero", "plata", "credito", "crédito", "tarjeta de crédito", "tarjeta de credito",
        "hipoteca", "inversion", "inversión", "acciones", "criptomonedas",
        "trabajo", "empleo", "negocio",

        # tareas / estudios / programación
        "tarea", "tareas", "colegio", "prueba", "examen de matematicas",
        "matemáticas", "matematicas",
        "programar", "programación", "programacion", "código", "codigo",
        "python", "java", "javascript",
    ]

    return any(kw in t for kw in non_medical_keywords)


# ---------------------------------
# Config / imports internos
# ---------------------------------
from .config import (
    APP_NAME,
    META_WA_VERIFY_TOKEN,
    PUBLIC_BASE_URL,
    PDF_DIR,
    META_WA_ACCESS_TOKEN,
    META_WA_PHONE_NUMBER_ID,
    MEDIA_SAVE_TO_DISK,
    DATA_RETENTION_DAYS,
    BOT_NAME,
    PRIVACY_URL,
    DISCLAIMER,
    BUSINESS_NAME,
    BUSINESS_CONTACT_EMAIL,
    BUSINESS_CONTACT_PHONE,
    EMERGENCY_HINT,
)

from app.helpers.housekeeping import clean_old_files

from .memory import (
    append_chat_media,
    append_chat_media_b64,
    get_chat_history,
    clear_chat_history,
    sanitize_history_media_urls,
    set_ctx,
    get_ctx,
    start_encounter,
)

from .llm import handle_message, render_assessment_markdown
from .pdf_utils import save_markdown_as_pdf

# ---------------------------------
# App FastAPI
# ---------------------------------
app = FastAPI(title=APP_NAME or "DR MAX SALUD")

logger = logging.getLogger("webhook")
if not logger.handlers:
    handler = logging.StreamHandler()
    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(fmt)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

os.makedirs(PDF_DIR, exist_ok=True)
MEDIA_DIR = os.path.join(os.getcwd(), "media")
os.makedirs(MEDIA_DIR, exist_ok=True)

PHONE_NUMBER_ID = META_WA_PHONE_NUMBER_ID

# ---------------------------------
# Utils internos
# ---------------------------------
def _get_wa_headers() -> dict:
    return {
        "Authorization": f"Bearer {META_WA_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


async def send_text(to: str, text: str):
    if not PHONE_NUMBER_ID:
        logger.error("❌ PHONE_NUMBER_ID no está configurado. Revisa tu .env / config.")
        return

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text[:4096]},
    }
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, headers=_get_wa_headers(), json=payload)
        logger.info(f"📤 send_text -> {r.status_code} {r.text}")


async def send_document_link(to: str, file_url: str, filename: str):
    if not PHONE_NUMBER_ID:
        logger.error("❌ PHONE_NUMBER_ID no está configurado. No puedo enviar documentos.")
        return

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "document",
        "document": {
            "link": file_url,
            "filename": filename,
        },
    }
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, headers=_get_wa_headers(), json=payload)
        logger.info(f"📤 send_document_link -> {r.status_code} {r.text}")


def _extract_wa_message(body: dict) -> Tuple[Optional[dict], Optional[str]]:
    try:
        entry = (body.get("entry") or [{}])[0]
        change = (entry.get("changes") or [{}])[0]
        value = change.get("value") or {}
        messages = value.get("messages") or []
        if not messages:
            return None, None
        msg = messages[0]
        wa_from = msg.get("from")
        return msg, wa_from
    except Exception:
        return None, None


# ---------------------------------
# Manejo de media (Base64, disco, etc.)
# ---------------------------------
async def get_media_base64(msg: dict) -> Optional[Tuple[str, str]]:
    t = msg.get("type")
    if t not in ("image", "document"):
        return None

    if t == "image":
        media = msg.get("image", {})
    else:
        media = msg.get("document", {})

    media_id = media.get("id")
    mime = media.get("mime_type") or "application/octet-stream"

    if not media_id:
        return None

    url = f"https://graph.facebook.com/v19.0/{media_id}"
    params = {"phone_number_id": PHONE_NUMBER_ID}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, headers=_get_wa_headers(), params=params)
        r.raise_for_status()
        meta = r.json()
        media_url = meta.get("url")
        if not media_url:
            return None
        r2 = await client.get(media_url, headers=_get_wa_headers())
        r2.raise_for_status()
        b64 = base64.b64encode(r2.content).decode("ascii")
        return b64, mime


async def _fetch_media_b64_via_graph(msg: dict) -> Optional[Tuple[str, str, str]]:
    t = msg.get("type")
    if t not in ("image", "document"):
        return None

    if t == "image":
        media = msg.get("image", {})
        default_filename = f"image_{msg.get('id','noid')}.jpg"
    else:
        media = msg.get("document", {})
        default_filename = media.get("filename") or f"document_{msg.get('id','noid')}"

    media_id = media.get("id")
    mime = media.get("mime_type") or "application/octet-stream"

    if not media_id:
        return None

    url = f"https://graph.facebook.com/v19.0/{media_id}"
    params = {"phone_number_id": PHONE_NUMBER_ID}
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            r = await client.get(url, headers=_get_wa_headers(), params=params)
            r.raise_for_status()
            meta = r.json()
            media_url = meta.get("url")
            if not media_url:
                return None

            r2 = await client.get(media_url, headers=_get_wa_headers())
            r2.raise_for_status()
            b64 = base64.b64encode(r2.content).decode("ascii")
            return b64, mime, default_filename
        except Exception as e:
            logger.warning(f"⚠️ _fetch_media_b64_via_graph error: {e}")
            return None


async def _save_media_from_message(msg: dict) -> Optional[str]:
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

    if not media_id or not filename:
        return None

    url = f"https://graph.facebook.com/v19.0/{media_id}"
    params = {"phone_number_id": PHONE_NUMBER_ID}
    path = os.path.join(MEDIA_DIR, filename)

    async with httpx.AsyncClient(timeout=40) as client:
        try:
            r = await client.get(url, headers=_get_wa_headers(), params=params)
            r.raise_for_status()
            meta = r.json()
            media_url = meta.get("url")
            if not media_url:
                return None

            r2 = await client.get(media_url, headers=_get_wa_headers())
            r2.raise_for_status()
            with open(path, "wb") as f:
                f.write(r2.content)
            logger.info(f"💾 Media guardada en {path} ({mime})")
            return path
        except Exception as e:
            logger.warning(f"⚠️ _save_media_from_message error: {e}")
            return None


# ---------------------------------
# Rutas
# ---------------------------------
@app.get("/health")
async def health():
    return {"status": "ok", "app": APP_NAME or "DR MAX SALUD"}


@app.get("/webhook")
async def verify_webhook(req: Request):
    params = dict(req.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == META_WA_VERIFY_TOKEN:
        return PlainTextResponse(challenge or "")
    return PlainTextResponse("Forbidden", status_code=403)


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
        msg_type = msg.get("type")

        logger.info(f"📨 Mensaje de {wa_from} tipo {msg_type}")

        user_text: Optional[str] = None

        # ------------------ tipos básicos ------------------
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

            b64, mime = None, None
            try:
                maybe = await get_media_base64(msg)
                if isinstance(maybe, (list, tuple)) and len(maybe) >= 2:
                    b64, mime = maybe[0], maybe[1]
            except Exception as e:
                logger.warning(f"⚠️ get_media_base64 fallback: {e}")

            filename = None
            if not b64:
                fetched = await _fetch_media_b64_via_graph(msg)
                if fetched:
                    b64, mime, filename = fetched

            if b64 and mime and (mime.startswith("image/") or mime == "application/pdf"):
                append_chat_media_b64(wa_from, "user", mime, b64, caption or (filename or ""))
                user_text = caption.strip() or (f"Adjunté un {msg_type}.")
                await _save_media_from_message(msg)
            else:
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

        lower_text = user_text.strip().lower() if isinstance(user_text, str) else ""

        # ------------------------------------------------------------
        # Comando para borrar datos de conversación
        # ------------------------------------------------------------
        if lower_text in {
            "borrar", "borrar datos", "eliminar datos",
            "olvidar datos", "olvida mis datos",
        }:
            clear_chat_history(wa_from)
            for k in ("encounter_id", "new_clinical_input", "pdf_offer_done",
                      "exam_prompted", "consent_status"):
                set_ctx(wa_from, k, None)

            await send_text(
                wa_from,
                "✅ Tus datos de conversación en DR MAX SALUD han sido eliminados. "
                "Si deseas volver a usar el servicio, solo inicia una nueva conversación."
            )
            return JSONResponse({"status": "deleted"}, status_code=200)

        # ------------------------------------------------------------
        # Flujo de consentimiento explícito + identidad negocio
        # ------------------------------------------------------------
        consent_status = get_ctx(wa_from, "consent_status", None)
        if consent_status != "granted":
            if any(
                token in lower_text
                for token in ("si", "sí", "acepto", "autorizo", "de acuerdo", "ok, acepto")
            ):
                set_ctx(wa_from, "consent_status", "granted")
                lines = [
                    f"✅ Gracias. Desde ahora {BOT_NAME} puede analizar tus datos de salud de forma automatizada.",
                    "",
                    "La orientación que entrego es general y NO reemplaza una consulta médica presencial.",
                ]
                if BUSINESS_NAME:
                    lines.append(f"Este servicio es operado por: *{BUSINESS_NAME}*.")
                if BUSINESS_CONTACT_EMAIL or BUSINESS_CONTACT_PHONE:
                    parts = []
                    if BUSINESS_CONTACT_EMAIL:
                        parts.append(f"📧 {BUSINESS_CONTACT_EMAIL}")
                    if BUSINESS_CONTACT_PHONE:
                        parts.append(f"📞 {BUSINESS_CONTACT_PHONE}")
                    lines.append("Contacto: " + "  |  ".join(parts))
                await send_text(wa_from, "\n".join(lines))
                return JSONResponse({"status": "consent_granted"}, status_code=200)

            lines = [
                f"👋 Hola, soy {BOT_NAME}, un asistente automatizado para ayudarte a entender tus exámenes y dudas de salud.",
            ]
            if BUSINESS_NAME:
                lines.append(f"Servicio operado por: *{BUSINESS_NAME}*.")
            lines.extend(
                [
                    "",
                    "Antes de continuar necesito tu autorización para procesar *datos sensibles de salud*.",
                    "Usaré esta información solo para darte una orientación general basada en lo que me compartes.",
                ]
            )
            if PRIVACY_URL:
                lines.append(f"Puedes revisar nuestra Política de Privacidad aquí: {PRIVACY_URL}")
            if BUSINESS_CONTACT_EMAIL or BUSINESS_CONTACT_PHONE:
                parts = []
                if BUSINESS_CONTACT_EMAIL:
                    parts.append(f"📧 {BUSINESS_CONTACT_EMAIL}")
                if BUSINESS_CONTACT_PHONE:
                    parts.append(f"📞 {BUSINESS_CONTACT_PHONE}")
                lines.append("Contacto: " + "  |  ".join(parts))
            lines.extend(
                [
                    "",
                    "Si estás de acuerdo, responde *SI* o *ACEPTO* para continuar.",
                    "Si no deseas que procese tus datos, solo deja de usar el servicio.",
                ]
            )
            await send_text(wa_from, "\n".join(lines))
            set_ctx(wa_from, "consent_status", "pending")
            return JSONResponse({"status": "consent_required"}, status_code=200)

        # ------------------------------------------------------------
        # Acciones directas del usuario para PDF (comando explícito)
        # ------------------------------------------------------------
        pdf_commands = {
            "generar pdf",
            "preparar hoja",
            "preparar pdf",
            "crear pdf",
            "pdf medico",
            "pdf médico",
        }
        if isinstance(user_text, str) and lower_text in pdf_commands:
            response = {
                "type": "action",
                "action": "generate_pdf",
                "text": "Preparando tu PDF…",
            }
        else:
            # --------------------------------------------------------
            # Guardas de seguridad previas al LLM
            # --------------------------------------------------------
            if isinstance(user_text, str):
                # 0) Temas no médicos
                if _looks_non_medical(user_text):
                    await send_text(
                        wa_from,
                        "Solo puedo ayudarte con temas de salud y con la interpretación general de exámenes médicos. "
                        "No estoy diseñado para responder sobre ese tipo de temas."
                    )
                    return JSONResponse({"status": "non_medical"}, status_code=200)

                # 1) Síntomas de posible urgencia
                if _should_redirect_to_urgency(user_text):
                    await send_text(
                        wa_from,
                        "Por los síntomas que describes, lo más prudente es que seas evaluado/a de forma presencial "
                        "a la brevedad.\n\n"
                        f"{EMERGENCY_HINT}"
                    )
                    return JSONResponse({"status": "emergency_redirect"}, status_code=200)

                # 2) Peticiones claras de interpretación de imagen avanzada
                if _looks_radiology_request(user_text):
                    await send_text(
                        wa_from,
                        "No puedo interpretar formalmente radiografías, tomografías, resonancias u otras imágenes de "
                        "este tipo. Esa interpretación debe hacerla un médico radiólogo u otro profesional habilitado.\n\n"
                        "Sí puedo ayudarte a entender informes escritos o resultados numéricos de exámenes de laboratorio "
                        "(por ejemplo, hemograma, glicemia, colesterol, función renal, etc.)."
                    )
                    return JSONResponse({"status": "imaging_limited"}, status_code=200)

            if not get_ctx(wa_from, "encounter_id"):
                enc_id = start_encounter(wa_from)
                set_ctx(wa_from, "encounter_id", str(enc_id))

            if PUBLIC_BASE_URL:
                sanitize_history_media_urls(wa_from, PUBLIC_BASE_URL)

            new_clinical = False
            if msg_type in ("image", "video", "document"):
                new_clinical = True
            elif msg_type == "text" and _looks_clinical_text(user_text or ""):
                new_clinical = True
            set_ctx(wa_from, "new_clinical_input", "1" if new_clinical else "0")

            response = handle_message(wa_from, user_text)
            logger.info(f"🤖 handle_message -> {response}")

        # ------------------------------------------------------------
        # Acción: generar PDF
        # ------------------------------------------------------------
        if response.get("type") == "action" and response.get("action") == "generate_pdf":
            md = render_assessment_markdown(wa_from)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"ResumenSalud_{wa_from}_{ts}.pdf"
            path = save_markdown_as_pdf(
                markdown_text=md,
                out_dir=PDF_DIR,
                filename=filename,
                title="Resumen de orientación de salud - DR MAX SALUD",
            )
            basename = os.path.basename(path)

            if PUBLIC_BASE_URL:
                file_url = f"{PUBLIC_BASE_URL}/files/{basename}"
                await send_document_link(wa_from, file_url, basename)
            else:
                await send_text(
                    wa_from,
                    "He generado un PDF con tu resumen de salud, pero no tengo una URL pública configurada "
                    "para enviártelo como documento. Por favor contacta al administrador del sistema."
                )

            set_ctx(wa_from, "encounter_id", None)
            set_ctx(wa_from, "last_pdf_md", None)
            set_ctx(wa_from, "pdf_offer_done", "0")
            set_ctx(wa_from, "new_clinical_input", "0")

            await send_text(
                wa_from,
                "✅ *Resumen en PDF generado*. ¿Puedo ayudarte con algo más?"
            )
            return JSONResponse({"status": "pdf_generated"}, status_code=200)

        # ------------------------------------------------------------
        # Respuesta normal + ofertas proactivas (exámenes / PDF)
        # ------------------------------------------------------------
        reply_text = response.get("text", "").strip()
        await send_text(wa_from, reply_text or " ")

        had_new = get_ctx(wa_from, "new_clinical_input", "0") == "1"
        exam_prompted = get_ctx(wa_from, "exam_prompted", "0") == "1"
        pdf_offer_done = get_ctx(wa_from, "pdf_offer_done", "0") == "1"

        # Sugerir envío de exámenes
        if (
            msg_type == "text"
            and had_new
            and _looks_clinical_text(user_text or "")
            and not exam_prompted
        ):
            await send_text(
                wa_from,
                "Si tienes exámenes de laboratorio en PDF o en foto legible, puedes adjuntarlos y te ayudo a interpretarlos "
                "en forma general. Recuerda ocultar datos que no quieras compartir."
            )
            set_ctx(wa_from, "exam_prompted", "1")

        # Oferta de PDF (una sola vez por episodio)
        history = get_chat_history(wa_from) or []
        if had_new and not pdf_offer_done and len(history) >= 4:
            await send_text(
                wa_from,
                "Si lo deseas, luego de esta conversación puedo preparar un *PDF con el resumen de orientación* "
                "para que lo guardes o lo muestres a tu médico. Cuando quieras, escribe *\"generar pdf\"* o *\"preparar hoja\"*."
            )
            set_ctx(wa_from, "pdf_offer_done", "1")

        return JSONResponse({"status": "ok"}, status_code=200)

    except Exception as e:
        logger.exception(f"❌ Error en receive_webhook: {e}")
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=200)


# ---------------------------------
# Servir PDFs y Media
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
        result = clean_old_files(
            PDF_DIR,
            MEDIA_DIR if MEDIA_SAVE_TO_DISK else None,
            int(DATA_RETENTION_DAYS),
        )
        return {"ok": True, "result": result, "retention_days": int(DATA_RETENTION_DAYS)}
    except Exception as e:
        logger.exception(f"❌ Error en cleanup: {e}")
        return {"ok": False, "error": str(e)}
