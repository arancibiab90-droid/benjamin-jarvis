import logging
import os
import threading
from collections import deque
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

# Memoria de conversación (últimos mensajes por chat)
MAX_HISTORY = 12
chat_histories = {}

SYSTEM_PROMPT = """Eres Benjamin Jarvis (Agente 1), el Cerebro Operativo y Orquestador del Holding Arancibia (Proyecto Vórtice IVFA).

Tu rol principal:
- Liderar la estrategia del holding.
- Coordinar y crear sub-agentes cuando sea necesario.
- Generar ingresos y avanzar el proyecto de forma práctica.
- Tomar decisiones claras y proponer acciones concretas.

Contexto del proyecto:
- Ubicación: Paine (humedad aprox. 30%).
- Procesa: plásticos, madera/ramas (briquetas/aserrín) y orgánicos (biogás).

Forma de trabajar:
- Hablas de forma profesional, directa, estratégica y en español.
- Cuando una tarea sea compleja, piensas cómo dividirla y qué sub-agentes o herramientas necesitarías.
- Si el usuario pide crear un agente, proponer estructura o coordinar trabajo, respondes como el orquestador que eres.
- No inventas capacidades que aún no tienes. Si algo requiere una herramienta o sub-agente nuevo, lo dices claramente y propones el siguiente paso.
- Respondes en lenguaje natural, claro y accionable.

Eres el cerebro. Tu trabajo es hacer que las cosas avancen."""

# Servidor Flask para mantener activo el servidor en Render
app = Flask(__name__)


@app.route("/")
def home():
    return "Benjamin Jarvis (Agente 1) - Cerebro Operativo activo 24/7."


def run_flask():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


def get_history(chat_id: int) -> list:
    if chat_id not in chat_histories:
        chat_histories[chat_id] = deque(maxlen=MAX_HISTORY)
    return list(chat_histories[chat_id])


def add_to_history(chat_id: int, role: str, content: str):
    if chat_id not in chat_histories:
        chat_histories[chat_id] = deque(maxlen=MAX_HISTORY)
    chat_histories[chat_id].append({"role": role, "content": content})


async def call_multi_ai(user_message: str, chat_id: int) -> str:
    history = get_history(chat_id)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history:
        messages.append(msg)
    messages.append({"role": "user", "content": user_message})

    # 1. Gemini
    if GEMINI_API_KEY:
        gemini_models = [
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-flash-8b",
        ]
        gemini_contents = []
        for m in messages:
            if m["role"] == "system":
                continue
            role = "user" if m["role"] == "user" else "model"
            gemini_contents.append({"role": role, "parts": [{"text": m["content"]}]})

        if gemini_contents:
            first_text = gemini_contents[0]["parts"][0]["text"]
            gemini_contents[0]["parts"][0]["text"] = f"{SYSTEM_PROMPT}\n\n{first_text}"

        payload = {
            "contents": gemini_contents,
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1500},
        }

        async with httpx.AsyncClient(timeout=45) as client:
            for model in gemini_models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
                try:
                    r = await client.post(url, json=payload)
                    if r.status_code == 200:
                        data = r.json()
                        return data["candidates"][0]["content"]["parts"][0]["text"]
                    else:
                        logger.warning(f"Gemini {model} → {r.status_code}")
                except Exception as e:
                    logger.error(f"Error Gemini {model}: {e}")

    # 2. Grok
    if GROK_API_KEY:
        headers = {
            "Authorization": f"Bearer {GROK_API_KEY.strip()}",
            "Content-Type": "application/json",
        }
        grok_models = ["grok-2-mini", "grok-2"]
        async with httpx.AsyncClient(timeout=45) as client:
            for g_model in grok_models:
                payload_grok = {
                    "messages": messages,
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
                except Exception as e:
                    logger.error(f"Error Grok {g_model}: {e}")

    # 3. DeepSeek
    if DEEPSEEK_API_KEY:
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY.strip()}",
            "Content-Type": "application/json",
        }
        payload_ds = {
            "messages": messages,
            "model": "deepseek-chat",
            "temperature": 0.7,
        }
        async with httpx.AsyncClient(timeout=45) as client:
            try:
                r = await client.post(
                    "https://api.deepseek.com/chat/completions",
                    headers=headers,
                    json=payload_ds,
                )
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"]
            except Exception as e:
                logger.error(f"Error DeepSeek: {e}")

    return "⚠️ Todos los proveedores de IA están saturados temporalmente. Reintenta en unos segundos."


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in chat_histories:
        chat_histories[chat_id].clear()

    await update.message.reply_text(
        "🧠 **Benjamin Jarvis activo.**\n\n"
        "Soy el Cerebro Operativo del Holding Arancibia (Vórtice IVFA).\n"
        "Háblame de estrategia, sub-agentes, tareas o cualquier avance del proyecto."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    await update.message.chat.send_action("typing")

    add_to_history(chat_id, "user", text)
    reply = await call_multi_ai(text, chat_id)
    add_to_history(chat_id, "assistant", reply)

    await update.message.reply_text(reply)


def main():
    threading.Thread(target=run_flask, daemon=True).start()

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(
        MessageHandler(filters.TEXT & \~filters.COMMAND, handle_message)
    )

    logger.info("Benjamin Jarvis (Cerebro) en marcha...")
    application.run_polling()


if __name__ == "__main__":
    main()
