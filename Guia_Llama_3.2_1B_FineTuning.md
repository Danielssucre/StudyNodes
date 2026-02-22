# Guía de Fine-Tuning: Edición Llama 3.2 (1B) para AI-Med

Esta versión está optimizada para el modelo **Llama 3.2 (1B)**. Al ser un modelo mucho más pequeño, el entrenamiento es más rápido y su ejecución en tu Mac M3 será casi instantánea, con un consumo de batería mínimo.

---

### Paso 1: Instalación de Dependencias (Sigue igual)
```python
%%capture
!pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
!pip install --no-deps xformers "trl<0.9.0" peft accelerate bitsandbytes datasets
```

---

### Paso 2: Carga del Modelo Llama 3.2 (1B)
**Cambio Importante:** Cambiamos el nombre del modelo. Usamos la versión de 1 billón de parámetros, ideal para tareas de borde (Edge AI).

```python
from unsloth import FastLanguageModel
import torch

max_seq_length = 2048 # Al ser un modelo 1B, 2048 es el "sweet spot" para estabilidad
load_in_4bit = True   

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = "unsloth/Llama-3.2-1B-Instruct-bnb-4bit", # Versión 3.2 (1B)
    max_seq_length = max_seq_length,
    load_in_4bit = load_in_4bit,
)
```

---

### Paso 3: Configuración LoRA para 1B
**¿Qué sucede aquí?** Ajustamos los adaptadores. Para un modelo 1B, un rango (`r`) de 16 suele ser suficiente para aprender formatos de BattleCards sin perder su capacidad de razonamiento.

```python
model = FastLanguageModel.get_peft_model(
    model,
    r = 16, # Reducido a 16 para evitar overfitting en el modelo 1B
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                      "gate_proj", "up_proj", "down_proj",],
    lora_alpha = 16,
    lora_dropout = 0,
    bias = "none",
    use_gradient_checkpointing = "unsloth",
    random_state = 3407,
)
```

---

### Paso 4: Entrenamiento Optimizado
Debido a que el modelo es más pequeño, el `learning_rate` puede ser un poco más alto para "aprender" rápido, o mantener el actual para máxima precisión.

```python
from trl import SFTTrainer
from transformers import TrainingArguments

trainer = SFTTrainer(
    model = model,
    tokenizer = tokenizer,
    train_dataset = dataset, # Asegúrate de haber ejecutado la celda del dataset de la guía anterior
    dataset_text_field = "text",
    max_seq_length = max_seq_length,
    args = TrainingArguments(
        per_device_train_batch_size = 4, # Podemos subir el batch size porque el modelo 1B ocupa menos VRAM
        gradient_accumulation_steps = 4,
        max_steps = 120, 
        learning_rate = 3e-4, # Ligeramente más alto para modelos pequeños
        fp16 = not torch.cuda.is_bf16_supported(),
        bf16 = torch.cuda.is_bf16_supported(),
        logging_steps = 1,
        optim = "adamw_8bit",
        weight_decay = 0.01,
        lr_scheduler_type = "linear",
        seed = 3407,
        output_dir = "outputs",
    ),
)
trainer.train()
```

---

### Paso 5: Exportación para tu Mac M3
Este paso generará un archivo `.gguf` que será extremadamente ligero (menos de 1GB) y volará en tu equipo local.

```python
model.save_pretrained_gguf("Llama_3.2_1B_Med_Local", tokenizer, quantization_method = "q4_k_m")

from google.colab import drive
import shutil
import os

# Montar Google Drive
drive.mount('/content/drive')

try:
    archivo_final = [f for f in os.listdir("Llama_3.2_1B_Med_Local") if f.endswith(".gguf")][0]
    source_path = os.path.join("Llama_3.2_1B_Med_Local", archivo_final)
    dest_path = f"/content/drive/MyDrive/{archivo_final}"
    
    print(f"✅ ¡Éxito! Copiando {archivo_final} a tu Google Drive...")
    shutil.copy2(source_path, dest_path)
    print("¡Listo! Ya puedes descargar el archivo desde tu Drive en tu Mac.")
except Exception as e:
    print(f"Error: {e}")
```
