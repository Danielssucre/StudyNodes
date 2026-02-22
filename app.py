import sqlite3
import datetime
import glob
import os
import random
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI()
DB_PATH = 'temario.db'
CARDS_DIR = 'BattleCards'

from local_ai_adapter import LocalAIAdapter
from notebook_adapter import NotebookAdapter

ai_adapter = LocalAIAdapter()
nb_adapter = NotebookAdapter()

# --- DATA MODELS ---
class Review(BaseModel):
    card_filename: str
    rating: int  # 1=Again, 2=Hard, 3=Good, 4=Easy

# --- DATABASE HELPERS ---
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def parse_card(filepath):
    """Parses a Battle Card MD file into granular sections for sequential unlock."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Section markers
    markers = {
        "vignette": "## 1. 🚨 LA TRAMPA CLINICA",
        "foundation": "## 1.5 🔬 CIENCIA DE BASE",
        "algorithm": "## 2. 🌳 ÁRBOL DE DECISIÓN",
        "keys": "## 3. 🔑 LLAVES MAESTRAS",
        "pearls": "## 5. 💡 PERLAS CLÍNICAS",
        "mcq": "## 6. 🏁 CHECK POINT"
    }
    
    # Find the main title (robust parsing)
    topic_title = "Sin Título"
    possible_headers = [
        '# 🛡️ CARTA DE BATALLA: ',
        '# ⚔️ BATTLE CARD: ',
        '## CARTA DE BATALLA: ',
        '# BATTLE CARD: '
    ]
    for header in possible_headers:
        if header in content:
            topic_title = content.split(header)[1].split('\n')[0].strip()
            # Clean up trailing markdown if any
            topic_title = topic_title.replace('**', '').replace('__', '').strip()
            break
    
    def extract_between(text, start_marker, end_marker=None):
        if start_marker not in text: return ""
        parts = text.split(start_marker)
        if len(parts) < 2: return ""
        remaining = parts[1]
        
        if end_marker:
            if end_marker in remaining:
                return remaining.split(end_marker)[0].strip()
            return remaining.strip()
        return remaining.strip()

    # Extracting sections (ignoring preamble)
    vignette = extract_between(content, markers["vignette"], markers["foundation"])
    foundation = extract_between(content, markers["foundation"], markers["algorithm"])
    algorithm = extract_between(content, markers["algorithm"], markers["keys"])
    keys = extract_between(content, markers["keys"], markers["pearls"])
    pearls = extract_between(content, markers["pearls"], markers["mcq"])
    mcq_raw = extract_between(content, markers["mcq"])
    
    # MCQ Parsing
    mcq_data = None
    if mcq_raw:
        try:
             lines = mcq_raw.split('\n')
             question = ""
             options = []
             answer = ""
             
             for line in lines:
                 l = line.strip()
                 # Handle both * and - bullet styles
                 l_clean = l.lstrip('* -').strip()
                 
                 if "**Pregunta:**" in l: 
                     question = l.split("**Pregunta:**")[1].strip()
                 elif any(l_clean.startswith(f"{prefix}{sep}") for prefix in "ABCD" for sep in [")", "."]):
                     options.append(l_clean)
                 elif "**Respuesta Correcta:**" in l: 
                     raw_ans = l.split("**Respuesta Correcta:**")[1].strip()
                     # Extract the first letter (A, B, C, or D) from the response
                     for char in raw_ans:
                         if char.upper() in "ABCD":
                             answer = char.upper()
                             break
             
             if question and options:
                 mcq_data = {"question": question, "options": options, "answer": answer}
        except Exception as e:
            print(f"Error parsing MCQ: {e}")
            pass

    return {
        "filename": os.path.basename(filepath),
        "topic": topic_title,
        "vignette": vignette,
        "foundation": foundation,
        "algorithm": algorithm,
        "keys": keys,
        "pearls": pearls,
        "mcq": mcq_data
    }

# --- ALGORITHM (Simplified SM-2) ---
def calculate_next_review(rating, current_interval, ease_factor):
    # Rating: 1=Fail, 2=Hard, 3=Good, 4=Easy
    
    if rating == 1:
        new_interval = 0 # 10 min (today)
        new_ease = max(1.3, ease_factor - 0.2)
    elif rating == 2:
        new_interval = 1 # 1 day
        new_ease = max(1.3, ease_factor - 0.15)
    elif rating == 3:
        if current_interval == 0: new_interval = 1
        elif current_interval == 1: new_interval = 3
        else: new_interval = round(current_interval * ease_factor)
        new_ease = ease_factor
    elif rating == 4:
        if current_interval == 0: new_interval = 2
        elif current_interval == 1: new_interval = 4
        else: new_interval = round(current_interval * ease_factor * 1.3)
        new_ease = min(3.0, ease_factor + 0.15)
        
    return new_interval, new_ease

# --- API ENDPOINTS ---

@app.get("/api/card")
async def get_next_card(topic: str = None):
    conn = get_db_connection()
    now = datetime.datetime.now().isoformat()
    
    row = None
    cursor = conn.cursor() # Define cursor here to be available for both branches
    if topic:
        cursor.execute("SELECT title FROM topics WHERE title = ?", (topic,))
        row = cursor.fetchone()
        if not row:
            # Try fuzzy match if exact not found
            cursor.execute("SELECT title FROM topics WHERE title LIKE ? LIMIT 1", (f"%{topic}%",))
            row = cursor.fetchone()
    
    if not row:
        # SRS selection logic (backup if no topic requested or found)
        cursor.execute('''
            SELECT t.title, p.next_review, p.status
            FROM topics t
            LEFT JOIN angles a ON t.id = a.topic_id
            LEFT JOIN progress p ON a.id = p.angle_id
            GROUP BY t.title
            ORDER BY 
                CASE WHEN p.next_review <= ? THEN 0 ELSE 1 END,
                CASE WHEN p.status = 'learning' THEN 1 ELSE 2 END,
                CASE WHEN p.status = 'pending' OR p.status IS NULL THEN 3 ELSE 4 END,
                p.next_review ASC
            LIMIT 1
        ''', (now,))
        row = cursor.fetchone()
    
    # Map files to topics to see if we already have it
    files = glob.glob(os.path.join(CARDS_DIR, "*.md"))
    file_map = {}
    for f in files:
        try:
            # We don't want to parse EVERY card on every request for speed, 
            # so we'll guess from filename if possible or do a quick parse.
            # Filenames are usually "Topic_Name_GGUF.md" or similar now.
            # For robustness, let's keep the parse_card but maybe cache it?
            # For now, let's just parse what we need.
            card_data = parse_card(f)
            file_map[card_data["topic"]] = f
        except:
            continue

    if row and row["title"] in file_map:
        selected_file = file_map[row["title"]]
    elif row:
        # TEMA SELECCIONADO POR EL SRS PERO SIN TARJETA MD
        topic_title = row["title"]
        print(f"⚠️ Tarjeta no encontrada para: {topic_title}. Generando con IA Local...")
        
        # --- PASO DE CLARIFICACIÓN DE ACRÓNIMOS ---
        full_title = topic_title
        context = f"Guía clínica detallada sobre {topic_title} siguiendo protocolos de Colombia 2024-2025."
        
        try:
            # Siempre intentamos resolver para tener mayor precisión, 
            # pero especialmente si es corto (< 6 chars) o todo mayúsculas
            is_acronym = len(topic_title) <= 6 or any(word.isupper() for word in topic_title.split())
            if is_acronym:
                print(f"🔍 Detectado posible acrónimo: {topic_title}. Consultando NotebookLM...")
                resolution = nb_adapter.resolve_topic_acronym(topic_title)
                full_title = resolution.get("full_title", topic_title)
                context = resolution.get("context", context)
                print(f"✅ Acrónimo resuelto: {topic_title} -> {full_title}")
        except Exception as e:
            print(f"⚠️ Error en paso de clarificación: {e}")

        generated_content = ai_adapter.generate_battlecard(topic_title, context, full_title=full_title)
        if generated_content:
            selected_file = ai_adapter.save_card(topic_title, generated_content)
            print(f"✅ Tarjeta generada y guardada en: {selected_file}")
        else:
            raise HTTPException(status_code=500, detail="Error generando la tarjeta con la IA Local.")
    else:
        # Fallback to random if DB selection fails
        selected_file = random.choice(files)
    
    card_data = parse_card(selected_file)
    return card_data

@app.get("/api/stats")
async def get_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Total Topics in Syllabus
    cursor.execute("SELECT COUNT(*) FROM topics")
    total_topics = cursor.fetchone()[0]
    
    # 2. Topics with at least one Battle Card generated
    # We look into the BattleCards folder
    files = glob.glob(os.path.join(CARDS_DIR, "*.md"))
    generated_count = len(files)
    
    # 3. Cards due for review today
    now = datetime.datetime.now().isoformat()
    # We need to map files back to topics/progress
    # For speed, we just count things in DB where next_review <= now
    cursor.execute("SELECT COUNT(DISTINCT a.topic_id) FROM progress p JOIN angles a ON p.angle_id = a.id WHERE p.next_review <= ? AND p.status = 'review'", (now,))
    due_reviews = cursor.fetchone()[0]
    
    # 4. Pending Topics (never generated)
    # Total - generated is a good proxy, but let's be precise
    cursor.execute("SELECT COUNT(DISTINCT t.id) FROM topics t JOIN angles a ON t.id = a.topic_id JOIN progress p ON a.id = p.angle_id WHERE p.status = 'pending'")
    pending_to_generate = cursor.fetchone()[0]

    conn.close()
    
    return {
        "total": total_topics,
        "generated": generated_count,
        "due_reviews": due_reviews,
        "pending_gen": pending_to_generate,
        "days_left": (datetime.date(2026, 3, 14) - datetime.date.today()).days
    }

@app.get("/api/roadmap")
async def get_roadmap():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get all topics and their aggregate progress
    # We take the best interval for a topic as its "stability"
    cursor.execute("""
        SELECT t.id, t.title, MAX(p.interval) as max_int, p.status, p.next_review
        FROM topics t
        LEFT JOIN angles a ON t.id = a.topic_id
        LEFT JOIN progress p ON a.id = p.angle_id
        GROUP BY t.id
        ORDER BY t.id ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    
    now = datetime.datetime.now().isoformat()
    roadmap = []
    
    for r in rows:
        status = r["status"]
        interval = r["max_int"] or 0
        next_r = r["next_review"]
        
        # Color Level Logic
        level = "pending" # Gray
        if status == 'review':
            if next_r and next_r <= now:
                level = "urgent" # Orange/Red - Due now
            elif interval >= 14:
                level = "mastered" # Green - Long term
            elif interval >= 3:
                level = "learning" # Blue
            else:
                level = "fresh" # Yellow - Just started
                
        roadmap.append({
            "id": r["id"],
            "title": r["title"],
            "level": level,
            "interval": interval
        })
        
    return roadmap

@app.post("/api/review")
async def submit_review(review: Review):
    # Parse card to get topic
    filepath = os.path.join(CARDS_DIR, review.card_filename)
    card_data = parse_card(filepath)
    topic_title = card_data["topic"]
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get current SRS stats
    cursor.execute('''
        SELECT p.angle_id, p.interval, p.ease_factor
        FROM progress p
        JOIN angles a ON p.angle_id = a.id
        JOIN topics t ON a.topic_id = t.id
        WHERE t.title = ?
        LIMIT 1
    ''', (topic_title,))
    
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"status": "error", "message": "Topic not found in progress"}
    
    # Calculate next review
    new_interval, new_ease = calculate_next_review(
        review.rating, 
        row["interval"] or 0, 
        row["ease_factor"] or 2.5
    )
    
    next_review_date = (datetime.datetime.now() + datetime.timedelta(days=new_interval)).isoformat()
    
    # Update all angles for this topic (to sync SRS for the whole topic)
    cursor.execute('''
        UPDATE progress 
        SET status = 'review',
            interval = ?,
            ease_factor = ?,
            next_review = ?,
            last_reviewed = ?
        WHERE angle_id IN (
            SELECT a.id FROM angles a
            JOIN topics t ON a.topic_id = t.id
            WHERE t.title = ?
        )
    ''', (new_interval, new_ease, next_review_date, datetime.datetime.now().isoformat(), topic_title))
    
    conn.commit()
    conn.close()
    
    print(f"✅ SRS Update for {topic_title}: Int={new_interval}, Ease={new_ease}, Next={next_review_date}")
    return {"status": "success", "next_review": next_review_date}

# --- FRONTEND SERVING ---
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)
