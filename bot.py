import os
import logging
import threading
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)
from openai import OpenAI
from anthropic import Anthropic
import google.generativeai as genai

# ─────────────────────────────────────────────
# 1. LOGS
# ─────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("BenjaminJarvis")

# ─────────────────────────────────────────────
# 2. SERVIDOR DE SALUD PARA RENDER (PORT 10000)
# ─────────────────────────────────────────────
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("Benjamin Jarvis Active".encode("utf-8"))

    def log_message(self, format, *args):
        return

def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    logger.info(f"Servidor de salud corriendo en puerto {port}")
    server.serve_forever()

# ─────────────────────────────────────────────
# 3. LECTURA DE VARIABLES DE ENTORNO
# ─────────────────────────────────────────────
def get_env_var(keywords: list[str]) -> str | None:
    for key, val in os.environ.items():
        for kw in keywords:
            if kw.upper() in key.upper() and val and val.strip():
                return val.strip()
    return None

TELEGRAM_TOKEN    = get_env_var(["TELEGRAM", "TELEG", "BOT_TOKEN"])
NVIDIA_API_KEY   = get_env_var(["NVIDIA"])
GROK_API_KEY      = get_env_var(["GROK", "XAI"])
ANTHROPIC_API_KEY = get_env_var(["ANTHROPIC", "CLAUDE"])
GEMINI_API_KEY    = get_env_var(["GEMINI", "GOOGLE"])

# ─────────────────────────────────────────────
# 4. LIMPIADOR AUTOMÁTICO DE WEBHOOKS
# ─────────────────────────────────────────────
def auto_clean_webhook(token: str):
    """Borra webhooks atascados directamente en la API de Telegram al iniciar."""
    try:
        url = f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=true"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as response:
            res = response.read().decode("utf-8")
            logger.info(f"Limpieza de Telegram completada: {res}")
    except Exception as e:
        logger.warning(f"No se pudo limpiar webhook automáticamente: {e}")

# ─────────────────────────────────────────────
# 5. CLIENTES DE IA
# ─────────────────────────────────────────────
nvidia_client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=NVIDIA_API_KEY) if NVIDIA_API_KEY else None
grok_client = OpenAI(base_url="https://api.x.ai/v1", api_key=GROK_API_KEY) if GROK_API_KEY else None
anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

if GEMINI_API_KEY:
    try: genai.configure(api_key=GEMINI_API_KEY)
    except Exception: pass

NVIDIA_MODEL = "meta/llama-3.1-70b-instruct"
GROK_MODEL   = "grok-beta"
CLAUDE_MODEL = "claude-3-5-sonnet-20241022"
GEMINI_MODELS_TO_TRY = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]

SYSTEM_PROMPT = (
    "Eres Benjamin Jarvis, el orquestador principal de IA de AGG Global Group Arancibia. "
    "Respondes de forma clara, ejecutiva, precisa y directa. "
    "Ayudas a Izan Arancibia (CEO de AGG) con la gestión estratégica de Vórtice IVFA y Abasto Express."
)

conversation_history: dict[int, list[dict]] = {}

def get_history(chat_id: int) -> list[dict]:
    return conversation_history.setdefault(chat_id, [])

def append_history(chat_id: int, role: str, content: str):
    history = get_history(chat_id)
    history.append({"role": role, "content": content})
    if len(history) > 20:
        conversation_history[chat_id] = history[-20:]

def generate_ai_response(chat_id: int, prompt_text: str) -> str:
    # 1. NVIDIA
    if nvidia_client:
        try:
            msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + get_history(chat_id) + [{"role": "user", "content": prompt_text}]
            res = nvidia_client.chat.completions.create(model=NVIDIA_MODEL, messages=msgs, temperature=0.6, max_tokens=1024)
            return res.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"Error NVIDIA: {e}")

    # 2. GROK
    if grok_client:
        try:
            msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + get_history(chat_id) + [{"role": "user", "content": prompt_text}]
            res = grok_client.chat.completions.create(model=GROK_MODEL, messages=msgs, temperature=0.6, max_tokens=1024)
            return res.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"Error Grok: {e}")

    # 3. CLAUDE
    if anthropic_client:
        try:
            msgs = get_history(chat_id) + [{"role": "user", "content": prompt_text}]
            res = anthropic_client.messages.create(model=CLAUDE_MODEL, max_tokens=1024, system=SYSTEM_PROMPT, messages=msgs)
            return "\n".join([b.text for b in res.content if b.type == "text"]).strip()
        except Exception as e:
            logger.warning(f"Error Claude: {e}")

    # 4. GEMINI
    if GEMINI_API_KEY:
        for m in GEMINI_MODELS_TO_TRY:
            try:
                res = genai.GenerativeModel(m).generate_content(prompt_text)
                if res and res.text: return res.text.strip()
            except Exception:
                continue

    return "⚠️ Error crítico: Ninguna API de IA respondió."

# ─────────────────────────────────────────────
# 6. HANDLERS TELEGRAM
# ─────────────────────────────────────────────
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Benjamin Jarvis online. Sistema desinhibido y listo.")

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.message or not update.message.text: return
    chat_id = update.effective_chat.id
    user_text = update.message.text

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    sent = await update.message.reply_text("🔄 Procesando...")

    ai_res = generate_ai_response(chat_id, user_text)

    if not ai_res.startswith("⚠️"):
        append_history(chat_id, "user", user_text)
        append_history(chat_id, "assistant", ai_res)

    await context.bot.edit_message_text(chat_id=chat_id, message_id=sent.message_id, text=ai_res)

# ─────────────────────────────────────────────
# 7. EJECUCIÓN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    if not TELEGRAM_TOKEN:
        raise RuntimeError("No se detectó TELEGRAM_BOT_TOKEN en Render.")

    # Auto-limpieza de conexiones viejas
    auto_clean_webhook(TELEGRAM_TOKEN)

    # Inicia puerto web para Render
    threading.Thread(target=start_health_server, daemon=True).start()

    # Arranca Telegram
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_user_message))

    logger.info("Bot Benjamin Jarvis en ejecución...")
    app.run_polling()
