# app/llm.py
from .memory import get_ctx, set_ctx, get_patient, append_chat, get_chat_history
from .config import DISCLAIMER, PRIVACY_URL, USE_LLM
from .pdf_utils import save_markdown_as_pdf

try:
    from .llm_client import chat_doctor
except Exception:
    chat_doctor = None


def handle_message(wa_id: str, user_text: str) -> dict:
    """
    Orquesta la conversación con el LLM manteniendo el historial en la base.
    - Guarda el mensaje del usuario.
    - Llama a chat_doctor (OpenAI).
    - Guarda la respuesta del asistente.
    - Si el LLM propone markdown para PDF o manda el comando especial,
      deja marcas en el contexto para que el webhook lo use.
    """

    # 1) Guardar turno del usuario en el historial
    if user_text:
        append_chat(wa_id, "user", user_text)

    # 2) Si no hay LLM disponible, responder algo simple
    if not USE_LLM or chat_doctor is None:
        reply = (
            "Hola, soy un asistente automático para ayudarte a entender tus síntomas y resultados de exámenes. "
            "En este momento no tengo disponible el motor de IA para un análisis detallado, pero puedes comentar "
            "estos resultados con tu médico de confianza."
        )
        append_chat(wa_id, "assistant", reply)
        return {"type": "text", "text": reply}

    # 3) Obtener historial y llamar al LLM
    history = get_chat_history(wa_id)
    result = chat_doctor(history) or {}

    reply_text = (result.get("reply_text") or "").strip()
    pdf_md = result.get("pdf_markdown")
    wants_pdf = bool(result.get("wants_pdf"))

    # 4) Guardar turno del asistente
    if reply_text:
        append_chat(wa_id, "assistant", reply_text)

    # 5) Si el LLM envía markdown explícito para el PDF, lo guardamos
    if pdf_md:
        set_ctx(wa_id, "last_pdf_md", pdf_md)

    # 6) Si el LLM pidió generar PDF, devolvemos una acción especial
    if wants_pdf:
        return {
            "type": "action",
            "action": "generate_pdf",
            "text": reply_text or "",
        }

    # 7) Respuesta normal
    return {"type": "text", "text": reply_text or ""}


def render_assessment_markdown(wa_id: str) -> str:
    """
    Devuelve el markdown clínico propuesto por el LLM o,
    si no existe, genera un resumen del historial.
    Este texto está pensado como **resumen de orientación**, NO como informe médico oficial.
    """
    md = get_ctx(wa_id, "last_pdf_md")
    if md:
        return md

    # Fallback: generar un transcript con disclaimer
    chat = get_chat_history(wa_id)
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in chat)

    text = "# Resumen de orientación de salud\n\n"
    text += transcript
    text += "\n\n---\n"
    text += f"**Aviso:** {DISCLAIMER}\n"
    text += (
        "Este documento es un resumen automatizado de la conversación con el asistente DR MAX SALUD. "
        "No constituye un informe médico oficial, ni un certificado, ni reemplaza una consulta presencial "
        "con un profesional de salud."
    )
    if PRIVACY_URL:
        text += f"\n\nPolítica de Privacidad: {PRIVACY_URL}"
    return text
