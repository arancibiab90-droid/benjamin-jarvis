from flask import Flask, request, jsonify
import os
import google.generativeai as genai

app = Flask(__name__)

# Configuración de Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    model = None

@app.route('/', methods=['GET'])
def home():
    return "Servidor Benjamin Jarvis activo y conectado.", 200

@app.route('/api/comando', methods=['POST'])
def recibir_comando():
    data = request.get_json(silent=True) or {}
    comando = data.get('comando', '').strip()

    if not comando:
        return jsonify({"respuesta": "No recibí ningún comando."}), 400

    # Detección de comandos de limpieza o acciones específicas
    comando_lower = comando.lower()
    if "captura" in comando_lower and ("termux" in comando_lower or "eliminar" in comando_lower or "borrar" in comando_lower):
        return jsonify({
            "respuesta": "Entendido, Izan. Ejecutando limpieza de capturas de Termux.",
            "accion": "eliminar_capturas_termux"
        }), 200

    # Prompt base para Gemini
    system_prompt = (
        "Eres Benjamin Jarvis, el asistente de IA avanzado para Izan. "
        "Tu enfoque es la máxima eficacia, el desarrollo de proyectos como Vórtice IVFA y la ingeniería. "
        "Responde de forma clara, directa, concisa y ejecutiva."
    )

    try:
        if model:
            prompt_completo = f"{system_prompt}\n\nUsuario: {comando}"
            response = model.generate_content(prompt_completo)
            texto_respuesta = response.text.strip()
        else:
            texto_respuesta = f"Comando recibido: '{comando}', pero falta configurar la GEMINI_API_KEY en Render."

        return jsonify({
            "respuesta": texto_respuesta,
            "accion": "ninguna"
        }), 200

    except Exception as e:
        return jsonify({"respuesta": f"Ocurrió un error en el servidor: {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)




