



import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai

# ====================== CONFIGURACIÓN ======================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ALLOWED_CHAT_IDS = {int(x.strip()) for x in os.getenv("ALLOWED_CHAT_IDS", "").split(",") if x.strip()}

# Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")
else:
    model = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Estado simple de confirmaciones pendientes
pending_actions = {}

SYSTEM_PROMPT = """Eres Benjamin Jarvis, el agente principal de Izan.
Eres directo, claro y ejecutivo.
Nunca hagas cambios importantes sin que el usuario confirme.
Si propones algo, espera su "sí" o "confirma".
Responde siempre en español.
"""

def is_authorized(chat_id: int) -> bool:
    return chat_id in ALLOWED_CHAT_IDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_chat.id):
        await update.message.reply_text("⛔ Acceso denegado.")
        return
    await update.message.reply_text(
        "🤖 Benjamin Jarvis online.\n\n"
        "Solo tú puedes darme órdenes.\n"
        "Toda acción importante requiere tu confirmación.\n\n"
        "Escribe lo que necesites."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    if not is_authorized(chat_id):
        await update.message.reply_text("⛔ Acceso denegado.")
        return

    if not text:
        return

    # ¿Hay acción pendiente de confirmación?
    if chat_id in pending_actions:
        if text.lower() in ["sí", "si", "confirma", "ok", "hazlo", "adelante"]:
            accion = pending_actions.pop(chat_id)
            await update.message.reply_text(f"✅ Confirmado. Ejecutando: {accion}")
            # Aquí más adelante pondremos la ejecución real de código
            return
        elif text.lower() in ["no", "cancelar", "cancela"]:
            pending_actions.pop(chat_id, None)
            await update.message.reply_text("❌ Acción cancelada.")
            return
        else:
            await update.message.reply_text("⏳ Tienes una acción pendiente. Responde **sí** o **no**.")
            return

    # Respuesta normal con Gemini
    if not model:
        await update.message.reply_text("⚠️ Falta configurar GEMINI_API_KEY en Render.")
        return

    try:
        prompt = f"{SYSTEM_PROMPT}\n\nUsuario: {text}"
        response = model.generate_content(prompt)
        respuesta = response.text.strip()
        await update.message.reply_text(respuesta)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

def main():
    if not TELEGRAM_TOKEN:
        raise RuntimeError("Falta TELEGRAM_BOT_TOKEN")
    if not ALLOWED_CHAT_IDS:
        raise RuntimeError("Falta ALLOWED_CHAT_IDS")

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & \~filters.COMMAND, handle_message))

    logger.info("Benjamin Jarvis iniciando... Solo responde a: %s", ALLOWED_CHAT_IDS)
    app.run_polling()

if __name__ == "__main__":
    main()
