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
    El LLM lleva toda la conversación como un médico real.
    Este handler solo mantiene el contexto y detecta comandos especiales
    (por ejemplo <<<CMD:GENERAR_PDF>>>).
    """
    # Guardar turno del usuario en el historial
    append_chat(wa_id, "user", user_text)

    # Recuperar historial
    history = get_chat_history(wa_id)

    # Si no hay modelo configurado, respondemos fallback
    if not (USE_LLM and chat_doctor):
        disclaimer = f"\n\n_{DISCLAIMER}_"
        if PRIVACY_URL:
            disclaimer += f"\nPolítica: {PRIVACY_URL}"
        return {
            "type": "text",
            "text": (
                "Actualmente no tengo acceso al razonamiento clínico. "
                "Cuéntame tus síntomas y antecedentes; te orientaré según las reglas locales."
                + disclaimer
            ),
        }

    # Llamar al LLM con el historial de conversación
    res = chat_doctor(history)

    reply_text = res.get("reply_text") or "¿Podrías repetirlo, por favor?"
    wants_pdf = bool(res.get("wants_pdf"))
    pdf_md = res.get("pdf_markdown")

    # Guardar turno del asistente y posible markdown del informe
    append_chat(wa_id, "assistant", reply_text)
    if pdf_md:
        set_ctx(wa_id, "last_pdf_md", pdf_md)

    # Si el LLM pidió generar PDF
    if wants_pdf:
        return {"type": "action", "action": "generate_pdf"}

    # Respuesta normal al usuario
    return {"type": "text", "text": reply_text}


def render_assessment_markdown(wa_id: str) -> str:
    """
    Devuelve el markdown clínico propuesto por el LLM o,
    si no existe, genera un resumen del historial.
    """
    md = get_ctx(wa_id, "last_pdf_md")
    if md:
        return md

    # Fallback: generar un transcript con disclaimer
    chat = get_chat_history(wa_id)
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in chat)
    text = f"# Cita Médica\n\n{transcript}\n\n---\n**Aviso:** {DISCLAIMER}"
    if PRIVACY_URL:
        text += f"\n\nPolítica de Privacidad: {PRIVACY_URL}"
    return text
