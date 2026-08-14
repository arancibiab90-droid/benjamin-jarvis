import os
import logging
import threading
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import httpx

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Flask Servidor Web para Render
app = Flask(__name__)

@app.route('/')
def home():
    return "Benjamin Jarvis (Agente CEO - Arancibia Global Group) está activo."

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# Prompt del Agente CEO Orquestador
SYSTEM_PROMPT = """
Eres Benjamin Jarvis, el Agente CEO y Orquestador Principal de Arancibia Global Group (Holding de Izan Benjamín Arancibia Martinez).
Tu rol es coordinar estratégicamente todas las empresas del holding, asignando y gestionando sub-agentes ingenieros especializados:

1. Agente Ingeniero Vórtice IVFA: Especialista en la planta de reciclaje/pirólisis en Paine, layouts, refinación, separador de Foucault y flujos masivos.
2. Agente Ingeniero Drones & Logística: Especialista en drones de carga pesada, enjambres y seguridad industrial.
3. Agente Ingeniero Apps & Software: Especialista en arquitectura digital, desarrollo ágil de startups y aplicaciones.
4. Agente Radar-Pyme: Especialista en caja rápida, cotizaciones de insumos (mercadería/empaques) y oportunidades de negocio.

Tu tono debe ser profesional, ejecutivo, ultra eficiente y enfocado en accionables técnicos, costos (CAPEX/OPEX), tiempos de operación y retornos de inversión.
"""

# Lógica IA con Contexto de CEO
async def responder_ia(prompt_usuario: str) -> str:
    gemini_key = os.environ.get("GEMINI_API_KEY")
    groq_key = os.environ.get("GROQ_API_KEY") or os.environ.get("GROK_API_KEY")

    prompt_completo = f"{SYSTEM_PROMPT}\n\nOrden del Fundador/CEO Izan:\n{prompt_usuario}"

    # 1. Intentar Gemini
    if gemini_key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            payload = {"contents": [{"parts": [{"text": prompt_completo}]}]}
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    return data['candidates'][0]['content']['parts'][0]['text']
        except Exception as e:
            logging.error(f"Error Gemini: {e}")

    # 2. Fallback a Groq
    if groq_key:
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt_usuario}
                ]
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(url, json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    return data['choices'][0]['message']['content']
        except Exception as e:
            logging.error(f"Error Groq: {e}")

    return "⚠️ Todos los proveedores de IA están saturados o sin API Key. Reintenta en unos segundos."

# Comandos y Handlers de Telegram
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    saludo = (
        "🧠 **Benjamin Jarvis - Agente CEO Orquestador**\n"
        "Arancibia Global Group listo para operar.\n\n"
        "Sub-agentes disponibles bajo mi mando:\n"
        "• ⚙️ `/vortice` - Ingeniero Vórtice IVFA\n"
        "• 🛸 `/drones` - Ingeniero Drones Heavy-Duty\n"
        "• 📱 `/apps` - Ingeniero Software & Startups\n"
        "• 📦 `/pyme` - Radar de Oportunidades & Caja Rápida\n\n"
        "¿Cuál es la primera instrucción estratégica?"
    )
    await update.message.reply_text(saludo, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_usuario = update.message.text
    respuesta = await responder_ia(texto_usuario)
    await update.message.reply_text(respuesta)

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()

    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        print("ERROR: No se encontró TELEGRAM_TOKEN")
    else:
        telegram_app = ApplicationBuilder().token(token).build()
        telegram_app.add_handler(CommandHandler("start", start))
        telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        print("Benjamin Jarvis (CEO) iniciado y escuchando en Telegram...")
        telegram_app.run_polling(drop_pending_updates=True)
