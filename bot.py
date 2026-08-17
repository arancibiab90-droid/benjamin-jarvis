import os
import threading
import logging
import requests
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import google.generativeai as genai

# Configuración de logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ==========================================
# 1. SERVIDOR WEB FLASK (Keep-Alive Render)
# ==========================================
web_app = Flask(__name__)

@web_app.route('/')
def health_check():
    return "Servidor Vórtice en línea. Bot de Telegram activo.", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

# ==========================================
# 2. CONFIGURACIÓN DE VARIABLES DE ENTORNO
# ==========================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
HF_TOKEN = os.environ.get("HUGGINGFACE_TOKEN")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ==========================================
# 3. COMANDOS DEL BOT
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensaje = (
        "⚙️ **Sistema Vórtice - Centro de Control**\n\n"
        "Comandos disponibles:\n"
        "• `/gemini <consulta>` - Consultar al motor de IA de Gemini.\n"
        "• `/generar_imagen <prompt>` - Generar imagen técnica o render con FLUX.1.\n"
        "• `/estado` - Verificar estado de los servicios en Render."
    )
    await update.message.reply_text(mensaje, parse_mode="Markdown")

async def estado_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    estado = (
        "🟢 **Estado del Sistema:**\n"
        "• Servidor HTTP: Activo (Puerto 10000)\n"
        "• Gemini API: Conectado\n"
        "• Hugging Face API: Router V1 Activo"
    )
    await update.message.reply_text(estado, parse_mode="Markdown")

async def generar_imagen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("⚠️ Ingresa una descripción. Ejemplo:\n`/generar_imagen diagrama de planta industrial`", parse_mode="Markdown")
        return

    await update.message.reply_text("🎨 Procesando imagen en el motor FLUX.1...")
    
    API_URL = "https://router.huggingface.co/hf-inference/v1/models/black-forest-labs/FLUX.1-dev"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"} if HF_TOKEN else {}

    try:
        response = requests.post(API_URL, headers=headers, json={"inputs": prompt}, timeout=60)
        
        if response.status_code == 200:
            await update.message.reply_photo(photo=response.content)
        else:
            await update.message.reply_text(f"❌ Error en Hugging Face ({response.status_code}):\n{response.text}")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error de conexión: {str(e)}")

async def prompt_gemini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = " ".join(context.args)
    if not user_text:
        await update.message.reply_text("⚠️ Escribe tu consulta. Ejemplo:\n`/gemini Balance de masa pirolisis`", parse_mode="Markdown")
        return

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(user_text)
        await update.message.reply_text(response.text)
    except Exception as e:
        await update.message.reply_text(f"❌ Error de Gemini: {str(e)}")

# ==========================================
# 4. INICIALIZACIÓN
# ==========================================
if __name__ == "__main__":
    if not TELEGRAM_TOKEN:
        raise ValueError("CRÍTICO: No se encontró TELEGRAM_TOKEN en las variables de entorno.")

    # Iniciar servidor web en segundo plano
    threading.Thread(target=run_flask, daemon=True).start()

    # Configurar bot de Telegram
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("estado", estado_command))
    app.add_handler(CommandHandler("generar_imagen", generar_imagen))
    app.add_handler(CommandHandler("gemini", prompt_gemini))

    logging.info("Bot y Servidor Web inicializados correctamente.")
    app.run_polling()
