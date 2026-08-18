import os
import logging
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters
import google.generativeai as genai

# ─────────────────────────────────────────────
# CONFIGURACIÓN DE LOGS
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("BenjaminJarvis")

# ─────────────────────────────────────────────
# CONFIGURACIÓN DE APIs — Cascada: NVIDIA → Grok → Claude → Gemini
# ─────────────────────────────────────────────
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")        # Primary — gratis
GROK_API_KEY = os.environ.get("GROK_API_KEY")             # Fallback 1 — xAI
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")   # Fallback 2 — pago, opcional
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")         # Fallback 3 — gratis
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

anthropic_client = None
if ANTHROPIC_API_KEY:
    from anthropic import Anthropic
    anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)

# Primary: NVIDIA NIM — Llama 3.1 70B (OpenAI-compatible)
NVIDIA_MODEL = "meta/llama-3.1-70b-instruct"
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

# Fallback 1: Grok (xAI) — OpenAI-compatible
GROK_MODEL = "grok-2-latest"
GROK_URL = "https://api.x.ai/v1/chat/completions"

# Fallback 2: Claude (solo si hay key de pago configurada)
CLAUDE_MODEL = "claude-sonnet-5"

# Fallback 3: Gemini
GEMINI_MODELS_TO_TRY = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]

# ─────────────────────────────────────────────
# APIS DE APOYO: VOZ (ElevenLabs) E IMÁGENES (Replicate)
# ─────────────────────────────────────────────
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # voz default multilingüe
ELEVENLABS_URL = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"

REPLICATE_API_KEY = os.environ.get("REPLICATE_API_KEY")
REPLICATE_MODEL_VERSION = os.environ.get(
    "REPLICATE_MODEL_VERSION",
    "black-forest-labs/flux-schnell",  # rápido y gratis dentro del free tier de Replicate
)
REPLICATE_URL = f"https://api.replicate.com/v1/models/{REPLICATE_MODEL_VERSION}/predictions"

SYSTEM_PROMPT = (
    "Eres Benjamin Jarvis, orquestador principal de IA y director de operaciones digitales "
    "de AGG Global Group, bajo la dirección de Izan Arancibia (CEO). "
    "Enfoque corporativo: VÓRTICE IVFA (revalorización industrial de residuos en Paine), "
    "ABASTO EXPRESS/HOLDING AGG (caja rápida, prospección B2B) y TRABAJO EN ALTURA "
    "(seguridad técnica, arneses, protocolos de infraestructura). "
    "Tono: ejecutivo, conciso, directo a la solución, sin rodeos ni relleno."
)

# ─────────────────────────────────────────────
# MEMORIA DE CONVERSACIÓN (en RAM, por chat_id)
# ─────────────────────────────────────────────
# Nota: esto es memoria de corto plazo por proceso. Para persistencia real
# entre reinicios de Render, engancha esto a tu GitHub Contents API
# (leer historial al iniciar, guardar tras cada intercambio).
conversation_history: dict[int, list[dict]] = {}
last_ai_response: dict[int, str] = {}
MAX_HISTORY_MESSAGES = 20  # últimos N mensajes por usuario


def get_history(chat_id: int) -> list[dict]:
    return conversation_history.setdefault(chat_id, [])


def append_history(chat_id: int, role: str, content: str):
    history = get_history(chat_id)
    history.append({"role": role, "content": content})
    if len(history) > MAX_HISTORY_MESSAGES:
        conversation_history[chat_id] = history[-MAX_HISTORY_MESSAGES:]


# ─────────────────────────────────────────────
# GENERACIÓN DE RESPUESTA — Cascada: NVIDIA → Grok → Claude → Gemini
# ─────────────────────────────────────────────
def generate_with_nvidia(prompt_text: str) -> str | None:
    if not NVIDIA_API_KEY:
        logger.warning("NVIDIA_API_KEY no configurada, saltando NVIDIA (primary).")
        return None
    try:
        logger.info("Intentando generar respuesta con NVIDIA NIM (%s)...", NVIDIA_MODEL)
        headers = {
            "Authorization": f"Bearer {NVIDIA_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": NVIDIA_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt_text},
            ],
            "max_tokens": 1024,
        }
        resp = requests.post(NVIDIA_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        return content or None
    except Exception as e:
        logger.warning("Fallo en NVIDIA (primary): %s. Probando Grok (fallback 1)...", str(e))
        return None


def generate_with_grok(prompt_text: str) -> str | None:
    if not GROK_API_KEY:
        logger.warning("GROK_API_KEY no configurada, saltando Grok (fallback 1).")
        return None
    try:
        logger.info("Intentando generar respuesta con Grok (%s)...", GROK_MODEL)
        headers = {
            "Authorization": f"Bearer {GROK_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": GROK_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt_text},
            ],
            "max_tokens": 1024,
        }
        resp = requests.post(GROK_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        return content or None
    except Exception as e:
        logger.warning("Fallo en Grok (fallback 1): %s. Probando Claude (fallback 2)...", str(e))
        return None


def generate_with_claude(chat_id: int, prompt_text: str) -> str | None:
    if not anthropic_client:
        logger.info("ANTHROPIC_API_KEY no configurada, saltando Claude (fallback 2).")
        return None
    try:
        logger.info("Intentando generar respuesta con Claude (%s)...", CLAUDE_MODEL)
        messages = get_history(chat_id) + [{"role": "user", "content": prompt_text}]
        response = anthropic_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        text_blocks = [block.text for block in response.content if block.type == "text"]
        result = "\n".join(text_blocks).strip()
        return result or None
    except Exception as e:
        logger.warning("Fallo en Claude (fallback 2): %s. Probando Gemini (fallback 3)...", str(e))
        return None


def generate_with_gemini(prompt_text: str) -> str | None:
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY no configurada, saltando Gemini (fallback 3).")
        return None
    for model_name in GEMINI_MODELS_TO_TRY:
        try:
            logger.info("Intentando generar respuesta con Gemini: %s", model_name)
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt_text)
            if response and response.text:
                return response.text
        except Exception as e:
            logger.warning("Fallo en modelo %s: %s. Probando siguiente...", model_name, str(e))
            continue
    return None


def generate_ai_response(chat_id: int, prompt_text: str) -> str:
    """Circuito redundante: NVIDIA (primary) → Grok → Claude → Gemini."""
    for fn in (
        lambda: generate_with_nvidia(prompt_text),
        lambda: generate_with_grok(prompt_text),
        lambda: generate_with_claude(chat_id, prompt_text),
        lambda: generate_with_gemini(prompt_text),
    ):
        result = fn()
        if result:
            return result

    return (
        "⚠️ Error crítico: ningún modelo de la cascada respondió (NVIDIA/Grok/Claude/Gemini).\n"
        "Revisa las API keys en Render."
    )


# ─────────────────────────────────────────────
# VOZ (ElevenLabs) — texto a audio
# ─────────────────────────────────────────────
def generate_voice(text: str) -> bytes | None:
    if not ELEVENLABS_API_KEY:
        logger.warning("ELEVENLABS_API_KEY no configurada, no se puede generar voz.")
        return None
    try:
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text[:2000],  # límite prudente por solicitud
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        resp = requests.post(ELEVENLABS_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        logger.warning("Fallo generando voz con ElevenLabs: %s", str(e))
        return None


# ─────────────────────────────────────────────
# IMÁGENES (Replicate) — texto a imagen
# ─────────────────────────────────────────────
def generate_image(prompt: str) -> str | None:
    if not REPLICATE_API_KEY:
        logger.warning("REPLICATE_API_KEY no configurada, no se puede generar imagen.")
        return None
    try:
        headers = {
            "Authorization": f"Bearer {REPLICATE_API_KEY}",
            "Content-Type": "application/json",
            "Prefer": "wait",  # espera la predicción sin tener que hacer polling manual
        }
        payload = {"input": {"prompt": prompt}}
        resp = requests.post(REPLICATE_URL, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        output = data.get("output")
        if isinstance(output, list) and output:
            return output[0]
        if isinstance(output, str):
            return output
        return None
    except Exception as e:
        logger.warning("Fallo generando imagen con Replicate: %s", str(e))
        return None


# ─────────────────────────────────────────────
# HANDLERS DE TELEGRAM
# ─────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Benjamin Jarvis operativo. Escríbeme cualquier consulta sobre AGG y te respondo.\n"
        "Comandos: /voz (te leo la última respuesta) · /imagen <descripción> (genero una imagen)"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    sent_message = await update.message.reply_text("🔄 Procesando solicitud...")

    ai_response = generate_ai_response(chat_id, user_text)

    # Guardar en historial solo si la respuesta fue exitosa (no un mensaje de error)
    if not ai_response.startswith("⚠️"):
        append_history(chat_id, "user", user_text)
        append_history(chat_id, "assistant", ai_response)
        last_ai_response[chat_id] = ai_response

    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=sent_message.message_id,
        text=ai_response,
    )


async def cmd_voz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = last_ai_response.get(chat_id)
    if not text:
        await update.message.reply_text("No tengo una respuesta previa para leer. Pregúntame algo primero.")
        return

    await context.bot.send_chat_action(chat_id=chat_id, action="record_voice")
    audio_bytes = generate_voice(text)
    if not audio_bytes:
        await update.message.reply_text(
            "⚠️ No pude generar el audio. Revisa que ELEVENLABS_API_KEY esté bien configurada en Render."
        )
        return
    await context.bot.send_voice(chat_id=chat_id, voice=audio_bytes)


async def cmd_imagen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    prompt = " ".join(context.args) if context.args else ""
    if not prompt:
        await update.message.reply_text("Uso: /imagen <descripción de lo que quieres generar>")
        return

    await context.bot.send_chat_action(chat_id=chat_id, action="upload_photo")
    sent_message = await update.message.reply_text("🎨 Generando imagen...")
    image_url = generate_image(prompt)

    if not image_url:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=sent_message.message_id,
            text="⚠️ No pude generar la imagen. Revisa que REPLICATE_API_KEY esté bien configurada en Render.",
        )
        return

    await context.bot.delete_message(chat_id=chat_id, message_id=sent_message.message_id)
    await context.bot.send_photo(chat_id=chat_id, photo=image_url, caption=f"🖼️ {prompt}")


# ─────────────────────────────────────────────
# ARRANQUE DEL BOT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    if not TELEGRAM_TOKEN:
        raise RuntimeError("Falta TELEGRAM_BOT_TOKEN en las variables de entorno de Render.")
    if not any([NVIDIA_API_KEY, GROK_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY]):
        raise RuntimeError(
            "Falta al menos una API key de la cascada: NVIDIA_API_KEY, GROK_API_KEY, "
            "ANTHROPIC_API_KEY o GEMINI_API_KEY en Render."
        )

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("voz", cmd_voz))
    app.add_handler(CommandHandler("imagen", cmd_imagen))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    logger.info("Bot Benjamin Jarvis en ejecución...")
    app.run_polling()
