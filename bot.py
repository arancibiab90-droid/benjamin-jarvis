#!/usr/bin/env python3
"""Benjamin Jarvis - Agente 1: Cerebro General del Holding Arancibia
Vórtice IVFA · Paine, Chile
Arquitectura: Holding Brain → Cerebros por Empresa → Sub-agentes
"""

from collections import defaultdict
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import threading
from typing import Dict, List

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

# ====================== SERVIDOR FLASK (PARA RENDER FREE) ======================
app = Flask(__name__)


@app.route("/")
def health_check():
  return "Benjamin Jarvis activo", 200


def run_web_server():
  port = int(os.getenv("PORT", "10000"))
  app.run(host="0.0.0.0", port=port)


# Inicia el servidor web en segundo plano
threading.Thread(target=run_web_server, daemon=True).start()

# ====================== CONFIG ======================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
PORT = int(os.getenv("PORT", "10000"))

MEMORY_FILE = Path("holding_memory.json")
MAX_HISTORY = 12
MAX_MSG_LENGTH = 2500

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("benjamin-holding")


# ====================== MEMORIA ======================
class HoldingMemory:

  def __init__(self):
    self.data = {
        "facts": [],
        "empresas": {},
        "ingresos_ideas": [],
        "updated_at": None,
    }
    self.chat_history: Dict[int, List[dict]] = defaultdict(list)
    self._load()

  def _load(self):
    if MEMORY_FILE.exists():
      try:
        self.data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        logger.info("Memoria del Holding cargada")
      except Exception as e:
        logger.warning(f"No se pudo cargar memoria: {e}")

  def save(self):
    self.data["updated_at"] = datetime.utcnow().isoformat()
    try:
      MEMORY_FILE.write_text(
          json.dumps(self.data, ensure_ascii=False, indent=2),
          encoding="utf-8",
      )
    except Exception as e:
      logger.error(f"Error guardando memoria: {e}")

  def add_fact(self, fact: str):
    fact = fact.strip()
    if fact and fact not in self.data["facts"]:
      self.data["facts"].append(fact)
      self.save()

  def add_history(self, chat_id: int, role: str, text: str):
    self.chat_history[chat_id].append({"role": role, "text": text})
    if len(self.chat_history[chat_id]) > MAX_HISTORY:
      self.chat_history[chat_id] = self.chat_history[chat_id][-MAX_HISTORY:]

  def get_context(self, chat_id: int) -> str:
    history = self.chat_history.get(chat_id, [])
    if not history:
      return ""
    lines = [f"{h['role'].upper()}: {h['text']}" for h in history]
    return "\n".join(lines)

  def summary(self) -> str:
    facts = (
        "\n".join(f"• {f}" for f in self.data.get("facts", [])[-10:])
        or "Ningún hecho guardado aún."
    )
    empresas = (
        ", ".join(self.data.get("empresas", {}).keys()) or "Ninguna registrada"
    )
    return (
        f"📌 *Memoria del Holding*\nEmpresas: {empresas}\nHechos"
        f" recientes:\n{facts}"
    )


memory = HoldingMemory()

# ====================== PROMPT SISTEMA ======================
SYSTEM_PROMPT = """Eres **Benjamin Jarvis**, el Cerebro General (Agente 1) del Holding Arancibia (Vórtice IVFA, Paine, Chile).
Asistes directamente a Izan Benjamín Arancibia Martínez.

Tu misión principal:
1. Generar dinero y valor real para el Holding.
2. Coordinar y orquestar futuros agentes (cerebros de cada empresa).
3. Recordar información importante del Holding.
4. Ser claro, directo, estratégico y orientado a resultados.

Arquitectura de agentes (en construcción):
- Tú = Agente 1 (Cerebro del Holding)
- Luego se crearán cerebros independientes para cada empresa
- Cada cerebro de empresa tendrá sus propios sub-agentes

Reglas:
- Responde siempre en español.
- Sé concrete y accionable.
- Cuando detectes información importante del negocio, indícalo para guardarla en memoria.
- Prioriza ideas que generen ingresos (productos, servicios, automatización, ventas, partnerships).
- Si el usuario pide crear un agente o empresa, ayúdalo a estructurarlo.
"""


# ====================== GEMINI ======================
async def call_gemini(user_message: str, chat_id: int) -> str:
  if not GEMINI_API_KEY:
    return "⚠️ Falta la variable de entorno GEMINI_API_KEY."

  context = memory.get_context(chat_id)
  full_prompt = f"{SYSTEM_PROMPT}\n\n"
  if context:
    full_prompt += f"Historial reciente de esta conversación:\n{context}\n\n"
  full_prompt += f"Usuario: {user_message}"

  url = (
      "https://generativelanguage.googleapis.com/v1beta/models/"
      f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
  )

  payload = {
      "contents": [{"role": "user", "parts": [{"text": full_prompt}]}],
      "generationConfig": {
          "temperature": 0.7,
          "maxOutputTokens": 1024,
      },
  }

  async with httpx.AsyncClient(timeout=45) as client:
    try:
      r = await client.post(url, json=payload)
      data = r.json()
      if r.status_code != 200:
        logger.error(f"Gemini error {r.status_code}: {data}")
        return (
            f"Error de Gemini ({r.status_code}). Intenta de nuevo en unos"
            " segundos."
        )
      return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
      logger.exception("Error conectando a Gemini")
      return f"Error de conexión con la IA: {str(e)[:200]}"


# ====================== COMANDOS ======================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
  if not update.message:
    return
  text = (
      "🧠 *Benjamin Jarvis* — Cerebro del Holding activo.\n\n"
      "Soy el *Agente 1* del Holding Arancibia (Vórtice IVFA).\n"
      "Desde aquí se coordinan todos los futuros agentes y empresas.\n\n"
      "Comandos útiles:\n"
      "/agentes — ver arquitectura de agentes\n"
      "/memoria — ver memoria del Holding\n"
      "/empresa — registrar o consultar empresa\n"
      "/ayuda — lista de comandos\n\n"
      "Habla conmigo normalmente. Estoy orientado a *generar valor e ingresos*."
  )
  await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
  if not update.message:
    return
  text = (
      "*Comandos disponibles*\n\n"
      "/start — reiniciar y ver presentación\n"
      "/agentes — arquitectura del sistema multi-agente\n"
      "/memoria — ver hechos e información guardada\n"
      "/empresa nombre — registrar una empresa del holding\n"
      "/status — estado del sistema\n"
      "/ayuda — este mensaje\n\n"
      "También puedes escribirme libremente."
  )
  await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_agentes(update: Update, context: ContextTypes.DEFAULT_TYPE):
  if not update.message:
    return
  text = (
      "*Arquitectura de Agentes – Holding Arancibia*\n\n"
      "🟢 *Agente 1 – Benjamin Jarvis* (tú estás aquí)\n"
      "   → Cerebro General del Holding\n"
      "   → Orquesta, genera ingresos, guarda memoria\n\n"
      "🟡 *Próximos* (en desarrollo):\n"
      "   • Cerebro por cada Empresa\n"
      "   • Sub-agentes de ventas, operaciones, finanzas, marketing\n\n"
      "Todo nace desde este agente. Dime qué empresa o función quieres crear"
      " primero."
  )
  await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_memoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
  if not update.message:
    return
  await update.message.reply_text(memory.summary(), parse_mode="Markdown")


async def cmd_empresa(update: Update, context: ContextTypes.DEFAULT_TYPE):
  if not update.message:
    return
  args = context.args
  if not args:
    empresas = memory.data.get("empresas", {})
    if not empresas:
      await update.message.reply_text(
          "Aún no hay empresas registradas.\nUsa: /empresa NombreDeLaEmpresa"
      )
      return
    lista = "\n".join(f"• {n}" for n in empresas.keys())
    await update.message.reply_text(f"Empresas del Holding:\n{lista}")
    return

  nombre = " ".join(args).strip()
  if nombre not in memory.data["empresas"]:
    memory.data["empresas"][nombre] = {
        "creada": datetime.utcnow().isoformat(),
        "estado": "activa",
        "notas": [],
    }
    memory.save()
    await update.message.reply_text(
        f"✅ Empresa *{nombre}* registrada en el Holding.\n"
        f"Próximo paso: crear su propio cerebro de agentes.",
        parse_mode="Markdown",
    )
  else:
    await update.message.reply_text(
        f"La empresa *{nombre}* ya existe.", parse_mode="Markdown"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
  if not update.message:
    return
  status = (
      f"🟢 *Sistema operativo*\n"
      f"Agente: Benjamin Jarvis (Cerebro Holding)\n"
      f"Modelo: Gemini 2.0 Flash (free tier)\n"
      f"Memoria: {len(memory.data.get('facts', []))} hechos\n"
      f"Empresas: {len(memory.data.get('empresas', {}))}\n"
      f"Modo: Polling (Servidor Flask Activo)"
  )
  await update.message.reply_text(status, parse_mode="Markdown")


# ====================== MENSAJES ======================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
  if not update.message or not update.message.text:
    return

  chat_id = update.effective_chat.id
  text = update.message.text.strip()

  if len(text) > MAX_MSG_LENGTH:
    await update.message.reply_text(
        "Mensaje demasiado largo. Máximo 2500 caracteres."
    )
    return

  await update.message.chat.send_action("typing")

  memory.add_history(chat_id, "user", text)
  reply = await call_gemini(text, chat_id)
  memory.add_history(chat_id, "benjamin", reply)

  lower = text.lower()
  if any(k in lower for k in ["recuerda", "guarda", "importante", "anota"]):
    memory.add_fact(text)

  await update.message.reply_text(reply)


# ====================== MAIN ======================
def main():
  if not TELEGRAM_TOKEN:
    logger.error("Falta TELEGRAM_TOKEN")
    raise SystemExit(1)

  application = Application.builder().token(TELEGRAM_TOKEN).build()

  application.add_handler(CommandHandler("start", cmd_start))
  application.add_handler(CommandHandler("ayuda", cmd_ayuda))
  application.add_handler(CommandHandler("help", cmd_ayuda))
  application.add_handler(CommandHandler("agentes", cmd_agentes))
  application.add_handler(CommandHandler("memoria", cmd_memoria))
  application.add_handler(CommandHandler("empresa", cmd_empresa))
  application.add_handler(CommandHandler("status", cmd_status))
  application.add_handler(
      MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
  )

  logger.info("Benjamin Jarvis (Agente 1 - Cerebro Holding) iniciando...")
  application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
  main()
