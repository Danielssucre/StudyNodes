import sqlite3
import json
import random
import time
import sys
import os
from gemini_adapter import GeminiAdapter
from notebook_adapter import NotebookAdapter

class DiagnosticEngine:
    def __init__(self, db_path='temario.db'):
        self.db_path = db_path
        self.gemini = GeminiAdapter()
        self.nb = NotebookAdapter()

    def get_diagnostic_topics(self, n=20):
        """Selects n high-priority or unknown topics for the baseline test."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        # Prioritize topics with priority 90+ that haven't been reviewed much
        c.execute("SELECT title, priority FROM topics WHERE priority >= 80 ORDER BY RANDOM() LIMIT ?", (n,))
        topics = c.fetchall()
        conn.close()
        return topics

    def run_simulacro(self, count=20):
        print("="*60)
        print(f"🚀 INICIANDO SIMULACRO DE DIAGNÓSTICO CORTEX ({count} TEMAS)")
        print("="*60)
        
        topics = self.get_diagnostic_topics(count)
        results = []

        for i, (title, prio) in enumerate(topics):
            print(f"\n[{i+1}/{count}] TEMA: {title} (Prioridad: {prio})")
            
            # 1. Resolve context
            res = self.nb.resolve_topic_acronym(title)
            full_title = res.get('full_title', title)
            context = res.get('context', f'Guía clínica sobre {title}')
            
            # 2. Generate Challenge (Angle: Diagnosis)
            try:
                challenge = self.gemini.generate_clinical_challenge(title, full_title, context)
                if not challenge:
                    print("  ⚠️ Falló Gemini, saltando tema...")
                    continue
                
                print(f"\n{challenge['content']}")
                for opt in challenge['options']:
                    print(f"  {opt}")
                
                start_time = time.time()
                ans = input("\n👉 Tu respuesta (A, B, C, D) o Enter para saltar: ").strip().upper()
                duration = time.time() - start_time
                
                if not ans:
                    continue
                
                is_correct = ans == challenge['correct_answer']
                if is_correct:
                    print("  ✅ ¡CORRECTO!")
                else:
                    print(f"  ❌ INCORRECTO. La correcta era {challenge['correct_answer']}")
                
                print(f"  💡 EXPLICACIÓN: {challenge['explanation'][:200]}...")
                
                results.append({
                    "title": title,
                    "is_correct": is_correct,
                    "duration": duration
                })
                
                # Update DB baseline
                self.update_topic_baseline(title, is_correct)
                
            except Exception as e:
                print(f"  ❌ Error en reto: {e}")

        self.print_summary(results)

    def update_topic_baseline(self, title, is_correct):
        """Sets the initial SRS parameters in the database."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # SM-2 inspired baseline
        # Ease factor: 2.5 (avg), Interval: 1 day if correct, 0 if wrong
        if is_correct:
            ef = 2.5
            interval = 1
        else:
            ef = 1.3
            interval = 0
            
        c.execute("""
            UPDATE topics 
            SET ease_factor = ?, interval = ?, next_review = date('now', '+' || ? || ' days')
            WHERE title = ?
        """, (ef, interval, interval, title))
        
        conn.commit()
        conn.close()

    def print_summary(self, results):
        if not results:
            print("\nNo se completaron retos.")
            return
            
        correct = sum(1 for r in results if r['is_correct'])
        pct = (correct / len(results)) * 100
        avg_time = sum(r['duration'] for r in results) / len(results)
        
        print("\n" + "="*60)
        print("🏆 RESUMEN DEL DIAGNÓSTICO")
        print("="*60)
        print(f"  Precisión: {pct:.1f}% ({correct}/{len(results)})")
        print(f"  Tiempo prom: {avg_time:.1f}s por pregunta")
        print("  Los intervalos de repaso han sido actualizados en temario.db")
        print("="*60)

if __name__ == "__main__":
    engine = DiagnosticEngine()
    # If called with --test, only run 3 topics
    count = 3 if "--test" in sys.argv else 20
    engine.run_simulacro(count)
