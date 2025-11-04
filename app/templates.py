# app/templates.py
# Helpers de texto para armar mensajes con secciones claras en WhatsApp.

from textwrap import dedent
from typing import List

def human_summary(summary: str, risk_level: str) -> str:
    emoji = {"bajo": "🟢", "moderado": "🟡", "alto": "🔴"}.get(risk_level, "ℹ️")
    return dedent(f"""
    {emoji} *Resumen rápido*
    {summary}
    """).strip()

def bullet_section(title: str, bullets: List[str]) -> str:
    if not bullets:
        return ""
    lines = "\n".join([f"• {b}" for b in bullets])
    return f"*{title}:*\n{lines}\n"

def doctor_questions_section(questions: List[str]) -> str:
    return bullet_section("Preguntas útiles para tu médico", questions)
