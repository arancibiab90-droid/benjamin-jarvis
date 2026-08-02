#!/usr/bin/env python3
import os
import logging
import httpx
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("benjamin")

async def call_gemini(user_message: str) -> str:
    if not GEMINI_API_KEY:
        return "⚠️ Falta la variable GEMINI_API_KEY en Render."
    
    prompt_sistema = "Eres Benjamin Jarvis, cerebro autónomo del Holding Arancibia (Vórtice IVFA, Paine, Chile). Asistes a Izan Benjamín Arancibia Martínez."
    contents = [
        {
            "role": "user",
            "parts": [{"text": f"{prompt_sistema}\n\nEl usuario dice: {user_message}"}]
        }
    ]

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            r = await client.post(url, json={"contents": contents})
            data = r.json()
            if r.status_code != 200:
                return f"Error de Gemini ({r.status_code}): {data}"
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            return f"Error al conectar con la IA: {str(e)}"

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("🧠 *Benjamin Jarvis* activo.\n¿En qué te ayudo hoy con Vórtice IVFA?", parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    await update.message.chat.send_action("typing")
    
    reply = await call_gemini(text)
    await update.message.reply_text(reply)

def main():
    if not TELEGRAM_TOKEN:
        logger.error("Falta TELEGRAM_TOKEN")
        raise SystemExit(1)

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    if WEBHOOK_URL:
        clean_url = WEBHOOK_URL.rstrip("/")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=f"{clean_url}/webhook",
            url_path="webhook",
            drop_pending_updates=True
        )
    else:
        application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
