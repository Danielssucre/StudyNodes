import json
import os
import sqlite3
import math
from datetime import datetime
import agent_srs
from gemini_adapter import GeminiAdapter
from notebook_adapter import NotebookAdapter

DB_PATH = 'temario.db'
GRAPH_PATH = 'study_dashboard/graph_data.json'
SESSION_PATH = 'current_session.json'

def get_daily_metrics():
    """Calcula las métricas de progreso para el dashboard y Telegram."""
    if not os.path.exists(GRAPH_PATH):
        return None
    
    with open(GRAPH_PATH, 'r') as f:
        graph = json.load(f)
    
    total_possible = 126 * 3
    current_mastery = sum(n.get('mastery_level', 0) for n in graph.get('nodes', []))
    pending = total_possible - current_mastery
    
    today = datetime.now()
    target_date = datetime(2026, 3, 13, 23, 59, 59)
    days_left = (target_date - today).days + 1
    if days_left < 1: days_left = 1
    
    daily_goal = math.ceil(pending / days_left)
    
    done_today = 0
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT count(*) FROM progress WHERE last_reviewed LIKE ?", (f"{today.strftime('%Y-%m-%d')}%",))
        done_today = c.fetchone()[0]
        conn.close()
    except Exception as e:
        print(f"⚠️ Error SQLite Metrics: {e}")
    
    return {
        "daily_goal": daily_goal,
        "done_today": done_today,
        "pending_total": pending,
        "days_left": days_left,
        "current_mastery": current_mastery,
        "total_possible": total_possible
    }

def process_review(topic_label, rating):
    """Procesa una respuesta (EASY/HARD) y actualiza Grafo + SQLite."""
    print(f"⚙️ [CORE] Procesando Review: {topic_label} | {rating}")
    
    # 1. Actualizar Grafo JSON
    if os.path.exists(GRAPH_PATH):
        with open(GRAPH_PATH, 'r') as f:
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
            
            with open(GRAPH_PATH, 'w') as f:
                json.dump(graph, f, indent=4)
        else:
            print(f"  ⚠️ No se encontró el nodo activo en el grafo para: {topic_label}")

    # 2. Actualizar SQLite SRS
    try:
        srs_rating = 4 if rating == 'EASY' else 2
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        search_title = topic_label.replace('\n', ' ').strip()
        c.execute('SELECT id FROM topics WHERE title = ? OR title LIKE ?', (search_title, f"%{search_title}%"))
        row = c.fetchone()
        if row:
            agent_srs.update_progress(row[0], srs_rating)
            print(f"  💾 SQLite Sync OK para ID: {row[0]}")
        conn.close()
    except Exception as e:
        print(f"  ⚠️ Error SQLite Sync: {e}")
    
    # 3. Invalidar Sesión Actual (Forzar nuevo reto)
    if os.path.exists(SESSION_PATH):
        try:
            os.remove(SESSION_PATH)
            print("  🗑️ [CORE] Sesión previa eliminada.")
        except Exception as e:
            print(f"  ⚠️ Error eliminando sesión: {e}")
            
    return True

def get_or_generate_challenge():
    """Obtiene el reto actual o genera el siguiente si es necesario."""
    # 1. Cargar Grafo
    if not os.path.exists(GRAPH_PATH):
        return None
        
    with open(GRAPH_PATH, 'r') as f:
        graph = json.load(f)
    
    # 2. Buscar nodo activo o activar siguiente
    current_node = next((n for n in graph['nodes'] if n['group'] == 'active'), None)
    
    if current_node:
        mastery = current_node.get('mastery_level', 0)
        if mastery >= 3:
            current_node['group'] = 'mastered'
            current_node['title'] = "🏆 DOMINADO"
            current_node = None
            
    if not current_node:
        current_node = next((n for n in graph['nodes'] if n['group'] == 'locked'), None)
        if current_node:
            current_node['group'] = 'active'
            current_node['title'] = "⚠️ OBJETIVO ACTUAL"
            current_node['mastery_level'] = 0
            with open(GRAPH_PATH, 'w') as f:
                json.dump(graph, f, indent=4)
    
    if not current_node:
        return {"status": "completed", "message": "¡Felicidades! Todo el calendario está dominado."}
    
    target_topic = current_node['label'].replace('\n', ' ').strip()
    m_level = current_node.get('mastery_level', 0)
    
    # 3. Generar Desafío si no hay sesión actual válida para este tema/nivel
    if os.path.exists(SESSION_PATH):
        with open(SESSION_PATH, 'r') as f:
            session = json.load(f)
            # Si el reto en disco coincide con el actual, devolverlo
            if session.get('target_topic') == target_topic and session.get('m_level') == m_level:
                return session
    
    # De lo contrario, generar nuevo
    angles = ["Diagnosis", "Treatment", "Trap"]
    current_angle = angles[min(m_level, 2)]
    
    nb = NotebookAdapter()
    res = nb.resolve_topic_acronym(target_topic)
    full_t = res.get('full_title', target_topic)
    ctx = res.get('context', f'Guía clínica sobre {target_topic}.')
    
    gemini = GeminiAdapter()
    session_data = gemini.generate_clinical_challenge(target_topic, full_t, ctx, angle=current_angle)
    
    if session_data:
        session_data['target_topic'] = target_topic
        session_data['m_level'] = m_level
        session_data['mode'] = f"Dr. Epi | MAESTRÍA {m_level+1}/3"
        with open(SESSION_PATH, 'w') as f:
            json.dump(session_data, f)
        return session_data
    
    return None
