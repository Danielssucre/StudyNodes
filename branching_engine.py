import json
import os
import sqlite3
from local_ai_adapter import LocalAIAdapter

class BranchingEngine:
    def __init__(self, db_path='temario.db', graph_path='study_dashboard/graph_data.json'):
        self.db_path = db_path
        self.graph_path = graph_path
        self.ai = LocalAIAdapter()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def suggest_subtopics(self, parent_title):
        """Calls local AI to suggest 2-3 subtopics, grounded with NotebookLM/Glossary."""
        from notebook_adapter import NotebookAdapter
        nb = NotebookAdapter()
        resolution = nb.resolve_topic_acronym(parent_title)
        
        prompt = f"""Actúa como un Diseñador de Examen Médico de Élite.
TEMA PADRE: {resolution['full_title']}
CONTEXTO: {resolution['context']}

OBJETIVO: Identifica 2 subtemas de alta rentabilidad (high-yield) sobre {parent_title} para profundizar.
Ejemplos: "Clasificación TNM", "Diferencial con X", "Manejo en Shock".

REGLAS:
- Responde SOLO con una lista numerada de 2 temas.
- NO generes una carta de batalla.
- Sé breve (max 3 palabras por tema)."""

        try:
            response = self.ai.generate_response(prompt, temperature=0.7)
            print(f"DEBUG: AI branching response: {response}")
            
            # 1. Try JSON extraction exactly
            if "[" in response and "]" in response:
                json_str = response[response.find("["):response.rfind("]")+1]
                subtopics = json.loads(json_str)
                return subtopics
            
            # 2. Extract from numbered list (more likely with 1B)
            import re
            lines = response.split('\n')
            subtopics = []
            
            # Filtros para evitar secciones genéricas que la 1B intenta repetir
            prohibited = ["trampa", "ciencia", "árbol", "llaves", "perlas", "check", "punto", "base", "decisión", "caso", "pregunta", "objetivo"]
            
            for line in lines:
                # Buscar patrones numerados o con viñetas
                match = re.match(r'^\d\.\s*(.*)', line.strip())
                if match:
                    raw_name = match.group(1).strip()
                elif line.strip().startswith('- '):
                    raw_name = line.strip()[2:].strip()
                else:
                    continue
                
                # Limpiar Markdown (asteriscos, etc) y truncar en ':' o '('
                # Queremos nombres limpios de temas médicos
                clean_name = raw_name.replace('*', '').replace('_', '').split(':')[0].split('(')[0].strip()
                
                # Verificar si es un tema real o una sección genérica
                if not any(word in clean_name.lower() for word in prohibited) and len(clean_name) > 4:
                    # Evitar duplicados exactos en la lista temporal
                    if clean_name not in subtopics:
                        subtopics.append(clean_name[:25]) # Un poco más de margen
            
            if subtopics:
                print(f"DEBUG: Extracted & Cleaned subtopics: {subtopics}")
                return subtopics[:2]

        except Exception as e:
            print(f"⚠️ Error sugiriendo subtemas: {e}")
        
        return []

    def expand_graph(self, parent_node_label):
        """Expands the graph with new subtopics from the parent."""
        print(f"🌲 Expandiendo grafo desde: {parent_node_label}")
        subtopics = self.suggest_subtopics(parent_node_label)
        if not subtopics:
            return False

        conn = self._get_conn()
        c = conn.cursor()
        
        try:
            with open(self.graph_path, 'r') as f:
                graph = json.load(f)
            
            # Find parent ID
            parent_id = None
            for node in graph['nodes']:
                if node['label'].replace('\n', ' ') == parent_node_label:
                    parent_id = node['id']
                    break
            
            if parent_id is None:
                return False

            new_node_id = max([n['id'] for n in graph['nodes']] + [0]) + 1
            
            for sub in subtopics:
                # 1. Insert into DB if not exists
                try:
                    c.execute("INSERT OR IGNORE INTO topics (title, priority) VALUES (?, ?)", (sub, 40))
                except: pass
                
                # 2. Add to graph_data.json
                graph['nodes'].append({
                    "id": new_node_id,
                    "label": sub,
                    "group": "locked",
                    "title": f"Subtema de {parent_node_label}"
                })
                
                # 3. Add edge from parent to sub
                graph['edges'].append({
                    "from": parent_id,
                    "to": new_node_id,
                    "dashes": True,
                    "label": "Derivación"
                })
                
                new_node_id += 1
            
            with open(self.graph_path, 'w') as f:
                json.dump(graph, f, indent=4)
            
            conn.commit()
            return True
        except Exception as e:
            print(f"⚠️ Error expandiendo grafo: {e}")
            return False
        finally:
            conn.close()
