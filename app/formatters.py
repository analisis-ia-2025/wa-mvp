# app/formatters.py
# Convierte la salida del LLM (JSON + explicación) a mensaje de WhatsApp.

import json
from typing import Tuple, Dict
from .templates import human_summary, bullet_section, doctor_questions_section
from .branding import DISCLAIMER

class ParseError(Exception):
    pass

def parse_llm_json_prefix(text: str) -> Tuple[Dict, str]:
    """
    Extrae el primer bloque JSON válido al inicio del texto y retorna (dict, resto).
    Espera el JSON *al principio* según el system prompt. Lanza ParseError si falla.
    """
    text = text.lstrip()
    if not text.startswith("{"):
        raise ParseError("La respuesta no inicia con JSON")

    brace = 0
    end = None
    for i, ch in enumerate(text):
        if ch == '{':
            brace += 1
        elif ch == '}':
            brace -= 1
            if brace == 0:
                end = i + 1
                break
    if end is None:
        raise ParseError("JSON incompleto")

    payload = json.loads(text[:end])
    return payload, text[end:].strip()

def format_whatsapp_message(llm_text: str) -> str:
    """Convierte la salida de la IA en un mensaje formateado para WhatsApp."""
    try:
        data, human_part = parse_llm_json_prefix(llm_text)
    except ParseError:
        # Fallback: mensaje plano + disclaimer
        return f"{llm_text}\n\n_{DISCLAIMER}_"

    summary = data.get("summary", "")
    findings = data.get("findings", [])
    risk = data.get("risk_level", "")
    recs = data.get("recommendations", [])
    questions = data.get("doctor_questions", [])
    follow = data.get("follow_up", {})

    parts = [human_summary(summary, risk)]

    if findings:
        mapped = [f"{f.get('item','')}: {f.get('status','')}" for f in findings]
        parts.append(bullet_section("Hallazgos", mapped))

    if recs:
        parts.append(bullet_section("Recomendaciones", recs))

    if follow:
        when = follow.get("when")
        what = follow.get("what")
        follow_lines = [l for l in [f"Cuándo: {when}" if when else None,
                                    f"Qué: {what}" if what else None] if l]
        parts.append(bullet_section("Próximos pasos", follow_lines))

    parts.append(doctor_questions_section(questions))

    # Agrega explicación humana adicional si existe (tras el JSON)
    if human_part:
        parts.append(human_part)

    parts.append(f"_{DISCLAIMER}_")
    return "\n".join([p for p in parts if p and p.strip()])
