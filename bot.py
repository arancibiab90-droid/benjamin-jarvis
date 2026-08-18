import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters
from openai import OpenAI
from anthropic import Anthropic
import google.generativeai as genai

# ─────────────────────────────────────────────
# LOGS Y CONFIGURACIÓN INICIAL
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("BenjaminJarvis")

# ─────────────────────────────────────────────
# CARGA DE TOKENS DESDE RENDER (ENVIRONMENT)
# ─────────────────────────────────────────────
NVIDIA_API_KEY   = os.environ.get("NVIDIA_API_KEY")
GROK_API_KEY      = os.environ.get("GROK_API_KEY") or os.environ.get("GROK_...")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_...")
ELEVEN_API_KEY    = os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("ELEVE...")
REPLICATE_API_KEY = os.environ.get("REPLICATE_API_KEY") or os.environ.get("REPLI...")
HUGGING_API_KEY   = os.environ.get("HUGGING_FACE_TOKEN") or os.environ.get("HUGGI...")
TELEGRAM_TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEG...")

# ─────────────────────────────────────────────
# INICIALIZACIÓN DE CLIENTES DE IA
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
    genai.configure(api_key=GEMINI_API_KEY)

# ─────────────────────────────────────────────
# CONFIGURACIÓN DE MODELOS
# ─────────────────────────────────────────────
NVIDIA_MODEL = "meta/llama-3.1-70b-instruct"
GROK_MODEL   = "grok-beta"
CLAUDE_MODEL = "claude-3-5-sonnet-20241022"
GEMINI_MODELS_TO_TRY = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]

SYSTEM_PROMPT = (
    "Eres Benjamin Jarvis, el orquestador de IA de AGG Global Group Arancibia. "
    "Respondes de forma clara, ejecutiva y directa. "
    "Ayudas a Izan (CEO de AGG) con la gestión estratégica de Vórtice IVFA, Abasto Express y demás proyectos."
)

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
# CIRCUITO EN CASCADA (NVIDIA -> GROK -> CLAUDE -> GEMINI)
# ─────────────────────────────────────────────
def generate_with_nvidia(chat_id: int, prompt_text: str) -> str | None:
    if not nvidia_client: return None
    try:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + get_history(chat_id) + [{"role": "user", "content": prompt_text}]
        response = nvidia_client.chat.completions.create(model=NVIDIA_MODEL, messages=messages, temperature=0.6, max_tokens=1024)
        return response.choices[0].message.content.strip() or None
    except Exception as e:
        logger.warning("Fallo NVIDIA: %s", str(e))
        return None

def generate_with_grok(chat_id: int, prompt_text: str) -> str | None:
    if not grok_client: return None
    try:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + get_history(chat_id) + [{"role": "user", "content": prompt_text}]
        response = grok_client.chat.completions.create(model=GROK_MODEL, messages=messages, temperature=0.6, max_tokens=1024)
        return response.choices[0].message.content.strip() or None
    except Exception as e:
        logger.warning("Fallo Grok: %s", str(e))
        return None

def generate_with_claude(chat_id: int, prompt_text: str) -> str | None:
    if not anthropic_client: return None
    try:
        messages = get_history(chat_id) + [{"role": "user", "content": prompt_text}]
        response = anthropic_client.messages.create(model=CLAUDE_MODEL, max_tokens=1024, system=SYSTEM_PROMPT, messages=messages)
        text_blocks = [block.text for block in response.content if block.type == "text"]
        return "\n".join(text_blocks).strip() or None
    except Exception as e:
        logger.warning("Fallo Claude: %s", str(e))
        return None

def generate_with_gemini(prompt_text: str) -> str | None:
    if not GEMINI_API_KEY: return None
    for model_name in GEMINI_MODELS_TO_TRY:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt_text)
            if response and response.text: return response.text
        except Exception:
            continue
    return None

def generate_ai_response(chat_id: int, prompt_text: str) -> str:
    for engine in [
        lambda: generate_with_nvidia(chat_id, prompt_text),
        lambda: generate_with_grok(chat_id, prompt_text),
        lambda: generate_with_claude(chat_id, prompt_text),
        lambda: generate_with_gemini(prompt_text)
    ]:
        res = engine()
        if res: return res

    return "⚠️ Error crítico: Ninguna API de IA respondió. Revisa tus tokens en Render."

# ─────────────────────────────────────────────
# HANDLERS DE TELEGRAM Y EJECUCIÓN
# ─────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Benjamin Jarvis online. Todos los tokens y respaldos activos.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    sent_message = await update.message.reply_text("🔄 Procesando solicitud...")
    
    ai_response = generate_ai_response(chat_id, user_text)

    if not ai_response.startswith("⚠️"):
        append_history(chat_id, "user", user_text)
        append_history(chat_id, "assistant", ai_response)

    await context.bot.edit_message_text(chat_id=chat_id, message_id=sent_message.message_id, text=ai_response)

if __name__ == "__main__":
    if not TELEGRAM_TOKEN:
        raise RuntimeError("Falta TELEGRAM_BOT_TOKEN en las variables de entorno de Render.")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    logger.info("Bot Benjamin Jarvis operativo...")
    app.run_polling()
