# Guía Maestra: Pipeline de Fine-Tuning para tu Agente de BattleCards (AI-Med)

Esta guía detalla paso a paso qué está sucediendo en "las entrañas" de tu entrenamiento en Google Colab. Úsala para copiar y pegar cada bloque en una celda nueva de Colab.

---

### Paso 0: Verificación de Potencia (GPU)
Antes de empezar, asegúrate de que Google te prestó una GPU (T4). 
1. Ve a `Entorno de ejecución` -> `Cambiar tipo de entorno`.
2. Selecciona `T4 GPU`.
3. Ejecuta esta celda para confirmar:
```python
import torch
if torch.cuda.is_available():
    print(f"✅ GPU Detectada: {torch.cuda.get_device_name(0)}")
else:
    print("❌ NO hay GPU detectada. Ve al menú Entorno de ejecución y cámbialo.")
```

---

### Paso 1: Instalación de "Unsloth" (La Biblioteca Mágica)
**¿Qué sucede aquí?** Instalamos el motor que permite entrenar modelos gigantes en memorias pequeñas. 
*Nota: He corregido el `%%capture` para que no te dé error.*

```python
%%capture
# %%capture (con dos %) oculta el texto largo de instalación
!pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
!pip install --no-deps xformers "trl<0.9.0" peft accelerate bitsandbytes datasets
```

---

### Paso 2: Descarga del "Cerebro" (Llama-3.1-8B)
**¿Qué sucede aquí?** Bajamos el modelo base de Meta (Llama 3.1). Lo bajamos en "4-bits", que es como enviarle una versión comprimida para que quepa en la memoria RAM de la tarjeta de video (T4).

```python
from unsloth import FastLanguageModel
import torch

# Parámetros básicos
max_seq_length = 4096 # Longitud máxima de texto (largo para guías médicas)
load_in_4bit = True   # Cuantización para ahorrar memoria

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit",
    max_seq_length = max_seq_length,
    load_in_4bit = load_in_4bit,
)
print("✅ Cerebro base descargado y listo.")
```

---

### Paso 3: Activación de LoRA (Los Adaptadores Mentales)
**¿Qué sucede aquí?** En lugar de intentar cambiar todas las neuronas del modelo (billones), creamos "capas delgadas" de neuronas nuevas (LoRA). Solo estas se entrenarán con tus datos médicos, lo que hace el proceso 10 veces más rápido.

```python
model = FastLanguageModel.get_peft_model(
    model,
    r = 32, # Rango: Determina qué tan "inteligente" será el ajuste. 32 es ideal para formatos complejos.
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                      "gate_proj", "up_proj", "down_proj",],
    lora_alpha = 32,
    lora_dropout = 0,
    bias = "none",
    use_gradient_checkpointing = "unsloth",
    random_state = 1234,
)
print("✅ Adaptadores LoRA conectados.")
```

---

### Paso 4: Preparación de tus Datos (Dataset)
**¿Qué sucede aquí?** Le decimos al modelo cómo se ve una "BattleCard" perfecta. 
1. **Sube tu archivo** `dataset_casos_clinicos.jsonl` a la carpeta lateral de Colab antes de ejecutar esto.

```python
# Definimos el molde (prompt) estricto
prompt_escuela = """Eres el Agente Generador Experto de AI-Med Learning.
Extrae la información médica del [Contexto] y conviértela en una [BattleCard]. 

### Contexto Científico:
{}

### BattleCard (Formato Estricto):
{}"""

EOS_TOKEN = tokenizer.eos_token # Fin de respuesta

def format_func(examples):
    contextos = examples["contexto_mcp"]
    salidas   = examples["casos_generados"]
    return { "text" : [prompt_escuela.format(c, s) + EOS_TOKEN for c, s in zip(contextos, salidas)] }

from datasets import load_dataset
# Carga tus datos reales
dataset = load_dataset("json", data_files="dataset_casos_clinicos.jsonl", split="train")
dataset = dataset.map(format_func, batched = True)
print(f"✅ Dataset cargado: {len(dataset)} ejemplos listos para el entrenamiento.")
```

---

### Paso 5: El Entrenamiento (Fine-Tuning Real)
**¿Qué sucede aquí?** Inicia el proceso donde el modelo empieza a leer tus datos y a ajustar sus adaptadores LoRA para imitar tu estilo de BattleCards.
*Nota: Esto toma entre 10 y 20 minutos según el tamaño de tu dataset.*

```python
from trl import SFTTrainer
from transformers import TrainingArguments

trainer = SFTTrainer(
    model = model,
    tokenizer = tokenizer,
    train_dataset = dataset,
    dataset_text_field = "text",
    max_seq_length = max_seq_length,
    args = TrainingArguments(
        per_device_train_batch_size = 2,
        gradient_accumulation_steps = 4,
        max_steps = 100, # Número de pasos de entrenamiento
        learning_rate = 2e-4, # Velocidad de aprendizaje (ajustada para precisión)
        fp16 = not torch.cuda.is_bf16_supported(),
        bf16 = torch.cuda.is_bf16_supported(),
        logging_steps = 1,
        output_dir = "outputs",
        optim = "adamw_8bit",
    ),
)
print("🚀 Iniciando entrenamiento. Mira los logs abajo...")
trainer.train()
```

---

### Paso 6: Verificación de Cordura (Inferencia)
**¿Qué sucede aquí?** Probamos si el modelo aprendió. Le damos un texto médico nuevo y vemos si nos genera la BattleCard con el formato correcto.

```python
FastLanguageModel.for_inference(model) # Activa modo respuesta rápida

texto_medico_nuevo = "Paciente con dolor abdominal en fosa iliaca derecha, signo de McBurney (+) y fiebre de 38.5°C."

inputs = tokenizer([prompt_escuela.format(texto_medico_nuevo, "")], return_tensors = "pt").to("cuda")

outputs = model.generate(**inputs, max_new_tokens = 512)
print("\n--- RESULTADO DEL AGENTE ---\n")
print(tokenizer.batch_decode(outputs)[0])
```

---

### Paso 7: Exportación a GGUF (Para tu Mac M3)
**¿Qué sucede aquí?** Convertimos todo el trabajo en un solo archivo `.gguf` que tu Mac pueda leer sin internet y a máxima velocidad. 
*Nota: Este archivo es el que usarás en tu Dashboard local.*

```python
# Guardamos en formato Q4_K_M (Máxima calidad para Apple Silicon M3)
model.save_pretrained_gguf("Modelo_AI_Med_M3", tokenizer, quantization_method = "q4_k_m")

from google.colab import drive
import shutil
import os

# Montar Google Drive
drive.mount('/content/drive')

try:
    archivo_final = [f for f in os.listdir("Modelo_AI_Med_M3") if f.endswith(".gguf")][0]
    source_path = os.path.join("Modelo_AI_Med_M3", archivo_final)
    dest_path = f"/content/drive/MyDrive/{archivo_final}"
    
    print(f"✅ ¡Éxito! Copiando {archivo_final} a tu Google Drive...")
    shutil.copy2(source_path, dest_path)
    print("¡Listo! Ya puedes descargar el archivo desde tu Drive en tu Mac.")
except Exception as e:
    print(f"Error: {e}")
```
