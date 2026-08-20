import os
import io
import time
import asyncio
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
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
# SERVIDOR HTTP MÍNIMO — solo para que Render detecte un puerto abierto
# ─────────────────────────────────────────────
# Render (plan free) exige que el servicio escuche en un puerto HTTP,
# aunque el bot funcione por polling a Telegram. Este servidor no hace
# nada más que responder "OK" para que el health check de Render pase.
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Benjamin Jarvis operativo")

    def log_message(self, format, *args):
        pass  # silenciar el log de cada ping de Render


def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    logger.info("Health check server escuchando en puerto %s", port)
    server.serve_forever()

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
# APIS DE APOYO: VOZ (ElevenLabs) E IMÁGENES (Pollinations.ai)
# ─────────────────────────────────────────────
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # voz default multilingüe
ELEVENLABS_URL = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"

# Pollinations.ai — generación de imágenes gratis, sin API key ni tarjeta de crédito (respaldo)
POLLINATIONS_URL = "https://image.pollinations.ai/prompt"

# Hugging Face Inference API — Qwen-Image (Alibaba), gratis con token, mejor calidad/nitidez
# Acepta cualquiera de estos 3 nombres de variable, por si Render la tiene con otro nombre
HF_API_KEY = (
    os.environ.get("HUGGINGFACE_API_KEY")
    or os.environ.get("HF_TOKEN")
    or os.environ.get("HUGGINGFACE_TOKEN")
)
HF_IMAGE_MODEL = os.environ.get("HF_IMAGE_MODEL", "Qwen/Qwen-Image")
HF_IMAGE_URL = f"https://api-inference.huggingface.co/models/{HF_IMAGE_MODEL}"
HF_MAX_WAIT_SECONDS = 40   # tiempo máximo esperando a que el modelo "despierte" en el free tier
HF_POLL_INTERVAL = 5

SYSTEM_PROMPT = (
    "Eres Benjamin Jarvis, orquestador principal de IA y director de operaciones digitales "
    "de AGG Global Group, bajo la dirección de Izan Arancibia (CEO). "
    "Enfoque corporativo: VÓRTICE IVFA (revalorización industrial de residuos en Paine), "
    "ABASTO EXPRESS/HOLDING AGG (caja rápida, prospección B2B) y TRABAJO EN ALTURA "
    "(seguridad técnica, arneses, protocolos de infraestructura). "
    "Tono: ejecutivo, conciso, directo a la solución, sin rodeos ni relleno."
)

# Plantilla usada por /contenido — genera 3 formatos listos para publicar en una sola pasada
CONTENT_PROMPT_TEMPLATE = (
    "Genera contenido de redes sociales para AGG Global Group / Vórtice IVFA sobre este tema: "
    '"{tema}"\n\n'
    "Entrega EXACTAMENTE estos 3 bloques, listos para copiar y pegar:\n\n"
    "1) GUION REEL/TIKTOK (30-45 seg, con gancho en la primera línea, lenguaje hablado, "
    "indicaciones de corte de cámara entre corchetes)\n\n"
    "2) POST LINKEDIN (tono profesional/inversionista, 150-200 palabras, con 3 hashtags al final)\n\n"
    "3) CAPTION INSTAGRAM/WHATSAPP (corto, con emojis, para difusión masiva/movimiento popular, "
    "con llamado a la acción claro)\n\n"
    "No agregues explicaciones extra, solo los 3 bloques con sus títulos."
)

# ─────────────────────────────────────────────
# MEMORIA DE CONVERSACIÓN (en RAM, por chat_id)
# ─────────────────────────────────────────────
# Nota: esto es memoria de corto plazo por proceso. Para persistencia real
# entre reinicios de Render, engancha esto a tu GitHub Contents API
# (leer historial al iniciar, guardar tras cada intercambio).
conversation_history: dict[int, list[dict]] = {}
last_ai_response: dict[int, str] = {}
voice_mode: dict[int, bool] = {}  # True = responde con texto + nota de voz automática
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
# IMÁGENES — cascada: Qwen-Image (Hugging Face, alta calidad) → Pollinations (respaldo)
# ─────────────────────────────────────────────
from urllib.parse import quote


def generate_image_hf(prompt: str) -> bytes | None:
    """Genera imagen con Qwen-Image vía Hugging Face. Devuelve bytes de la imagen o None."""
    if not HF_API_KEY:
        return None
    headers = {"Authorization": f"Bearer {HF_API_KEY}"}
    elapsed = 0
    while elapsed <= HF_MAX_WAIT_SECONDS:
        try:
            resp = requests.post(HF_IMAGE_URL, headers=headers, json={"inputs": prompt}, timeout=45)
        except Exception as e:
            logger.warning("Fallo de red con Hugging Face: %s", str(e))
            return None

        if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image/"):
            return resp.content

        if resp.status_code == 503:
            # El modelo gratuito estaba "dormido" y se está cargando en el servidor — reintentamos
            logger.info("Qwen-Image cargando en Hugging Face, reintentando en %ss...", HF_POLL_INTERVAL)
            time.sleep(HF_POLL_INTERVAL)
            elapsed += HF_POLL_INTERVAL
            continue

        logger.warning("Hugging Face devolvió estado %s: %s", resp.status_code, resp.text[:200])
        return None

    logger.warning("Hugging Face no respondió a tiempo (modelo tardó demasiado en cargar).")
    return None


def generate_image_pollinations(prompt: str) -> bytes | None:
    """Genera imagen con Pollinations.ai (gratis, sin key). Devuelve bytes de la imagen o None."""
    try:
        encoded_prompt = quote(prompt)
        url = f"{POLLINATIONS_URL}/{encoded_prompt}?width=1024&height=1024&nologo=true"
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        if resp.headers.get("Content-Type", "").startswith("image/"):
            return resp.content
        logger.warning("Pollinations no devolvió una imagen válida.")
        return None
    except Exception as e:
        logger.warning("Fallo generando imagen con Pollinations: %s", str(e))
        return None


def generate_image(prompt: str) -> bytes | None:
    """Cascada: primero Qwen-Image (mejor calidad, requiere HF_API_KEY), luego Pollinations."""
    image_bytes = generate_image_hf(prompt)
    if image_bytes:
        logger.info("Imagen generada con Qwen-Image (Hugging Face).")
        return image_bytes

    logger.info("Hugging Face no disponible, usando Pollinations como respaldo.")
    return generate_image_pollinations(prompt)


# ─────────────────────────────────────────────
# HANDLERS DE TELEGRAM
# ─────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Benjamin Jarvis operativo. Escríbeme cualquier consulta sobre AGG y te respondo.\n"
        "Comandos:\n"
        "/voz — te leo la última respuesta\n"
        "/vozon — activo audio automático en cada respuesta\n"
        "/vozoff — vuelvo a solo texto\n"
        "/imagen <descripción> — genero una imagen\n"
        "/contenido <tema> — guion + post LinkedIn + caption listos para publicar"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    sent_message = await update.message.reply_text("🔄 Procesando solicitud...")

    ai_response = await asyncio.to_thread(generate_ai_response, chat_id, user_text)

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

    # Si el usuario activó el modo voz, además del texto le mando la nota de audio
    if voice_mode.get(chat_id) and not ai_response.startswith("⚠️"):
        await context.bot.send_chat_action(chat_id=chat_id, action="record_voice")
        audio_bytes = await asyncio.to_thread(generate_voice, ai_response)
        if audio_bytes:
            await context.bot.send_voice(chat_id=chat_id, voice=audio_bytes)
        else:
            logger.warning("Modo voz activo pero ElevenLabs no generó audio (revisar key o cuota).")


async def cmd_vozon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    voice_mode[chat_id] = True
    await update.message.reply_text(
        "🔊 Modo voz activado. Desde ahora respondo con texto + audio en cada mensaje.\n"
        "Usa /vozoff para volver a solo texto."
    )


async def cmd_vozoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    voice_mode[chat_id] = False
    await update.message.reply_text("🔇 Modo voz desactivado. Vuelvo a responder solo con texto.")


async def cmd_voz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = last_ai_response.get(chat_id)
    if not text:
        await update.message.reply_text("No tengo una respuesta previa para leer. Pregúntame algo primero.")
        return

    await context.bot.send_chat_action(chat_id=chat_id, action="record_voice")
    audio_bytes = await asyncio.to_thread(generate_voice, text)
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
    sent_message = await update.message.reply_text("🎨 Generando imagen (calidad alta, puede tardar 20-40 seg)...")
    image_bytes = await asyncio.to_thread(generate_image, prompt)

    if not image_bytes:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=sent_message.message_id,
            text="⚠️ No pude generar la imagen. Los dos servicios (Hugging Face y Pollinations) fallaron. Intenta de nuevo en un rato.",
        )
        return

    await context.bot.delete_message(chat_id=chat_id, message_id=sent_message.message_id)
    photo_file = io.BytesIO(image_bytes)
    photo_file.name = "benjamin_jarvis.png"
    await context.bot.send_photo(chat_id=chat_id, photo=photo_file, caption=f"🖼️ {prompt}")


# ─────────────────────────────────────────────
# CONTENIDO DE REDES — genera guion + post LinkedIn + caption en una sola pasada
# ─────────────────────────────────────────────
async def cmd_contenido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    tema = " ".join(context.args) if context.args else ""
    if not tema:
        await update.message.reply_text(
            "Uso: /contenido <tema>\nEj: /contenido avances de Vórtice esta semana"
        )
        return

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    sent_message = await update.message.reply_text("✍️ Generando contenido (guion + LinkedIn + caption)...")

    prompt = CONTENT_PROMPT_TEMPLATE.format(tema=tema)
    # chat_id se pasa solo para reutilizar la cascada de IA (no se guarda en el historial del chat)
    resultado = await asyncio.to_thread(generate_ai_response, chat_id, prompt)

    await context.bot.delete_message(chat_id=chat_id, message_id=sent_message.message_id)
    # Telegram limita cada mensaje a 4096 caracteres — partimos si hace falta
    for i in range(0, len(resultado), 4000):
        await update.message.reply_text(resultado[i:i + 4000])


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
    app.add_handler(CommandHandler("vozon", cmd_vozon))
    app.add_handler(CommandHandler("vozoff", cmd_vozoff))
    app.add_handler(CommandHandler("imagen", cmd_imagen))
    app.add_handler(CommandHandler("contenido", cmd_contenido))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    # Arranca el servidor HTTP mínimo en un hilo aparte, en paralelo al polling de Telegram
    threading.Thread(target=start_health_server, daemon=True).start()

    logger.info("Bot Benjamin Jarvis en ejecución...")
    app.run_polling()
