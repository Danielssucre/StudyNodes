from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
import os
import sys
import sqlite3
from datetime import datetime

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

print(f"\n--- REINICIO DE SERVIDOR (V3.13): {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")

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
                        print(f"  🔁 Manteniendo maestría {current_m}")
                        
                    # Sincronizar con SQLite
                    try:
                        srs_rating = 4 if rating == 'EASY' else 2
                        conn = sqlite3.connect('temario.db')
                        c = conn.cursor()
                        search_title = topic_label.replace('\n', ' ').strip()
                        c.execute('SELECT id FROM topics WHERE title = ? OR title LIKE ?', (search_title, f"%{search_title}%"))
                        row = c.fetchone()
                        if row:
                            import agent_srs
                            agent_srs.update_progress(row[0], srs_rating)
                            print(f"  💾 SRS en SQLite OK (ID: {row[0]})")
                        conn.close()
                    except Exception as e:
                        print(f"  ⚠️ Error SQLite: {e}")
                
                with open(graph_path, 'w') as f:
                    json.dump(graph, f, indent=4)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode())
            except Exception as e:
                print(f"❌ Error /log_srs: {e}")
                self.send_error(500)

        elif self.path == '/trigger_next':
            try:
                graph_path = 'study_dashboard/graph_data.json'
                with open(graph_path, 'r') as f:
                    graph = json.load(f)
                
                current_node = next((n for n in graph['nodes'] if n['group'] == 'active'), None)
                
                if current_node:
                    mastery = current_node.get('mastery_level', 0)
                    if mastery >= 3:
                        current_node['group'] = 'mastered'
                        current_node['title'] = "🏆 DOMINADO (3/3 Ángulos)"
                        current_node = None
                
                if not current_node:
                    current_node = next((n for n in graph['nodes'] if n['group'] == 'locked'), None)
                    if current_node:
                        current_node['group'] = 'active'
                        current_node['title'] = "⚠️ OBJETIVO ACTUAL"
                        current_node['mastery_level'] = 0
                
                if not current_node:
                    self.send_error(404, "Calendario completado.")
                    return
                
                target_topic = current_node['label'].replace('\n', ' ').strip()
                m_level = current_node.get('mastery_level', 0)
                angles = ["Diagnosis", "Treatment", "Trap"]
                current_angle = angles[min(m_level, 2)]
                
                from notebook_adapter import NotebookAdapter
                nb = NotebookAdapter()
                res = nb.resolve_topic_acronym(target_topic)
                full_t = res.get('full_title', target_topic)
                ctx = res.get('context', f'Guía clínica sobre {target_topic}.')
                
                gemini = GeminiAdapter()
                session_data = gemini.generate_clinical_challenge(target_topic, full_t, ctx, angle=current_angle)
                if session_data:
                    session_data['mode'] = f"Dr. Epi | MAESTRÍA {m_level+1}/3"
                else:
                    session_data = {"mode": "FALLBACK", "type": "selection", "content": "Error generador.", "options": ["A", "B"], "correct_answer": "A", "explanation": "Fallback."}
                
                with open('current_session.json', 'w') as f:
                    json.dump(session_data, f)
                with open(graph_path, 'w') as f:
                    json.dump(graph, f, indent=4)

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "next": target_topic}).encode())
            except Exception as e:
                print(f"❌ Error trigger_next: {e}")
                self.send_error(500)

    def do_GET(self):
        if self.path == '/graph_data':
            try:
                graph_path = 'study_dashboard/graph_data.json'
                if not os.path.exists(graph_path):
                    graph = {"nodes": [], "edges": []}
                else:
                    with open(graph_path, 'r') as f:
                        graph = json.load(f)
                
                # Metrics logic (V3.13)
                total_possible = 126 * 3
                current_mastery = sum(n.get('mastery_level', 0) for n in graph.get('nodes', []))
                pending = total_possible - current_mastery
                
                today = datetime.now()
                target_date = datetime(2026, 3, 13, 23, 59, 59)
                days_left = (target_date - today).days + 1
                if days_left < 1: days_left = 1
                
                daily_goal = int((pending / days_left) + 0.99)
                
                done_today = 0
                try:
                    conn = sqlite3.connect('temario.db')
                    c = conn.cursor()
                    c.execute("SELECT count(*) FROM progress WHERE last_reviewed LIKE ?", (f"{today.strftime('%Y-%m-%d')}%",))
                    done_today = c.fetchone()[0]
                    conn.close()
                except: pass
                
                graph['metrics'] = {
                    "daily_goal": daily_goal,
                    "done_today": done_today,
                    "pending_total": pending,
                    "days_left": days_left
                }
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(graph).encode())
            except Exception as e:
                print(f"❌ Error graph_data: {e}")
                self.send_error(500)

        elif self.path in ['/current_session', '/current_session.json']:
            try:
                session_path = 'current_session.json'
                if os.path.exists(session_path):
                    with open(session_path, 'r') as f:
                        session = json.load(f)
                else:
                    session = {"mode": "Sincronizando...", "type": "selection", "content": "Cargando...", "options": ["X"], "correct_answer": "X", "explanation": "Iniciando."}
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(session).encode())
            except Exception as e:
                self.send_error(500)
        else:
            super().do_GET()

if __name__ == '__main__':
    # Configurar directorio de trabajo
    os.chdir(os.path.dirname(os.path.abspath(__file__)) + '/..')
    server = HTTPServer(('', PORT), StudyHandler)
    print(f"✅ Servidor iniciado en puerto {PORT}")
    server.serve_forever()
