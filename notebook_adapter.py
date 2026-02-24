import subprocess
import json
import os
import sys

# Wrapper for notebooklm-mcp
class NotebookAdapter:
    def __init__(self, executable_path="~/.local/bin/notebooklm-mcp"):
        self.cmd = os.path.expanduser(executable_path)

    def _call_tool(self, tool_name, arguments={}):
        """Generic method to call an MCP tool."""
        init_msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "study-system", "version": "1.0"}
            }
        }

        call_msg = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        try:
            # We need to launch a new process for each call OR keep one open. 
            # For simplicity/robustness in this script, we launch one per call 
            # (less efficient but cleaner state).
            proc = subprocess.Popen(
                [self.cmd],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Handshake
            proc.stdin.write(json.dumps(init_msg) + "\n")
            proc.stdin.flush()
            init_res = proc.stdout.readline() # Read init response
            
            # Tool Call
            proc.stdin.write(json.dumps(call_msg) + "\n")
            proc.stdin.flush()
            
            call_res_line = proc.stdout.readline().strip()
            
            print(f"RAW MCP RESPONSE for {tool_name}: {call_res_line[:100]}...")
            
            proc.terminate()
            
            if not call_res_line:
                print(f"❌ Error: No response from NotebookLM MCP for {tool_name}")
                return None

            try:
                # Debug Logging
                # print(f"DEBUG MCP RESPONSE: {call_res_line[:200]}")
                
                response = json.loads(call_res_line)
                if "error" in response:
                    print(f"❌ MCP Error: {response['error']}")
                    return None
                
                # Check for application-level error inside content text
                result = response.get("result", {})
                if "content" in result:
                    first_text = result["content"][0]["text"]
                    # If the text is JSON, unpack it for the caller
                    try:
                        inner_json = json.loads(first_text)
                        if isinstance(inner_json, dict):
                            # SENIOR FIX: Return the inner JSON if it looks like a tool response
                            # but keep the 'content' key for compatibility with raw MCP readers
                            if "answer" in inner_json:
                                inner_json["content"] = result["content"]
                                return inner_json
                            return inner_json
                    except:
                        pass
                
                return result
            except json.JSONDecodeError:
                print(f"❌ Error decoding JSON: {call_res_line}")
                return None

        except Exception as e:
            print(f"❌ Exception calling NotebookLM: {e}")
            return None

    def list_notebooks(self):
        """Returns a list of notebooks."""
        res = self._call_tool("notebook_list", {"max_results": 20})
        if not res: return []
        
        if isinstance(res, dict) and "notebooks" in res:
             return res["notebooks"]
        
        if "content" in res:
             try:
                 text_content = res["content"][0]["text"]
                 data = json.loads(text_content)
                 return data.get("notebooks", [])
             except: pass
        return []

    def create_notebook(self, title):
        """Creates a new notebook and returns its ID."""
        res = self._call_tool("notebook_create", {"title": title})
        if not res: return None
        
        if "notebook" in res and isinstance(res["notebook"], dict):
            return res["notebook"].get("id")
        if "id" in res: return res.get("id")
        
        if "content" in res:
            try:
                text_content = res["content"][0]["text"]
                data = json.loads(text_content)
                if "notebook" in data: return data["notebook"].get("id")
                return data.get("id")
            except: pass
        return None

    def ensure_notebook(self, topic):
        """Routes the topic to its corresponding Super-Notebook with overflow handling."""
        SUPER_NOTEBOOKS = {
            "MI_I": {"id": "d4737997-77d9-4f4f-9fe5-fc879d1d33c4", "name": "CORTEX: MEDICINA INTERNA (Super-Notebook)"},
            "MI_II": {"id": "a295fb79-0d00-48be-bf9c-b97e01a82750", "name": "CORTEX: MEDICINA INTERNA II (Super-Notebook)"},
            "PEDIATRIA": {"id": "0301217b-b6a3-41c1-8f74-c6bc24c41ca8", "name": "CORTEX: PEDIATRÍA (Super-Notebook)"},
            "GINECO": {"id": "3dcbf908-81e1-415e-9a24-3d4b518346e7", "name": "CORTEX: GINECOBSTETRICIA (Super-Notebook)"},
            "CIRUGIA": {"id": "014d7abd-6aa6-4200-a0e2-fc4d81053bb4", "name": "CORTEX: CIRUGÍA Y URGENCIAS (Super-Notebook)"},
            "SALUD_PUBLICA": {"id": "37cac7fe-3458-405d-b352-4f27641ed555", "name": "CORTEX: SALUD PÚBLICA, ÉTICA Y LEGAL (Super-Notebook)"}
        }

        # Mapping of common keywords to specialties
        SPECIALTY_MAP = {
            "card": "MI_I", "insuficiencia cardíaca": "MI_I", "hfrer": "MI_I", "hfpef": "MI_I", 
            "neumo": "MI_I", "epoc": "MI_I", "asma": "MI_I", "tep": "MI_I",
            "nefro": "MI_I", "aki": "MI_I", "erc": "MI_I",
            "infec": "MI_II", "vih": "MI_II", "dengue": "MI_II", "malaria": "MI_II", "tuberculosis": "MI_II", "tb": "MI_II",
            "neuro": "MI_II", "epileps": "MI_II", "guillain": "MI_II", "parkinson": "MI_II",
            "endo": "MI_II", "diabetes": "MI_II", "ada": "MI_II", "tiroides": "MI_II", "addison": "MI_II",
            "reuma": "MI_II", "lupus": "MI_II", "artritis": "MI_II", "hemat": "MI_II",
            "pediat": "PEDIATRIA", "lactante": "PEDIATRIA", "neonat": "PEDIATRIA", "eda": "PEDIATRIA",
            "gineco": "GINECO", "obstet": "GINECO", "preeclampsia": "GINECO", "parto": "GINECO",
            "cirug": "CIRUGIA", "apendicitis": "CIRUGIA", "colecistitis": "CIRUGIA", "trauma": "CIRUGIA",
            "ley": "SALUD_PUBLICA", "norma": "SALUD_PUBLICA", "bioétic": "SALUD_PUBLICA", "bioestad": "SALUD_PUBLICA"
        }

        topic_lower = topic.lower()
        spec_key = "MI_II" # Fallback
        for key, spec in SPECIALTY_MAP.items():
            if key in topic_lower:
                spec_key = spec
                break
        
        target = SUPER_NOTEBOOKS[spec_key]
        primary_id = target["id"]
        primary_name = target["name"]

        # Check source count to handle overflow
        all_nbs = self.list_notebooks()
        primary_nb = next((nb for nb in all_nbs if nb.get("id") == primary_id), None)
        
        source_count = primary_nb.get("source_count", 0) if primary_nb else 0
        
        if source_count < 50:
            print(f"🎯 Ruteo Primario: '{topic}' -> {spec_key} ({source_count}/50 fuentes)")
            return primary_id
        
        # Overflow! Check for V2
        v2_name = f"{primary_name} (V2)"
        v2_nb = next((nb for nb in all_nbs if v2_name in nb.get("title", "")), None)
        
        if v2_nb:
            print(f"🚀 Ruteo OVERFLOW (V2): '{topic}' -> {spec_key} V2 ({v2_nb.get('source_count', 0)}/50 fuentes)")
            return v2_nb.get("id")
        
        # Create V2
        print(f"⚠️ {primary_name} está LLENO (50/50). Creando Volumen 2...")
        new_id = self.create_notebook(v2_name)
        return new_id
    
    def add_url_source(self, notebook_id, url):
        """Adds a URL source to the notebook."""
        return self._call_tool("notebook_add_url", {"notebook_id": notebook_id, "url": url})
        
    def query_notebook(self, notebook_id, query):
        """Queries the notebook."""
        return self._call_tool("notebook_query", {"notebook_id": notebook_id, "query": query})

    def research_latest_guidelines(self, notebook_id, topic, current_date=None):
        """Triggers a deep research for recent guidelines and imports them."""
        date_context = current_date if current_date else "febrero 2026"
        query = f"Guías clínicas y consensos médicos publicados hasta {date_context} sobre: {topic}"
        print(f"🌐 Iniciando búsqueda profunda 'Just-In-Time' ({date_context}) para: {topic}...")
        
        # Start Research
        res = self._call_tool("research_start", {
            "notebook_id": notebook_id,
            "query": query,
            "mode": "fast",
            "source": "web"
        })
        
        if not res: return False
        
        # res is already unpacked or is the result dict
        task_id = None
        if isinstance(res, dict):
            task_id = res.get("task_id")
            if not task_id and "content" in res:
                try:
                    data = json.loads(res["content"][0]["text"])
                    task_id = data.get("task_id")
                except: pass
                
        if task_id:
            if self._poll_research_status(notebook_id, task_id):
                return self._import_research_sources(notebook_id, task_id)
        
        return False

    def _poll_research_status(self, notebook_id, task_id):
        """Polls until research is completed."""
        import time
        print(f"⌛ Polling research status for task {task_id}...")
        for i in range(25): # Max ~15 mins
            res = self._call_tool("research_status", {
                "notebook_id": notebook_id,
                "task_id": task_id,
                "max_wait": 30
            })
            if not res: 
                time.sleep(10)
                continue
                
            # Deep search for status indicators
            all_str_values = []
            def extract_strings(obj):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if isinstance(v, (str, dict, list)):
                            extract_strings(v)
                elif isinstance(obj, list):
                    for item in obj:
                        extract_strings(item)
                elif isinstance(obj, str):
                    all_str_values.append(obj.lower())

            extract_strings(res)
            
            # Log for debugging - what keys and values did we get?
            if isinstance(res, dict):
                print(f"   [Poll {i+1}] Keys: {list(res.keys())} | Values head: {all_str_values[:10]}")
            
            # Check for completion
            if "completed" in all_str_values:
                print(f"✅ Research task {task_id} completed.")
                return True
                
            # Some MCPs return status=success for completion if result is present
            if "success" in all_str_values and ("sources" in all_str_values or "sources" in str(res).lower()):
                print(f"✅ Research task {task_id} completed (detected via sources).")
                return True

            if any(v in all_str_values for v in ["error", "failed"]):
                print(f"❌ Research task {task_id} failed: {res}")
                return False
                
            time.sleep(10)
        return False

    def _import_research_sources(self, notebook_id, task_id):
        """Imports discovered sources."""
        print(f"📥 Importing research sources for task {task_id} into notebook {notebook_id}...")
        res = self._call_tool("research_import", {
            "notebook_id": notebook_id,
            "task_id": task_id
        })
        if res:
            print(f"✅ Import successful.")
            return True
        print(f"❌ Import failed.")
        return False

    def generate_audio_overview(self, notebook_id, fmt="deep_dive", language="es"):
        """Generates an audio overview. (Requires confirm=True in the tool logic)"""
        return self._call_tool("audio_overview_create", {
            "notebook_id": notebook_id,
            "format": fmt,
            "language": language,
            "confirm": True
        })

    def get_studio_status(self, notebook_id):
        """Returns the status of studio artifacts for a notebook."""
        return self._call_tool("studio_status", {"notebook_id": notebook_id})

    def generate_clinical_case(self, notebook_id, topic, angle_name="", q_format="mcq", variant_context="MAESTRO"):
        """Generates a clinical case question for the given topic, angle and variant."""
        prompt = (
            f"Actúa como el motor de evaluación del Protocolo Centurión.\n\n"
            f"TEMA: {topic}\n"
            f"ÁNGULO: {angle_name}\n"
            f"NIVEL/VARIANTE: {variant_context}\n\n"
            f"OBJETIVO: Genera un CASO CLÍNICO corto y conciso.\n"
            f"Formato: {q_format.upper()}\n\n"
            "REGLAS DE SALIDA:\n"
            "- Retorna ESTRICTAMENTE un JSON válido.\n"
            "- El enunciado debe ser de máximo 3-4 líneas.\n"
            "- Incluye retroalimentación basada en la Master Key.\n"
            "- SIEMPRE añade un campo 'glosario' definiendo cualquier sigla médica usada (ej. LABA, SABA, MART, IECA).\n\n"
            "ESTRUCTURA JSON:\n"
            "{\n"
            "  \"enunciado\": \"...\",\n"
            "  \"opciones\": [\"A) ...\", \"B) ...\", \"C) ...\", \"D) ...\"],\n"
            "  \"correcta\": \"X\",\n"
            "  \"retroalimentacion\": \"...\",\n"
            "  \"glosario\": { \"LABA\": \"Long-Acting Beta Agonist...\", \"MART\": \"...\" }\n"
            "}"
        )
        return self.query_notebook(notebook_id, prompt)

    def distill_topic_to_atomic(self, notebook_id, topic_title, current_date=None):
        """Distills a notebook content into an Atomic Notebook (20 points + 5 cases)."""
        date_context = current_date if current_date else "febrero 2026"
        prompt = (
            f"Actúa como un Especialista en Síntesis Médica Axioma. Tu tarea es analizar todas las fuentes del cuaderno '{topic_title}' "
            f"priorizando estrictamente la información más RECIENTE y las GUÍAS DE PRÁCTICA CLÍNICA DE COLOMBIA publicadas hasta {date_context}. "
            f"Extrae y detalla los siguientes 20 PUNTOS CLAVE (ÁNGULOS) de alto rendimiento para el examen:\n"
            "1. Fisiopatología/Mecanismo\n2. Presentación Clínica Típica\n3. Hallazgo Físico Patognomónico\n"
            "4. Gold Standard Diagnóstico\n5. Criterios Diagnósticos (Tokyo/Alvarado/etc)\n6. Diagnóstico Diferencial Clave\n"
            "7. Tratamiento de Primera Línea\n8. Tratamiento de Segunda Línea/Rescate\n9. Manejo en Urgencias/Código Rojo\n"
            "10. Complicación más Frecuente\n11. Complicación más Letal\n12. Pronóstico/Factores de Riesgo\n"
            "13. Epidemiología/Salud Pública\n14. Población Especial (Embarazo)\n15. Población Especial (Pediatría)\n"
            "16. Población Especial (Geriatría)\n17. Contraindicación Absoluta de Terapia\n18. Efecto Secundario de Medicamento Clave\n"
            "19. Escala de Severidad/Score\n20. Actualización Guía 2025/2026\n\n"
            "Formato de salida: Markdown estructurado con ## para cada ángulo. "
            "Usa la Regla de los Porqués para explicar cada uno, conectando el síntoma con la causa de forma magistral."
        )
        res = self.query_notebook(notebook_id, prompt)
        
        if res and "content" in res:
            try:
                content = res["content"][0]["text"]
                # Save to locally
                file_path = f"/Users/danielsuarezsucre/ANALISIS DE TEMAS A ESTUDIAR/StudyData/AtomicNotebooks/{topic_title.replace(' ', '_')}.md"
                with open(file_path, "w") as f:
                    f.write(content)
                return file_path
            except Exception as e:
                print(f"Error saving atomic notebook: {e}")
        return None

    def generate_anki_card(self, topic, angle, wrong_answer, correct_answer, explanation):
        """Generates a high-fidelity Anki card (Markdown) for a failed concept."""
        prompt = (
            f"Basado en el fallo del estudiante sobre '{topic}' (Ángulo: {angle}), "
            f"genera una TARJETA DE MEMORIA (Anki style) que ataque la raíz del error.\n"
            f"Contexto: El usuario respondió '{wrong_answer}', pero la correcta era '{correct_answer}'.\n"
            f"Explicación previa: {explanation}\n\n"
            "Formato de salida esperado (Markdown):\n"
            "# CONCEPT: [Nombre del concepto]\n"
            "FRONT: [Pregunta corta y gatillo mental]\n"
            "BACK: [Respuesta directa y la 'regla de oro' para no volver a fallar]\n"
            "TAGS: #anki #fallo_critico #aki_graph"
        )
        # Use a general query or specific notebook if ID is known
        # For simplicity, we search for the topic's notebook
        nb_id = self.ensure_notebook(topic)
        res = self.query_notebook(nb_id, prompt)
        return res
    def resolve_topic_acronym(self, topic):
        """
        Expands acronyms using a local glossary or NotebookLM.
        """
        # 1. Local Glossary (Ground Truth for common exams)
        MEDICAL_GLOSSARY = {
            # Acrónimos
            "ADA": "American Diabetes Association (Guías 2024-2025)",
            "AKI": "Acute Kidney Injury (Lesión Renal Aguda - Guías KDIGO)",
            "PAI": "Programa Ampliado de Inmunizaciones (Esquema Vacunación Colombia 2025)",
            "ERC": "Enfermedad Renal Crónica (Guías KDIGO/Ministerio)",
            "EPI": "Enfermedad Pélvica Inflamatoria",
            "SARA": "Síndrome de Apnea del Sueño",
            "SIVIGILA": "Sistema de Vigilancia en Salud Pública (Colombia)",
            "FEMINICIDIO": "Protocolo de Valoración Forense y Vigilancia Epidemiológica (Violencia de Género - Ley 2356)",
            "SABA": "Short-Acting Beta Agonist (Salbutamol - Alerta GINA 2024)",
            "LABA": "Long-Acting Beta Agonist",
            "ICS": "Inhaled Corticosteroids",
            "MART": "Maintenance and Reliever Therapy (Asma - GINA 2024)",
            "CAD": "Cetoacidosis Diabética (Protocolo: Potasio antes de Insulina)",
            "HHS": "Estado Hiperosmolar Hiperglucémico (Hiperosmolaridad no cetósica)",
            "SCA": "Síndrome Coronario Agudo (IAMCEST - IAMSEST)",
            "TEP": "Tromboembolismo Pulmonar (Escala de Wells + dímero D)",
            "TB": "Tuberculosis (tratamiento RHZE - OPS 2024)",
            "TCE": "Traumatismo Craneoencefálico (Escala de Glasgow)",
            "SRI": "Secuencia Rápida de Intubación",
            "CURB": "Criterios de Severidad Neumonía (CURB-65)",
            "qSOFA": "Quick SOFA - Criterios Sepsis 3.0",
            "LES": "Lupus Eritematoso Sistémico (Anti-Sm, complemento bajo)",
            "DPPNI": "Desprendimiento Prematuro Placenta Normoinserta (Urgencia obstétrica)",
            "RR": "Riesgo Relativo y Riesgo Absoluto (Bioestadística)",
            # Títulos completos del calendario
            "LEY ESTATUTARIA 1751": "Ley Estatutaria 1751 de 2015 - Derecho Fundamental a la Salud (Colombia)",
            "FALLA CARDÍACA (HFREF)": "Falla Cardíaca con Fracción de Eyección Reducida - Regla de los 4 Fantásticos (IECA/ARA2, BB, ARM, iSGLT2)",
            "ASMA (MART)": "Asma Bronquial - Estrategia MART (GINA 2024): ICS/Formoterol como rescate y mantenimiento",
            "DENGUE (INS 2024)": "Dengue - Protocolo INS Colombia 2024: Clasificación, signos de alarma, manejo de líquidos",
            "ESTATUS EPILÉPTICO": "Estatus Epiléptico - Protocolo: Benzodiacepinas → Fenitoína → Anestésicos",
            "APENDICITIS (ALVARADO)": "Apendicitis Aguda - Score de Alvarado (MANTRELS): diagnóstico y manejo quirúrgico",
            "PREECLAMPSIA (ZUSPAN)": "Preeclampsia - Criterios de severidad, Sulfato de Magnesio (Zuspan), Hidralazina",
            "REANIMACIÓN NEO": "Reanimación Neonatal - Protocolo AHA/AAP 2022: calor, secar, estimular, FC 100",
            "ISGLT2 EN FALLA CARD.": "Inhibidores SGLT2 (Empagliflozina/Dapagliflozina) en Falla Cardíaca - Indicaciones NEJM 2023",
            "DENGUE GRAVE": "Dengue Grave - Criterios INS Colombia: choque, hemorragia, fallo orgánico",
            "ARTICULO 17 (1751)": "Artículo 17 Ley 1751 - Autonomía del paciente y consentimiento informado en Colombia",
            "ADA 2024 (DIABETES)": "Guías ADA 2024 Diabetes: Metas de HbA1c, iSGLT2 en ERC, GLP-1 en obesidad",
            "ASMA (SABA WARNING)": "Alerta GINA 2024: SABA solo (sin ICS) aumenta mortalidad por asma - cambio de paradigma",
            "VIH (PREP)": "VIH - Profilaxis Pre-Exposición (PrEP): Truvada (TDF/FTC) - Resolución Minsalud Colombia",
            "ESTADO HIPEROSMOLAR": "Estado Hiperosmolar Hiperglucémico (HHS): Osmolaridad >320, sin cetosis significativa",
            "GUILLAIN-BARRÉ (LCR)": "Síndrome de Guillain-Barré: LCR (disociación albumino-citológica), IVIG o plasmaféresis",
            "ARTRITIS REUMATOIDE": "Artritis Reumatoide: Anti-CCP (más específico), FR, metotrexato primera línea",
            "COLECISTITIS (MURPHY)": "Colecistitis Aguda - Criterios Tokyo 2018: Signo de Murphy, fiebre, eco abdominal",
            "CÓDIGO ROJO (4T)": "Hemorragia Obstétrica - Código Rojo: 4T (Tono, Trauma, Tejido, Trombina)",
            "EDA": "Enfermedad Diarreica Aguda (Protocolo AIEPI / OMS)",
            "EDA (ENFERMEDAD DIARREICA AGUDA)": "Enfermedad Diarreica Aguda - Manejo Integral (Planes A, B, C) y prevención de deshidratación",
            "EDA (PLAN B)": "Enfermedad Diarreica Aguda - Plan B de Hidratación OMS: Sales orales 75cc/kg en 4h",
            "PAI 2025 (PROTOCOLOS COLOMBIA)": "PAI Colombia 2025 - Esquema de vacunación actualizado: VPH niños, Dengue (Qdenga), Rotavirus",
            "FEMINICIDIO (LEY 2356)": "Ley 2356/2024 - Protocolo de atención a víctimas de violencia de género: SIVIGILA 400, ruta intersectorial",
            "GLP-1 EN ERC": "Agonistas GLP-1 (Semaglutida/Liraglutida) en Enfermedad Renal Crónica y obesidad - FLOW trial 2024",
            "EPOC (GRUPO E)": "EPOC - Clasificación GOLD 2023: Grupo E, broncodilatadores LABA+LAMA, rehabilitación pulmonar",
            "VIH (GESTACIONAL)": "VIH en embarazo - PTMH: AZT+3TC+LPV/r, cesárea si CV>1000, suspender lactancia",
            "HIPOTIROIDISMO": "Hipotiroidismo primario: TSH elevada, T4L baja, Levotiroxina - casos especiales en embarazo",
            "MIASTENIA GRAVIS": "Miastenia Gravis: Anticuerpos anti-AchR, test de Tensilón, crisis miasténica vs colinérgica",
            "GOTA (SINOVIAL)": "Gota: Cristales de urato monosódico en líquido sinovial (birrefringencia negativa), colchicina",
            "CIRUGÍA HERNIA": "Hernia Inguinal: Lichtensten sin malla en urgencia, laparoscopia electiva",
            "MADURACIÓN PULM.": "Maduración Pulmonar Fetal: Betametasona 12mg c/24h x2 dosis (24-34 semanas)",
            "BRONQUIOLITIS (WOOD)": "Bronquiolitis - Score de Wood-Downes: O2, hidratación, NO broncodilatadores rutinarios (evidencia)",
            "VACUNA DENGUE (QDENGA)": "Vacuna Dengue Qdenga (TAK-003): Solo en seropositivos, 2 dosis, 9-60 años - PAI 2025",
            "PROTOCOLO SIVIGE": "SIVIGILA: Notificación obligatoria de eventos de interés en salud pública Colombia - SIVIGE",
            "SCA (IAMCEST)": "IAMCEST: Supradesnivel ST, reperfusión <90min (ICP) o <30min (trombólisis) - Clopidogrel + AAS",
            "TEP (DIAGNÓSTICO)": "TEP: Wells score, dímero D, AngioTAC, anticoagulación con HBPM/rivaroxabán",
            "TB (RENAL)": "Tuberculosis Renal: Hematuria estéril, cultivo de Lowenstein-Jensen orina, RHZE ajuste en ERC",
            "TI-RADS": "TI-RADS (Thyroid Imaging Reporting): Clasificación ecográfica nódulos tiroideos, BAAF si ≥4",
            "MIGRAÑA": "Migraña: Triptanes (sumatriptán) en agudo, propranolol/topiramato en profilaxis",
            "VASCULITIS (KAWASAKI)": "Enfermedad de Kawasaki: Fiebre >5d + 4 de 5 criterios, IVIG + AAS - riesgo coronario",
            "TRAUMA ABDOMINAL": "Trauma Abdominal: FAST ultrasound, líquido libre peritoneal = cirugía urgente",
            "SANGRADO 1RA MITAD": "Sangrado 1er trimestre: Aborto amenazante vs inevitable, mola hidatiforme (β-hCG >100.000)",
            "CRUP (WESTLEY)": "Crup Laringotraqueítico - Score de Westley: dexametasona 0.6mg/kg, epinefrina nebulizada",
            "CADENA DE CUSTODIA": "Cadena de Custodia en Medicina Legal: Documentación forense, integridad de evidencia física",
            "HTA (URGENCIA)": "HTA Urgencia vs Emergencia: daño órgano blanco, Nitroprusiato IV en emergencia",
            "NEUMONÍA (CURB-65)": "Neumonía Adquirida en Comunidad - CURB-65: Score ≥2 hospitalizar, amoxicilina + macrólido",
            "HEPATITIS B (SERO)": "Hepatitis B: Interpretación serológica (HBsAg, Anti-HBs, Anti-HBc), vacunación",
            "CRISIS ADDISONIANA": "Crisis Addisoniana: Hipotensión + hiponatremia + hiperpotasemia, hidrocortisona IV 100mg STAT",
            "AKI (KDIGO)": "AKI - Guías KDIGO 2024: Creatinina ×1.5 en 7d o +0.3 en 48h, estadificación 1-3",
            "OBSTRUCCIÓN INTEST.": "Obstrucción Intestinal: Niveles hidroaéreos, SNG, cirugía si estrangulación",
            "PLACENTA PREVIA": "Placenta Previa: Sangrado indoloro, diagnóstico ecográfico, cesárea programada",
            "SENSIBILIDAD VS ESP.": "Bioestadística: Sensibilidad (VPN alto - descarta), Especificidad (VPP alto - confirma), LR",
            "LEY 1616 (S. MENTAL)": "Ley 1616/2013 - Salud Mental Colombia: Internamiento involuntario, consentimiento, derechos",
            "FIBRILACIÓN AURICULAR": "FA: Score CHA₂DS₂-VASc (anticoagulación), control de ritmo vs frecuencia, cardioversión",
            "DERRAME PLEURAL": "Derrame Pleural: Criterios de Light (exudado), toracocentesis diagnóstica, causas",
            "SEPSIS 3 (QSOFA)": "Sepsis 3.0: qSOFA ≥2, disfunción orgánica, lactato >2, cultivos + antibióticos <1h",
            "HIPERCALCEMIA": "Hipercalcemia: Hipercalcemia maligna (PTHrP), hiperparatiroidismo primario, tratamiento IV",
            "ALZHEIMER": "Alzheimer: MMSE, inhibidores colinesterasa (donepezilo), memantina en moderado-severo",
            "ERC (NEFRO-PROT)": "ERC - Nefroprotección: IECA/ARA2, iSGLT2, control PA <130/80, metas de albuminuria",
            "FISURA ANAL": "Fisura Anal: Aguda vs crónica, nitratos tópicos, esfinterotomía lateral en crónica",
            "RIESGO RELATIVO (RR)": "Bioestadística: RR, OR, RAR, NNT, NNH - interpretación en estudios clínicos",
            "PROTOCOLO SUICIDIO": "Protocolo de Atención Suicidio Colombia: Escala de riesgo, internamiento, Resolución 2481",
            "ENDOCARDITIS (DUKE)": "Endocarditis Infecciosa - Criterios Duke: hemocultivos + eco, antibióticos 4-6 semanas",
            "SRI (INTUBACIÓN)": "Secuencia Rápida de Intubación: Etomidato + Succinilcolina, laringoscopía directa vs video",
            "MENINGITIS BACTERIANA": "Meningitis Bacteriana: LCR turbia, glucosa baja, proteínas altas, cefalosporina 3G STAT",
            "METFORMINA": "Metformina: Primera línea DM2, contraindicada TFG<30, suspender contraste yodado",
            "PARKINSON": "Parkinson: Levodopa-carbidopa primera línea, temblor en reposo, fenómeno on-off",
            "HIPONATREMIA": "Hiponatremia: Clasificación por volumen, corrección lenta (máx 8-10 mEq/L/día), mielinólisis",
            "CÁNCER DE COLON": "Cáncer Colorrectal: Colonoscopia screening a 45 años, Lynch (MMR), FOLFOX en estadio III",
            "ANTICONCIPIÓN (CMS)": "Anticoncepción de Emergencia: Levonorgestrel <72h, meloxicam, criterios médicos de elegibilidad OMS",
            "VALOR P": "Valor P en investigación: significancia estadística, intervalo de confianza, error tipo I y II",
            "CONSENTIMIENTO INFORMADO": "Consentimiento Informado: Capacidad, información, voluntariedad - Ley 1751 y Ley 23/1981",
            "BLOQUEO AV (MOBITZ I)": "Bloqueo AV 2do grado Mobitz I (Wenckebach): Alargamiento PR progresivo, benigno",
            "IVU (PIELONEFRITIS)": "Pielonefritis Aguda: Fiebre + dolor lumbar + bacteriuria, ciprofloxacino 7 días",
            "DEPRESIÓN (ISRS)": "Depresión Mayor: ISRS primera línea, fluoxetina, evaluación riesgo suicida",
            "HIPERKALEMIA": "Hiperkalemia: ECG (ondas T picudas), gluconato de calcio IV, bicarbonato, kayexalato",
            "PANCREATITIS (ATLANTA)": "Pancreatitis Aguda - Atlanta 2012: Leve/Moderada/Severa, APACHE II, hidratación Ringer",
            "CÁNCER DE CÉRVIX": "Cáncer de Cérvix: VPH 16 y 18, colposcopia, LEEP, estadificación FIGO 2018",
            "RESOLUCIÓN 0-3960": "Resolución 3960/2019 - Colombia: Criterios internamiento no voluntario en salud mental",
            "BLOQUEO AV (MOBITZ II)": "Bloqueo AV 2do grado Mobitz II: PR fijo, QRS bloqueado, marcapasos obligatorio",
            "SÍFILIS CONGÉNITA": "Sífilis Congénita: Penicilina G cristalina IV al recién nacido, seguimiento VDRL",
            "PSICOSIS AGUDA": "Psicosis Aguda: Haloperidol IM en agitación, risperidona en mantenimiento",
            "ANION GAP": "Anión Gap: Na-(Cl+HCO3) normal 8-12, AG elevado (MUDPILES), diferencial acidosis metabólica",
            "FRACTURA COLLES": "Fractura de Colles: Caída en extensión, deformidad en dorso de tenedor, yeso vs cirugía",
            "BIOÉTICA (PRINCIPIALISMO)": "Bioética - Principios de Beauchamp y Childress: Autonomía, Beneficencia, No maleficencia, Justicia",
            "ESTENOSIS AÓRTICA": "Estenosis Aórtica: Tríada clásica (angina, síncope, ICC), gradiente >40mmHg, TAVI vs cx",
            "MALARIA (GOTA GRUESA)": "Malaria Colombia: Gota gruesa (diagnóstico), Plasmodium vivax (cloroquina+primaquina)",
            "TRASTORNO BIPOLAR": "Trastorno Bipolar: Litio primera línea, ácido valproico, carbamazepina, manía vs depresión",
            "ANEMIA FERROPÉNICA": "Anemia Ferropénica: Microcítica hipocrómica, ferritina baja, hierro oral 3-6 meses",
            "LUXACIÓN HOMBRO": "Luxación Glenohumeral Anterior: Maniobra de Cunningham, Kocher - reducción cerrada",
            "PERICARDITIS AGUDA": "Pericarditis Aguda: Roce pericárdico, supra ST cóncavo difuso, AINE + colchicina",
            "CELULITIS VS ERISIPELA": "Celulitis vs Erisipela: Erisipela bordes definidos (estreptococo), celulitis profunda difusa",
            "ANEMIA MEGALOBLÁS.": "Anemia Megaloblástica: B12 (neurológico) vs folato, VCM elevado, causa autoinmune (Biermer)",
            "MIOCARDITIS": "Miocarditis: RMN cardíaca (gold standard), troponina elevada sin coronarias, reposo",
            "PARASITISMO (EDA)": "EDA Parasitaria: Giardia (metronidazol), Entamoeba (tinidazol+iodoquinol), coproparasitológico",
            "LEUCEMIA AGUDA": "Leucemia Aguda: LLA (niños, vincristina) vs LMA (adultos, citarabina), blast >20%",
            "SHOCK CARDIOGÉNICO": "Shock Cardiogénico: Dobutamina, IABP, mortalidad alta - complicación IAMCEST",
            "MIELOMA MÚLTIPLE": "Mieloma Múltiple: CRAB (Calcio, Renal, Anemia, Bone), proteína Bence-Jones, bortezomib",
            "DISECCIÓN AÓRTICA": "Disección Aórtica: Stanford A (cirugía STAT), Stanford B (médico), labetalol IV, AngioTAC",
        }

        
        # Clean topic for lookup
        topic_upper = topic.strip().upper()
        clean_acronym = topic.split('(')[0].strip().upper()
        
        # Exact match (for full labels)
        if topic_upper in MEDICAL_GLOSSARY:
            return {
                "full_title": MEDICAL_GLOSSARY[topic_upper],
                "context": f"Concepto clave de {MEDICAL_GLOSSARY[topic_upper]}. Seguir protocolos de medicina basada en evidencia."
            }
            
        # Acronym match
        if clean_acronym in MEDICAL_GLOSSARY:
            return {
                "full_title": MEDICAL_GLOSSARY[clean_acronym],
                "context": f"Concepto clave de {MEDICAL_GLOSSARY[clean_acronym]}. Seguir protocolos de medicina basada en evidencia."
            }

        # 2. NotebookLM Fallback
        nb_id = self.ensure_notebook(topic)
        prompt = (
            f"Analiza: '{topic}'. Responde ESTRICTAMENTE JSON: "
            "{\"full_title\": \"Nombre Completo\", \"context\": \"Contexto clínico 1 oración\"}"
        )
        
        try:
            res = self.query_notebook(nb_id, prompt)
            if res and "content" in res:
                text = res["content"][0]["text"].replace("```json", "").replace("```", "").strip()
                if text:
                    data = json.loads(text)
                    return {
                        "full_title": data.get("full_title", topic),
                        "context": data.get("context", f"Guía clínica sobre {topic}.")
                    }
        except: pass
            
        return {"full_title": topic, "context": f"Guía clínica sobre {topic}."}

if __name__ == "__main__":
    # Test
    nb = NotebookAdapter()
    # print(nb.list_notebooks())
