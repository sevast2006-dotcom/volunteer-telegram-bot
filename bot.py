import os
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Загружаем токен из переменных окружения (для Railway)
TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')  # Исправлено!
if TOKEN == 'YOUR_BOT_TOKEN_HERE':
    raise ValueError("Токен бота не найден! Установите переменную окружения BOT_TOKEN")

DB_NAME = "volunteer_bot.db"

# --- Работа с базой данных ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    # ПОЛНЫЕ SQL запросы (исправлено!)
    cur.executescript('''
        -- Таблица мероприятий
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            location TEXT,
            max_volunteers INTEGER,
            is_active BOOLEAN DEFAULT 1
        );
        
        -- Таблица пользователей (студентов)
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            group_name TEXT,
            phone_number TEXT
        );
        
        -- Таблица записей (связь пользователь -> мероприятие)
        CREATE TABLE IF NOT EXISTS registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL,
            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            attended BOOLEAN DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (telegram_id),
            FOREIGN KEY (event_id) REFERENCES events (id),
            UNIQUE(user_id, event_id)
        );
    ''')
    
    # Добавим тестовое мероприятие, если таблица пуста
    cur.execute("SELECT COUNT(*) FROM events")
    if cur.fetchone()[0] == 0:
        cur.execute('''
            INSERT INTO events (title, description, date, time, location, max_volunteers, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            "Уборка территории",
            "Общеуниверситетский субботник",
            "2024-03-20",
            "10:00",
            "Главный корпус",
            50,
            1
        ))
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

def get_active_events():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        SELECT events.id, events.title, events.date, events.time, events.location, events.max_volunteers,
               (events.max_volunteers - COUNT(registrations.id)) as available_spots
        FROM events
        LEFT JOIN registrations ON events.id = registrations.event_id
        WHERE events.is_active = 1
        GROUP BY events.id
        HAVING available_spots > 0 OR events.max_volunteers IS NULL
        ORDER BY events.date, events.time
    ''')
    events = cur.fetchall()
    conn.close()
    return events

# --- Команды бота ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    # Регистрируем пользователя, если его нет
    cur.execute('INSERT OR IGNORE INTO users (telegram_id, full_name) VALUES (?, ?)', 
                (user.id, user.full_name))
    conn.commit()
    conn.close()

    keyboard = [
        [InlineKeyboardButton("📅 Активные мероприятия", callback_data='list_events')],
        [InlineKeyboardButton("📋 Мои записи", callback_data='my_events')],
        [InlineKeyboardButton("❌ Отменить запись", callback_data='cancel_registration')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"Привет, {user.first_name}!\n"
        "Я бот для записи на волонтерские мероприятия.\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )

async def list_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    events = get_active_events()
    if not events:
        await query.edit_message_text("На данный момент нет активных мероприятий для записи.")
        return

    keyboard = []
    for event in events:
        event_id, title, date, time, location, max_vol, available = event
        button_text = f"{title} ({date} {time}) - мест: {available if available else '∞'}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f'event_{event_id}')])

    keyboard.append([InlineKeyboardButton("« Назад", callback_data='back_to_main')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("📅 *Активные мероприятия:*\nВыберите для записи:", 
                                  reply_markup=reply_markup, parse_mode='Markdown')

async def event_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split('_')[1])

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT title, description, date, time, location, max_volunteers FROM events WHERE id = ?', (event_id,))
    event = cur.fetchone()
    
    # Проверяем, записан ли уже пользователь
    cur.execute('SELECT id FROM registrations WHERE user_id = ? AND event_id = ?', 
                (query.from_user.id, event_id))
    is_registered = cur.fetchone() is not None
    conn.close()

    if not event:
        await query.edit_message_text("Мероприятие не найдено.")
        return

    title, desc, date, time, location, max_vol = event
    text = f"*{title}*\n\n"
    text += f"📝 *Описание:* {desc}\n" if desc else ""
    text += f"📅 *Дата:* {date}\n"
    text += f"⏰ *Время:* {time}\n"
    text += f"📍 *Место:* {location}\n" if location else ""
    text += f"👥 *Макс. участников:* {max_vol if max_vol else 'не ограничено'}\n\n"

    keyboard = []
    if not is_registered:
        keyboard.append([InlineKeyboardButton("✅ Записаться", callback_data=f'register_{event_id}')])
    else:
        text += "✅ *Вы уже записаны на это мероприятие*\n"
        keyboard.append([InlineKeyboardButton("❌ Отменить запись", callback_data=f'unregister_{event_id}')])
    
    keyboard.append([InlineKeyboardButton("« К списку мероприятий", callback_data='list_events')])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def register_for_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split('_')[1])
    user_id = query.from_user.id

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    # Проверка, не записан ли уже
    cur.execute('SELECT id FROM registrations WHERE user_id = ? AND event_id = ?', (user_id, event_id))
    if cur.fetchone():
        await query.answer("Вы уже записаны на это мероприятие!", show_alert=True)
        conn.close()
        return
    
    # Проверка наличия свободных мест
    cur.execute('''
        SELECT max_volunteers, COUNT(registrations.id) 
        FROM events 
        LEFT JOIN registrations ON events.id = registrations.event_id 
        WHERE events.id = ?
        GROUP BY events.id
    ''', (event_id,))
    result = cur.fetchone()
    
    if result and result[0] and result[1] >= result[0]:
        await query.answer("К сожалению, все места уже заняты!", show_alert=True)
        conn.close()
        return
    
    # Записываем
    cur.execute('INSERT INTO registrations (user_id, event_id) VALUES (?, ?)', (user_id, event_id))
    conn.commit()
    conn.close()
    
    await query.answer("Вы успешно записаны! ✅", show_alert=True)
    # Возвращаемся к деталям мероприятия
    query.data = f'event_{event_id}'
    await event_detail(update, context)

async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    # Получаем активные записи пользователя
    cur.execute('''
        SELECT registrations.id, events.title, events.date, events.time
        FROM registrations
        JOIN events ON registrations.event_id = events.id
        WHERE registrations.user_id = ? AND events.date >= date('now')
        ORDER BY events.date
    ''', (user_id,))
    registrations = cur.fetchall()
    
    if not registrations:
        await query.edit_message_text("У вас нет активных записей для отмены.")
        conn.close()
        return
    
    keyboard = []
    for reg_id, title, date, time in registrations:
        button_text = f"{title} ({date} {time})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f'cancel_{reg_id}')])
    
    keyboard.append([InlineKeyboardButton("« Назад", callback_data='back_to_main')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text("Выберите запись для отмены:", reply_markup=reply_markup)
    conn.close()

async def unregister_for_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('cancel_'):
        reg_id = int(query.data.split('_')[1])
    elif query.data.startswith('unregister_'):
        event_id = int(query.data.split('_')[1])
        user_id = query.from_user.id
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute('SELECT id FROM registrations WHERE user_id = ? AND event_id = ?', (user_id, event_id))
        result = cur.fetchone()
        reg_id = result[0] if result else None
        conn.close()
    
    if not reg_id:
        await query.answer("Запись не найдена!", show_alert=True)
        return
    
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('DELETE FROM registrations WHERE id = ?', (reg_id,))
    conn.commit()
    conn.close()
    
    await query.answer("Запись отменена! ❌", show_alert=True)
    await query.edit_message_text("Ваша запись успешно отменена.")

async def my_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        SELECT events.id, events.title, events.date, events.time
        FROM registrations
        JOIN events ON registrations.event_id = events.id
        WHERE registrations.user_id = ? AND events.date >= date('now')
        ORDER BY events.date, events.time
    ''', (user_id,))
    events = cur.fetchall()
    conn.close()

    if not events:
        text = "У вас нет активных записей на будущие мероприятия."
    else:
        text = "📋 *Ваши записи:*\n\n"
        for event in events:
            event_id, title, date, time = event
            text += f"• {title}\n  {date} в {time}\n"

    keyboard = [[InlineKeyboardButton("« Назад", callback_data='back_to_main')]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    
    keyboard = [
        [InlineKeyboardButton("📅 Активные мероприятия", callback_data='list_events')],
        [InlineKeyboardButton("📋 Мои записи", callback_data='my_events')],
        [InlineKeyboardButton("❌ Отменить запись", callback_data='cancel_registration')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"Главное меню\nВыберите действие:",
        reply_markup=reply_markup
    )

# --- Запуск бота ---
def main():
    # Инициализируем базу данных
    init_db()
    
    print("🚀 Бот запускается...")
    print(f"Токен: {'Установлен' if TOKEN != 'YOUR_BOT_TOKEN_HERE' else 'НЕ НАЙДЕН!'}")
    
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(list_events, pattern='^list_events$'))
    application.add_handler(CallbackQueryHandler(event_detail, pattern='^event_'))
    application.add_handler(CallbackQueryHandler(register_for_event, pattern='^register_'))
    application.add_handler(CallbackQueryHandler(cancel_registration, pattern='^cancel_registration$'))
    application.add_handler(CallbackQueryHandler(unregister_for_event, pattern='^cancel_'))
    application.add_handler(CallbackQueryHandler(unregister_for_event, pattern='^unregister_'))
    application.add_handler(CallbackQueryHandler(my_events, pattern='^my_events$'))
    application.add_handler(CallbackQueryHandler(back_to_main, pattern='^back_to_main$'))
    
    print("✅ Обработчики зарегистрированы")
    print("🤖 Бот запущен и ожидает сообщений...")
    
    # Запускаем бота
    application.run_polling()

if __name__ == "__main__":
    main()