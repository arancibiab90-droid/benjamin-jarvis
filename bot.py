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
    return "Benjamin Jarvis está activo."

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# Lógica IA
async def responder_ia(prompt: str) -> str:
    gemini_key = os.environ.get("GEMINI_API_KEY")
    groq_key = os.environ.get("GROQ_API_KEY") or os.environ.get("GROK_API_KEY")

    # Intentar Gemini primero
    if gemini_key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    return data['candidates'][0]['content']['parts'][0]['text']
        except Exception as e:
            logging.error(f"Error Gemini: {e}")

    # Fallback a Groq
    if groq_key:
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}]
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(url, json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    return data['choices'][0]['message']['content']
        except Exception as e:
            logging.error(f"Error Groq: {e}")

    return "⚠️ Proveedores saturados o sin API Key configurada correctamente."

# Bot Telegram
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Hola! Soy Benjamin Jarvis. ¿En qué trabajamos hoy?")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_usuario = update.message.text
    respuesta = await responder_ia(texto_usuario)
    await update.message.reply_text(respuesta)

if __name__ == '__main__':
    # Arrancar Flask en segundo plano
    threading.Thread(target=run_flask, daemon=True).start()

    # Arrancar Bot de Telegram
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        print("ERROR: No se encontró TELEGRAM_TOKEN")
    else:
        telegram_app = ApplicationBuilder().token(token).build()
        telegram_app.add_handler(CommandHandler("start", start))
        telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        print("Benjamin Jarvis iniciado y escuchando en Telegram...")
        telegram_app.run_polling(drop_pending_updates=True)
