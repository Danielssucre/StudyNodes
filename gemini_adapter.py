import google.generativeai as genai
import json
import os

GEMINI_API_KEY = "AIzaSyBGaMNp3MiGXbLGWIkIK09NlH7KVfKllNM"

class GeminiAdapter:
    def __init__(self):
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel("gemini-2.5-flash")

    def _robust_json_extract(self, raw_text):
        """Extrae y limpia JSON de forma extrema."""
        try:
            # 1. Quitar bloques markdown
            cleaned = raw_text.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[-1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[-1].split("```")[0].strip()

            # 2. Encontrar límites de llaves
            import re
            start_match = re.search(r'\{', cleaned)
            end_match = re.findall(r'\}', cleaned)
            
            if not start_match or not end_match:
                return None
                
            start_idx = start_match.start()
            end_idx = cleaned.rfind('}') + 1
            json_str = cleaned[start_idx:end_idx]

            # 3. Limpieza de caracteres de control ilegales en JSON
            # Reemplazar saltos de línea y tabulaciones REALES dentro de strings por sus versiones escapadas
            # Pero solo si están dentro de comillas (esto es difícil con regex simple, mejor limpiar todo lo no imprimible)
            json_str = "".join(ch for ch in json_str if ord(ch) >= 32 or ch in "\n\r\t")
            
            # 4. Arreglar comas finales (trailing commas)
            json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
            
            # 5. Arreglar comillas inteligentes
            json_str = json_str.replace("“", "\"").replace("”", "\"").replace("‘", "'").replace("’", "'")

            # 6. Intento de parseo
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                # Intento final: quitar saltos de línea literales que rompen strings
                json_str_no_nl = json_str.replace("\n", "\\n").replace("\r", "")
                # Pero si rompimos el JSON exterior, esto fallará. Intentamos salvar lo que podamos.
                try:
                    # Este fix es arriesgado pero a veces salva la vida:
                    # Intentar parsar ignorando errores de escape
                    return json.loads(json_str, strict=False)
                except:
                    return None
        except Exception as e:
            print(f"⚠️ [RobustExtract] Error crítico: {e}")
            return None

    def generate_clinical_challenge(self, topic, full_title, context, angle="Diagnosis"):
        """Generates a high-quality clinical challenge using Gemini 2.5 Flash."""
        print(f"🧠 [Dr. Epi | 2.5 Flash] Generando desafío para: {topic} (Ángulo: {angle})")
        
        angle_prompts = {
            "Diagnosis": "Enfócate en la identificación de SIGNOS, SÍNTOMAS y PARACLÍNICOS iniciales para el diagnóstico correcto.",
            "Treatment": "Enfócate en la CONDUCTA MÁS ADECUADA, fármacos de primera línea o manejo quirúrgico inmediato.",
            "Trap": "Enfócate en una TRAMPA CLÍNICA COMÚN (distractor fuerte) o un error de concepto frecuente en este tema."
        }
        
        angle_instruction = angle_prompts.get(angle, angle_prompts["Diagnosis"])

        prompt = f"""Actúa como el Dr. Epi, Mentor de Élite de la Academia Centurión.
TEMA: {full_title} ({topic})
CONTEXTO: {context}

REGLA DE ORO DE LOCALIZACIÓN (CRÍTICO):
1. Basa TODO el conocimiento en las GUÍAS DE PRÁCTICA CLÍNICA DE COLOMBIA (INS, Ministerio de Salud, Consensos Nacionales).
2. Si el tema es DENGUE, usa ESTRICTAMENTE el Protocolo INS Colombia 2024. 
   - RECUERDA: El manejo de choque (Grupo C) es BOLO de cristaloides 20 ml/kg en 15 min. (NO 10 ml/kg).
3. PROHIBIDO usar guías de Perú (MINSA), México o internacionales si contradicen la norma colombiana.

TAREA: Genera un CASO CLÍNICO de ALTO NIVEL cognitivo centrado en: {angle}.
{angle_instruction}

IMPORTANTE: Retorna ÚNICAMENTE el objeto JSON. No incluyas texto antes o después. 
Evita caracteres de control como saltos de línea reales dentro de los valores de texto del JSON (usa \\n si es necesario).

FORMATO JSON:
{{
  "mode": "Dr. Epi | DESAFÍO ÉLITE",
  "type": "selection",
  "angle": "{angle}",
  "content": "### 🩺 Caso Clínico\\n\\n...",
  "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
  "correct_answer": "X",
  "explanation": "### 🔬 Análisis Clínico\\n...\\n\\n🚀 **ULTRA-RESUMEN [{angle}]**:\\n- ..."
}}
"""

        try:
            response = self.model.generate_content(prompt)
            data = self._robust_json_extract(response.text)
            if data:
                print(f"✅ [Gemini] Desafío generado correctamente.")
                return data
            else:
                print(f"❌ [Gemini] No se pudo extraer JSON válido del texto: {response.text[:200]}...")
        except Exception as e:
            print(f"❌ [Gemini] Error en llamada API: {e}")
        
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
