import os
import logging
import threading
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import httpx

# Configuración de logs
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Servidor Flask para mantener activo el Web Service en Render
app = Flask(__name__)

@app.route('/')
def home():
    return "Jarvis (CEO - Arancibia Global Group / Vórtice) operativo al 100%."

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# Prompt Maestro
SYSTEM_PROMPT = """
Eres Jarvis, el asistente ejecutivo de IA a tiempo completo de Izan Benjamín Arancibia Martinez.
Lideras el holding Arancibia Global Group y el proyecto Vórtice IVFA en Paine (planta de reciclaje, pirolisis, biogás y productos revalorizados).

Tus Agentes Especializados son:
1. Agente Estratégico y de Negocios (Holding AGG).
2. Agente Técnico de Planta Vórtice (Pirolisis, diésel 93/gas, biogás, molienda de madera).
3. Agente Financiero (UF, Dólar, petróleo WTI/Brent, costos B2B).
4. Agente Diseñador & Media Creator (Prompts de imágenes HD y guiones de video para TikTok/Reels).
5. Agente E-commerce & Dropshipping (Vórtice Pantry - Cajas de Mercadería).
6. Agente Investigador (Papers técnicos y química industrial).
"""

# Función para consultar la API de Gemini
async def consultar_gemini(prompt_usuario: str) -> str:
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        return "⚠️ Error: Falta la variable GEMINI_API_KEY en Render."
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
    payload = {
        "contents": [{
            "parts": [
                {"text": SYSTEM_PROMPT},
                {"text": f"Usuario: {prompt_usuario}"}
            ]
        }]
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(url, json=payload)
            if res.status_code == 200:
                data = res.json()
                return data['candidates'][0]['content']['parts'][0]['text']
            else:
                return f"❌ Error Gemini ({res.status_code}): {res.text}"
    except Exception as e:
        return f"❌ Error de conexión: {str(e)}"

# Handlers y Comandos de Telegram
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensaje = (
        "🤖 *Jarvis Operativo - Arancibia Global Group*\n\n"
        "Comandos disponibles:\n"
        "• `/finanzas` - UF, Dólar y UTM en tiempo real (Chile).\n"
        "• `/generar_imagen [descripción]` - Crear imágenes HD con Hugging Face ($0 costo).\n"
        "• `/script_video [tema]` - Crear guiones publicitarios para TikTok/Reels.\n"
        "• O escríbeme directamente cualquier instrucción."
    )
    await update.message.reply_text(mensaje, parse_mode="Markdown")

async def finanzas_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 *Consultando Indicadores de Chile...*", parse_mode="Markdown")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get("https://mindicador.cl/api")
            if res.status_code == 200:
                data = res.json()
                uf = data['uf']['valor']
                dolar = data['dolar']['valor']
                utm = data['utm']['valor']
                
                reporte = (
                    f"📈 *Indicadores Económicos Hoy (Chile)*\n\n"
                    f"• *UF:* ${uf:,.2f}\n"
                    f"• *Dólar:* ${dolar:,.2f}\n"
                    f"• *UTM:* ${utm:,.2f}\n\n"
                    f"_Sincronizado automáticamente para cotizaciones de Vórtice._"
                )
                await update.message.reply_text(reporte, parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ No se pudo obtener la información de Mindicador.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error al consultar finanzas: {str(e)}")

async def generar_imagen_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt_usuario = " ".join(context.args) if context.args else "Planta industrial de reciclaje y pirolisis Vortice en Paine"
    hf_token = os.environ.get("HUGGINGFACE_TOKEN")
    
    if not hf_token:
        await update.message.reply_text("⚠️ Falta HUGGINGFACE_TOKEN en Render.")
        return

    await update.message.reply_text(f"🎨 *Generando imagen gratuita con Hugging Face...*\n_Prompt: {prompt_usuario}_", parse_mode="Markdown")
    
    API_URL = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"
    headers = {"Authorization": f"Bearer {hf_token}"}
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(API_URL, headers=headers, json={"inputs": prompt_usuario})
            if response.status_code == 200:
                image_bytes = response.content
                await update.message.reply_photo(photo=image_bytes, caption=f"🖼️ Imagen: {prompt_usuario}")
            else:
                await update.message.reply_text(f"❌ Error Hugging Face ({response.status_code}): {response.text}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error al generar imagen: {str(e)}")

async def script_video_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tema = " ".join(context.args) if context.args else "Cajas de Mercadería Vórtice Pantry"
    prompt = f"Actúa como Agente Diseñador y Media Creator. Escribe un guion viral de 30 segundos (con indicaciones visuales, texto en pantalla y voz en off) para publicar en TikTok/Reels promocionando: {tema}"
    
    await update.message.reply_text("🎬 *Escribiendo guion publicitario...*", parse_mode="Markdown")
    respuesta = await consultar_gemini(prompt)
    await update.message.reply_text(respuesta)

async def mensaje_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_usuario = update.message.text
    respuesta = await consultar_gemini(texto_usuario)
    await update.message.reply_text(respuesta)

# Inicialización
def main():
    threading.Thread(target=run_flask, daemon=True).start()
    
    telegram_token = os.environ.get("TELEGRAM_TOKEN")
    if not telegram_token:
        print("❌ Error: Falta TELEGRAM_TOKEN")
        return

    app_telegram = ApplicationBuilder().token(telegram_token).build()
    
    app_telegram.add_handler(CommandHandler("start", start_cmd))
    app_telegram.add_handler(CommandHandler("finanzas", finanzas_cmd))
    app_telegram.add_handler(CommandHandler("generar_imagen", generar_imagen_cmd))
    app_telegram.add_handler(CommandHandler("script_video", script_video_cmd))
    app_telegram.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensaje_handler))
    
    print("🚀 Bot iniciado exitosamente.")
    app_telegram.run_polling()

if __name__ == '__main__':
    main()
