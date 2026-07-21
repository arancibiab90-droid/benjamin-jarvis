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
    await update.message.reply_text("¡Hola Izan! Benjamin Jarvis está oficialmente en línea y respondiendo desde Render.")

def main():
    if not TOKEN:
        print("Error: No se encontró la variable TELEGRAM_TOKEN.")
        return

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    
    print("Iniciando Benjamin Jarvis...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()


