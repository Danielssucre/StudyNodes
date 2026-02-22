import sqlite3
import datetime
import sys
import json
import math

DB_PATH = 'temario.db'

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def setup_db():
    # Ensure tables exist (redundant but safe)
    conn = get_conn()
    c = conn.cursor()
    # topics table is assumed to exist.
    # progress table:
    c.execute('''CREATE TABLE IF NOT EXISTS progress (
        angle_id INTEGER PRIMARY KEY,
        status TEXT DEFAULT 'pending', -- pending, learning, review
        interval INTEGER DEFAULT 0,
        ease_factor REAL DEFAULT 2.5,
        next_review TEXT,
        last_reviewed TEXT,
        FOREIGN KEY(angle_id) REFERENCES angles(id)
    )''')
    conn.commit()
    conn.close()

def get_next_topic():
    conn = get_conn()
    c = conn.cursor()
    now = datetime.datetime.now().isoformat()
    
    # 1. Check for DUE REVIEWS (status='review' and next_review <= now)
    # We join angles and topics to get the title
    c.execute('''
        SELECT t.id, t.title, p.status, p.interval, p.ease_factor
        FROM topics t
        JOIN angles a ON t.id = a.topic_id
        JOIN progress p ON a.id = p.angle_id
        WHERE p.status = 'review' AND p.next_review <= ?
        ORDER BY p.next_review ASC
        LIMIT 1
    ''', (now,))
    due = c.fetchone()
    
    if due:
        conn.close()
        return dict(due) | {"type": "review"}
        
    # 2. If no reviews, get next NEW topic (status='pending' OR NULL)
    # Left join to find topics that might not have a progress entry yet
    c.execute('''
        SELECT t.id, t.title, p.status, p.interval, p.ease_factor
        FROM topics t
        LEFT JOIN angles a ON t.id = a.topic_id 
        LEFT JOIN progress p ON a.id = p.angle_id
        WHERE p.status = 'pending' OR p.status IS NULL
        ORDER BY t.priority DESC, t.id ASC
        LIMIT 1
    ''')
    new_topic = c.fetchone()
    conn.close()
    
    if new_topic:
         # If it was NULL, it means we need to init the angle/progress row first?
         # Actually, for this lightweight script, we just return the topic info.
         # The 'update' function will need to handle inserting if missing.
         return {
             "id": new_topic["id"], 
             "title": new_topic["title"], 
             "type": "new", 
             "status": "pending", 
             "interval": 0, 
             "ease_factor": 2.5
         }
    
    return None

def update_progress(topic_id, rating):
    # Rating: 1 (Fail), 2 (Hard), 3 (Good), 4 (Easy)
    conn = get_conn()
    c = conn.cursor()
    
    # 1. Get the angle_id for this topic (assuming 1 angle per topic for now, or take the first V1)
    c.execute('SELECT id FROM angles WHERE topic_id = ? ORDER BY id LIMIT 1', (topic_id,))
    angle_row = c.fetchone()
    
    if not angle_row:
        # If no angle exists, create default 'General' angle
        c.execute('INSERT INTO angles (topic_id, angle_name, variant) VALUES (?, ?, ?)', (topic_id, 'General', 'V1'))
        angle_id = c.lastrowid
    else:
        angle_id = angle_row['id']
    
    # 2. Get current state
    c.execute('SELECT * FROM progress WHERE angle_id = ?', (angle_id,))
    row = c.fetchone()
    
    current_interval = row['interval'] if row else 0
    current_ease = row['ease_factor'] if row else 2.5
    
    # SM-2 Logic
    new_interval = 0
    new_ease = current_ease
    next_status = 'review'
    
    if rating == 1: # Again
        new_interval = 0 
        new_ease = max(1.3, current_ease - 0.2)
        next_status = 'learning'
    elif rating == 2: # Hard
        new_interval = 1 if current_interval == 0 else math.floor(current_interval * 1.2)
        new_ease = max(1.3, current_ease - 0.15)
        next_status = 'review'
    elif rating == 3: # Good
        if current_interval == 0: new_interval = 1
        elif current_interval == 1: new_interval = 3
        else: new_interval = math.floor(current_interval * current_ease)
        next_status = 'review'
    elif rating == 4: # Easy
        if current_interval == 0: new_interval = 2
        elif current_interval == 1: new_interval = 4
        else: new_interval = math.floor(current_interval * current_ease * 1.3)
        new_ease = min(3.0, current_ease + 0.15)
        next_status = 'review'

    days_delta = 1 if new_interval == 0 else new_interval
    next_date = (datetime.datetime.now() + datetime.timedelta(days=days_delta)).isoformat()
    now_str = datetime.datetime.now().isoformat()
    
    if row:
        c.execute('''
            UPDATE progress
            SET status = ?, interval = ?, ease_factor = ?, next_review = ?, last_reviewed = ?
            WHERE angle_id = ?
        ''', (next_status, new_interval, new_ease, next_date, now_str, angle_id))
    else:
        c.execute('''
            INSERT INTO progress (angle_id, status, interval, ease_factor, next_review, last_reviewed)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (angle_id, next_status, new_interval, new_ease, next_date, now_str))
    
    conn.commit()
    conn.close()
    
    return {"topic_id": topic_id, "new_interval": new_interval, "next_review": next_date}

if __name__ == '__main__':
    command = sys.argv[1] if len(sys.argv) > 1 else 'next'
    
    if command == 'setup':
        setup_db()
        print("Database structure verified.")
        
    elif command == 'next':
        topic = get_next_topic()
        if topic:
            print(json.dumps(topic, ensure_ascii=False))
        else:
            print(json.dumps({"message": "No topics pending!"}))
            
    elif command == 'update':
        # Usage: python agent_srs.py update <topic_id> <rating>
        try:
            t_id = int(sys.argv[2])
            rating = int(sys.argv[3])
            res = update_progress(t_id, rating)
            print(json.dumps(res))
        except Exception as e:
            print(json.dumps({"error": str(e)}))
