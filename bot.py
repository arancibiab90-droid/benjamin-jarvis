import httpx
import os

# Credenciales
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROK_API_KEY = os.getenv("GROK_API_KEY")
DEEPSEEK_API_KEY = os.getenv(
    "DEEPSEEK_API_KEY", ""
)  # Opcional si agregas DeepSeek


async def call_multi_ai(user_message: str) -> str:
  """Intenta responder con Gemini; si la cuota se agota (429), conmuta automáticamente a Grok / DeepSeek."""
  full_prompt = f"{SYSTEM_PROMPT}\n\nUsuario: {user_message}"

  # --- INTENTO 1: Gemini (Modelos Flash Gratuitos) ---
  if GEMINI_API_KEY:
    gemini_models = [
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
    ]
    payload = {
        "contents": [{"role": "user", "parts": [{"text": full_prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1024},
    }
    async with httpx.AsyncClient(timeout=30) as client:
      for model in gemini_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        try:
          r = await client.post(url, json=payload)
          if r.status_code == 200:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
          elif r.status_code == 429:
            logger.warning(f"Cuota agotada en Gemini ({model}). Proban de nuevo...")
            continue
        except Exception as e:
          logger.error(f"Error en Gemini {model}: {e}")

  # --- INTENTO 2: Grok (xAI API) ---
  if GROK_API_KEY:
    headers = {
        "Authorization": f"Bearer {GROK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload_grok = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "model": "grok-beta",  # o el modelo asignado a tu cuota gratuita
        "temperature": 0.7,
    }
    async with httpx.AsyncClient(timeout=30) as client:
      try:
        r = await client.post(
            "https://api.x.ai/v1/chat/completions",
            headers=headers,
            json=payload_grok,
        )
        if r.status_code == 200:
          return r.json()["choices"][0]["message"]["content"]
        else:
          logger.warning(f"Grok respondió con código {r.status_code}: {r.text}")
      except Exception as e:
        logger.error(f"Error conectando a Grok: {e}")

  # --- INTENTO 3: DeepSeek (OpenAI-compatible Endpoint) ---
  if DEEPSEEK_API_KEY:
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload_ds = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "model": "deepseek-chat",
        "temperature": 0.7,
    }
    async with httpx.AsyncClient(timeout=30) as client:
      try:
        r = await client.post(
            "https://api.deepseek.com/chat/completions",
            headers=headers,
            json=payload_ds,
        )
        if r.status_code == 200:
          return r.json()["choices"][0]["message"]["content"]
      except Exception as e:
        logger.error(f"Error conectando a DeepSeek: {e}")

  return "⚠️ Todos los proveedores de IA (Gemini, Grok, DeepSeek) están temporalmente ocupados. Intenta en unos segundos."
