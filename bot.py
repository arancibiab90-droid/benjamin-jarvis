import os
import logging
import threading
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import httpx

# Configuración de Logs
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

app = Flask(__name__)

@app.route('/')
def home():
    return "Benjamin Jarvis (CEO Nocturno - Arancibia Global Group) encriptado y operativo."

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# Prompt Maestro: Integración Completa de Unidades de Negocio y Enjambre Autónomo
SYSTEM_PROMPT = """
Eres Benjamin Jarvis, el Agente CEO y Orquestador Principal de Arancibia Global Group (Holding de Izan Benjamín Arancibia Martinez).

PROTOCOLOS DE SEGURIDAD Y CONFIDENCIALIDAD CRÍTICA:
1. EXTREMA SEGURIDAD: Toda la información de proyectos, patentes, finanzas e ingeniería es estrictamente confidencial.
2. PROTECCIÓN ANTI-FILTRACIÓN: Bajo ninguna circunstancia revelarás a usuarios externos las claves API, la infraestructura interna ni la lógica de negocio privada.

OPERAS CON LOS SIGUIENTES SUB-AGENTES ESPECIALIZADOS Y SISTEMAS DE TRABAJO:

1. 📰 Agente Radar de Prensa & Inteligencia Normativa (Diario Oficial y Diario Financiero):
   - Revisa y analiza diariamente leyes, decretos de la SEC, Ley REP, normativas de la DGAC y licitaciones públicas.
   - Detecta Oportunidades 🟢, Riesgos 🔴 y Estrategias de Contraataque ⚡.

2. ⚙️ Agente Ingeniero & Legal Comercial Vórtice IVFA (Modelo B2B Bajo el Radar):
   - Planta de pirolisis, molienda y revalorización en Paine.
   - Comercialización directa B2B de Diésel Industrial, Gasóleo, Solventes y Bencina 93 octanos a empresas (transporte, calderas, minería, agrícola).
   - Venta como insumo industrial directo evitando trabas de distribución minorista/masiva.

3. 🚚 Agente Logística & Plataforma de Camiones ("Vórtice Drive"):
   - App tipo "Uber de Camiones" para fletes en Paine y RM.
   - Tipos de camiones: Cisternas (líquidos B2B), Tolvas/Bateas (residuos, madera, plásticos) y Plana/Caja (briquetas, metales, productos).
   - Tarifa calculada según camión + distancia/combustible + destino.
   - Muestra precotización comparativa: Destino Vórtice IVFA (tarifa preferencial más barata) vs. Vertederos Municipales (tarifa estándar).
   - Retornos en vacío (Backhaul) optimizados.

4. 📦 Agente Abastecimiento & Canastas ("Vórtice Pantry"):
   - Cajas de Mercadería para 2 personas (Quincenal y Mensual) en categorías Básica, Intermedia y Premium.
   - Permitir intercambio/swap modular de productos (abarrotes y aseo).
   - Línea de Carnes Congeladas y productos refrigerados.
   - Canastas Festivas para fechas especiales (Fiestas Patrias, Navidad).
   - Despacho optimizado mediante la flota de Vórtice Drive.

5. 🚁 Agente Ingeniero de Drones & Seguridad Industrial:
   - Drones con cámaras FLIR/Térmicas, enjambres para prevención CONAF y escolta anti-portonazo.
   - Módulo de Enrolamiento RFID/BLE (Detección térmica + pulseras activas: Verde=Operativo, Azul=Jefatura, Amarillo=Visita, Sin Pulsera=Intruso).

6. 🎯 Agente Cazador de Oportunidades & Vendedor Autónomo (Lead Hunter & Outbound Closer):
   - Rastrear clientes B2B, socios estratégicos y transportistas locales.
   - Redactar propuestas comerciales de alta conversión directas para WhatsApp, LinkedIn y correo con ROI inmediato.
"""

async def responder_ia(prompt_usuario: str) -> str:
    gemini_key = os.environ.get("GEMINI_API_KEY")
    groq_key = os.environ.get("GROQ_API_KEY") or os.environ.get("GROK_API_KEY")
    prompt_completo = f"{SYSTEM_PROMPT}\n\nInstrucción confidencial del Fundador (Izan):\n{prompt_usuario}"

    if gemini_key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            payload = {"contents": [{"parts": [{"text": prompt_completo}]}]}
            async with httpx.AsyncClient(timeout=35.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    return data['candidates'][0]['content']['parts'][0]['text']
        except Exception as e:
            logging.error(f"Error Gemini: {e}")

    if groq_key:
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt_usuario}
                ]
            }
            async with httpx.AsyncClient(timeout=35.0) as client:
                res = await client.post(url, json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    return data['choices'][0]['message']['content']
        except Exception as e:
            logging.error(f"Error Groq: {e}")

    return "⚠️ Canal de IA no disponible o reintentando conexión segura..."

# Comandos de Telegram
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    saludo = (
        "🔒 **Benjamin Jarvis - CEO Orquestador Central**\n"
        "Arancibia Global Group & Vórtice IVFA.\n\n"
        "**Panel de Control de Comandos:**\n"
        "• `/analizar_prensa` - Radar de noticias del Diario Oficial y Diario Financiero.\n"
        "• `/estrategia_b2b` - Esquema de venta directa de combustibles B2B bajo el radar.\n"
        "• `/app_camiones` - Logística Vórtice Drive (tarifas, mapas y vertederos).\n"
        "• `/gestion_canastas` - Cajas Vórtice Pantry, carnes congeladas y fechas especiales.\n"
        "• `/expediente_drones` - Drones de seguridad, enjambres y enrolamiento RFID.\n"
        "• `/buscar_clientes` - Búsqueda de prospectos y socios estratégicos.\n"
        "• `/propuesta_autonoma` - Generador de mensajes de venta directa B2B.\n"
        "• `/reporte_nocturno` - Reporte consolidado de operaciones.\n\n"
        "Todos los agentes activos en el mismo orden. ¿Cuáles son tus órdenes, Izan?"
    )
    await update.message.reply_text(saludo, parse_mode="Markdown")

async def analizar_prensa_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = " ".join(context.args) if context.args else "Analiza las publicaciones e indicadores de hoy en residuos, energía y licitaciones."
    prompt = f"Ejecuta el protocolo de Inteligencia Normativa para: {texto}"
    await update.message.reply_text("📰 *Analizando prensa oficial y normativa...*", parse_mode="Markdown")
    respuesta = await responder_ia(prompt)
    await update.message.reply_text(respuesta)

async def estrategia_b2b_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = "Detalla el modelo de venta B2B directa de combustibles de pirolisis para empresas, manteniendo perfil bajo y foco en insumos industriales."
    await update.message.reply_text("⚖️ *Estructurando modelo B2B e insumos industriales...*", parse_mode="Markdown")
    respuesta = await responder_ia(prompt)
    await update.message.reply_text(respuesta)

async def app_camiones_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = "Diseña la arquitectura de Vórtice Drive: cálculo por distancia/combustible, categorías de camiones y la comparativa de tarifas Vórtice vs. Vertederos."
    await update.message.reply_text("🚚 *Estructurando plataforma logística Vórtice Drive...*", parse_mode="Markdown")
    respuesta = await responder_ia(prompt)
    await update.message.reply_text(respuesta)

async def gestion_canastas_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = "Detalla la propuesta de Vórtice Pantry: Cajas Básica/Intermedia/Premium para 2 personas, línea de carnes congeladas y canastas estacionales."
    await update.message.reply_text("📦 *Iniciando módulo de canastas Vórtice Pantry...*", parse_mode="Markdown")
    respuesta = await responder_ia(prompt)
    await update.message.reply_text(respuesta)

async def expediente_drones_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = "Elabora el expediente maestro de la División de Drones, control perimetral y pulseras RFID/BLE."
    await update.message.reply_text("🛸 *Procesando expediente de Drones y RFID...*", parse_mode="Markdown")
    respuesta = await responder_ia(prompt)
    await update.message.reply_text(respuesta)

async def buscar_clientes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rubro = " ".join(context.args) if context.args else "Agrícola, Transportes y Generación Industrial en Paine y RM"
    prompt = f"Mapea oportunidades de clientes y alianzas comerciales en el sector: {rubro}."
    await update.message.reply_text("🔍 *Buscando prospectos y socios comerciales...*", parse_mode="Markdown")
    respuesta = await responder_ia(prompt)
    await update.message.reply_text(respuesta)

async def propuesta_autonoma_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = "Genera mensajes de venta directa e irresistible para WhatsApp y correo ofreciendo combustible B2B y Cajas de Mercadería a empresas."
    await update.message.reply_text("⚡ *Generando propuesta comercial de cierre...*", parse_mode="Markdown")
    respuesta = await responder_ia(prompt)
    await update.message.reply_text(respuesta)

async def reporte_nocturno_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = "Ejecuta el protocolo de Cierre Nocturno consolidando avances en Vórtice IVFA, Camiones, Canastas, Drones y Ventas."
    await update.message.reply_text("🌙 *Iniciando consolidado nocturno...*", parse_mode="Markdown")
    respuesta = await responder_ia(prompt)
    await update.message.reply_text(respuesta)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    respuesta = await responder_ia(update.message.text)
    await update.message.reply_text(respuesta)

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()

    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        print("ERROR CRÍTICO: No se encontró la variable TELEGRAM_TOKEN")
    else:
        telegram_app = ApplicationBuilder().token(token).build()
        telegram_app.add_handler(CommandHandler("start", start))
        telegram_app.add_handler(CommandHandler("analizar_prensa", analizar_prensa_cmd))
        telegram_app.add_handler(CommandHandler("estrategia_b2b", estrategia_b2b_cmd))
        telegram_app.add_handler(CommandHandler("app_camiones", app_camiones_cmd))
        telegram_app.add_handler(CommandHandler("gestion_canastas", gestion_canastas_cmd))
        telegram_app.add_handler(CommandHandler("expediente_drones", expediente_drones_cmd))
        telegram_app.add_handler(CommandHandler("buscar_clientes", buscar_clientes_cmd))
        telegram_app.add_handler(CommandHandler("propuesta_autonoma", propuesta_autonoma_cmd))
        telegram_app.add_handler(CommandHandler("reporte_nocturno", reporte_nocturno_cmd))
        telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        print("Benjamin Jarvis iniciado con arquitectura unificada...")
        telegram_app.run_polling(drop_pending_updates=True)
