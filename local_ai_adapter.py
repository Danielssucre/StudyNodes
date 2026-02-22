import requests
import os

class LocalAIAdapter:
    def __init__(self, model_name="dr-epi-es:latest", url="http://localhost:11434/api/generate"):
        self.model_name = model_name
        self.url = url

    def generate_battlecard(self, topic, context, full_title=None):
        """Generates a structured BattleCard in Markdown format."""
        display_title = full_title if full_title else topic
        
        prompt = f"""Actúa como el motor de evaluación del Protocolo Centurión.
TEMA: {display_title} ({topic} - Siglas verificadas)
CONTEXTO CIENTÍFICO: {context}

OBJETIVO: Genera una BattleCard estructurada con las siguientes secciones exactas:
# 🛡️ CARTA DE BATALLA: {topic}

## 1. 🚨 LA TRAMPA CLINICA
(Caso clínico breve de 3-4 líneas)

## 1.5 🔬 CIENCIA DE BASE
(Fisiopatología clave explicada con la Regla de los Porqués)

## 2. 🌳 ÁRBOL DE DECISIÓN
(Algoritmo o pasos de manejo diagnóstico/terapéutico)

## 3. 🔑 LLAVES MAESTRAS
(2-3 puntos clave indispensables)

## 5. 💡 PERLAS CLÍNICAS
(El dato de alto rendimiento para el examen)

## 6. 🏁 CHECK POINT
**Pregunta:** (MCQ difícil)
A) ...
B) ...
C) ...
D) ...

**Respuesta Correcta:** X
**Retroalimentación:** (Por qué X es correcta y las otras no)

IMPORTANTE: Responde ÚNICAMENTE con el Markdown estructurado."""

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 1500
            }
        }

        try:
            print(f"🤖 [LocalAI] Solicitando generación para: {topic}")
            response = requests.post(self.url, json=payload, timeout=60)
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            print(f"❌ [LocalAI] Error: {e}")
            return None

    def generate_response(self, prompt, temperature=0.1):
        """Generates a raw response without the BattleCard template."""
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": 1000
            }
        }
        try:
            print(f"🤖 [LocalAI] Solicitando respuesta general...")
            response = requests.post(self.url, json=payload, timeout=60)
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            print(f"❌ [LocalAI] Error en respuesta general: {e}")
            return None

    def save_card(self, topic, content, directory="BattleCards"):
        """Saves the generated content to a file."""
        if not os.path.exists(directory):
            os.makedirs(directory)
            
        filename = f"{topic.replace(' ', '_')}_GGUF.md"
        filepath = os.path.join(directory, filename)
        
        with open(filepath, "w") as f:
            f.write(content)
            
        return filepath
