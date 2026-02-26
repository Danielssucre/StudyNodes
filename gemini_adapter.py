import google.generativeai as genai
import json
import os

GEMINI_API_KEY = "AIzaSyCFfDbzMN-0o7Q53peX77L2m1eCrfs65og"

class GeminiAdapter:
    def __init__(self):
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel("gemini-2.5-flash")

    def _robust_json_extract(self, raw_text):
        """Extrae y limpia JSON de forma extrema con auto-recuperación de MCQs (V3.11)."""
        try:
            # 1. Búsqueda directa del objeto JSON (independiente de bloques Markdown)
            import re
            # Buscamos el primer '{' y el último '}' en TODO el texto
            start_match = re.search(r'\{', raw_text, re.DOTALL)
            end_idx = raw_text.rfind('}')
            
            if not start_match or end_idx == -1 or end_idx < start_match.start():
                print(f"⚠️ [V3.11] No se encontraron delimitadores {{ }} en el texto.")
                return None
                
            json_str = raw_text[start_match.start():end_idx + 1]

            # 2. Limpieza de fundamentales
            # Eliminar caracteres de control excepto saltos de línea y tabs
            json_str = "".join(ch for ch in json_str if ord(ch) >= 32 or ch in "\n\r\t")
            # Arreglar comas finales
            json_str = re.sub(r',\s*([\]}])', r'\1', json_str)

            # 3. Intentos de parseo en cascada
            data = None
            errors = []
            
            # Usamos JSONDecoder para extraer el primer objeto válido ignorando basura posterior
            decoder = json.JSONDecoder(strict=False)
            
            # Intento de parseo robusto
            try:
                # raw_decode retorna (objeto, posición_final)
                data, index = decoder.raw_decode(json_str)
                # Si llegamos aquí, tenemos al menos un objeto válido al inicio
                print(f"✅ [V3.12] JSON decodificado exitosamente (index: {index})")
            except Exception as e:
                errors.append(f"RawDecode inicial: {e}")
                # Intento con corrección de comillas inteligentes si falla el inicial
                try:
                    json_str_fix = json_str.replace("“", "\\\"").replace("”", "\\\"").replace("‘", "'").replace("’", "'")
                    data, index = decoder.raw_decode(json_str_fix)
                    print(f"✅ [V3.12] JSON decodificado con FixQuotes (index: {index})")
                except Exception as e:
                    errors.append(f"RawDecode con FixQuotes: {e}")

            if not data:
                print(f"❌ [V3.12] Fallo total de parseo. Errores: {errors}")
                # Log truncado para no saturar memoria pero ver el inicio del problema
                print(f"🔍 [V3.12] Contexto del fallo: {json_str[:1000]}")
                return None

            # 4. [V3.10] Auto-Recuperación de Estructura MCQ (Refinada)
            if isinstance(data, dict):
                content = data.get("content", "")
                options = data.get("options", [])

                if (not options or len(options) < 2) and "A)" in content:
                    print("⚠️ [V3.11] Recuperando opciones del content...")
                    opt_patterns = re.findall(r'([A-D]\).*?)(?=\n|[A-D]\)|$)', content, re.DOTALL)
                    if opt_patterns:
                        extracted_opts = [opt.strip() for opt in opt_patterns if len(opt.strip()) > 3]
                        if len(extracted_opts) >= 2:
                            data["options"] = extracted_opts
                            for opt in extracted_opts:
                                data["content"] = data["content"].replace(opt, "").strip()
                            print(f"✅ [V3.11] Recuperadas {len(extracted_opts)} opciones.")

            return data
        except Exception as e:
            print(f"⚠️ [V3.11] Error crítico en extracción: {e}")
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

REGLA ESTRUCTURAL (V3.10) - ¡NO FALLAR!:
1. El campo 'content' debe contener ÚNICAMENTE el Caso Clínico y la PREGUNTA final.
2. NUNCA, bajo ninguna circunstancia, incluyas las opciones A, B, C, D dentro del campo 'content'.
3. Las opciones deben ir exclusivamente en el campo 'options'.
4. Cada opción en 'options' DEBE ser corta y directa.

TAREA: Genera un CASO CLÍNICO de ALTO NIVEL cognitivo centrado en: {angle}.
{angle_instruction}

FORMATO JSON REQUERIDO:
{{
  "mode": "Dr. Epi | DESAFÍO ÉLITE",
  "type": "selection",
  "angle": "{angle}",
  "content": "### 🩺 Caso Clínico\\n\\n[Resumen del caso]\\n\\n**Pregunta:** [La pregunta aquí]?",
  "options": ["A) [Texto]", "B) [Texto]", "C) [Texto]", "D) [Texto]"],
  "correct_answer": "X",
  "explanation": "### 🔬 Análisis Clínico\\n...\\n\\n🚀 **ULTRA-RESUMEN [{angle}]**:\\n- ..."
}}

IMPORTANTE: Retorna ÚNICAMENTE el JSON.
"""

        try:
            response = self.model.generate_content(prompt)
            data = self._robust_json_extract(response.text)
            if data:
                # Doble verificación de campos obligatorios
                required = ["content", "options", "correct_answer", "explanation"]
                if all(k in data for k in required):
                    print(f"✅ [Gemini] Desafío estructurado correctamente.")
                    return data
                else:
                    print(f"⚠️ [Gemini] JSON incompleto tras extracción. Faltan campos: {[k for k in required if k not in data]}")
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
