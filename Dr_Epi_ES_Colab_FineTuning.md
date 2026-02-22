# Dr. Epi-ES: Notebook de Fine-Tuning con Unsloth (Llama-3 8B)

Este documento contiene las celdas de código listas para ser copiadas y pegadas en un entorno de **Google Colab (con GPU T4 o superior)**. El objetivo es realizar un fine-tuning eficiente de Llama-3 para convertirlo en tu agente autónomo "Dr. Epi-ES", entrenado con los datos generados a través de NotebookLM.

---

## Celda 1: Instalación de Dependencias
*Ejecuta esta celda para instalar Unsloth y las librerías necesarias. Esto prepara el entorno para entrenar modelos grandes en GPUs con memoria limitada (como la T4 de 16GB).*

```python
%%capture
# Instalación de Unsloth, Xformers (para atención más rápida) y utilidades de HuggingFace
!pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
!pip install --no-deps xformers "trl<0.9.0" peft accelerate bitsandbytes
```

---

## Celda 2: Carga del Modelo Base y Tokenizer
*Aquí cargamos el modelo `Llama-3-8B-Instruct` cuantizado a 4-bits. Esto reduce drásticamente el uso de memoria RAM de la GPU permitiendo hacer fine-tuning en Colab gratuito.*

```python
from unsloth import FastLanguageModel
import torch

# Con 4-bit, un modelo de 8B cabe perfectamente en una T4 de Google Colab
max_seq_length = 2048 # Soporta hasta 8192, pero 2048 es más rápido y suficiente para casos clínicos
dtype = None # Detecta automáticamente si la GPU soporta bfloat16 (T4 usa float16)
load_in_4bit = True # Habilita cuantización a 4-bits

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = "unsloth/llama-3-8b-Instruct-bnb-4bit", # Modelo base Llama 3 optimizado
    max_seq_length = max_seq_length,
    dtype = dtype,
    load_in_4bit = load_in_4bit,
)
```

---

## Celda 3: Configuración de Adaptadores LoRA
*En lugar de entrenar todos los billones de parámetros (lo cual es imposible en una T4), usamos LoRA para entrenar solo un pequeño porcentaje de adaptadores (~1-2%).*

```python
model = FastLanguageModel.get_peft_model(
    model,
    r = 16, # Rango LoRA (16 es un buen balance entre calidad y velocidad)
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                      "gate_proj", "up_proj", "down_proj",],
    lora_alpha = 16,
    lora_dropout = 0, # Dropout a 0 es recomendado por optimización
    bias = "none",
    use_gradient_checkpointing = "unsloth", # Usa gradientes eficientes de memoria (ahorra mucho VRAM)
    random_state = 3407,
    use_rslora = False,
    loftq_config = None,
)
```

---

## Celda 4: Preparación del Dataset
*Aquí aplicaremos la plantilla "Alpaca" al dataset que hemos generado. **Nota:** Debes subir tu archivo `dr_epi_es_dataset.jsonl` a la sección de Archivos de Colab antes de ejecutar esta celda.*

```python
alpaca_prompt = """A continuación se presenta una instrucción que describe una tarea, junto con una entrada médica clínica o teórica que proporciona más contexto. Escribe una respuesta que complete adecuadamente la solicitud, asumiendo el rol de Dr. Epi-ES, un tutor médico estricto y basado en guías oficiales de Colombia y protocolos actualizados.

### Instrucción:
{}

### Información / Contexto (Input):
{}

### Respuesta del Dr. Epi-ES:
{}"""

EOS_TOKEN = tokenizer.eos_token # Obligatorio para indicarle al modelo que termine de generar

def formatting_prompts_func(examples):
    instructions = examples["instruction"]
    inputs       = examples["input"]
    outputs      = examples["output"]
    texts = []
    for instruction, input, output in zip(instructions, inputs, outputs):
        # Insertamos los datos en la plantilla y añadimos el token EOS
        text = alpaca_prompt.format(instruction, input, output) + EOS_TOKEN
        texts.append(text)
    return { "text" : texts, }

from datasets import load_dataset
# Carga el archivo subido a Colab llamado "dr_epi_es_dataset.jsonl". 
# Si tu archivo se llama distinto, cambia el string aquí.
dataset = load_dataset("json", data_files="dr_epi_es_dataset.jsonl", split="train")

# Mapeamos la función formateadora a todo el dataset
dataset = dataset.map(formatting_prompts_func, batched = True,)
```

---

## Celda 5: Configuración e Inicio del Entrenamiento
*Esta es la celda principal. Configura los hiperparámetros de fine-tuning. Dale Play y ve por un café.*

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
    packing = False, # Deja en False para contextos cortos médicos
    args = TrainingArguments(
        per_device_train_batch_size = 2,
        gradient_accumulation_steps = 4, # Efectivo batch_size = 8
        warmup_steps = 5,
        max_steps = 60, # Cambia esto a 'num_train_epochs = 1' para entrenar en todo el dataset
        learning_rate = 2e-4, # Tasa de aprendizaje ideal para Llama 3
        fp16 = not torch.cuda.is_bf16_supported(),
        bf16 = torch.cuda.is_bf16_supported(),
        logging_steps = 1,
        optim = "adamw_8bit", # Optimizador 8-bit para ahorrar VRAM
        weight_decay = 0.01,
        lr_scheduler_type = "linear",
        seed = 3407,
        output_dir = "outputs",
    ),
)

# ¡Iniciando el entrenamiento real!
trainer_stats = trainer.train()
```

---

## Celda 6: Prueba de Inferencia (Comprobación de Cordura)
*Una vez termine, probaremos el modelo directamente en el Colab.*

```python
# Habilitamos a Unsloth para inferencia x2 más rápida
FastLanguageModel.for_inference(model) 

inputs = tokenizer(
[
    alpaca_prompt.format(
        "Evalúa la conducta ante un paciente pediátrico masculino de 10 años que requiere la vacuna de VPH según la normativa actual de Colombia.", # instruction
        "Circular 002-2024 de Minsalud.", # input
        "", # output (lo dejamos vacío para que el modelo lo genere)
    )
], return_tensors = "pt").to("cuda")

# Generación
outputs = model.generate(**inputs, max_new_tokens = 512, use_cache = True)
print(tokenizer.batch_decode(outputs)[0])
```

---

## Celda 7: Exportación a GGUF (Para Mac M3 local)
*Esta es la celda vital para tu sistema. Guarda el modelo cuantizado en formato `.gguf`, el cual puedes descargar y correr localmente de forma ultra-rápida y sin internet en tu Mac M3 (usando llama.cpp, Ollama o LM Studio).*

```python
# Guarda el modelo en formato Q4_K_M (Excelente balance peso/calidad para M3 Mac)
# Esto tomará un par de minutos, pues fusionará los pesos LoRA y lo cuantizará a 4 bits.
model.save_pretrained_gguf("dr_epi_es_model", tokenizer, quantization_method = "q4_k_m")
```

---

## Celda 8: Exportar a Google Drive (Recomendado)
*Dado que el modelo cuantizado (.gguf) suele pesar varios Gigabytes, la descarga directa desde el navegador en Colab a menudo falla silenciosamente por límites de memoria. La forma 100% segura es guardarlo en tu Google Drive.*

```python
from google.colab import drive
import shutil
import os

# 1. Montar Google Drive (te pedirá permisos)
drive.mount('/content/drive')

# 2. Definir rutas
gguf_file = [f for f in os.listdir("dr_epi_es_model") if f.endswith(".gguf")][0]
source_path = os.path.join("dr_epi_es_model", gguf_file)
destination_path = f"/content/drive/MyDrive/{gguf_file}"

# 3. Copiar el archivo a Google Drive
print(f"Copiando {source_path} a tu Google Drive... (Esto puede tomar unos minutos)")
shutil.copy2(source_path, destination_path)
print("¡Copia completada! Ve a tu Google Drive (drive.google.com), descarga el archivo GGUF a tu Mac y úsalo con Ollama o LM Studio.")
```
