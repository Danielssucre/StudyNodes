import os
import json
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv
import study_core

# Cargar variables de entorno
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start: Bienvenida y estado actual."""
    metrics = study_core.get_daily_metrics()
    msg = (
        "🚀 **Bienvenido al Sistema CORTEX Mobile**\n\n"
        f"📊 **Misión de Hoy**: {metrics['done_today']} / {metrics['daily_goal']}\n"
        f"⏳ **Días Restantes**: {metrics['days_left']}\n"
        f"🏆 **Maestría Acumulada**: {metrics['current_mastery']} / {metrics['total_possible']}\n\n"
        "Usa /reto para recibir tu próximo desafío clínico."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def mision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /mision: Ver métricas detalladas."""
    metrics = study_core.get_daily_metrics()
    msg = (
        "📊 **ESTADO DE LA MISIÓN**\n"
        f"✅ Hechas hoy: {metrics['done_today']}\n"
        f"🎯 Meta diaria: {metrics['daily_goal']}\n"
        f"📚 Pendientes totales: {metrics['pending_total']}\n"
        f"🗓️ Días restantes: {metrics['days_left']}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

def escape_markdown(text):
    """Escapa caracteres que rompen el Markdown de Telegram (V2)."""
    # Para MarkdownV2, la lista es larga. 
    # Usaremos Markdown estándar ("Markdown") en el bot, que es más permisivo.
    # Pero '#' y '*' dentro del contenido generado pueden causar problemas si no están balanceados.
    return text.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`").replace("#", "")

async def execute_reto_flow(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    """Lógica unificada para obtener y enviar el próximo reto."""
    try:
        # Determinar si viene de un comando (message) o de un botón (callback_query)
        is_query = hasattr(update_or_query, 'message') and not hasattr(update_or_query, 'text')
        
        if is_query:
            messenger = update_or_query.message
        else:
            messenger = update_or_query.message

        await messenger.reply_text("🧠 Dr. Epi está analizando las guías... espera un momento.")
        
        challenge = study_core.get_or_generate_challenge()
        
        if not challenge:
            await messenger.reply_text("❌ No se pudo generar el reto. Intenta de nuevo.")
            return
            
        if challenge.get('status') == 'completed':
            await messenger.reply_text(f"🏁 {challenge['message']}")
            return

        # Formatear el reto para Telegram - Usamos escape preventivo básico
        # Nota: El contenido de Dr. Epi ya viene con Markdown (###, **).
        # El problema suele ser '#' mal puestos o guiones bajos huérfanos.
        
        clean_content = challenge['content'].replace("### ", "").replace("#", "📌")
        options_text = "\n".join([f"🔹 {opt}" for opt in challenge['options']])
        
        text = f"🛡️ **{challenge['mode']}**\n\n{clean_content}\n\n**Opciones:**\n{options_text}"
        
        # Crear botones compactos
        keyboard_row = []
        for opt in challenge['options']:
            letter = opt[0]
            keyboard_row.append(InlineKeyboardButton(f"[{letter}]", callback_data=f"ans_{letter}"))
        
        reply_markup = InlineKeyboardMarkup([keyboard_row])
        
        context.user_data['correct_answer'] = challenge['correct_answer']
        context.user_data['explanation'] = challenge['explanation']
        context.user_data['topic'] = challenge['target_topic']
        
        # Intentar enviar con Markdown, si falla, enviar texto plano para no bloquear
        try:
            await messenger.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        except Exception as e:
            print(f"  ⚠️ [BOT] Fallo Markdown en Reto: {e}. Reintentando texto plano.")
            await messenger.reply_text(text, reply_markup=reply_markup)
            
    except Exception as e:
        print(f"  ❌ [BOT] Error Crítico en execute_reto_flow: {e}")
        try:
            await update_or_query.message.reply_text("❌ Ocurrió un error al procesar el reto. Usa /reto para reintentar.")
        except:
            pass

async def reto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /reto: Dispara el flujo manual."""
    await execute_reto_flow(update, context)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los clics en los botones A, B, C, D y EASY/HARD."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    print(f"🖱️ [BOT] Botón presionado: {data}")
    
    if data.startswith("ans_"):
        user_ans = data.split("_")[1]
        
        # Intentar obtener del user_data
        correct_ans = context.user_data.get('correct_answer')
        explanation = context.user_data.get('explanation')
        topic = context.user_data.get('topic')
        
        # Fallback: Si se reinició el bot, intentar cargar de current_session.json
        if not correct_ans and os.path.exists(study_core.SESSION_PATH):
            print("  🔄 [BOT] Re-sincronizando estado desde JSON (bot restart detected)")
            with open(study_core.SESSION_PATH, 'r') as f:
                session = json.load(f)
                correct_ans = session.get('correct_answer')
                explanation = session.get('explanation')
                topic = session.get('target_topic')
        
        if not correct_ans:
            await query.message.reply_text("⚠️ Sesión expirada. Por favor usa /reto de nuevo.")
            return

        if user_ans == correct_ans:
            result = f"✅ **¡CORRECTO!** (Opción {user_ans})\n\n{explanation}"
        else:
            result = f"❌ **INCORRECTO.** La respuesta era {correct_ans}.\n\n{explanation}"
            
        # Preguntar por la dificultad para el SRS
        keyboard = [
            [
                InlineKeyboardButton("🟢 Fácil (EASY)", callback_data=f"srs_EASY_{topic}"),
                InlineKeyboardButton("🔴 Difícil (HARD)", callback_data=f"srs_HARD_{topic}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            # Texto base del resultado
            new_text = f"🛡️ **RESULTADO**\n\n{result}"
            prompt_srs = "\n\n📊 **¿Cómo te pareció este reto?**"
            
            # Telegram tiene un límite de 4096 caracteres. 
            if len(new_text) + len(prompt_srs) > 4000:
                print("  ⚠️ [BOT] Mensaje largo detectado (>4000), fragmentando...")
                # Enviar primera parte (resultado) sin botones
                safe_text = new_text[:3900] + "\n\n(Continúa...)" if len(new_text) > 3900 else new_text
                await query.message.reply_text(text=safe_text, parse_mode="Markdown")
                # Enviar segunda parte con los botones de SRS
                await query.message.reply_text(text=f"📌 **Finalización**{prompt_srs}", reply_markup=reply_markup, parse_mode="Markdown")
            else:
                # Caso estándar
                await query.message.reply_text(text=new_text + prompt_srs, reply_markup=reply_markup, parse_mode="Markdown")
                
            # Quitar botones del mensaje original
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception as e:
            print(f"  ❌ Error al enviar resultado: {e}")
            # Intento de envío ultra-seguro si falla el markdown o la longitud
            try:
                await query.message.reply_text(text="✅ Respuesta registrada. Califica la dificultad:", reply_markup=reply_markup)
            except:
                pass
                                      
    elif data.startswith("srs_"):
        # srs_RATING_TOPIC
        try:
            parts = data.split("_")
            rating = parts[1]
            topic = parts[2]
            
            print(f"  💾 [BOT] Registrando SRS: {topic} | {rating}")
            study_core.process_review(topic, rating)
            
            metrics = study_core.get_daily_metrics()
            
            # Notificar éxito y disparar el siguiente reto automáticamente
            await query.edit_message_text(text=f"✅ **SRS Actualizado ({rating})**\nSiguiente meta diaria: {metrics['done_today']}/{metrics['daily_goal']}")
            
            # --- FLUJO CONTINUO (V3.17) ---
            print("  🚀 [BOT] Disparando siguiente reto automáticamente...")
            await execute_reto_flow(query, context)
            
        except Exception as e:
            print(f"  ❌ Error SRS Handler: {e}")

if __name__ == "__main__":
    if not TOKEN:
        print("❌ Error: TELEGRAM_BOT_TOKEN no configurado en el entorno.")
    else:
        app = ApplicationBuilder().token(TOKEN).build()
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("mision", mision))
        app.add_handler(CommandHandler("reto", reto))
        app.add_handler(CallbackQueryHandler(button_handler))
        
        print("🤖 Bot de Telegram en marcha...")
        app.run_polling()
