import os
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ========== НАСТРОЙКИ ==========
TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
ADMIN_ID = 123456789  # ⬅️ ЗАМЕНИТЕ НА ВАШ TELEGRAM ID!

if TOKEN == 'YOUR_BOT_TOKEN_HERE':
    raise ValueError("❌ Токен бота не найден! Установите BOT_TOKEN в Railway")

DB_NAME = "volunteer_bot.db"
CSV_FILE = "volunteers.csv"

print(f"🚀 Бот запускается...")
print(f"👑 Админ ID: {ADMIN_ID}")

# ========== БАЗА ДАННЫХ ==========
def init_db():
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
            is_active BOOLEAN DEFAULT 1
        );
        
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            group_name TEXT,
            phone_number TEXT,
            email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL,
            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (telegram_id),
            FOREIGN KEY (event_id) REFERENCES events (id),
            UNIQUE(user_id, event_id)
        );
    ''')
    
    # Добавляем тестовые мероприятия если таблица пуста
    cur.execute("SELECT COUNT(*) FROM events")
    if cur.fetchone()[0] == 0:
        events = [
            ("Уборка территории", "Субботник в парке", "2024-03-20", "10:00", "Центральный парк", 50),
            ("Помощь в библиотеке", "Сортировка книг", "2024-03-22", "14:00", "Главная библиотека", 20),
            ("Донорская акция", "Сдача крови", "2024-03-25", "09:00", "Медпункт", 30),
            ("Экологический квест", "Сбор мусора на время", "2024-03-28", "12:00", "Набережная", 40),
            ("Помощь ветеранам", "Волонтерский визит", "2024-04-01", "11:00", "Совет ветеранов", 15)
        ]
        
        for event in events:
            cur.execute('''
                INSERT INTO events (title, description, date, time, location, max_volunteers)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', event)
        print("✅ Добавлены тестовые мероприятия")
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

# ========== CSV ТАБЛИЦА ==========
def init_csv():
    """Создает CSV файл с заголовками если его нет"""
    if not os.path.exists(CSV_FILE):
        import csv
        with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'ID записи', 'Дата записи', 'Время записи',
                'Telegram ID', 'ФИО', 'Группа', 'Телефон', 'Email',
                'ID мероприятия', 'Название мероприятия',
                'Дата мероприятия', 'Время мероприятия', 'Место',
                'Статус записи'
            ])
        print(f"✅ Создан CSV файл: {CSV_FILE}")

def save_to_csv(user_data, event_data):
    """Сохраняет запись в CSV файл"""
    try:
        import csv
        row = [
            user_data.get('registration_id', ''),
            datetime.now().strftime('%Y-%m-%d'),
            datetime.now().strftime('%H:%M:%S'),
            user_data.get('telegram_id', ''),
            user_data.get('full_name', ''),
            user_data.get('group', ''),
            user_data.get('phone', ''),
            user_data.get('email', ''),
            event_data.get('id', ''),
            event_data.get('title', ''),
            event_data.get('date', ''),
            event_data.get('time', ''),
            event_data.get('location', ''),
            'Записан'
        ]
        
        with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(row)
        
        print(f"✅ Запись {user_data.get('registration_id')} сохранена в CSV")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка сохранения в CSV: {e}")
        return False

def count_csv_lines():
    """Считает количество записей в CSV (без заголовка)"""
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            return sum(1 for line in f) - 1  # Минус заголовок
    return 0

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С БАЗОЙ ==========
def get_active_events():
    """Получает список активных мероприятий"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        SELECT events.id, events.title, events.date, events.time, events.location, 
               events.max_volunteers, events.description,
               (events.max_volunteers - COUNT(registrations.id)) as available_spots
        FROM events
        LEFT JOIN registrations ON events.id = registrations.event_id
        WHERE events.is_active = 1 AND events.date >= date('now')
        GROUP BY events.id
        HAVING available_spots > 0 OR events.max_volunteers IS NULL
        ORDER BY events.date, events.time
    ''')
    events = cur.fetchall()
    conn.close()
    return events

def get_user_registrations(user_id):
    """Получает записи пользователя"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        SELECT events.id, events.title, events.date, events.time, events.location,
               registrations.registration_date
        FROM registrations
        JOIN events ON registrations.event_id = events.id
        WHERE registrations.user_id = ? AND events.date >= date('now')
        ORDER BY events.date, events.time
    ''', (user_id,))
    events = cur.fetchall()
    conn.close()
    return events

# ========== КОМАНДЫ БОТА ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало работы с ботом"""
    user = update.effective_user
    
    # Регистрируем пользователя в БД
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        INSERT OR IGNORE INTO users (telegram_id, full_name) 
        VALUES (?, ?)
    ''', (user.id, user.full_name))
    conn.commit()
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton("📝 Записаться на мероприятие", callback_data='list_events')],
        [InlineKeyboardButton("👤 Мои данные", callback_data='my_info')],
        [InlineKeyboardButton("📋 Мои записи", callback_data='my_registrations')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help_info')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Я бот для записи на волонтерские мероприятия вашего ВУЗа.\n"
        "Сначала проверьте свои данные, затем выбирайте мероприятия!",
        reply_markup=reply_markup
    )

async def list_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список активных мероприятий"""
    query = update.callback_query
    await query.answer()
    
    events = get_active_events()
    
    if not events:
        await query.edit_message_text(
            "📭 На данный момент нет активных мероприятий.\n"
            "Загляните позже или свяжитесь с организаторами!",
            parse_mode='Markdown'
        )
        return
    
    # Создаем кнопки для мероприятий
    keyboard = []
    for event in events[:10]:  # Максимум 10 кнопок
        event_id, title, date, time, location, max_vol, desc, available = event
        button_text = f"{title[:25]}..." if len(title) > 25 else title
        button_text += f" ({date})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f'event_{event_id}')])
    
    # Добавляем служебные кнопки
    keyboard.append([InlineKeyboardButton("👤 Мои данные", callback_data='my_info')])
    keyboard.append([InlineKeyboardButton("🏠 В главное меню", callback_data='main_menu')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Формируем текст со списком мероприятий
    events_text = "📅 *Доступные мероприятия:*\n\n"
    for i, event in enumerate(events[:5], 1):  # Показываем первые 5
        event_id, title, date, time, location, max_vol, desc, available = event
        events_text += f"{i}. *{title}*\n"
        events_text += f"   📅 {date} ⏰ {time}\n"
        if location:
            events_text += f"   📍 {location}\n"
        events_text += f"   🎫 Мест: {available if available else '∞'}/{max_vol if max_vol else '∞'}\n"
        if desc:
            events_text += f"   📝 {desc[:50]}...\n" if len(desc) > 50 else f"   📝 {desc}\n"
        events_text += "\n"
    
    if len(events) > 5:
        events_text += f"*... и еще {len(events)-5} мероприятий*\n\n"
    
    events_text += "Выберите мероприятие для подробной информации и записи:"
    
    await query.edit_message_text(
        events_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def event_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает детали мероприятия"""
    query = update.callback_query
    await query.answer()
    
    try:
        event_id = int(query.data.split('_')[1])
    except:
        await query.edit_message_text("❌ Ошибка: неверный ID мероприятия")
        return
    
    # Получаем информацию о мероприятии
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT title, description, date, time, location, max_volunteers FROM events WHERE id = ?', (event_id,))
    event = cur.fetchone()
    
    if not event:
        await query.edit_message_text("❌ Мероприятие не найдено.")
        conn.close()
        return
    
    title, desc, date, time, location, max_vol = event
    
    # Проверяем, записан ли пользователь
    cur.execute('SELECT id FROM registrations WHERE user_id = ? AND event_id = ?', 
                (query.from_user.id, event_id))
    is_registered = cur.fetchone() is not None
    conn.close()
    
    # Формируем текст
    text = f"🎯 *{title}*\n\n"
    if desc:
        text += f"📝 *Описание:* {desc}\n\n"
    text += f"📅 *Дата:* {date}\n"
    text += f"⏰ *Время:* {time}\n"
    if location:
        text += f"📍 *Место:* {location}\n"
    text += f"👥 *Участников:* {max_vol if max_vol else 'без ограничений'}\n\n"
    
    if is_registered:
        text += "✅ *Вы уже записаны на это мероприятие*\n\n"
    
    # Создаем кнопки
    keyboard = []
    if not is_registered:
        keyboard.append([InlineKeyboardButton("✅ Записаться", callback_data=f'register_{event_id}')])
    else:
        keyboard.append([InlineKeyboardButton("❌ Отменить запись", callback_data=f'cancel_{event_id}')])
    
    keyboard.append([InlineKeyboardButton("📅 К списку мероприятий", callback_data='list_events')])
    keyboard.append([InlineKeyboardButton("👤 Проверить мои данные", callback_data='my_info')])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def my_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает и позволяет редактировать данные пользователя"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Получаем данные пользователя
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT full_name, group_name, phone_number, email FROM users WHERE telegram_id = ?', (user_id,))
    user = cur.fetchone()
    conn.close()
    
    if not user:
        text = "❌ Ваши данные не найдены. Пожалуйста, нажмите /start"
    else:
        full_name, group_name, phone, email = user
        text = "👤 *Ваши данные:*\n\n"
        text += f"• *ФИО:* {full_name if full_name else '❌ Не заполнено'}\n"
        text += f"• *Группа:* {group_name if group_name else '❌ Не заполнена'}\n"
        text += f"• *Телефон:* {phone if phone else '❌ Не заполнен'}\n"
        text += f"• *Email:* {email if email else '❌ Не заполнен'}\n\n"
        
        # Проверяем, все ли обязательные данные заполнены
        missing = []
        if not full_name: missing.append("ФИО")
        if not group_name: missing.append("группа")
        if not phone: missing.append("телефон")
        
        if missing:
            text += f"⚠️ *Для записи необходимо заполнить:* {', '.join(missing)}\n"
        else:
            text += "✅ *Все данные заполнены, можно записываться!*\n"
    
    # Создаем кнопки
    keyboard = [
        [InlineKeyboardButton("✏️ Заполнить/изменить данные", callback_data='edit_info')],
        [InlineKeyboardButton("📝 Записаться на мероприятие", callback_data='list_events')],
        [InlineKeyboardButton("📋 Мои записи", callback_data='my_registrations')],
        [InlineKeyboardButton("🏠 В главное меню", callback_data='main_menu')]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def edit_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрашивает данные пользователя"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "✏️ *Заполните ваши данные*\n\n"
        "Отправьте сообщение в формате:\n\n"
        "`ФИО, Группа, Телефон`\n\n"
        "*Пример:*\n"
        "`Иванов Иван Иванович, ИВТ-20-1, +79161234567`\n\n"
        "📌 *Все поля обязательны для записи на мероприятия.*",
        parse_mode='Markdown'
    )
    
    # Устанавливаем состояние ожидания данных
    context.user_data['awaiting_info'] = True

async def save_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняет данные пользователя"""
    if context.user_data.get('awaiting_info'):
        text = update.message.text.strip()
        parts = [part.strip() for part in text.split(',')]
        
        if len(parts) >= 3:
            full_name = parts[0]
            group = parts[1]
            phone = parts[2]
            email = parts[3] if len(parts) > 3 else ''
            
            # Сохраняем в БД
            conn = sqlite3.connect(DB_NAME)
            cur = conn.cursor()
            cur.execute('''
                INSERT OR REPLACE INTO users 
                (telegram_id, full_name, group_name, phone_number, email)
                VALUES (?, ?, ?, ?, ?)
            ''', (update.effective_user.id, full_name, group, phone, email))
            conn.commit()
            conn.close()
            
            await update.message.reply_text(
                "✅ *Данные сохранены!*\n\n"
                f"• ФИО: {full_name}\n"
                f"• Группа: {group}\n"
                f"• Телефон: {phone}\n"
                f"• Email: {email if email else 'не указан'}\n\n"
                "Теперь вы можете записываться на мероприятия!",
                parse_mode='Markdown'
            )
            
            # Показываем кнопки
            keyboard = [
                [InlineKeyboardButton("📝 Записаться на мероприятие", callback_data='list_events')],
                [InlineKeyboardButton("👤 Посмотреть мои данные", callback_data='my_info')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "Выберите действие:",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                "❌ *Неверный формат!*\n\n"
                "Пожалуйста, отправьте данные в формате:\n"
                "`ФИО, Группа, Телефон`\n\n"
                "Пример:\n"
                "`Иванов Иван Иванович, ИВТ-20-1, +79161234567`\n\n"
                "Email можно добавить через запятую (необязательно).",
                parse_mode='Markdown'
            )
        
        context.user_data['awaiting_info'] = False

async def register_for_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Записывает пользователя на мероприятие"""
    query = update.callback_query
    await query.answer()
    
    try:
        event_id = int(query.data.split('_')[1])
    except:
        await query.answer("❌ Ошибка: неверный ID мероприятия", show_alert=True)
        return
    
    user_id = query.from_user.id
    
    # 1. Проверяем данные пользователя
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT full_name, group_name, phone_number FROM users WHERE telegram_id = ?', (user_id,))
    user = cur.fetchone()
    
    if not user:
        await query.edit_message_text(
            "❌ Ваши данные не найдены. Пожалуйста, сначала заполните данные."
        )
        conn.close()
        return
    
    full_name, group, phone = user
    
    # Проверяем обязательные поля
    if not full_name or not group or not phone:
        missing = []
        if not full_name: missing.append("ФИО")
        if not group: missing.append("группа")
        if not phone: missing.append("телефон")
        
        keyboard = [
            [InlineKeyboardButton("✏️ Заполнить данные", callback_data='edit_info')],
            [InlineKeyboardButton("📅 К мероприятиям", callback_data='list_events')]
        ]
        
        await query.edit_message_text(
            f"❌ *Не хватает данных для записи:*\n"
            f"• {', '.join(missing)}\n\n"
            f"Пожалуйста, заполните данные перед записью.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        conn.close()
        return
    
    # 2. Проверяем мероприятие
    cur.execute('SELECT title, date, time, location, max_volunteers FROM events WHERE id = ?', (event_id,))
    event = cur.fetchone()
    
    if not event:
        await query.edit_message_text("❌ Мероприятие не найдено.")
        conn.close()
        return
    
    title, date, time, location, max_vol = event
    
    # 3. Проверяем, не записан ли уже
    cur.execute('SELECT id FROM registrations WHERE user_id = ? AND event_id = ?', (user_id, event_id))
    if cur.fetchone():
        await query.answer("Вы уже записаны на это мероприятие!", show_alert=True)
        conn.close()
        return
    
    # 4. Проверяем свободные места
    cur.execute('''
        SELECT COUNT(registrations.id) 
        FROM registrations 
        WHERE event_id = ?
    ''', (event_id,))
    registered_count = cur.fetchone()[0]
    
    if max_vol and registered_count >= max_vol:
        await query.answer("❌ К сожалению, все места уже заняты!", show_alert=True)
        conn.close()
        return
    
    # 5. Сохраняем запись в БД
    cur.execute('INSERT INTO registrations (user_id, event_id) VALUES (?, ?)', (user_id, event_id))
    registration_id = cur.lastrowid
    conn.commit()
    conn.close()
    
    # 6. Сохраняем в CSV
    user_data = {
        'registration_id': registration_id,
        'telegram_id': user_id,
        'full_name': full_name,
        'group': group,
        'phone': phone,
        'email': ''  # Можно добавить email если есть
    }
    
    event_data = {
        'id': event_id,
        'title': title,
        'date': date,
        'time': time,
        'location': location if location else 'Не указано'
    }
    
    csv_success = save_to_csv(user_data, event_data)
    
    # 7. Отправляем ответ пользователю
    if csv_success:
        text = (
            "✅ *Вы успешно записаны!*\n\n"
            f"🎯 *Мероприятие:* {title}\n"
            f"📅 *Дата:* {date}\n"
            f"⏰ *Время:* {time}\n"
        )
        
        if location:
            text += f"📍 *Место:* {location}\n"
        
        text += (
            f"👥 *Место в списке:* {registered_count + 1}/{max_vol if max_vol else '∞'}\n\n"
            "📊 *Ваши данные сохранены в таблицу волонтеров.*\n"
            "Организаторы увидят вашу запись.\n\n"
            "📌 *Не забудьте добавить мероприятие в календарь!*"
        )
        
        await query.answer("✅ Запись сохранена в таблицу!", show_alert=True)
    else:
        text = (
            "⚠️ *Запись сохранена в боте, но возникла ошибка при сохранении в таблицу.*\n\n"
            f"🎯 *Мероприятие:* {title}\n"
            f"📅 *Дата:* {date}\n\n"
            "Пожалуйста, свяжитесь с организаторами для подтверждения записи."
        )
        
        await query.answer("⚠️ Ошибка сохранения в таблицу", show_alert=True)
    
    # Кнопки после записи
    keyboard = [
        [InlineKeyboardButton("📝 Записаться еще", callback_data='list_events')],
        [InlineKeyboardButton("📋 Мои записи", callback_data='my_registrations')],
        [InlineKeyboardButton("🏠 В главное меню", callback_data='main_menu')]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def my_registrations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает записи пользователя"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    registrations = get_user_registrations(user_id)
    
    if not registrations:
        text = (
            "📭 *У вас пока нет записей на мероприятия.*\n\n"
            "Выберите мероприятие из списка и запишитесь!"
        )
    else:
        text = "📋 *Ваши записи на мероприятия:*\n\n"
        for i, reg in enumerate(registrations, 1):
            event_id, title, date, time, location, reg_date = reg
            text += f"{i}. *{title}*\n"
            text += f"   📅 {date} ⏰ {time}\n"
            if location:
                text += f"   📍 {location}\n"
            text += f"   📝 Записан: {reg_date[:10]}\n\n"
    
    # Кнопки
    keyboard = [
        [InlineKeyboardButton("📝 Записаться на мероприятие", callback_data='list_events')],
        [InlineKeyboardButton("👤 Мои данные", callback_data='my_info')],
        [InlineKeyboardButton("🏠 В главное меню", callback_data='main_menu')]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет запись пользователя"""
    query = update.callback_query
    await query.answer()
    
    try:
        event_id = int(query.data.split('_')[1])
    except:
        await query.answer("❌ Ошибка", show_alert=True)
        return
    
    user_id = query.from_user.id
    
    # Удаляем запись из БД
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('DELETE FROM registrations WHERE user_id = ? AND event_id = ?', (user_id, event_id))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    
    if deleted > 0:
        await query.answer("✅ Запись отменена", show_alert=True)
        await query.edit_message_text(
            "✅ *Запись отменена успешно.*\n\n"
            "Место освобождено для других волонтеров.",
            parse_mode='Markdown'
        )
    else:
        await query.answer("❌ Запись не найдена", show_alert=True)

async def help_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает справку"""
    query = update.callback_query
    await query.answer()
    
    text = (
        "❓ *Помощь по использованию бота*\n\n"
        "1. *Заполните данные* — перед записью укажите ФИО, группу и телефон\n"
        "2. *Выберите мероприятие* — из списка доступных\n"
        "3. *Запишитесь* — данные автоматически сохранятся в таблицу\n\n"
        "📌 *Для организаторов:*\n"
        "Все записи сохраняются в CSV файл.\n"
        "Для получения таблицы используйте команду /table (только для админов).\n\n"
        "🔄 *Проблемы с записью?*\n"
        "Напишите организаторам или попробуйте позже."
    )
    
    keyboard = [
        [InlineKeyboardButton("👤 Мои данные", callback_data='my_info')],
        [InlineKeyboardButton("📝 Записаться", callback_data='list_events')],
        [InlineKeyboardButton("🏠 В главное меню", callback_data='main_menu')]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📝 Записаться на мероприятие", callback_data='list_events')],
        [InlineKeyboardButton("👤 Мои данные", callback_data='my_info')],
        [InlineKeyboardButton("📋 Мои записи", callback_data='my_registrations')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help_info')]
    ]
    
    await query.edit_message_text(
        "🏠 *Главное меню*\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ========== АДМИН КОМАНДЫ ==========
async def admin_table(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет CSV таблицу админу"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ У вас нет прав доступа.")
        return
    
    if not os.path.exists(CSV_FILE):
        await update.message.reply_text("❌ Таблица еще не создана.")
        return
    
    try:
        # Читаем CSV файл
        with open(CSV_FILE, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=f'волонтеры_{datetime.now().strftime("%Y-%m-%d")}.csv',
                caption=f"📊 Таблица волонтеров\nВсего записей: {count_csv_lines()}"
            )
        print(f"✅ Таблица отправлена админу {ADMIN_ID}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при отправке таблицы: {e}")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику админу"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ У вас нет прав доступа.")
        return
    
    # Статистика из БД
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM users")
    users_count = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM events")
    events_count = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM registrations")
    regs_count = cur.fetchone()[0]
    
    # Популярные мероприятия
    cur.execute('''
        SELECT events.title, COUNT(registrations.id) as count
        FROM events
        LEFT JOIN registrations ON events.id = registrations.event_id
        GROUP BY events.id
        ORDER BY count DESC
        LIMIT 5
    ''')
    popular_events = cur.fetchall()
    
    conn.close()
    
    # Формируем текст
    text = "👑 *Статистика для админа*\n\n"
    text += f"👥 Пользователей: {users_count}\n"
    text += f"📅 Мероприятий: {events_count}\n"
    text += f"📝 Записей: {regs_count}\n"
    text += f"📊 Записей в CSV: {count_csv_lines()}\n\n"
    
    text += "🔥 *Самые популярные мероприятия:*\n"
    for title, count in popular_events:
        text += f"• {title}: {count} записей\n"
    
    # Кнопки для админа
    keyboard = [
        [InlineKeyboardButton("📥 Скачать таблицу", callback_data='admin_download')],
        [InlineKeyboardButton("🔄 Обновить статистику", callback_data='admin_stats')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def admin_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки скачивания таблицы"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    # Вызываем функцию отправки таблицы
    await admin_table(Update(message=query.message), context)

# ========== ЗАПУСК БОТА ==========
def main():
    # Инициализируем БД и CSV
    init_db()
    init_csv()
    
    print("=" * 50)
    print("🤖 Волонтерский бот запускается...")
    print(f"👑 Админ ID: {ADMIN_ID}")
    print(f"💾 База данных: {DB_NAME}")
    print(f"📊 CSV таблица: {CSV_FILE}")
    print("=" * 50)
    
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("table", admin_table))
    application.add_handler(CommandHandler("stats", admin_stats))
    
    # Регистрируем обработчики callback-запросов
    application.add_handler(CallbackQueryHandler(list_events, pattern='^list_events$'))
    application.add_handler(CallbackQueryHandler(event_detail, pattern='^event_'))
    application.add_handler(CallbackQueryHandler(register_for_event, pattern='^register_'))
    application.add_handler(CallbackQueryHandler(cancel_registration, pattern='^cancel_'))
    application.add_handler(CallbackQueryHandler(my_info, pattern='^my_info$'))
    application.add_handler(CallbackQueryHandler(edit_info, pattern='^edit_info$'))
    application.add_handler(CallbackQueryHandler(my_registrations, pattern='^my_registrations$'))
    application.add_handler(CallbackQueryHandler(help_info, pattern='^help_info$'))
    application.add_handler(CallbackQueryHandler(main_menu, pattern='^main_menu$'))
    application.add_handler(CallbackQueryHandler(admin_download_callback, pattern='^admin_download$'))
    application.add_handler(CallbackQueryHandler(admin_stats, pattern='^admin_stats$'))
    
    # Обработчик текстовых сообщений (для сохранения данных)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_user_info))
    
    print("✅ Бот запущен и ожидает сообщений...")
    print("=" * 50)
    
    # Запускаем бота
    application.run_polling()

if __name__ == "__main__":
    main()