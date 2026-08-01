#!/usr/bin/env python3
import os
import json
import logging
from pathlib import Path

import httpx
from flask import Flask
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
PORT = int(os.getenv("PORT", "10000"))

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("benjamin")

app_flask = Flask(__name__)

async def call_gemini(messages: list) -> str:
    if not GEMINI_API_KEY:
        return "⚠️ Falta la variable GEMINI_API_KEY en Render."
    
    contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, json={"contents": contents})
        data = r.json()
        if r.status_code != 200:
            return f"Error Gemini: {data}"
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            return f"Error leyendo respuesta: {data}"

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🧠 *Benjamin Jarvis* activo.\n¿En qué te ayudo hoy con Vórtice IVFA?", parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    await update.message.chat.send_action("typing")
    
    prompt_sistema = "Eres Benjamin Jarvis, cerebro autónomo del Holding Arancibia (Vórtice IVFA, Paine, Chile). Asistes a Izan Benjamín Arancibia Martínez."
    historial = [
        {"role": "user", "content": f"{prompt_sistema}\n\nEl usuario dice: {text}"}
    ]
    
    reply = await call_gemini(historial)
    await update.message.reply_text(reply)

def main():
    if not TELEGRAM_TOKEN:
        logger.error("Falta TELEGRAM_TOKEN")
        raise SystemExit(1)

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    if WEBHOOK_URL:
        url = WEBHOOK_URL.rstrip("/") + "/webhook"
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="webhook",
            webhook_url=url,
            drop_pending_updates=True,
        )
    else:
        application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
