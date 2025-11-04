# test_pdf.py
from app.pdf_utils import save_markdown_as_pdf

md = """# DR-IA
## Datos clave aportados por el usuario
- Edad: 37 años
- Sexo: Masculino
## Síntomas
- Dolor torácico leve, intermitente, desde hace 3 días.
## Exámenes y hallazgos relevantes
- Hemograma 2025-10-20: Hb 14.2 g/dL (ref 13-17)
## Preguntas concisas para el médico
- ¿Estos valores justifican estudio adicional?
- ¿Qué signos de alarma debo vigilar en casa?
"""

path = save_markdown_as_pdf(md, out_dir="./out", filename="prueba_DR-IA.pdf",
                            title="Hoja de Preparación para Cita Médica")
print("PDF generado en:", path)
