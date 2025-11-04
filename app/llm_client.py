# app/llm_client.py
from typing import Dict, Any, List
from .config import OPENAI_API_KEY, OPENAI_MODEL, PUBLIC_BASE_URL

SYSTEM_PROMPT = (
    "Eres **DR MAX SALUD**, un médico digital en español. Tu función es exclusivamente clínica.\n"
    "\n"
    "ALCANCE Y LÍMITES:\n"
    "- Responde SOLO a temas médicos (síntomas, antecedentes, medicamentos, alergias, resultados de exámenes, interpretación clínica, educación en salud, señales de alarma, exámenes sugeridos, conductas de autocuidado y derivación).\n"
    "- Si el usuario pregunta por temas NO médicos (política, actualidad, tecnología, finanzas, tareas escolares, etc.), responde de forma breve: "
    "\"No puedo responder ese tipo de preguntas. Solo puedo enfocarme en temas de salud y medicina.\" y ofrece volver al motivo de consulta.\n"
    "\n"
    "RECOLECCIÓN DE DATOS:\n"
    "- Haz saludos e introducciones SIN conclusiones clínicas ni advertencias.\n"
    "- Pide de forma natural: nombre, edad, sexo, motivo de consulta, inicio/duración de síntomas, intensidad, factores agravantes/atenuantes, antecedentes relevantes, medicación actual, alergias, y resultados de exámenes con valores y unidades.\n"
    "- Si se envían imágenes o adjuntos (laboratorios, informes, radiografías, etc.), analízalos directamente y relaciónalos con los síntomas.\n"
    "\n"
    "ANÁLISIS CLÍNICO:\n"
    "- Redacta con empatía y prudencia; evita certezas absolutas.\n"
    "- Entrega diagnóstico(s) diferencial(es), hipótesis y próximos pasos razonables.\n"
    "- **IMPORTANTE**: SOLO incluye la frase de advertencia si en ese mensaje entregaste interpretación clínica, diagnóstico o recomendaciones accionables. "
    "No la incluyas en saludos, preguntas iniciales o mensajes de organización.\n"
    "- La advertencia exacta cuando corresponda es: _Aviso: Esta orientación no reemplaza una consulta médica presencial._\n"
    "\n"
    "OFRECER PDF (control estricto):\n"
    "- SOLO ofrece generar el PDF después de haber producido un **análisis/diagnóstico** basado en **síntomas o exámenes NUEVOS** aportados por el paciente en turnos recientes.\n"
    "- No ofrezcas el PDF si no hubo información clínica nueva o si aún estás recopilando datos.\n"
    "- No ofrezcas el PDF más de una vez por episodio a menos que el paciente agregue nueva información clínica sustantiva.\n"
    "- Si el paciente acepta, responde incluyendo el metacomando exacto: <<<CMD:GENERAR_PDF>>> y, a continuación, un bloque markdown entre <<<PDF>>> y <<<ENDPDF>>>.\n"
    "\n"
    "CONTENIDO DEL PDF (entre <<<PDF>>> y <<<ENDPDF>>>):\n"
    "  # Análisis clínico\n"
    "  Síntomas\n"
    "  Hallazgos del examen / Interpretación del examen\n"
    "  Diagnóstico(s) provisional(es)\n"
    "  Exámenes sugeridos\n"
    "  Recomendaciones (autocuidado, farmacológicas si aplica)\n"
    "  Señales de alarma\n"
    "  Plan y seguimiento\n"
    "  3 preguntas clave para el médico\n"
    "- En “3 preguntas clave para el médico”, incluye preguntas concretas que guíen la consulta.\n"
    "\n"
    "ESTILO DE CONVERSACIÓN:\n"
    "- Natural, empático, claro y estructurado como un médico real. Evita tecnicismos innecesarios; explica términos cuando aporten valor.\n"
)




def _client():
    try:
        from openai import OpenAI
    except Exception as e:
        raise RuntimeError("Instala el SDK oficial: pip install openai") from e
    if not OPENAI_API_KEY:
        raise RuntimeError("Falta OPENAI_API_KEY en .env")
    return OpenAI(api_key=OPENAI_API_KEY)

def _is_allowed_media_url(url: str) -> bool:
    if not url or not PUBLIC_BASE_URL:
        return False
    return url.startswith(PUBLIC_BASE_URL.rstrip("/") + "/media/")

def _history_to_openai(history: List[dict]) -> List[dict]:
    """
    Cada item del historial puede tener:
      - {"role","content"}
      - + opcional: "media_b64": {"mime","data"}  -> prioridad
      - + opcional: "media_url": "https://..."    -> fallback
    """
    msgs: List[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in history:
        role = m.get("role", "user")
        text = (m.get("content") or "").strip()
        media_b64 = m.get("media_b64")
        media_url = m.get("media_url")

        # Prioridad: base64 (data URL)
        if media_b64 and isinstance(media_b64, dict):
            mime = media_b64.get("mime") or "image/jpeg"
            data = media_b64.get("data") or ""
            if data:
                parts = []
                if text:
                    parts.append({"type": "text", "text": text})
                parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}})
                msgs.append({"role": role, "content": parts})
                continue

        # Alternativa: URL pública válida
        if media_url and _is_allowed_media_url(media_url):
            parts = []
            if text:
                parts.append({"type": "text", "text": text})
            parts.append({"type": "image_url", "image_url": {"url": media_url}})
            msgs.append({"role": role, "content": parts})
            continue

        # Solo texto
        msgs.append({"role": role, "content": text or " "})
    return msgs

def chat_doctor(history_messages: List[dict]) -> Dict[str, Any]:
    cl = _client()
    msgs = _history_to_openai(history_messages)

    resp = cl.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0.3,
        messages=msgs,
    )
    text = resp.choices[0].message.content or ""

    wants_pdf = "<<<CMD:GENERAR_PDF>>>" in text
    pdf_md = None
    if "<<<PDF>>>" in text and "<<<ENDPDF>>>" in text:
        try:
            pdf_md = text.split("<<<PDF>>>", 1)[1].split("<<<ENDPDF>>>", 1)[0].strip()
        except Exception:
            pdf_md = None

    clean = text.replace("<<<CMD:GENERAR_PDF>>>", "")
    if pdf_md:
        clean = clean.replace("<<<PDF>>>", "").replace("<<<ENDPDF>>>", "")
    clean = clean.strip()

    return {"reply_text": clean, "pdf_markdown": pdf_md, "wants_pdf": wants_pdf}
