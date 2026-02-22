import sqlite3
import datetime
import sys
import json

DB_PATH = 'temario.db'

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def log_question_db(topic_title, question_data):
    # question_data expected to be a dict with:
    # question, options (list), answer, explanation, context (optional)
    
    conn = get_conn()
    c = conn.cursor()
    
    # 1. Find Topic ID
    c.execute('SELECT id FROM topics WHERE title = ?', (topic_title,))
    topic_row = c.fetchone()
    
    if not topic_row:
        print(f"Error: Topic '{topic_title}' not found.")
        conn.close()
        return
        
    topic_id = topic_row['id']
    
    # 2. Find or Create Angle (Default 'General' or 'Journal')
    # We'll use a specific angle name 'Journal' to distinguish these active recall questions
    c.execute("SELECT id FROM angles WHERE topic_id = ? AND angle_name = 'Journal'", (topic_id,))
    angle_row = c.fetchone()
    
    if angle_row:
        angle_id = angle_row['id']
    else:
        c.execute("INSERT INTO angles (topic_id, angle_name, variant) VALUES (?, 'Journal', 'Socratic')", (topic_id,))
        angle_id = c.lastrowid
        
    # 3. Insert Question
    # Ensure json is valid
    json_content = json.dumps(question_data, ensure_ascii=False)
    created_at = datetime.datetime.now().isoformat()
    
    c.execute('INSERT INTO questions (angle_id, content_json, created_at) VALUES (?, ?, ?)', 
              (angle_id, json_content, created_at))
    
    conn.commit()
    conn.close()
    print(f"✅ Question saved for '{topic_title}' (Angle ID: {angle_id})")

if __name__ == "__main__":
    # Usage: python agent_journal.py "Topic Name" '{"question": "...", ...}'
    if len(sys.argv) < 3:
        print("Usage: python agent_journal.py <topic> <json_data>")
        sys.exit(1)
        
    topic = sys.argv[1]
    raw_json = sys.argv[2]
    
    try:
        data = json.loads(raw_json)
        log_question_db(topic, data)
    except json.JSONDecodeError as e:
        print(f"JSON Error: {e}")
