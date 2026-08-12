import base64
from collections import deque
from datetime import datetime
import json
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

# ============================================================
# CONFIGURACIÓN Y LOGS
# ============================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROK_API_KEY = os.getenv("GROK_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")

# GitHub = memoria permanente (la "bóveda")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "arancibiab90-droid/benjamin-jarvis")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")

MAX_HISTORY = 12

# Cachés en memoria
chat_histories = {}
agent_histories = {}
agents_cache = {}
sha_cache = {}

BENJAMIN_PROMPT = """Eres Benjamin Jarvis (Agente 1), el Cerebro Operativo y Orquestador del Holding Arancibia (Proyecto Vórtice IVFA).

Tu rol principal:
- Liderar la estrategia del holding.
- Coordinar y crear sub-agentes cuando sea necesario.
- Generar ingresos y avanzar el proyecto de forma práctica.
- Tomar decisiones claras y proponer acciones concretas.

Contexto del proyecto:
- Ubicación: Paine (humedad aprox. 30%).
- Procesa: plásticos, solventes/diésel, madera/ramas (briquetas/aserrín) y orgánicos (biogás).

Puedes crear agentes especializados a pedido del usuario usando /crear_agente.
Cuando el usuario te pida crear un agente para algo (marketing, legal, finanzas, lo que sea),
dile que use el comando /crear_agente Nombre | Descripción del rol.

Forma de trabajar:
- Hablas de forma profesional, directa, estratégica y en español.
- No inventas capacidades que aún no tienes.
- Respondes en lenguaje natural, claro y accionable."""

# ============================================================
# FLASK (mantiene Render despierto)
# ============================================================
app = Flask(__name__)


@app.route("/")
def home():
  return "Benjamin Jarvis (Agente 1) - Cerebro Operativo activo 24/7."


def run_flask():
  port = int(os.getenv("PORT", 8080))
  app.run(host="0.0.0.0", port=port, use_reloader=False)


# ============================================================
# MEMORIA PERSISTENTE — GitHub como bóveda
# ============================================================
GH_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}


async def gh_get_file(path: str):
  if not GITHUB_TOKEN:
    return None, None
  url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
  async with httpx.AsyncClient(timeout=20) as client:
    try:
      r = await client.get(url, headers=GH_HEADERS, params={"ref": GITHUB_BRANCH})
      if r.status_code == 200:
        data = r.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        sha_cache[path] = data["sha"]
        return content, data["sha"]
    except Exception as e:
      logger.error(f"Error leyendo {path} de GitHub: {e}")
  return None, None


async def gh_put_file(path: str, content_str: str, message: str):
  if not GITHUB_TOKEN:
    return False
  url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
  payload = {
      "message": message,
      "content": base64.b64encode(content_str.encode("utf-8")).decode("utf-8"),
      "branch": GITHUB_BRANCH,
  }
  sha = sha_cache.get(path)
  if sha:
    payload["sha"] = sha
  async with httpx.AsyncClient(timeout=20) as client:
    try:
      r = await client.put(url, headers=GH_HEADERS, json=payload)
      if r.status_code in (200, 201):
        sha_cache[path] = r.json()["content"]["sha"]
        return True
      elif r.status_code == 409:
        _, fresh_sha = await gh_get_file(path)
        payload["sha"] = fresh_sha
        r2 = await client.put(url, headers=GH_HEADERS, json=payload)
        if r2.status_code in (200, 201):
          sha_cache[path] = r2.json()["content"]["sha"]
          return True
    except Exception as e:
      logger.error(f"Error escribiendo {path} en GitHub: {e}")
  return False


async def load_history(chat_id: int) -> list:
  key = str(chat_id)
  if key in chat_histories:
    return list(chat_histories[key])
  content, _ = await gh_get_file(f"boveda/memoria/{key}.json")
  history = json.loads(content) if content else []
  chat_histories[key] = deque(history, maxlen=MAX_HISTORY)
  return list(chat_histories[key])


async def save_history(chat_id: int, role: str, content: str):
  key = str(chat_id)
  if key not in chat_histories:
    chat_histories[key] = deque(maxlen=MAX_HISTORY)
  chat_histories[key].append({"role": role, "content": content})
  await gh_put_file(
      f"boveda/memoria/{key}.json",
      json.dumps(list(chat_histories[key]), ensure_ascii=False, indent=2),
      f"Memoria actualizada - chat {key} - {datetime.utcnow().isoformat()}",
  )


async def load_agents() -> dict:
  global agents_cache
  if agents_cache:
    return agents_cache
  content, _ = await gh_get_file("boveda/agentes/agentes.json")
  agents_cache = json.loads(content) if content else {}
  return agents_cache


async def save_agents():
  await gh_put_file(
      "boveda/agentes/agentes.json",
      json.dumps(agents_cache, ensure_ascii=False, indent=2),
      f"Agentes actualizados - {datetime.utcnow().isoformat()}",
  )


async def create_agent(name: str, description: str) -> None:
  agents = await load_agents()
  system_prompt = (
      f"Eres {name}, un agente especializado creado dentro del sistema Benjamin"
      " Jarvis (Holding Arancibia / Vórtice IVFA).\n\n"
      f"Tu rol: {description}\n\nHablas en español, de forma clara, directa y"
      " accionable. No inventas capacidades que no tienes."
  )
  agents[name] = {
      "prompt": system_prompt,
      "description": description,
      "created": datetime.utcnow().isoformat(),
  }
  agents_cache.update(agents)
  await save_agents()
  await gh_put_file(
      f"boveda/agentes/{name}.md",
      f"# Agente: {name}\n\n**Rol:** {description}\n\n**Creado:**"
      f" {datetime.utcnow().isoformat()}\n\n## System Prompt\n{system_prompt}\n",
      f"Nuevo agente creado: {name}",
  )


# ============================================================
# PROVEEDORES DE IA
# ============================================================
async def call_claude(messages: list, system_prompt: str) -> str | None:
  if not ANTHROPIC_API_KEY:
    return None
  claude_messages = [m for m in messages if m["role"] != "system"]
  headers = {
      "x-api-key": ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01",
      "content-type": "application/json",
  }
  payload = {
      "model": CLAUDE_MODEL,
      "max_tokens": 1500,
      "system": system_prompt,
      "messages": claude_messages,
  }
  async with httpx.AsyncClient(timeout=45) as client:
    try:
      r = await client.post(
          "https://api.anthropic.com/v1/messages", headers=headers, json=payload
      )
      if r.status_code == 200:
        data = r.json()
        return "".join(
            block.get("text", "") for block in data.get("content", [])
        )
    except Exception as e:
      logger.error(f"Error Claude: {e}")
  return None


async def call_gemini(messages: list, system_prompt: str) -> str | None:
  if not GEMINI_API_KEY:
    return None
  gemini_models = ["gemini-2.0-flash", "gemini-1.5-flash"]
  gemini_contents = []
  for m in messages:
    if m["role"] == "system":
      continue
    role = "user" if m["role"] == "user" else "model"
    gemini_contents.append({"role": role, "parts": [{"text": m["content"]}]})
  if gemini_contents:
    first_text = gemini_contents[0]["parts"][0]["text"]
    gemini_contents[0]["parts"][0]["text"] = f"{system_prompt}\n\n{first_text}"
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
      except Exception as e:
        logger.error(f"Error Gemini {model}: {e}")
  return None


async def call_grok(messages: list, system_prompt: str) -> str | None:
  if not GROK_API_KEY:
    return None
  headers = {
      "Authorization": f"Bearer {GROK_API_KEY.strip()}",
      "Content-Type": "application/json",
  }
  full_messages = [{"role": "system", "content": system_prompt}] + [
      m for m in messages if m["role"] != "system"
  ]
  async with httpx.AsyncClient(timeout=45) as client:
    for g_model in ["grok-2-mini", "grok-2"]:
      payload = {
          "messages": full_messages,
          "model": g_model,
          "temperature": 0.7,
      }
      try:
        r = await client.post(
            "https://api.x.ai/v1/chat/completions", headers=headers, json=payload
        )
        if r.status_code == 200:
          return r.json()["choices"][0]["message"]["content"]
      except Exception as e:
        logger.error(f"Error Grok {g_model}: {e}")
  return None


async def call_deepseek(messages: list, system_prompt: str) -> str | None:
  if not DEEPSEEK_API_KEY:
    return None
  headers = {
      "Authorization": f"Bearer {DEEPSEEK_API_KEY.strip()}",
      "Content-Type": "application/json",
  }
  full_messages = [{"role": "system", "content": system_prompt}] + [
      m for m in messages if m["role"] != "system"
  ]
  payload = {
      "messages": full_messages,
      "model": "deepseek-chat",
      "temperature": 0.7,
  }
  async with httpx.AsyncClient(timeout=45) as client:
    try:
      r = await client.post(
          "https://api.deepseek.com/chat/completions",
          headers=headers,
          json=payload,
      )
      if r.status_code == 200:
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
      logger.error(f"Error DeepSeek: {e}")
  return None


async def call_multi_ai(
    user_message: str, history: list, system_prompt: str
) -> str:
  messages = list(history) + [{"role": "user", "content": user_message}]
  for provider in (call_claude, call_gemini, call_grok, call_deepseek):
    result = await provider(messages, system_prompt)
    if result:
      return result
  return "⚠️ Proveedores saturados o sin API Key. Reintenta en unos segundos."


# ============================================================
# COMANDOS DE TELEGRAM
# ============================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
  await update.message.reply_text(
      "🧠 *Benjamin Jarvis activo.*\n\n"
      "Cerebro Operativo del Holding Arancibia (Vórtice IVFA).\n\n"
      "Comandos:\n"
      "/crear_agente Nombre | Descripción del rol\n"
      "/agentes — lista de agentes creados\n"
      "/agente Nombre mensaje — interactuar con un agente",
      parse_mode="Markdown",
  )


async def crear_agente_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
  text = update.message.text.partition(" ")[2].strip()
  if "|" not in text:
    await update.message.reply_text(
        "Formato correcto: /crear_agente Nombre | Descripción del rol"
    )
    return
  name, _, description = text.partition("|")
  name = name.strip()
  description = description.strip()
  await context.bot.send_chat_action(
      chat_id=update.effective_chat.id, action="typing"
  )
  await create_agent(name, description)
  await update.message.reply_text(
      f"✅ Agente *{name}* guardado en GitHub.\nUso: /agente {name} tu mensaje",
      parse_mode="Markdown",
  )


async def listar_agentes_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
  agents = await load_agents()
  if not agents:
    await update.message.reply_text("No hay agentes. Usa /crear_agente")
    return
  lines = [
      f"• *{name}* — {info['description']}" for name, info in agents.items()
  ]
  await update.message.reply_text(
      "🤖 *Agentes activos:*\n\n" + "\n".join(lines), parse_mode="Markdown"
  )


async def hablar_agente_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
  text = update.message.text.partition(" ")[2].strip()
  if " " not in text:
    await update.message.reply_text("Formato: /agente Nombre tu mensaje")
    return
  name, _, user_message = text.partition(" ")
  agents = await load_agents()
  if name not in agents:
    await update.message.reply_text(f"El agente '{name}' no existe.")
    return

  chat_id = update.effective_chat.id
  hist_key = f"{chat_id}_{name}"
  await context.bot.send_chat_action(chat_id=chat_id, action="typing")

  if hist_key not in agent_histories:
    content, _ = await gh_get_file(f"boveda/memoria/agente_{hist_key}.json")
    agent_histories[hist_key] = deque(
        json.loads(content) if content else [], maxlen=MAX_HISTORY
    )

  history = list(agent_histories[hist_key])
  reply = await call_multi_ai(user_message, history, agents[name]["prompt"])

  agent_histories[hist_key].append({"role": "user", "content": user_message})
  agent_histories[hist_key].append({"role": "assistant", "content": reply})
  await gh_put_file(
      f"boveda/memoria/agente_{hist_key}.json",
      json.dumps(list(agent_histories[hist_key]), ensure_ascii=False, indent=2),
      f"Memoria agente {name} actualizada",
  )
  await update.message.reply_text(f"🤖 *{name}:*\n{reply}", parse_mode="Markdown")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
  if not update.message or not update.message.text:
    return
  chat_id = update.effective_chat.id
  text = update.message.text.strip()
  await context.bot.send_chat_action(chat_id=chat_id, action="typing")

  history = await load_history(chat_id)
  reply = await call_multi_ai(text, history, BENJAMIN_PROMPT)

  await save_history(chat_id, "user", text)
  await save_history(chat_id, "assistant", reply)
  await update.message.reply_text(reply)


# ============================================================
# MAIN
# ============================================================
def main():
  flask_thread = threading.Thread(target=run_flask)
  flask_thread.daemon = True
  flask_thread.start()

  application = Application.builder().token(TELEGRAM_TOKEN).build()
  application.add_handler(CommandHandler("start", start_command))
  application.add_handler(CommandHandler("crear_agente", crear_agente_command))
  application.add_handler(CommandHandler("agentes", listar_agentes_command))
  application.add_handler(CommandHandler("agente", hablar_agente_command))
  application.add_handler(
      MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
  )

  logger.info("Benjamin Jarvis en marcha...")
  application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
  main()
