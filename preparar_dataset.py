import os
import json
import re

# Directorios de interés
BATTLECARDS_DIR = '/Users/danielsuarezsucre/ANALISIS DE TEMAS A ESTUDIAR/BattleCards'
OUTPUT_FILE = '/Users/danielsuarezsucre/ANALISIS DE TEMAS A ESTUDIAR/dataset_casos_clinicos.jsonl'

def extract_content(file_path):
    """Extrae el tema y el contenido de una BattleCard en Markdown."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Intentar extraer el título del H1 o H2
    title_match = re.search(r'^#+ (.*)', content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else os.path.basename(file_path)
    
    # El 'contexto_mcp' sería el contenido médico (simplificado para este ejemplo)
    # En un entorno real, esto vendría de los PDFs/Guías. Aquí usamos la tarjeta como base de conocimiento.
    contexto = f"Guía detallada sobre {title}. Contenido: {content[:1000]}..." # Limitamos para el ejemplo
    
    return {
        "tema": title,
        "contexto_mcp": contexto,
        "casos_generados": content # La tarjeta completa es nuestro 'target'
    }

def generate_dataset():
    if not os.path.exists(BATTLECARDS_DIR):
        print(f"❌ No se encontró la carpeta: {BATTLECARDS_DIR}")
        return

    files = [f for f in os.listdir(BATTLECARDS_DIR) if f.endswith('.md')]
    dataset = []

    for file in files:
        data = extract_content(os.path.join(BATTLECARDS_DIR, file))
        dataset.append(data)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for entry in dataset:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    
    print(f"✅ Dataset generado con {len(dataset)} ejemplos en: {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_dataset()
