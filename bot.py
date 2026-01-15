import os
import sys
import sqlite3
import csv
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# ========== НАСТРОЙКИ ==========
TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
ADMIN_ID = 1121098820  # ⬅️ ЗАМЕНИТЕ НА ВАШ TELEGRAM ID!

if TOKEN == 'YOUR_BOT_TOKEN_HERE':
    raise ValueError("❌ Токен бота не найден! Установите BOT_TOKEN в Railway")

DB_NAME = "volunteer_bot.db"
CSV_FILE = "volunteers.csv"

# Состояния для ConversationHandler
EDITING_INFO, ADDING_EVENT, EDITING_EVENT, MANAGE_EVENT, EDIT_EVENT_DETAILS, ADDING_COMMENT = range(6)

print(f"🚀 Бот запускается...")
print(f"👑 Админ ID: {ADMIN_ID}")

# ========== ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ И CSV ==========
def init_db():
    """Инициализирует базу данных"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    cur.executescript('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            location TEXT,
            max_volunteers INTEGER,
            is_active BOOLEAN DEFAULT 1,
            registration_open BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            group_name TEXT,
            birth_date TEXT,
            phone_number TEXT,
            username TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL,
            comment TEXT,
            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (telegram_id),
            FOREIGN KEY (event_id) REFERENCES events (id),
            UNIQUE(user_id, event_id)
        );
    ''')
    
    # Добавляем тестовые мероприятия для демонстрации
    cur.execute("SELECT COUNT(*) FROM events")
    if cur.fetchone()[0] == 0:
        # Будущие мероприятия
        today = datetime.now()
        events = [
            ("Уборка территории", "Субботник в парке", 
             (today + timedelta(days=2)).strftime('%Y-%m-%d'), 
             "10:00", "Центральный парк", 50, 1, 1),
            ("Помощь в библиотеке", "Сортировка книг", 
             (today + timedelta(days=4)).strftime('%Y-%m-%d'), 
             "14:00", "Главная библиотека", 20, 1, 1),
            ("Донорская акция", "Сдача крови", 
             (today + timedelta(days=7)).strftime('%Y-%m-%d'), 
             "09:00", "Медпункт", 30, 1, 1),
        ]
        
        for event in events:
            cur.execute('''
                INSERT INTO events (title, description, date, time, location, max_volunteers, is_active, registration_open)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', event)
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С МЕРОПРИЯТИЯМИ ==========
def get_active_events():
    """Получает все активные мероприятия с открытой регистрацией"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    cur.execute('''
        SELECT id, title, description, date, time, location, max_volunteers,
               (SELECT COUNT(*) FROM registrations WHERE event_id = events.id) as registered_count
        FROM events 
        WHERE is_active = 1 
        AND registration_open = 1
        AND date >= date('now')
        ORDER BY date ASC, time ASC
    ''')
    
    events = cur.fetchall()
    conn.close()
    return events

def get_event_details(event_id):
    """Получает детали мероприятия по ID"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    cur.execute('''
        SELECT id, title, description, date, time, location, max_volunteers,
               (SELECT COUNT(*) FROM registrations WHERE event_id = events.id) as registered_count
        FROM events 
        WHERE id = ? AND is_active = 1 AND registration_open = 1
    ''', (event_id,))
    
    event = cur.fetchone()
    conn.close()
    return event

def is_user_registered(user_id, event_id):
    """Проверяет, зарегистрирован ли пользователь на мероприятие"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    cur.execute('''
        SELECT 1 FROM registrations 
        WHERE user_id = ? AND event_id = ?
    ''', (user_id, event_id))
    
    result = cur.fetchone() is not None
    conn.close()
    return result

def register_for_event(user_id, event_id, comment=""):
    """Регистрирует пользователя на мероприятие"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    try:
        cur.execute('''
            INSERT INTO registrations (user_id, event_id, comment)
            VALUES (?, ?, ?)
        ''', (user_id, event_id, comment))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # Уже зарегистрирован
    finally:
        conn.close()

# ========== ОСНОВНЫЕ КОМАНДЫ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    
    # Сохраняем пользователя в базе
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    cur.execute('''
        INSERT OR IGNORE INTO users (telegram_id, full_name, username)
        VALUES (?, ?, ?)
    ''', (user.id, user.full_name, user.username))
    
    # Обновляем username если он изменился
    cur.execute('''
        UPDATE users SET username = ? WHERE telegram_id = ?
    ''', (user.username, user.id))
    
    conn.commit()
    conn.close()
    
    # Приветственное сообщение
    keyboard = [
        [InlineKeyboardButton("📋 Посмотреть мероприятия", callback_data="view_events")],
        [InlineKeyboardButton("👤 Мои регистрации", callback_data="my_registrations")],
        [InlineKeyboardButton("ℹ️ Информация обо мне", callback_data="my_info")],
    ]
    
    if user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👋 Привет, {user.full_name}!\n\n"
        f"Я бот для регистрации на волонтёрские мероприятия.\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

async def view_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список активных мероприятий"""
    query = update.callback_query
    await query.answer()
    
    events = get_active_events()
    
    if not events:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📭 На данный момент нет доступных мероприятий.\n"
            "Пожалуйста, проверьте позже.",
            reply_markup=reply_markup
        )
        return
    
    # Если есть только одно мероприятие, показываем его детали
    if len(events) == 1:
        await show_event_details(update, context, events[0][0])
        return
    
    # Создаем список мероприятий с кнопками
    buttons = []
    for event in events:
        event_id, title, _, date, time, _, max_volunteers, registered_count = event
        
        # Форматируем дату
        event_date = datetime.strptime(date, '%Y-%m-%d')
        date_str = event_date.strftime('%d.%m.%Y')
        
        # Проверяем доступные места
        available = max_volunteers - registered_count
        status = "✅" if available > 0 else "❌"
        
        button_text = f"{status} {title} ({date_str} {time})"
        buttons.append([InlineKeyboardButton(button_text, callback_data=f"event_{event_id}")])
    
    # Добавляем кнопку "Назад"
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="start")])
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await query.edit_message_text(
        "📋 *Доступные мероприятия:*\n\n"
        "✅ - есть свободные места\n"
        "❌ - мест нет\n\n"
        "Выберите мероприятие для просмотра деталей:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def show_event_details(update: Update, context: ContextTypes.DEFAULT_TYPE, event_id=None):
    """Показывает детали мероприятия и кнопку регистрации"""
    query = update.callback_query
    
    # Если event_id передан как аргумент
    if event_id is None:
        # Извлекаем event_id из callback_data
        callback_data = query.data
        if callback_data.startswith("event_"):
            event_id = int(callback_data.split("_")[1])
        else:
            await query.answer("Ошибка: мероприятие не найдено")
            return
    
    await query.answer()
    
    event = get_event_details(event_id)
    
    if not event:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="view_events")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "❌ Мероприятие не найдено или регистрация закрыта.",
            reply_markup=reply_markup
        )
        return
    
    (event_id, title, description, date, time, location, 
     max_volunteers, registered_count) = event
    
    # Форматируем дату
    event_date = datetime.strptime(date, '%Y-%m-%d')
    date_str = event_date.strftime('%d.%m.%Y')
    
    # Проверяем, зарегистрирован ли пользователь
    user_registered = is_user_registered(query.from_user.id, event_id)
    
    # Формируем текст
    event_text = (
        f"📌 *{title}*\n\n"
        f"📝 *Описание:* {description}\n"
        f"📅 *Дата:* {date_str}\n"
        f"⏰ *Время:* {time}\n"
        f"📍 *Место:* {location}\n"
        f"👥 *Мест всего:* {max_volunteers}\n"
        f"✅ *Зарегистрировано:* {registered_count}/{max_volunteers}\n"
    )
    
    # Создаем клавиатуру
    keyboard = []
    
    if not user_registered and registered_count < max_volunteers:
        keyboard.append([InlineKeyboardButton("📝 Зарегистрироваться", callback_data=f"register_{event_id}")])
    elif user_registered:
        keyboard.append([InlineKeyboardButton("✅ Вы уже зарегистрированы", callback_data=f"already_registered_{event_id}")])
    else:
        keyboard.append([InlineKeyboardButton("❌ Мест нет", callback_data=f"no_slots_{event_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 К списку мероприятий", callback_data="view_events")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        event_text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def register_for_event_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает регистрацию на мероприятие"""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем event_id из callback_data
    callback_data = query.data
    event_id = int(callback_data.split("_")[1])
    
    # Регистрируем пользователя
    success = register_for_event(query.from_user.id, event_id)
    
    if success:
        # Получаем информацию о мероприятии для подтверждения
        event = get_event_details(event_id)
        
        if event:
            _, title, _, date, time, location, _, _ = event
            event_date = datetime.strptime(date, '%Y-%m-%d')
            date_str = event_date.strftime('%d.%m.%Y')
            
            keyboard = [
                [InlineKeyboardButton("📋 Посмотреть другие мероприятия", callback_data="view_events")],
                [InlineKeyboardButton("👤 Мои регистрации", callback_data="my_registrations")],
                [InlineKeyboardButton("🔙 На главную", callback_data="start")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"✅ *Вы успешно зарегистрированы!*\n\n"
                f"📌 *Мероприятие:* {title}\n"
                f"📅 *Дата:* {date_str}\n"
                f"⏰ *Время:* {time}\n"
                f"📍 *Место:* {location}\n\n"
                f"Не забудьте взять с собой хорошее настроение! 😊",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
    else:
        # Пользователь уже зарегистрирован
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=f"event_{event_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "❌ Вы уже зарегистрированы на это мероприятие.",
            reply_markup=reply_markup
        )

async def my_registrations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает мероприятия, на которые зарегистрирован пользователь"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    cur.execute('''
        SELECT e.id, e.title, e.description, e.date, e.time, e.location, r.registration_date
        FROM events e
        JOIN registrations r ON e.id = r.event_id
        WHERE r.user_id = ? AND e.is_active = 1
        ORDER BY e.date ASC, e.time ASC
    ''', (user_id,))
    
    registrations = cur.fetchall()
    conn.close()
    
    if not registrations:
        keyboard = [
            [InlineKeyboardButton("📋 Посмотреть мероприятия", callback_data="view_events")],
            [InlineKeyboardButton("🔙 На главную", callback_data="start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📭 Вы пока не зарегистрированы ни на одно мероприятие.\n\n"
            "Хотите посмотреть доступные мероприятия?",
            reply_markup=reply_markup
        )
        return
    
    # Формируем список мероприятий
    events_text = "📋 *Ваши регистрации:*\n\n"
    
    for i, reg in enumerate(registrations, 1):
        event_id, title, description, date, time, location, reg_date = reg
        
        event_date = datetime.strptime(date, '%Y-%m-%d')
        date_str = event_date.strftime('%d.%m.%Y')
        
        events_text += f"{i}. *{title}*\n"
        events_text += f"   📅 {date_str} ⏰ {time}\n"
        events_text += f"   📍 {location}\n\n"
    
    keyboard = [
        [InlineKeyboardButton("📋 Посмотреть другие мероприятия", callback_data="view_events")],
        [InlineKeyboardButton("🔙 На главную", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        events_text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

# ========== ОБРАБОТЧИКИ КНОПОК ==========
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback-кнопок"""
    query = update.callback_query
    data = query.data
    
    if data == "start":
        await start_from_button(update, context)
    elif data == "view_events":
        await view_events(update, context)
    elif data.startswith("event_"):
        await show_event_details(update, context)
    elif data.startswith("register_"):
        await register_for_event_handler(update, context)
    elif data == "my_registrations":
        await my_registrations(update, context)
    elif data == "my_info":
        await show_my_info(update, context)
    elif data == "admin_panel":
        if query.from_user.id == ADMIN_ID:
            await admin_panel(update, context)
        else:
            await query.answer("⛔ У вас нет доступа к админ-панели!")
    elif data == "already_registered_" or data.startswith("no_slots_"):
        await query.answer()
        # Ничего не делаем, пользователь уже видит статус

async def start_from_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'На главную'"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    keyboard = [
        [InlineKeyboardButton("📋 Посмотреть мероприятия", callback_data="view_events")],
        [InlineKeyboardButton("👤 Мои регистрации", callback_data="my_registrations")],
        [InlineKeyboardButton("ℹ️ Информация обо мне", callback_data="my_info")],
    ]
    
    if user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"👋 Привет, {user.full_name}!\n\n"
        f"Я бот для регистрации на волонтёрские мероприятия.\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

async def show_my_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает информацию о пользователе"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    cur.execute('''
        SELECT full_name, group_name, birth_date, phone_number, username, created_at
        FROM users WHERE telegram_id = ?
    ''', (user_id,))
    
    user_info = cur.fetchone()
    conn.close()
    
    if not user_info:
        await query.edit_message_text("❌ Информация не найдена")
        return
    
    full_name, group_name, birth_date, phone_number, username, created_at = user_info
    
    info_text = (
        f"👤 *Ваша информация:*\n\n"
        f"📛 *ФИО:* {full_name}\n"
        f"🎓 *Группа:* {group_name or 'не указана'}\n"
        f"🎂 *Дата рождения:* {birth_date or 'не указана'}\n"
        f"📞 *Телефон:* {phone_number or 'не указан'}\n"
        f"👤 *Username:* @{username or 'не указан'}\n"
        f"📅 *Зарегистрирован:* {created_at[:10] if created_at else 'неизвестно'}\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("✏️ Редактировать информацию", callback_data="edit_info")],
        [InlineKeyboardButton("🔙 На главную", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        info_text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

# ========== АДМИН-ПАНЕЛЬ ==========
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает админ-панель"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("➕ Добавить мероприятие", callback_data="admin_add_event")],
        [InlineKeyboardButton("📋 Список мероприятий", callback_data="admin_events")],
        [InlineKeyboardButton("📥 Экспорт в CSV", callback_data="admin_export")],
        [InlineKeyboardButton("🔙 На главную", callback_data="start")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "👑 *Админ-панель*\n\n"
        "Выберите действие:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========
def main():
    """Запускает бота"""
    # Инициализация базы данных
    init_db()
    
    # Создание приложения
    app = Application.builder().token(TOKEN).build()
    
    # Регистрация обработчиков
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Запуск бота
    print("🤖 Бот запущен и готов к работе!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()