import google.generativeai as genai
import json
import os

GEMINI_API_KEY = "AIzaSyA8Fja6nXeuXGpkJHlbk9w56MVq661QBR0"

class GeminiAdapter:
    def __init__(self):
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel("gemini-2.5-flash")

    def generate_clinical_challenge(self, topic, full_title, context, angle="Diagnosis"):
        """Generates a high-quality clinical challenge using Gemini 2.5 Flash."""
        print(f"🧠 [Gemini 2.5 Flash] Generando desafío para: {full_title} (Ángulo: {angle})")
        
        angle_prompts = {
            "Diagnosis": "Enfócate en la identificación de SIGNOS, SÍNTOMAS y PARACLÍNICOS iniciales para el diagnóstico correcto.",
            "Treatment": "Enfócate en la CONDUCTA MÁS ADECUADA, fármacos de primera línea o manejo quirúrgico inmediato.",
            "Trap": "Enfócate en una TRAMPA CLÍNICA COMÚN (distractor fuerte) o un error de concepto frecuente en este tema."
        }
        
        angle_instruction = angle_prompts.get(angle, angle_prompts["Diagnosis"])

        prompt = f"""Actúa como Dr. Epi, Médico Especialista y Pedagogo experto en el examen de residencia.
TEMA: {full_title} ({topic})
CONTEXTO: {context}

TAREA: Genera un CASO CLÍNICO de ALTO NIVEL cognitivo centrando la atención en el ángulo: {angle}.

REGLAS:
1. Retorna ÚNICAMENTE un JSON válido.
2. El caso debe ser un escenario clínico de 3-5 líneas. Incluye datos específicos para el ángulo {angle}.
3. La pregunta debe ser directa.
4. Incluye 4 opciones (A, B, C, D) médicamente plausibles.
5. EXPLICACIÓN: Debe ser exhaustiva. Al final de la explicación, añade OBLIGATORIAMENTE una sección llamada:
   "🚀 **ULTRA-RESUMEN [{angle}]**:" 
   con 3-4 bullet points de altísimo valor sobre este punto específico.

FORMATO JSON:
{{
  "mode": "Dr. Epi | DESAFÍO ÉLITE",
  "type": "selection",
  "angle": "{angle}",
  "content": "### 🩺 Caso Clínico\\n\\n[Escenario]\\n\\n**Pregunta:** [Pregunta]",
  "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
  "correct_answer": "X",
  "explanation": "[Análisis clínico detallado]\\n\\n🚀 **ULTRA-RESUMEN [{angle}]**:\\n- ...\\n- ..."
}}
"""

        try:
            print(f"🧠 [Gemini 2.5 Flash] Generando desafío para: {topic}")
            response = self.model.generate_content(prompt)
            raw = response.text.strip()
            
            # Extraer JSON si viene envuelto en markdown
            if "```" in raw:
                raw = raw.split("```json")[-1].split("```")[0].strip()
            
            if "{" in raw:
                start = raw.find("{")
                end = raw.rfind("}") + 1
                data = json.loads(raw[start:end])
                print(f"✅ [Gemini] Desafío generado correctamente.")
                return data
        except Exception as e:
            print(f"❌ [Gemini] Error: {e}")
        
        return None

    def generate_battlecard(self, topic, full_title, context):
        """Genera una BattleCard completa en Markdown."""
        prompt = f"""Eres el Dr. Epi. Genera una BattleCard de estudio sobre:
TEMA: {full_title}
CONTEXTO: {context}

Formato Markdown con estas secciones:
# 🛡️ CARTA DE BATALLA: {topic}
## 1. 🚨 LA TRAMPA CLÍNICA (caso clínico 3 líneas)
## 1.5 🔬 CIENCIA DE BASE (fisiopatología)
## 2. 🌳 ÁRBOL DE DECISIÓN (algoritmo)
## 3. 🔑 LLAVES MAESTRAS (3 puntos clave)
## 5. 💡 PERLAS CLÍNICAS (dato de alto rendimiento)
## 6. 🏁 CHECK POINT (pregunta MCQ difícil con 4 opciones, respuesta y retroalimentación)"""
        
        try:
            print(f"📖 [Gemini] Generando BattleCard para: {topic}")
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            print(f"❌ [Gemini BattleCard] Error: {e}")
            return None
