# Lista de modelos a utilizar en orden de prioridad
MODELS_TO_TRY = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
]


async def call_gemini(user_message: str, chat_id: int) -> str:
  if not GEMINI_API_KEY:
    return "⚠️ Falta la variable de entorno GEMINI_API_KEY."

  context = memory.get_context(chat_id)
  full_prompt = f"{SYSTEM_PROMPT}\n\n"
  if context:
    full_prompt += f"Historial reciente de esta conversación:\n{context}\n\n"
  full_prompt += f"Usuario: {user_message}"

  payload = {
      "contents": [{"role": "user", "parts": [{"text": full_prompt}]}],
      "generationConfig": {
          "temperature": 0.7,
          "maxOutputTokens": 1024,
      },
  }

  async with httpx.AsyncClient(timeout=45) as client:
    # Intenta con cada modelo de la lista si el anterior falla por cuota (429)
    for model_name in MODELS_TO_TRY:
      url = (
          "https://generativelanguage.googleapis.com/v1beta/models/"
          f"{model_name}:generateContent?key={GEMINI_API_KEY}"
      )
      try:
        r = await client.post(url, json=payload)
        data = r.json()

        if r.status_code == 200:
          return data["candidates"][0]["content"]["parts"][0]["text"]
        elif r.status_code == 429:
          logger.warning(
              f"Cuota agotada en {model_name} (429). Probando el siguiente"
              " modelo..."
          )
          continue  # Salta al siguiente modelo de la lista
        else:
          logger.error(f"Error en {model_name} ({r.status_code}): {data}")
          return f"Error en la IA ({r.status_code}). Intenta de nuevo."

      except Exception as e:
        logger.exception(f"Error conectando a {model_name}")
        continue

    return "⚠️ Todos los modelos de la IA están temporalmente ocupados. Por favor intenta en un minuto."
