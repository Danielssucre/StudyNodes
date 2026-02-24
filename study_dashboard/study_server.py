from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
import os
import sys

# Agregar el directorio raíz al path para importar herramientas locales
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    import agent_srs
    from local_ai_adapter import LocalAIAdapter
    from gemini_adapter import GeminiAdapter
except ImportError:
    pass

# Redirigir logs para depuración automática
LOG_FILE = "study_dashboard/debug_exec.log"
sys.stdout = open(LOG_FILE, "a", buffering=1)
sys.stderr = sys.stdout

print(f"\n--- REINICIO DE SERVIDOR: {os.popen('date').read().strip()} ---")

# Define the port
PORT = 8000

class StudyHandler(SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/log_srs':
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data)
                topic_label = data.get('topic', '').strip()
                rating = data.get('rating', 'HARD')
                
                print(f"📡 [LOG_SRS] Tema: '{topic_label}' | Calificación: {rating}")
                
                graph_path = 'study_dashboard/graph_data.json'
                with open(graph_path, 'r') as f:
                    graph = json.load(f)
                
                active_node = None
                for node in graph['nodes']:
                    # Búsqueda flexible ignorando saltos de línea y espacios
                    cleaned_label = node['label'].replace('\n', ' ').strip()
                    if node['group'] == 'active' and (cleaned_label == topic_label or node['label'].strip() == topic_label):
                        active_node = node
                        break
                
                if active_node:
                    current_m = active_node.get('mastery_level', 0)
                    if rating == 'EASY':
                        active_node['mastery_level'] = current_m + 1
                        print(f"  ✅ Maestría incrementada: {current_m} -> {active_node['mastery_level']}")
                    else:
                        print(f"  🔁 Manteniendo maestría {current_m} (Dificultad reportada)")
                        
                    # Sincronizar con SQLite
                    try:
                        import agent_srs
                        agent_srs.update_topic_after_review(topic_label, rating)
                    except Exception as e:
                        print(f"  ⚠️ Error al actualizar SQLite: {e}")
                else:
                    print(f"  ❌ No se encontró el nodo activo para '{topic_label}'")
                
                with open(graph_path, 'w') as f:
                    json.dump(graph, f, indent=4)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode())
            except Exception as e:
                print(f"❌ Error en /log_srs: {e}")
                self.send_error(500)
        elif self.path == '/trigger_next':
            try:
                graph_path = 'study_dashboard/graph_data.json'
                with open(graph_path, 'r') as f:
                    graph = json.load(f)
                
                # 1. Buscar nodo activo actual
                current_node = None
                for node in graph['nodes']:
                    if node['group'] == 'active':
                        current_node = node
                        break
                
                # 2. Verificar maestría antes de avanzar
                if current_node:
                    mastery = current_node.get('mastery_level', 0)
                    print(f"🔍 [TRIGGER_NEXT] Nodo: '{current_node['label']}' | Maestría: {mastery}/3")
                    if mastery >= 3:
                        print(f"  🏆 Tema dominado. Buscando siguiente...")
                        current_node['group'] = 'mastered'
                        current_node['title'] = "🏆 DOMINADO (3/3 Ángulos)"
                        current_node = None # Forzar búsqueda de un nuevo nodo locked
                
                # 3. Si no hay nodo activo, activar el próximo locked
                if not current_node:
                    for node in graph['nodes']:
                        if node['group'] == 'locked':
                            node['group'] = 'active'
                            node['title'] = "⚠️ OBJETIVO ACTUAL"
                            node['mastery_level'] = 0
                            current_node = node
                            print(f"  🆕 Activado nuevo nodo: '{current_node['label']}'")
                            break
                
                if not current_node:
                    print("  🏁 Calendario completado.")
                    with open(graph_path, 'w') as f:
                        json.dump(graph, f, indent=4)
                    self.send_error(404, "Fin del calendario alcanzado.")
                    return
                
                target_topic = current_node['label'].replace('\n', ' ').strip()
                m_level = current_node.get('mastery_level', 0)
                
                angles = ["Diagnosis", "Treatment", "Trap"]
                current_angle = angles[min(m_level, 2)]
                print(f"  🎯 Generando ángulo: {current_angle}")

                # 4. Generar contenido
                from notebook_adapter import NotebookAdapter
                nb = NotebookAdapter()
                res = nb.resolve_topic_acronym(target_topic)
                full_t = res.get('full_title', target_topic)
                ctx = res.get('context', f'Guía clínica sobre {target_topic}.')
                
                session_data = None
                try:
                    gemini = GeminiAdapter()
                    session_data = gemini.generate_clinical_challenge(target_topic, full_t, ctx, angle=current_angle)
                    if session_data:
                        session_data['mode'] = f"Dr. Epi | MAESTRÍA {m_level+1}/3"
                except Exception as e:
                    print(f"  ⚠️ Error Gemini: {e}")
                
                if not session_data:
                    session_data = {
                        "mode": "FALLBACK MODO",
                        "type": "selection",
                        "content": f"### Reanudar Estudio\nTema: {full_t}\nÁngulo: {current_angle}",
                        "options": ["A) Intentar", "B) Reintentar", "C) Omitir", "D) Guardar"],
                        "correct_answer": "A",
                        "explanation": "Error de generación."
                    }
                
                with open('current_session.json', 'w') as f:
                    json.dump(session_data, f)
                with open(graph_path, 'w') as f:
                    json.dump(graph, f, indent=4)

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "next": target_topic}).encode())
            except Exception as e:
                import traceback
                print(f"❌ Error en trigger_next: {e}")
                traceback.print_exc()
                self.send_error(500)
        else:
            self.send_error(404)

    def do_GET(self):
        if self.path == '/graph_data':
            try:
                graph_path = 'study_dashboard/graph_data.json'
                with open(graph_path, 'r') as f:
                    graph = json.load(f)
                
                # Guardia de Cold Start: si no hay nodo activo, activar el primero
                has_active = any(n['group'] == 'active' for n in graph['nodes'])
                if not has_active:
                    for node in graph['nodes']:
                        if node['group'] == 'locked':
                            node['group'] = 'active'
                            node['title'] = "⚠️ SIGUIENTE EN CALENDARIO"
                            with open(graph_path, 'w') as f:
                                json.dump(graph, f, indent=4)
                            break
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(graph).encode())
            except Exception as e:
                print(f"Error en graph_data: {e}")
                self.send_error(500)
        elif self.path in ['/current_session', '/current_session.json']:
            try:
                session_path = 'current_session.json'
                if os.path.exists(session_path):
                    with open(session_path, 'r') as f:
                        session = json.load(f)
                else:
                    # Fallback session object if file is missing
                    session = {
                        "mode": "Sincronizando...",
                        "type": "selection",
                        "content": "### Preparando Reto Elite\nDr. Epi está analizando las guías 2024. Por favor espera un momento...",
                        "options": ["Cargando..."],
                        "correct_answer": "X",
                        "explanation": "El sistema se está inicializando."
                    }
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(session).encode())
            except Exception as e:
                print(f"Error en current_session: {e}")
                self.send_error(500)
        else:
            # Servir archivos estáticos
            super().do_GET()

    def log_message(self, format, *args):
        with open('study_dashboard/server.log', 'a') as f:
            f.write(f"{self.address_string()} - - [{self.log_date_time_string()}] {format%args}\n")

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)) + '/..')
    server = HTTPServer(('', PORT), StudyHandler)
    print(f"✅ Servidor iniciado en puerto {PORT}")
    server.serve_forever()
