import requests
import json

# Configuración del modelo local
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "dr-epi-es:latest"  # El modelo de 807MB que corresponde al GGUF del usuario

def generate_local_battlecard(topic, context):
    prompt = f"""Actúa como el motor de evaluación del Protocolo Centurión.
TEMA: {topic}
CONTEXTO CIENTÍFICO: {context}

OBJETIVO: Genera una BattleCard estructurada con las siguientes secciones:
1. 🚨 LA TRAMPA CLINICA: Breve caso clínico (3-4 líneas).
2. 🔬 CIENCIA DE BASE: Fisiopatología clave.
3. 🌳 ÁRBOL DE DECISIÓN: Algoritmo diagnóstico/manejo.
4. 🔑 LLAVES MAESTRAS: 2-3 puntos clave indispensables.
5. 💡 PERLAS CLÍNICAS: El "dato de oro" para el examen.
6. 🏁 CHECK POINT: Una pregunta MCQ con 4 opciones, respuesta correcta y retroalimentación con glosario.

IMPORTANTE: Responde en formato Markdown estricto."""

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 1024
        }
    }

    try:
        print(f"🚀 Generando BattleCard local para: {topic}...")
        response = requests.post(OLLAMA_URL, json=payload)
        response.raise_for_status()
        result = response.json()
        return result.get("response", "No se generó respuesta.")
    except Exception as e:
        return f"❌ Error llamando a Ollama: {e}"

if __name__ == "__main__":
    topic = "Apendicitis Aguda"
    context = "Dolor periumbilical que migra a fosa iliaca derecha. Signo de McBurney (+) en el examen físico. Escala de Alvarado > 7 indica alta probabilidad. Gold standard en adultos: TAC con contraste. Tratamiento: Apendicectomía."
    
    battlecard = generate_local_battlecard(topic, context)
    
    print("\n" + "="*50)
    print("SALIDA DEL MODELO LOCAL (Llama 3.2 1B):")
    print("="*50 + "\n")
    print(battlecard)
    
    with open("test_output_battlecard.md", "w") as f:
        f.write(battlecard)
    print(f"\n✅ Resultado guardado en 'test_output_battlecard.md'")
