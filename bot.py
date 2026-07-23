import os
import logging
from threading import Thread
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Servidor Flask para Webhooks de la Esfera Flotante
app_web = Flask(__name__)

# Configurar Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    chat_session = model.start_chat(history=[])

PROMPT_SISTEMA = (
    "Eres Benjamin Jarvis, el asistente de IA avanzado, simbiótico y leal de Izan Benjamín Arancibia Martínez. "
    "Tienes razonamiento lógico impecable, capacidad para procesar código y ayudarlo con el desarrollo "
    "del proyecto Vórtice IVFA. Responde de forma directa, inteligente, clara y precisa."
)

@app_web.route('/')
def home():
    return "Benjamin Jarvis Core - Activo", 200

# Endpoint para la Esfera Flotante de tu teléfono
@app_web.route('/api/comando', methods=['POST'])
def recibir_comando_movil():
    try:
        datos = request.get_json()
        comando_texto = datos.get("comando", "")
        
        if not comando_texto:
            return jsonify({"respuesta": "No recibí ninguna instrucción."}), 400

        respuesta = chat_session.send_message(f"{PROMPT_SISTEMA}\n\nIzan dice por voz: {comando_texto}")
        return jsonify({"respuesta": respuesta.text}), 200
    except Exception as e:
        return jsonify({"respuesta": f"Error interno en Jarvis: {str(e)}"}), 500

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# Handlers para Telegram
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Sistemas de Benjamin Jarvis en línea, Izan. Servidor y API móvil conectados.")

async def responder_inteligente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_usuario = update.message.text
    if not GEMINI_API_KEY:
        await update.message.reply_text("Falta la GEMINI_API_KEY en Render.")
        return

    try:
        respuesta = chat_session.send_message(f"{PROMPT_SISTEMA}\n\nIzan dice: {texto_usuario}")
        await update.message.reply_text(respuesta.text)
    except Exception as e:
        logging.error(f"Error: {e}")
        await update.message.reply_text("Ocurrió un error al procesar tu solicitud.")

def main():
    # Iniciar servidor Flask en hilo separado
    Thread(target=run_flask, daemon=True).start()

    if TELEGRAM_TOKEN:
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), responder_inteligente))
        app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()




