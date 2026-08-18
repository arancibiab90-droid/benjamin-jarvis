import os
import logging
import threading
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
# 1. CONFIGURACIÓN DE LOGS Y SISTEMA
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("BenjaminJarvis")

# ─────────────────────────────────────────────
# 2. SERVIDOR DE SALUD (HEALTHCHECK PARA RENDER WEB SERVICE)
# ─────────────────────────────────────────────
class HealthCheckHandler(BaseHTTPRequestHandler):
    """Responde 200 OK a los pings de Render para evitar cierres por puerto no detectado."""
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("Benjamin Jarvis OK - AGG Systems".encode("utf-8"))

    def log_message(self, format, *args):
        # Desactiva logs repetitivos del healthcheck
        return

def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    logger.info(f"Servidor de salud iniciado en el puerto {port}")
    server.serve_forever()

# ─────────────────────────────────────────────
# 3. LECTURA FLEXIBLE DE VARIABLES DE ENTORNO
# ─────────────────────────────────────────────
def get_env_variable(keywords: list[str]) -> str | None:
    """Busca en las variables de entorno de Render coincidencia con las palabras clave."""
    for key, value in os.environ.items():
        for kw in keywords:
            if kw.upper() in key.upper() and value and value.strip():
                return value.strip()
    return None

TELEGRAM_TOKEN    = get_env_variable(["TELEGRAM", "TELEG", "BOT_TOKEN"])
NVIDIA_API_KEY   = get_env_variable(["NVIDIA"])
GROK_API_KEY      = get_env_variable(["GROK", "XAI"])
ANTHROPIC_API_KEY = get_env_variable(["ANTHROPIC", "CLAUDE"])
GEMINI_API_KEY    = get_env_variable(["GEMINI", "GOOGLE"])

# ─────────────────────────────────────────────
# 4. INICIALIZACIÓN DE CLIENTES DE IA
# ─────────────────────────────────────────────
nvidia_client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=NVIDIA_API_KEY
) if NVIDIA_API_KEY else None

grok_client = OpenAI(
    base_url="https://api.x.ai/v1",
    api_key=GROK_API_KEY
) if GROK_API_KEY else None

anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
    except Exception as e:
        logger.error(f"Error configurando Gemini: {e}")

# Configuración de modelos exactos
NVIDIA_MODEL = "meta/llama-3.1-70b-instruct"
GROK_MODEL   = "grok-beta"
CLAUDE_MODEL = "claude-3-5-sonnet-20241022"
GEMINI_MODELS_TO_TRY = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]

SYSTEM_PROMPT = (
    "Eres Benjamin Jarvis, el orquestador principal de IA de AGG Global Group Arancibia. "
    "Respondes de forma clara, ejecutiva, precisa y directa. "
    "Ayudas a Izan Arancibia (CEO de AGG) con la gestión estratégica de Vórtice IVFA, Abasto Express "
    "y la supervisión de operaciones."
)

# ─────────────────────────────────────────────
# 5. GESTIÓN DE MEMORIA EN RAM
# ─────────────────────────────────────────────
conversation_history: dict[int, list[dict]] = {}
MAX_HISTORY_MESSAGES = 20

def get_history(chat_id: int) -> list[dict]:
    return conversation_history.setdefault(chat_id, [])

def append_history(chat_id: int, role: str, content: str):
    history = get_history(chat_id)
    history.append({"role": role, "content": content})
    if len(history) > MAX_HISTORY_MESSAGES:
        conversation_history[chat_id] = history[-MAX_HISTORY_MESSAGES:]

# ─────────────────────────────────────────────
# 6. MOTORES DE GENERACIÓN (CASCADA INDEPENDIENTE)
# ─────────────────────────────────────────────
def generate_with_nvidia(chat_id: int, prompt_text: str) -> str | None:
    if not nvidia_client:
        return None
    try:
        logger.info("Solicitando respuesta a NVIDIA...")
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + get_history(chat_id) + [{"role": "user", "content": prompt_text}]
        response = nvidia_client.chat.completions.create(
            model=NVIDIA_MODEL,
            messages=messages,
            temperature=0.6,
            max_tokens=1024
        )
        if response and response.choices:
            return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"Error en motor NVIDIA: {e}")
    return None

def generate_with_grok(chat_id: int, prompt_text: str) -> str | None:
    if not grok_client:
        return None
    try:
        logger.info("Solicitando respuesta a Grok...")
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + get_history(chat_id) + [{"role": "user", "content": prompt_text}]
        response = grok_client.chat.completions.create(
            model=GROK_MODEL,
            messages=messages,
            temperature=0.6,
            max_tokens=1024
        )
        if response and response.choices:
            return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"Error en motor Grok: {e}")
    return None

def generate_with_claude(chat_id: int, prompt_text: str) -> str | None:
    if not anthropic_client:
        return None
    try:
        logger.info("Solicitando respuesta a Claude...")
        messages = get_history(chat_id) + [{"role": "user", "content": prompt_text}]
        response = anthropic_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages
        )
        text_blocks = [block.text for block in response.content if block.type == "text"]
        result = "\n".join(text_blocks).strip()
        if result:
            return result
    except Exception as e:
        logger.warning(f"Error en motor Claude: {e}")
    return None

def generate_with_gemini(prompt_text: str) -> str | None:
    if not GEMINI_API_KEY:
        return None
    for model_name in GEMINI_MODELS_TO_TRY:
        try:
            logger.info(f"Solicitando respuesta a Gemini ({model_name})...")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt_text)
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            logger.warning(f"Error en modelo Gemini {model_name}: {e}")
            continue
    return None

def generate_ai_response(chat_id: int, prompt_text: str) -> str:
    """Orquestador: NVIDIA -> Grok -> Claude -> Gemini."""
    res = generate_with_nvidia(chat_id, prompt_text)
    if res: return res

    res = generate_with_grok(chat_id, prompt_text)
    if res: return res

    res = generate_with_claude(chat_id, prompt_text)
    if res: return res

    res = generate_with_gemini(prompt_text)
    if res: return res

    return "⚠️ Error crítico: Ninguno de los proveedores de IA (NVIDIA, Grok, Claude, Gemini) respondió. Revisa los tokens en Render."

# ─────────────────────────────────────────────
# 7. HANDLERS DE TELEGRAM
# ─────────────────────────────────────────────
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = "👋 Benjamin Jarvis online. Sistema de redundancia de 4 niveles activo para AGG y Vórtice IVFA."
    await update.message.reply_text(welcome_text)

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    user_text = update.message.text

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    sent_message = await update.message.reply_text("🔄 Procesando solicitud...")

    ai_response = generate_ai_response(chat_id, user_text)

    if not ai_response.startswith("⚠️"):
        append_history(chat_id, "user", user_text)
        append_history(chat_id, "assistant", ai_response)

    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=sent_message.message_id,
        text=ai_response
    )

# ─────────────────────────────────────────────
# 8. PUNTO DE ENTRADA PRINCIPAL
# ─────────────────────────────────────────────
if __name__ == "__main__":
    if not TELEGRAM_TOKEN:
        logger.error("No se encontró el token de Telegram en las variables de entorno.")
        raise RuntimeError("No se detectó el TELEGRAM_BOT_TOKEN en Render.")

    # Inicia el servidor de salud HTTP en un hilo independiente
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()

    # Construye la aplicación de Telegram
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_user_message))

    logger.info("Bot Benjamin Jarvis iniciado correctamente. Escuchando mensajes...")
    app.run_polling()
