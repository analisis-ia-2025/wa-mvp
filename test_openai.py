import os
from dotenv import load_dotenv
from openai import OpenAI

# Carga .env (en tu proyecto) para leer OPENAI_API_KEY
load_dotenv()

key = os.getenv("OPENAI_API_KEY")
print("KEY? ", "OK" if key else "NO")

client = OpenAI(api_key=key)
resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role":"user","content":"Di 'hola' y nada más."}],
    temperature=0
)
print("Respuesta:", resp.choices[0].message.content)
