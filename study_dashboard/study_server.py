import sys
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
from datetime import datetime

# Agregar el directorio raíz al path para importar herramientas locales
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import study_core

# Redirigir logs para depuración automática
LOG_FILE = "study_dashboard/debug_exec.log"
sys.stdout = open(LOG_FILE, "a", buffering=1)
sys.stderr = sys.stdout

print(f"\n--- REINICIO DE SERVIDOR (REFACTORED V3.14): {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")

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
                
                # Usar el CORE para procesar la respuesta
                study_core.process_review(topic_label, rating)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode())
            except Exception as e:
                print(f"❌ Error /log_srs: {e}")
                self.send_error(500)

        elif self.path == '/trigger_next':
            try:
                # Usar el CORE para obtener o generar el siguiente reto
                session_data = study_core.get_or_generate_challenge()
                
                if session_data and session_data.get('status') == 'completed':
                    self.send_error(404, session_data.get('message'))
                    return
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "next": session_data.get('target_topic')}).encode())
            except Exception as e:
                print(f"❌ Error trigger_next: {e}")
                self.send_error(500)

    def do_GET(self):
        if self.path == '/graph_data':
            try:
                # Usar el CORE para obtener métricas y cargar el grafo
                graph_path = study_core.GRAPH_PATH
                if not os.path.exists(graph_path):
                    graph = {"nodes": [], "edges": []}
                else:
                    with open(graph_path, 'r') as f:
                        graph = json.load(f)
                
                # Inyectar métricas desde el CORE
                graph['metrics'] = study_core.get_daily_metrics()
                
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
                # Intentar obtener el reto actual del CORE (lo carga de disco o lo genera)
                session = study_core.get_or_generate_challenge()
                
                if not session:
                    # Fallback por si falla la generación
                    session = {"mode": "Error", "type": "selection", "content": "No se pudo generar el reto.", "options": ["Reintentar"], "correct_answer": "X", "explanation": "Error de API."}
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(session).encode())
            except Exception as e:
                print(f"❌ Error /current_session: {e}")
                self.send_error(500)
        else:
            super().do_GET()

if __name__ == '__main__':
    # Configurar directorio de trabajo
    os.chdir(os.path.dirname(os.path.abspath(__file__)) + '/..')
    server = HTTPServer(('', PORT), StudyHandler)
    print(f"✅ Servidor iniciado en puerto {PORT}")
    server.serve_forever()
