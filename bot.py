import logging
import os
import threading
from flask import Flask
import httpx
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Configuración de logs
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Credenciales y variables de entorno
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROK_API_KEY = os.getenv("GROK_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

SYSTEM_PROMPT = """Eres Benjamin Jarvis (Agente 1), el Cerebro Operativo del Holding Arancibia (Vórtice IVFA).
Tu objetivo principal es liderar la estrategia, coordinar sub-agentes en segundo plano y generar ingresos para el holding.
Hablas de forma profesional, directa y estratégica. Recuerdas que el proyecto Vórtice IVFA está ubicado en Paine (30% humedad) y procesa plásticos, madera/ramas para briquetas/aserrín, y orgánicos para biogás.
Respondes en lenguaje natural sin exigir formatos rígidos de código al usuario."""

# Servidor Flask para mantener activo el servidor en Render
app = Flask(__name__)


@app.route("/")
def home():
  return "Benjamin Jarvis (Agente 1) activo 24/7."


def run_flask():
  port = int(os.getenv("PORT", 8080))
  app.run(host="0.0.0.0", port=port)


# Conmutación inteligente entre APIs (Gemini -> Grok -> DeepSeek)
async def call_multi_ai(user_message: str) -> str:
  full_prompt = f"{SYSTEM_PROMPT}\n\nUsuario: {user_message}"

  # 1. Intento con modelos de Gemini (Versión v1beta)
  if GEMINI_API_KEY:
    gemini_models = [
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
    ]
    payload = {
        "contents": [{"role": "user", "parts": [{"text": full_prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1024},
    }
    async with httpx.AsyncClient(timeout=30) as client:
      for model in gemini_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        try:
          r = await client.post(url, json=payload)
          if r.status_code == 200:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
          else:
            logger.warning(
                f"Gemini {model} devolvió código {r.status_code}: {r.text}"
            )
        except Exception as e:
          logger.error(f"Error Gemini {model}: {e}")

  # 2. Resguardo con Grok (Modelos xAI actualizados: grok-2-mini / grok-2)
  if GROK_API_KEY:
    headers = {
        "Authorization": f"Bearer {GROK_API_KEY.strip()}",
        "Content-Type": "application/json",
    }
    grok_models = ["grok-2-mini", "grok-2"]
    async with httpx.AsyncClient(timeout=30) as client:
      for g_model in grok_models:
        payload_grok = {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "model": g_model,
            "temperature": 0.7,
        }
        try:
          r = await client.post(
              "https://api.x.ai/v1/chat/completions",
              headers=headers,
              json=payload_grok,
          )
          if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
          else:
            logger.warning(
                f"Grok ({g_model}) respondió con código {r.status_code}:"
                f" {r.text}"
            )
        except Exception as e:
          logger.error(f"Error en Grok ({g_model}): {e}")

  # 3. Resguardo con DeepSeek
  if DEEPSEEK_API_KEY:
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY.strip()}",
        "Content-Type": "application/json",
    }
    payload_ds = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "model": "deepseek-chat",
        "temperature": 0.7,
    }
    async with httpx.AsyncClient(timeout=30) as client:
      try:
        r = await client.post(
            "https://api.deepseek.com/chat/completions",
            headers=headers,
            json=payload_ds,
        )
        if r.status_code == 200:
          return r.json()["choices"][0]["message"]["content"]
      except Exception as e:
        logger.error(f"Error en DeepSeek: {e}")

  return "⚠️ Todos los proveedores de IA están saturados temporalmente. Reintenta en unos segundos."


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
  await update.message.reply_text(
      "🧠 **Benjamin Jarvis activo.** Háblame directamente en lenguaje natural"
      " sobre la estrategia, los sub-agentes o el desarrollo del Holding"
      " Arancibia."
  )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
  if not update.message or not update.message.text:
    return

  await update.message.chat.send_action("typing")
  text = update.message.text.strip()

  reply = await call_multi_ai(text)
  await update.message.reply_text(reply)


def main():
  threading.Thread(target=run_flask, daemon=True).start()

  application = Application.builder().token(TELEGRAM_TOKEN).build()
  application.add_handler(CommandHandler("start", start_command))
  application.add_handler(
      MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
  )

  logger.info("Bot en marcha...")
  application.run_polling()


if __name__ == "__main__":
  main()
