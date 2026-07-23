import os
import logging
import threading
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai

# Configurar logs
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# --- Servidor Web Liviano para mantener a Render feliz ---
web_app = Flask(__name__)

@web_app.route('/')
def health_check():
    return "Benjamin Jarvis Backend Activo", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

# --- Configurar Gemini ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    chat_session = model.start_chat(history=[])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Sistemas de Benjamin Jarvis en línea, Izan. Estoy listo para procesar datos, gestionar Vórtice IVFA y conectar tus ideas.")

async def responder_inteligente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_usuario = update.message.text
    
    if not GEMINI_API_KEY:
        await update.message.reply_text("Error: Falta la variable GEMINI_API_KEY en Render.")
        return

    try:
        contexto_sistema = (
            "Eres Benjamin Jarvis, el asistente de IA avanzado, simbiótico y leal de Izan Benjamín Arancibia Martínez. "
            "Tienes razonamiento lógico impecable, capacidad para procesar código, ejecutar automatizaciones y "
            "ayudarlo en el desarrollo técnico e industrial del proyecto Vórtice IVFA. Responde de forma clara, directa y audaz."
        )
        
        respuesta = chat_session.send_message(f"{contexto_sistema}\n\nIzan dice: {texto_usuario}")
        await update.message.reply_text(respuesta.text)
        
    except Exception as e:
        logging.error(f"Error al procesar en Jarvis: {e}")
        await update.message.reply_text("Ocurrió un error interno al conectar con la red neuronal de Jarvis.")

def main():
    if not TELEGRAM_TOKEN:
        print("Error: No se encontró TELEGRAM_TOKEN.")
        return

    # Iniciar servidor web en un hilo secundario
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Iniciar Bot de Telegram
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), responder_inteligente))
    
    print("Benjamin Jarvis con IA y Web Server iniciado...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()



