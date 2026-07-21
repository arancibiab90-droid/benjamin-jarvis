import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.environ.get("TELEGRAM_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Hola Izan! Benjamin Jarvis está en línea y escuchando desde Render.")

if __name__ == '__main__':
    if not TOKEN:
        print("Error: No se encontró TELEGRAM_TOKEN en las variables de entorno.")
    else:
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        print("Bot iniciado correctamente...")
        app.run_polling()
