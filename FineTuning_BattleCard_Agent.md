# Pipeline de Entrenamiento Autónomo: Agente Generador de Casos Clínicos (AI-Med)

Este entorno (notebook) está diseñado desde cero exclusivamente para las necesidades actuales de tu plataforma AI-Med Learning. El objetivo es entrenar a tu propio modelo local para que actúe como un **Generador Clínico Autónomo**. 

En lugar de ser un simple chatbot como el ejemplo anterior (Dr. Epi), este agente aprenderá a ingerir el conocimiento puro que extraigas de tus guías médicas (usando el MCP de NotebookLM) y lo transformará **siempre** y **estrictamente** en el formato *BattleCards* y *Drills* (Casos Clínicos, Nivel 1 MCQ y Nivel 2 Abierto) que usa tu `app.py` y `agent_srs.py`.

---

## 1. Preparación del Entorno Acelerado (Para Colab T4)
*Instalamos Unsloth y Xformers para optimizar la memoria y hacer posible el fine-tuning de un modelo de 8B parámetros en una sola GPU gratuita.*

```python
%%capture
# Usamos la rama principal de unsloth que incluye mitigaciones recientes
!pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
!pip install --no-deps xformers "trl<0.9.0" peft accelerate bitsandbytes datasets
```

---

## 2. Inicialización del Modelo Base Clínico
*Cargamos `Llama-3.1-8B-Instruct` cuantizado a 4 bits. Llama 3.1 tiene un razonamiento excepcional para estructurar documentos (esencial para que respete tu formato de BattleCards).*

```python
from unsloth import FastLanguageModel
import torch

max_seq_length = 4096 # Ampliado a 4096 porque el contexto de las guías médicas suele ser largo
dtype = None 
load_in_4bit = True 

# Modelo Base recomendado para tareas de estructuración profunda
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit",
    max_seq_length = max_seq_length,
    dtype = dtype,
    load_in_4bit = load_in_4bit,
)
```

---

## 3. Configuración de Filtros de Memoria (LoRA)
*Acoplamos los adaptadores que interceptarán todo el conocimiento de la red base para transformarlo únicamente en tus formatos de clínica.*

```python
model = FastLanguageModel.get_peft_model(
    model,
    r = 32, # Aumentamos el rango R a 32 para capturar mejor la estructura Markdown de tus tarjetas
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                      "gate_proj", "up_proj", "down_proj",],
    lora_alpha = 32,
    lora_dropout = 0, 
    bias = "none",
    use_gradient_checkpointing = "unsloth", 
    random_state = 1234,
    use_rslora = True, # rslora mejora la estabilidad en rangos más altos
    loftq_config = None,
)
```

---

## 4. Estructuración Estricta del Prompt (El Núcleo del Agente)
*Aquí definiremos exactamente qué va a aprender el modelo. No aprenderá a ser un chatbot; aprenderá a ser un **procesador de datos médicos hacia BattleCards** usando el formato exacto que necesita tu plataforma.*

```python
# Este prompt fuerza al modelo a no alucinar. Debe usar ÚNICAMENTE el input proporcionado.
battlecard_prompt = """Eres el Agente Generador Experto de AI-Med Learning.
Tu ÚNICA tarea es extraer la información médica provista en el [Contexto Científico] (previamente extraído vía MCP de NotebookLM) y estructurarla de forma estricta en una [BattleCard] compatible con la plataforma del usuario.
Bajo NINGUNA circunstancia puedes inventar datos que no estén en el contexto. Si algo no está, no lo incluyas.

### Tema Solicitado:
{}

### Contexto Científico (Input desde MCP NotebookLM):
{}

### BattleCard (Salida Estructurada):
{}"""

EOS_TOKEN = tokenizer.eos_token

def formatting_prompts_func(examples):
    temas    = examples["tema"]
    contextos = examples["contexto_mcp"]
    salidas  = examples["casos_generados"] # El markdown perfecto de tu BattleCard
    texts = []
    
    for tema, contexto, salida in zip(temas, contextos, salidas):
        text = battlecard_prompt.format(tema, contexto, salida) + EOS_TOKEN
        texts.append(text)
    return { "text" : texts, }

from datasets import load_dataset
# Sube tu dataset con columnas: "tema", "contexto_mcp" y "casos_generados" en formato Parquet o JSONL.
dataset = load_dataset("json", data_files="dataset_casos_clinicos.jsonl", split="train")

# Aplicar el formato
dataset = dataset.map(formatting_prompts_func, batched = True)
```

---

## 5. Bucle de Entrenamiento Especializado
*Ajustamos el optimizador para garantizar una reducción de pérdida estable que no comprometa las comillas sueltas ni la sintaxis Markdown (crítico para tu UI web).*

```python
from trl import SFTTrainer
from transformers import TrainingArguments

trainer = SFTTrainer(
    model = model,
    tokenizer = tokenizer,
    train_dataset = dataset,
    dataset_text_field = "text",
    max_seq_length = max_seq_length,
    dataset_num_proc = 2,
    packing = False,
    args = TrainingArguments(
        per_device_train_batch_size = 2,
        gradient_accumulation_steps = 4,
        warmup_steps = 10, # Más warmup para que no colapse al inicio con el formato estricto
        max_steps = 150, # Puedes ajustar los pasos según tu dataset
        learning_rate = 1.5e-4, # Ligeramente más bajo para evitar sobre-encajar estructuras
        fp16 = not torch.cuda.is_bf16_supported(),
        bf16 = torch.cuda.is_bf16_supported(),
        logging_steps = 5,
        optim = "adamw_8bit",
        weight_decay = 0.05,
        lr_scheduler_type = "cosine", # Mejora la convergencia final
        seed = 1234,
        output_dir = "outputs",
    ),
)

trainer_stats = trainer.train()
```

---

## 6. Validación Anti-Alucinación (Prueba)
*Hacemos una prueba en vivo con un extracto falso o real para comprobar que solo responde en formato BattleCard basándose en ese extracto.*

```python
FastLanguageModel.for_inference(model)

# Prueba de un escenario en vivo
tema_prueba = "Cetoacidosis Diabética (CAD)"
contexto_prueba = "Las guías 2024 recomiendan bolos de fluidos iniciales seguidos de insulina IV a 0.1 U/kg/hr. Criterios de resolución: Glucosa < 200, HCO3 >= 18."

inputs = tokenizer(
[
    battlecard_prompt.format(
        tema_prueba,
        contexto_prueba,
        "", # El campo de salida va vacío para forzar la generación
    )
], return_tensors = "pt").to("cuda")

# Generamos limitando la creatividad (temperature baja) para que no alucine
from transformers import TextStreamer
text_streamer = TextStreamer(tokenizer)
_ = model.generate(**inputs, streamer = text_streamer, max_new_tokens = 1024, temperature=0.1, do_sample=False)
```

---

## 7. Exportación Definitiva (GGUF V2) y Guardado en Drive
*Exportamos nuestro nuevo Agente Generador a un GGUF preparado para ser consumido localmente en tu Mac y lo guardamos directamente en Google Drive para evitar fallos de descarga.*

```python
# 1. Cuantizar y guardar el modelo a GGUF (4 bits, excelente para Mac M3)
model.save_pretrained_gguf("ai_med_model", tokenizer, quantization_method = "q4_k_m")

# 2. Exportarlo a tu Google Drive para descargarlo seguro
from google.colab import drive
import shutil
import os

drive.mount('/content/drive')

gguf_file = [f for f in os.listdir("ai_med_model") if f.endswith(".gguf")][0]
source_path = os.path.join("ai_med_model", gguf_file)
destination_path = f"/content/drive/MyDrive/{gguf_file}"

print(f"Copiando {source_path} a tu Google Drive... (Tomará unos minutos)")
shutil.copy2(source_path, destination_path)
print("¡Listo! Ya puedes descargar el GGUF desde tu Google Drive en tu Mac.")
```

## 8. Arquitectura de Integración (El Ecosistema Completo)

Entrenar el modelo (GGUF) es solo "fabricar el motor". Para lograr que la plataforma haga todo sola (calendario, SRS, preguntas de sub-nodos tras fallar y maestría total), el motor GGUF debe integrarse y ser orquestado por tu backend en Python.

Así es como estructuraremos la conexión entre tu nuevo modelo local de Colab y los sistemas que ya hemos venido desarrollando en `agent_srs.py` y tu base de datos SQLite `temario.db`:

### A. Calendario y Orden de Temas (La Cola de Prioridad)
*   **Gestión en DB:** `temario.db` tiene la tabla `topics` con columnas como `priority`, `date_assigned`, o `modulo`. 
*   **Orquestación:** Tu script `app.py` o `agent_srs.py` (en la función `get_next_topic()`) consulta la base de datos. Si hay temas nuevos (sin revisar), se los pide ordenados por el calendario. Si hay repasos pendientes por el SRS, estos tienen máxima prioridad.

### B. Repetición Espaciada (El Motor SM-2 Modernizado)
*   **Interacción Usuario-Modelo:** El GGUF (consumido vía `llama.cpp` en Python o vía API local de LM Studio) genera la *BattleCard* o el *Drill*.
*   **Feedback:** Tú respondes en la UI (`index.html`) e indicas si fue *Easy*, *Good*, *Hard*, o *Fail*.
*   **Algoritmo (`update_progress` en `agent_srs.py`):** Si respondes *Hard* o *Fail*, el SRS programa la siguiente revisión en 1 día o minutos. Si es *Easy*, la empuja a semanas o meses. El modelo local GGUF *no sabe* de SRS; su único trabajo es generar la pregunta. El backend en Python controla *cuándo* debe generarla.

### C. Sub-Nodos Dinámicos (El Castigo Inteligente al Fallar)
*Recuerda que implementamos la lógica de "Ángulos" o "Variantes" (`angle_id`) en tu `temario.db`.*
*   **La Lógica:** Cuando tú calificas una pregunta como *Fail* (1), el backend en Python captura ese fallo.
*   **Generación de Variantes:** El backend envía un nuevo prompt al *Agente Generador GGUF*:
    > *"El estudiante falló la pregunta sobre [Apendicitis]. Genera un nuevo caso clínico clínico (Sub-nodo B) sobre el mismo tema, pero planteando el problema desde una perspectiva diferente (Ej. complicaciones post-operatorias o diagnóstico diferencial pélvico). Usa este Nuevo Contexto: [...]"*
*   **Registro:** El nuevo *BattleCard* se asocia a la tabla `angles`, forzándote a responder la variante hasta que domines el sub-nodo.

### D. Aprendizaje Total (La Maestría del Tema)
*La maestría no se obtiene con MCQ. Se obtiene con el formato Abierto (Recall Activo) y factores de facilidad altos.*
1.  **Nivel 1 (Fase Cognitiva):** El GGUF genera preguntas de Selección Múltiple (MCQ). El SRS empieza en intervalo 0.
2.  **Transición:** Cuando el `ease_factor` (Factor de Facilidad en `temario.db`) de un tema cruza un umbral (ej. > 2.6) y su intervalo > 7 días, el tema avanza a Nivel 2.
3.  **Nivel 2 (Maestría / Recall Activo):** La próxima vez que el SRS dictamine que debes repasar ese tema, el backend le ordena al GGUF:
    > *"El estudiante ha alcanzado Nivel 2 en [Estatus Epiléptico]. Genera un Reto de Formato Abierto (Sin opciones). Exige el esquema completo de tratamiento de primera y segunda línea."*
4.  **Estado "Masterizado":** Si aciertas en Nivel 2 repetidas veces, el tema se marca como "Dominado" en el Dashboard, reduciendo la carga global de estudio.
