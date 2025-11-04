# app/pdf_builder.py
# Construye Markdown desde el JSON estructurado del LLM
# y delega la renderización a tu app/pdf_utils.py -> save_markdown_as_pdf(...)

from typing import Dict, Optional
from datetime import datetime
from .branding import APP_NAME
from .pdf_utils import save_markdown_as_pdf  # usa TU implementación existente

def _md_escape(text: str) -> str:
    return (text or "").replace("#", "\\#").replace("*", "\\*").replace("_", "\\_")

def build_clinical_markdown(data: Dict, patient: Optional[Dict] = None, privacy_url: Optional[str] = None) -> str:
    """
    Crea un documento Markdown con secciones estándar:
    Resumen, Hallazgos, Recomendaciones, Preguntas, Próximos pasos, Datos del paciente.
    """
    lines = []

    # Título principal
    lines.append(f"# Informe Médico — {APP_NAME}")
    lines.append(f"*Generado:* {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if privacy_url:
        # Tu pdf_utils detecta automáticamente .../privacy... y lo añade abajo
        lines.append(f"(Privacidad: {privacy_url})")
    lines.append("---")

    # Resumen
    summary = _md_escape(data.get("summary", ""))
    if summary:
        lines.append("## Interpretación del examen")
        lines.append(summary)
        lines.append("")

    # Nivel de riesgo (se muestra como subtítulo/sección)
    risk = (data.get("risk_level") or "").strip()
    if risk:
        lines.append("## Conclusión")
        lines.append(f"Nivel de riesgo: **{risk.title()}**")
        lines.append("")

    # Hallazgos
    findings = data.get("findings") or []
    lines.append("## Hallazgos clave")
    if findings:
        for f in findings:
            item = _md_escape(f.get("item", ""))
            status = _md_escape(f.get("status", ""))
            lines.append(f"- {item}: {status}")
    else:
        lines.append("- (sin datos proporcionados)")
    lines.append("")

    # Recomendaciones (usa prefijo RECOMENDACIÓN: para que tu pdf_utils lo pinte con check)
    recs = data.get("recommendations") or []
    lines.append("## Recomendaciones")
    if recs:
        for r in recs:
            lines.append(f"RECOMENDACIÓN: { _md_escape(r) }")
    else:
        lines.append("- (sin datos proporcionados)")
    lines.append("")

    # Preguntas para el médico (sección especial)
    qs = data.get("doctor_questions") or []
    lines.append("## 3 preguntas clave para el médico")
    if qs:
        for q in qs[:3]:
            lines.append(f"- { _md_escape(q) }")
    else:
        lines.append("- (sin datos proporcionados)")
    lines.append("")

    # Próximos pasos
    follow = data.get("follow_up") or {}
    lines.append("## Plan de seguimiento")
    if follow.get("when") or follow.get("what"):
        if follow.get("when"):
            lines.append(f"- Cuándo: { _md_escape(follow['when']) }")
        if follow.get("what"):
            lines.append(f"- Qué: { _md_escape(follow['what']) }")
    else:
        lines.append("- (sin datos proporcionados)")
    lines.append("")

    # Datos del paciente (opcional)
    if patient:
        lines.append("## Datos del paciente")
        name = _md_escape(str(patient.get("name","N/D")))
        age  = _md_escape(str(patient.get("age","N/D")))
        pid  = _md_escape(str(patient.get("id","N/D")))
        lines.append(f"- Nombre: {name}")
        lines.append(f"- Edad: {age}")
        lines.append(f"- ID: {pid}")
        lines.append("")

    return "\n".join(lines).strip()

def build_clinical_pdf_from_structured(
    data: Dict,
    out_dir: str,
    filename: str = "Informe_DR_MAX.pdf",
    title: Optional[str] = None,
    patient: Optional[Dict] = None,
    privacy_url: Optional[str] = None
) -> str:
    """
    Construye el Markdown y lo convierte a PDF usando *tu* save_markdown_as_pdf.
    Retorna la ruta absoluta del PDF.
    """
    md = build_clinical_markdown(data, patient=patient, privacy_url=privacy_url)
    return save_markdown_as_pdf(
        markdown_text=md,
        out_dir=out_dir,
        filename=filename,
        title=title or "Informe Médico"
    )
