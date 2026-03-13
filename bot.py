import os
import sys
import sqlite3
import csv
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from dotenv import load_dotenv
load_dotenv()

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
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

def init_csv():
    """Создает CSV файл с заголовками"""
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'ID записи', 'Дата записи', 'Время записи',
                'Telegram ID', 'ФИО', 'Группа', 'Дата рождения', 'Телефон', 'Username',
                'ID мероприятия', 'Название мероприятия',
                'Дата мероприятия', 'Время мероприятия', 'Место',
                'Комментарий к записи',
                'Статус записи'
            ])
        print(f"✅ Создан CSV файл: {CSV_FILE}")

def save_to_csv(user_data, event_data, comment='', status='Записан'):
    """Сохраняет запись в CSV файл"""
    try:
        row = [
            user_data.get('registration_id', ''),
            datetime.now().strftime('%Y-%m-%d'),
            datetime.now().strftime('%H:%M:%S'),
            user_data.get('telegram_id', ''),
            user_data.get('full_name', ''),
            user_data.get('group', ''),
            user_data.get('birth_date', ''),
            user_data.get('phone', ''),
            user_data.get('username', ''),
            event_data.get('id', ''),
            event_data.get('title', ''),
            event_data.get('date', ''),
            event_data.get('time', ''),
            event_data.get('location', ''),
            comment,
            status
        ]
        
        with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(row)
        
        print(f"✅ Запись {user_data.get('registration_id')} сохранена в CSV со статусом: {status}")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка сохранения в CSV: {e}")
        return False

def update_csv_status(registration_id, new_status):
    """Обновляет статус записи в CSV файле"""
    try:
        # Читаем весь файл
        rows = []
        with open(CSV_FILE, 'r', newline='', encoding='utf-8') as infile:
            reader = csv.reader(infile)
            header = next(reader)
            rows.append(header)
            
            for row in reader:
                if len(row) > 0 and row[0] == str(registration_id):
                    row[-1] = new_status  # Обновляем статус
                    print(f"✅ Обновлена запись {registration_id} в CSV: {new_status}")
                rows.append(row)
        
        # Записываем обратно
        with open(CSV_FILE, 'w', newline='', encoding='utf-8') as outfile:
            writer = csv.writer(outfile)
            writer.writerows(rows)
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка обновления CSV: {e}")
        return False

def delete_from_csv(registration_id):
    """Удаляет запись из CSV файла"""
    try:
        # Читаем весь файл
        rows = []
        with open(CSV_FILE, 'r', newline='', encoding='utf-8') as infile:
            reader = csv.reader(infile)
            header = next(reader)
            rows.append(header)
            
            deleted = False
            for row in reader:
                if len(row) > 0 and row[0] == str(registration_id):
                    deleted = True
                    print(f"✅ Удалена запись {registration_id} из CSV")
                else:
                    rows.append(row)
        
        # Записываем обратно
        with open(CSV_FILE, 'w', newline='', encoding='utf-8') as outfile:
            writer = csv.writer(outfile)
            writer.writerows(rows)
        
        return deleted
        
    except Exception as e:
        print(f"❌ Ошибка удаления из CSV: {e}")
        return False

def count_csv_lines():
    """Считает количество записей в CSV"""
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            return sum(1 for line in f) - 1
    return 0

def get_event_csv(event_id):
    """Создает CSV файл для конкретного мероприятия"""
    try:
        # Создаем уникальное имя файла
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        event_file = f"event_{event_id}_{timestamp}.csv"
        
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        
        # Получаем информацию о мероприятии
        cur.execute('SELECT title, date, time, location FROM events WHERE id = ?', (event_id,))
        event = cur.fetchone()
        
        if not event:
            return None
        
        event_title, event_date, event_time, event_location = event
        
        # Получаем всех записанных на мероприятие
        cur.execute('''
            SELECT registrations.id, registrations.registration_date, registrations.comment,
                   users.telegram_id, users.full_name, users.group_name, 
                   users.birth_date, users.phone_number, users.username
            FROM registrations
            JOIN users ON registrations.user_id = users.telegram_id
            WHERE registrations.event_id = ?
            ORDER BY registrations.registration_date
        ''', (event_id,))
        
        registrations = cur.fetchall()
        conn.close()
        
        # Создаем CSV файл
        with open(event_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # Записываем заголовок мероприятия
            writer.writerow([f"Мероприятие: {event_title}"])
            writer.writerow([f"Дата: {event_date} Время: {event_time}"])
            writer.writerow([f"Место: {event_location}"])
            writer.writerow([])
            
            # Записываем заголовки таблицы
            writer.writerow([
                'ID записи', 'Дата и время записи', 'ФИО', 'Группа', 
                'Дата рождения', 'Телефон', 'Username', 'Комментарий'
            ])
            
            # Записываем данные
            for reg in registrations:
                reg_id, reg_date, comment, user_id, full_name, group_name, birth_date, phone, username = reg
                writer.writerow([
                    reg_id, reg_date, full_name, group_name or '',
                    birth_date or '', phone or '', username or '', comment or ''
                ])
        
        print(f"✅ Создан CSV файл для мероприятия {event_id}: {event_file}")
        return event_file
        
    except Exception as e:
        print(f"❌ Ошибка создания CSV для мероприятия: {e}")
        return None

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С БАЗОЙ ==========
def get_active_events():
    """Получает список активных мероприятий (только для пользователей)"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        SELECT events.id, events.title, events.date, events.time, events.location, 
               events.max_volunteers, events.description,
               (events.max_volunteers - COUNT(registrations.id)) as available_spots
        FROM events
        LEFT JOIN registrations ON events.id = registrations.event_id
        WHERE events.is_active = 1 
          AND events.registration_open = 1
          AND events.date >= date('now')
        GROUP BY events.id
        HAVING available_spots > 0 OR events.max_volunteers IS NULL OR events.max_volunteers = 0
        ORDER BY events.date, events.time
    ''')
    events = cur.fetchall()
    conn.close()
    return events

def get_all_events_admin():
    """Получает ВСЕ мероприятия для админа"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        SELECT id, title, date, time, location, max_volunteers, description,
               is_active, registration_open,
               (SELECT COUNT(*) FROM registrations WHERE event_id = events.id) as registered
        FROM events
        ORDER BY date, time
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
               registrations.id as registration_id, registrations.registration_date,
               registrations.comment
        FROM registrations
        JOIN events ON registrations.event_id = events.id
        WHERE registrations.user_id = ? AND events.date >= date('now') AND events.is_active = 1
        ORDER BY events.date, events.time
    ''', (user_id,))
    events = cur.fetchall()
    conn.close()
    return events

def toggle_event_registration(event_id):
    """Открывает/закрывает запись на мероприятие"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    cur.execute('SELECT registration_open FROM events WHERE id = ?', (event_id,))
    current = cur.fetchone()[0]
    new_value = 0 if current == 1 else 1
    cur.execute('UPDATE events SET registration_open = ? WHERE id = ?', (new_value, event_id))
    conn.commit()
    conn.close()
    return new_value == 1  # True если запись открыта, False если закрыта

def toggle_event_active_status(event_id):
    """Активирует/деактивирует мероприятие"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    cur.execute('SELECT is_active FROM events WHERE id = ?', (event_id,))
    current = cur.fetchone()[0]
    new_value = 0 if current == 1 else 1
    cur.execute('UPDATE events SET is_active = ? WHERE id = ?', (new_value, event_id))
    conn.commit()
    conn.close()
    return new_value == 1  # True если активно, False если неактивно

def delete_event(event_id):
    """Удаляет мероприятие"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    # Получаем все записи на это мероприятие для удаления из CSV
    cur.execute('SELECT id FROM registrations WHERE event_id = ?', (event_id,))
    registration_ids = [row[0] for row in cur.fetchall()]
    
    # Сначала удаляем все записи на это мероприятие
    cur.execute('DELETE FROM registrations WHERE event_id = ?', (event_id,))
    # Затем удаляем само мероприятие
    cur.execute('DELETE FROM events WHERE id = ?', (event_id,))
    deleted = cur.rowcount
    
    conn.commit()
    conn.close()
    
    # Удаляем записи из CSV
    for reg_id in registration_ids:
        delete_from_csv(reg_id)
    
    return deleted > 0

def get_event_details(event_id):
    """Получает детали мероприятия"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        SELECT title, description, date, time, location, max_volunteers, 
               is_active, registration_open
        FROM events WHERE id = ?
    ''', (event_id,))
    event = cur.fetchone()
    conn.close()
    return event

def update_event(event_id, field, value):
    """Обновляет поле мероприятия"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    if field == 'title':
        cur.execute('UPDATE events SET title = ? WHERE id = ?', (value, event_id))
    elif field == 'description':
        cur.execute('UPDATE events SET description = ? WHERE id = ?', (value, event_id))
    elif field == 'date':
        cur.execute('UPDATE events SET date = ? WHERE id = ?', (value, event_id))
    elif field == 'time':
        cur.execute('UPDATE events SET time = ? WHERE id = ?', (value, event_id))
    elif field == 'location':
        cur.execute('UPDATE events SET location = ? WHERE id = ?', (value, event_id))
    elif field == 'max_volunteers':
        cur.execute('UPDATE events SET max_volunteers = ? WHERE id = ?', (int(value), event_id))
    
    conn.commit()
    conn.close()
    return True

def get_registration_info(registration_id):
    """Получает информацию о записи"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        SELECT registrations.id, registrations.user_id, registrations.event_id, registrations.comment,
               users.full_name, users.group_name, users.birth_date, users.phone_number, users.username,
               events.title, events.date, events.time, events.location
        FROM registrations
        JOIN users ON registrations.user_id = users.telegram_id
        JOIN events ON registrations.event_id = events.id
        WHERE registrations.id = ?
    ''', (registration_id,))
    registration = cur.fetchone()
    conn.close()
    return registration

def cancel_registration_db(registration_id):
    """Отменяет запись в базе данных"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    # Получаем информацию о записи перед удалением
    cur.execute('''
        SELECT user_id, event_id FROM registrations WHERE id = ?
    ''', (registration_id,))
    result = cur.fetchone()
    
    if not result:
        conn.close()
        return None
    
    user_id, event_id = result
    
    # Удаляем запись
    cur.execute('DELETE FROM registrations WHERE id = ?', (registration_id,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    
    if deleted > 0:
        # Удаляем из CSV
        delete_from_csv(registration_id)
        return user_id, event_id
    return None

# ========== ОСНОВНЫЕ КОМАНДЫ БОТА ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало работы с ботом"""
    user = update.effective_user
    
    # Регистрируем пользователя в БД
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        INSERT OR IGNORE INTO users (telegram_id, full_name, username) 
        VALUES (?, ?, ?)
    ''', (user.id, user.full_name, f"@{user.username}" if user.username else ""))
    conn.commit()
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton("📝 Записаться на мероприятие", callback_data='list_events')],
        [InlineKeyboardButton("👤 Мои данные", callback_data='my_info')],
        [InlineKeyboardButton("📋 Мои записи", callback_data='my_registrations')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Я бот для записи на волонтерские мероприятия.\n"
        "Сначала заполните свои данные, затем выбирайте мероприятия!",
        reply_markup=reply_markup
    )

async def list_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список активных мероприятий ДЛЯ ПОЛЬЗОВАТЕЛЕЙ"""
    query = update.callback_query
    await query.answer()
    
    events = get_active_events()
    
    if not events:
        keyboard = [
            [InlineKeyboardButton("👤 Мои данные", callback_data='my_info')],
            [InlineKeyboardButton("📋 Мои записи", callback_data='my_registrations')],
            [InlineKeyboardButton("🏠 В главное меню", callback_data='main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📭 *На данный момент нет доступных мероприятий для записи.*\n\n"
            "Загляните позже или свяжитесь с организаторами!",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Создаем кнопки для мероприятий
    keyboard = []
    for event in events[:10]:
        event_id, title, date, time, location, max_vol, desc, available = event
        button_text = f"{title[:25]}..." if len(title) > 25 else title
        button_text += f" ({date})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f'event_{event_id}')])
    
    keyboard.append([InlineKeyboardButton("👤 Мои данные", callback_data='my_info')])
    keyboard.append([InlineKeyboardButton("🏠 В главное меню", callback_data='main_menu')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Формируем текст со списком мероприятий
    events_text = "📅 *Доступные мероприятия для записи:*\n\n"
    for i, event in enumerate(events[:5], 1):
        event_id, title, date, time, location, max_vol, desc, available = event
        events_text += f"{i}. *{title}*\n"
        events_text += f"   📅 {date} ⏰ {time}\n"
        if location:
            events_text += f"   📍 {location}\n"
        events_text += f"   🎫 Свободно: {available if available else '∞'}/{max_vol if max_vol else '∞'}\n\n"
    
    if len(events) > 5:
        events_text += f"*... и еще {len(events)-5} мероприятий*\n\n"
    
    events_text += "Выберите мероприятие для подробной информации:"
    
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
    cur.execute('SELECT title, description, date, time, location, max_volunteers, registration_open, is_active FROM events WHERE id = ?', (event_id,))
    event = cur.fetchone()
    
    if not event:
        await query.edit_message_text("❌ Мероприятие не найдено.")
        conn.close()
        return
    
    title, desc, date, time, location, max_vol, registration_open, is_active = event
    
    # Проверяем, активно ли мероприятие
    if not is_active:
        await query.edit_message_text(
            "❌ *Это мероприятие временно недоступно.*\n\n"
            "Оно было деактивировано организаторами.\n\n"
            "Пожалуйста, выберите другое мероприятие.",
            parse_mode='Markdown'
        )
        conn.close()
        return
    
    # Проверяем, записан ли пользователь
    cur.execute('SELECT id FROM registrations WHERE user_id = ? AND event_id = ?', 
                (query.from_user.id, event_id))
    registration = cur.fetchone()
    is_registered = registration is not None
    registration_id = registration[0] if registration else None
    conn.close()
    
    # Формируем текст
    text = f"🎯 *{title}*\n\n"
    if desc:
        text += f"📝 *Описание:* {desc}\n\n"
    text += f"📅 *Дата:* {date}\n"
    text += f"⏰ *Время:* {time}\n"
    if location:
        text += f"📍 *Место:* {location}\n"
    text += f"👥 *Участников:* {max_vol if max_vol else 'без ограничений'}\n"
    
    if not registration_open:
        text += f"❌ *Запись закрыта*\n\n"
    else:
        text += f"✅ *Запись открыта*\n\n"
    
    if is_registered:
        text += "✅ *Вы уже записаны на это мероприятие*\n\n"
    
    # Создаем кнопки
    keyboard = []
    if registration_open and not is_registered:
        keyboard.append([InlineKeyboardButton("✅ Записаться", callback_data=f'register_{event_id}')])
    elif is_registered and registration_id:
        keyboard.append([InlineKeyboardButton("❌ Отменить запись", callback_data=f'cancel_reg_{registration_id}')])
    
    keyboard.append([InlineKeyboardButton("📅 К списку мероприятий", callback_data='list_events')])
    keyboard.append([InlineKeyboardButton("👤 Мои данные", callback_data='my_info')])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def my_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает данные пользователя"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Получаем данные пользователя
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT full_name, group_name, birth_date, phone_number, username FROM users WHERE telegram_id = ?', (user_id,))
    user = cur.fetchone()
    conn.close()
    
    if not user:
        text = "❌ Ваши данные не найдены. Пожалуйста, нажмите /start"
    else:
        full_name, group_name, birth_date, phone, username = user
        text = "👤 *Ваши данные:*\n\n"
        text += f"• *ФИО:* {full_name if full_name else '❌ Не заполнено'}\n"
        text += f"• *Группа:* {group_name if group_name else '❌ Не заполнена'}\n"
        text += f"• *Дата рождения:* {birth_date if birth_date else '❌ Не заполнена'}\n"
        text += f"• *Телефон:* {phone if phone else '❌ Не заполнен'}\n"
        text += f"• *Username:* {username if username else '❌ Не заполнен'}\n\n"
        
        # Проверяем, все ли данные заполнены
        missing = []
        if not full_name: missing.append("ФИО")
        if not group_name: missing.append("группа")
        if not birth_date: missing.append("дата рождения")
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

async def edit_info_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает процесс редактирования данных"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "✏️ *Заполните ваши данные*\n\n"
        "Отправьте сообщение в формате:\n\n"
        "`ФИО, Группа, Дата рождения (ДД.ММ.ГГГГ), Телефон, @username`\n\n"
        "*Пример:*\n"
        "`Иванов Иван Иванович, ИВТ-20-1, 15.05.2000, +79161234567, @ivanov`\n\n"
        "📌 *Все поля обязательны для записи на мероприятия.*\n"
        "📌 *Данные сохранятся и не нужно будет вводить их заново.*\n\n"
        "Для отмены отправьте /cancel",
        parse_mode='Markdown'
    )
    
    return EDITING_INFO

async def save_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняет данные пользователя"""
    text = update.message.text.strip()
    
    # Проверяем отмену
    if text.lower() == '/cancel':
        await update.message.reply_text("✅ Заполнение данных отменено.")
        return ConversationHandler.END
    
    parts = [part.strip() for part in text.split(',')]
    
    if len(parts) >= 5:
        try:
            full_name = parts[0]
            group = parts[1]
            birth_date = parts[2]
            phone = parts[3]
            username = parts[4]
            
            # Проверяем формат даты рождения
            try:
                datetime.strptime(birth_date, '%d.%m.%Y')
            except ValueError:
                await update.message.reply_text(
                    "❌ Неверный формат даты рождения! Используйте ДД.ММ.ГГГГ\n"
                    "Пример: 15.05.2000\n\n"
                    "Попробуйте еще раз или отправьте /cancel для отмены"
                )
                return EDITING_INFO
            
            # Проверяем username
            if not username.startswith('@'):
                await update.message.reply_text(
                    "❌ Username должен начинаться с @\n"
                    "Пример: @ivanov\n\n"
                    "Попробуйте еще раз или отправьте /cancel для отмены"
                )
                return EDITING_INFO
            
            # Сохраняем в БД
            conn = sqlite3.connect(DB_NAME)
            cur = conn.cursor()
            cur.execute('''
                INSERT OR REPLACE INTO users 
                (telegram_id, full_name, group_name, birth_date, phone_number, username)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (update.effective_user.id, full_name, group, birth_date, phone, username))
            conn.commit()
            conn.close()
            
            await update.message.reply_text(
                "✅ *Данные сохранены!*\n\n"
                f"• ФИО: {full_name}\n"
                f"• Группа: {group}\n"
                f"• Дата рождения: {birth_date}\n"
                f"• Телефон: {phone}\n"
                f"• Username: {username}\n\n"
                "📌 *Данные сохранены. Теперь вы можете записываться на мероприятия!*",
                parse_mode='Markdown'
            )
            
            # Показываем кнопки
            keyboard = [
                [InlineKeyboardButton("📝 Записаться на мероприятие", callback_data='list_events')],
                [InlineKeyboardButton("👤 Посмотреть мои данные", callback_data='my_info')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)
            
        except Exception as e:
            await update.message.reply_text(
                f"❌ Ошибка при сохранении: {e}\n\n"
                "Пожалуйста, проверьте правильность ввода данных."
            )
            return EDITING_INFO
    else:
        await update.message.reply_text(
            "❌ *Неверный формат!*\n\n"
            "Пожалуйста, отправьте данные в формате:\n"
            "`ФИО, Группа, Дата рождения, Телефон, @username`\n\n"
            "Пример:\n"
            "`Иванов Иван Иванович, ИВТ-20-1, 15.05.2000, +79161234567, @ivanov`\n\n"
            "Попробуйте еще раз или отправьте /cancel для отмены",
            parse_mode='Markdown'
        )
        return EDITING_INFO
    
    return ConversationHandler.END

async def register_for_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает процесс записи на мероприятие"""
    query = update.callback_query
    await query.answer()
    
    try:
        event_id = int(query.data.split('_')[1])
    except:
        await query.answer("❌ Ошибка: неверный ID мероприятия", show_alert=True)
        return
    
    context.user_data['registering_event_id'] = event_id
    
    await query.edit_message_text(
        "📝 *Добавление комментария к записи*\n\n"
        "За какой семестр выставлять баллы:\n\n"
        "Примеры комментариев:\n"
        "• 'Осень 2024/ весна 2025/ другое'\n\n"
        "Отправьте комментарий или отправьте /skip чтобы пропустить.\n"
        "Для отмены отправьте /cancel",
        parse_mode='Markdown'
    )
    
    return ADDING_COMMENT

async def save_registration_with_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняет запись с комментарием"""
    text = update.message.text.strip()
    
    # Проверяем отмену
    if text.lower() == '/cancel':
        await update.message.reply_text("✅ Запись отменена.")
        if 'registering_event_id' in context.user_data:
            del context.user_data['registering_event_id']
        return ConversationHandler.END
    
    # Проверяем пропуск комментария
    if text.lower() == '/skip':
        comment = ''
    else:
        comment = text[:200]  # Ограничиваем длину комментария
    
    event_id = context.user_data.get('registering_event_id')
    user_id = update.effective_user.id
    
    # Проверяем, что event_id существует
    if not event_id:
        await update.message.reply_text("❌ Ошибка: мероприятие не найдено.")
        return ConversationHandler.END
    
    # 1. Проверяем данные пользователя
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT full_name, group_name, birth_date, phone_number, username FROM users WHERE telegram_id = ?', (user_id,))
    user = cur.fetchone()
    
    if not user:
        await update.message.reply_text("❌ Ваши данные не найдены. Пожалуйста, сначала заполните данные.")
        conn.close()
        if 'registering_event_id' in context.user_data:
            del context.user_data['registering_event_id']
        return ConversationHandler.END
    
    full_name, group, birth_date, phone, username = user
    
    # Проверяем обязательные поля
    missing = []
    if not full_name: missing.append("ФИО")
    if not group: missing.append("группа")
    if not birth_date: missing.append("дата рождения")
    if not phone: missing.append("телефон")
    
    if missing:
        keyboard = [
            [InlineKeyboardButton("✏️ Заполнить данные", callback_data='edit_info')],
            [InlineKeyboardButton("📅 К мероприятиям", callback_data='list_events')]
        ]
        
        await update.message.reply_text(
            f"❌ *Не хватает данных для записи:*\n• {', '.join(missing)}\n\n"
            f"Пожалуйста, заполните данные перед записью.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        conn.close()
        if 'registering_event_id' in context.user_data:
            del context.user_data['registering_event_id']
        return ConversationHandler.END
    
    # 2. Проверяем мероприятие и открыта ли запись
    cur.execute('SELECT title, date, time, location, max_volunteers, registration_open, is_active FROM events WHERE id = ?', (event_id,))
    event = cur.fetchone()
    
    if not event:
        await update.message.reply_text("❌ Мероприятие не найдено.")
        conn.close()
        if 'registering_event_id' in context.user_data:
            del context.user_data['registering_event_id']
        return ConversationHandler.END
    
    title, date, time, location, max_vol, registration_open, is_active = event
    
    # Проверяем, активно ли мероприятие
    if not is_active:
        await update.message.reply_text("❌ Это мероприятие временно недоступно!")
        conn.close()
        if 'registering_event_id' in context.user_data:
            del context.user_data['registering_event_id']
        return ConversationHandler.END
    
    if not registration_open:
        await update.message.reply_text("❌ Запись на это мероприятие закрыта!")
        conn.close()
        if 'registering_event_id' in context.user_data:
            del context.user_data['registering_event_id']
        return ConversationHandler.END
    
    # 3. Проверяем, не записан ли уже
    cur.execute('SELECT id FROM registrations WHERE user_id = ? AND event_id = ?', (user_id, event_id))
    if cur.fetchone():
        await update.message.reply_text("Вы уже записаны на это мероприятие!")
        conn.close()
        if 'registering_event_id' in context.user_data:
            del context.user_data['registering_event_id']
        return ConversationHandler.END
    
    # 4. Проверяем свободные места
    cur.execute('SELECT COUNT(*) FROM registrations WHERE event_id = ?', (event_id,))
    registered_count = cur.fetchone()[0]
    
    if max_vol and registered_count >= max_vol:
        await update.message.reply_text("❌ К сожалению, все места уже заняты!")
        conn.close()
        if 'registering_event_id' in context.user_data:
            del context.user_data['registering_event_id']
        return ConversationHandler.END
    
    # 5. Сохраняем запись в БД
    cur.execute('INSERT INTO registrations (user_id, event_id, comment) VALUES (?, ?, ?)', 
                (user_id, event_id, comment))
    registration_id = cur.lastrowid
    conn.commit()
    conn.close()
    
    # 6. Получаем полные данные для CSV
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        SELECT registrations.id, users.full_name, users.group_name, users.birth_date, 
               users.phone_number, users.username, events.title, events.date, events.time, events.location
        FROM registrations
        JOIN users ON registrations.user_id = users.telegram_id
        JOIN events ON registrations.event_id = events.id
        WHERE registrations.id = ?
    ''', (registration_id,))
    registration_data = cur.fetchone()
    conn.close()
    
    if registration_data:
        reg_id, full_name, group_name, birth_date, phone, username, event_title, event_date, event_time, event_location = registration_data
        
        user_data = {
            'registration_id': reg_id,
            'telegram_id': user_id,
            'full_name': full_name,
            'group': group_name,
            'birth_date': birth_date,
            'phone': phone,
            'username': username
        }
        
        event_data = {
            'id': event_id,
            'title': event_title,
            'date': event_date,
            'time': event_time,
            'location': event_location if event_location else 'Не указано'
        }
        
        csv_success = save_to_csv(user_data, event_data, comment, 'Записан')
    
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
        
        if comment:
            text += f"💬 *Ваш комментарий:* {comment}\n\n"
        
        text += (
            f"👥 *Место в списке:* {registered_count + 1}/{max_vol if max_vol else '∞'}\n\n"
            "📊 *Ваши данные сохранены в таблицу волонтеров.*\n"
            "Организаторы увидят вашу запись.\n\n"
            "📌 *Не забудьте добавить мероприятие в календарь!*"
        )
        
        # Отправляем уведомление
        await update.message.reply_text("✅ Запись сохранена в таблицу!")
    else:
        text = (
            "⚠️ *Запись сохранена в боте, но возникла ошибка при сохранении в таблицу.*\n\n"
            f"🎯 *Мероприятие:* {title}\n"
            f"📅 *Дата:* {date}\n\n"
            "Пожалуйста, свяжитесь с организаторами для подтверждения записи."
        )
        
        await update.message.reply_text("⚠️ Ошибка сохранения в таблицу")
    
    # Кнопки после записи
    keyboard = [
        [InlineKeyboardButton("📝 Записаться еще", callback_data='list_events')],
        [InlineKeyboardButton("📋 Мои записи", callback_data='my_registrations')],
        [InlineKeyboardButton("🏠 В главное меню", callback_data='main_menu')]
    ]
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    # Очищаем контекст
    if 'registering_event_id' in context.user_data:
        del context.user_data['registering_event_id']
    
    return ConversationHandler.END

async def my_registrations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает записи пользователя с возможностью отмены"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    registrations = get_user_registrations(user_id)
    
    if not registrations:
        text = (
            "📭 *У вас пока нет записей на мероприятия.*\n\n"
            "Выберите мероприятие из списка и запишитесь!"
        )
        keyboard = [
            [InlineKeyboardButton("📝 Записаться на мероприятие", callback_data='list_events')],
            [InlineKeyboardButton("👤 Мои данные", callback_data='my_info')],
            [InlineKeyboardButton("🏠 В главное меню", callback_data='main_menu')]
        ]
    else:
        text = "📋 *Ваши записи на мероприятия:*\n\n"
        keyboard = []
        
        for i, reg in enumerate(registrations, 1):
            event_id, title, date, time, location, registration_id, reg_date, comment = reg
            text += f"{i}. *{title}*\n"
            text += f"   📅 {date} ⏰ {time}\n"
            if location:
                text += f"   📍 {location}\n"
            if comment:
                text += f"   💬 Комментарий: {comment}\n"
            text += f"   📝 Записан: {reg_date[:10]}\n"
            text += f"   🆔 ID записи: {registration_id}\n\n"
            
            # Добавляем кнопку отмены для каждой записи
            keyboard.append([
                InlineKeyboardButton(f"❌ Отменить запись на '{title[:15]}...'", 
                                   callback_data=f'cancel_reg_{registration_id}')
            ])
        
        keyboard.append([InlineKeyboardButton("📝 Записаться на мероприятие", callback_data='list_events')])
        keyboard.append([InlineKeyboardButton("👤 Мои данные", callback_data='my_info')])
        keyboard.append([InlineKeyboardButton("🏠 В главное меню", callback_data='main_menu')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет запись пользователя"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Извлекаем registration_id из callback_data
        if query.data.startswith('cancel_reg_'):
            registration_id = int(query.data.split('_')[2])
        else:
            await query.answer("❌ Ошибка формата команды", show_alert=True)
            return
    except:
        await query.answer("❌ Ошибка: неверный ID записи", show_alert=True)
        return
    
    user_id = query.from_user.id
    
    # Получаем информацию о записи
    registration_info = get_registration_info(registration_id)
    
    if not registration_info:
        await query.answer("❌ Запись не найдена", show_alert=True)
        return
    
    # Проверяем, что это запись текущего пользователя
    reg_id, reg_user_id, event_id, comment, full_name, group_name, birth_date, phone, username, title, date, time, location = registration_info
    
    if reg_user_id != user_id:
        await query.answer("❌ Вы не можете отменить чужую запись!", show_alert=True)
        return
    
    # Отменяем запись в БД
    result = cancel_registration_db(registration_id)
    
    if result:
        await query.answer("✅ Запись успешно отменена!", show_alert=True)
        
        # Показываем подтверждение
        text = (
            "✅ *Запись отменена успешно!*\n\n"
            f"🎯 *Мероприятие:* {title}\n"
            f"📅 *Дата:* {date}\n"
            f"⏰ *Время:* {time}\n"
        )
        
        if location:
            text += f"📍 *Место:* {location}\n"
        
        if comment:
            text += f"💬 *Ваш комментарий:* {comment}\n"
        
        text += "\n📊 *Запись удалена из таблицы волонтеров.*\n"
        text += "Место освобождено для других участников."
        
        keyboard = [
            [InlineKeyboardButton("📝 Записаться на другое мероприятие", callback_data='list_events')],
            [InlineKeyboardButton("📋 Мои записи", callback_data='my_registrations')],
            [InlineKeyboardButton("🏠 В главное меню", callback_data='main_menu')]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        await query.answer("❌ Ошибка при отмене записи", show_alert=True)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📝 Записаться на мероприятие", callback_data='list_events')],
        [InlineKeyboardButton("👤 Мои данные", callback_data='my_info')],
        [InlineKeyboardButton("📋 Мои записи", callback_data='my_registrations')]
    ]
    
    await query.edit_message_text(
        "🏠 *Главное меню*\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ========== АДМИН КОМАНДЫ ==========
async def admin_add_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса добавления мероприятия"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ У вас нет прав доступа.")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📝 *Добавление нового мероприятия*\n\n"
        "Отправьте данные в формате:\n\n"
        "`Название, Описание, Дата (ГГГГ-ММ-ДД), Время (ЧЧ:ММ), Место, Макс. участников`\n\n"
        "*Пример:*\n"
        "`Уборка парка, Субботник в центральном парке, 2024-04-10, 14:00, Центральный парк, 30`\n\n"
        "📌 *Примечания:*\n"
        "- Дата в формате ГГГГ-ММ-ДД\n"
        "- Время в формате ЧЧ:ММ\n"
        "- Макс. участников: число или 0 для неограниченного\n"
        "- Описание не обязательно\n\n"
        "Для отмены отправьте /cancel",
        parse_mode='Markdown'
    )
    
    context.user_data['adding_event'] = True
    return ADDING_EVENT

async def save_new_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняет новое мероприятие из сообщения"""
    # Проверяем, что это именно админ и он в режиме добавления
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ У вас нет прав доступа.")
        return ConversationHandler.END
    
    text = update.message.text.strip()
    
    if text.lower() == '/cancel':
        await update.message.reply_text("✅ Добавление мероприятия отменено.")
        return ConversationHandler.END
    
    parts = [part.strip() for part in text.split(',')]
    
    if len(parts) >= 5:
        try:
            # Определяем части в зависимости от количества
            if len(parts) == 5:
                # Формат без описания: Название, Дата, Время, Место, Макс
                title = parts[0]
                description = ""
                date = parts[1]
                time = parts[2]
                location = parts[3]
                max_volunteers = int(parts[4]) if parts[4].isdigit() else 0
            else:
                # Формат с описанием: Название, Описание, Дата, Время, Место, Макс
                title = parts[0]
                description = parts[1]
                date = parts[2]
                time = parts[3]
                location = parts[4]
                max_volunteers = int(parts[5]) if parts[5].isdigit() else 0
            
            # Проверяем формат даты
            try:
                datetime.strptime(date, '%Y-%m-%d')
            except ValueError:
                await update.message.reply_text(
                    "❌ Неверный формат даты! Используйте ГГГГ-ММ-ДД\n"
                    "Пример: 2024-04-10\n\n"
                    "Попробуйте еще раз или отправьте /cancel для отмены"
                )
                return ADDING_EVENT
            
            # Проверяем формат времени
            try:
                datetime.strptime(time, '%H:%M')
            except ValueError:
                await update.message.reply_text(
                    "❌ Неверный формат времени! Используйте ЧЧ:ММ\n"
                    "Пример: 14:00\n\n"
                    "Попробуйте еще раз или отправьте /cancel для отмены"
                )
                return ADDING_EVENT
            
            # Сохраняем в БД
            conn = sqlite3.connect(DB_NAME)
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO events (title, description, date, time, location, max_volunteers, is_active, registration_open)
                VALUES (?, ?, ?, ?, ?, ?, 1, 1)
            ''', (title, description, date, time, location, max_volunteers))
            event_id = cur.lastrowid
            conn.commit()
            conn.close()
            
            # Формируем ответ
            response_text = (
                "✅ *Мероприятие добавлено!*\n\n"
                f"🎯 *Название:* {title}\n"
                f"📅 *Дата:* {date}\n"
                f"⏰ *Время:* {time}\n"
                f"📍 *Место:* {location}\n"
                f"👥 *Макс. участников:* {max_volunteers if max_volunteers > 0 else 'не ограничено'}\n"
            )
            
            if description:
                response_text += f"📝 *Описание:* {description}\n"
            
            response_text += f"\n🆔 *ID мероприятия:* {event_id}"
            
            await update.message.reply_text(response_text, parse_mode='Markdown')
            
            print(f"✅ Добавлено мероприятие: {title} (ID: {event_id})")
            
        except Exception as e:
            print(f"❌ Ошибка при добавлении мероприятия: {e}")
            await update.message.reply_text(
                f"❌ Ошибка: {str(e)[:200]}\n\n"
                "Проверьте правильность ввода данных и попробуйте еще раз.\n"
                "Для отмены отправьте /cancel"
            )
            return ADDING_EVENT
    else:
        await update.message.reply_text(
            "❌ *Неверный формат!* Требуется минимум 5 полей.\n\n"
            "Отправьте данные в формате:\n"
            "`Название, Описание, Дата, Время, Место, Макс. участников`\n\n"
            "*Пример:*\n"
            "`Уборка парка, Субботник в парке, 2024-04-10, 14:00, Центральный парк, 30`\n\n"
            "Попробуйте еще раз или отправьте /cancel для отмены",
            parse_mode='Markdown'
        )
        return ADDING_EVENT
    
    # Сбрасываем флаг
    if 'adding_event' in context.user_data:
        del context.user_data['adding_event']
    
    return ConversationHandler.END

async def admin_list_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список мероприятий админу"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ У вас нет прав доступа.")
        return
    
    events = get_all_events_admin()
    
    if not events:
        text = "📭 Нет мероприятий."
    else:
        text = "📋 *Все мероприятия:*\n\n"
        for event in events:
            event_id, title, date, time, location, max_vol, desc, is_active, registration_open, registered = event
            status = "✅ Активно" if is_active == 1 else "❌ Неактивно"
            reg_status = "✅ Открыта" if registration_open == 1 else "❌ Закрыта"
            max_text = f"{max_vol}" if max_vol > 0 else "∞"
            
            text += f"🆔 *{event_id}*\n"
            text += f"🎯 *{title}*\n"
            text += f"   📅 {date} ⏰ {time}\n"
            if location:
                text += f"   📍 {location}\n"
            text += f"   👥 {registered}/{max_text} записей\n"
            text += f"   🏷️ Статус: {status}\n"
            text += f"   📝 Запись: {reg_status}\n\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def admin_manage_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню управления мероприятиями для админа"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    events = get_all_events_admin()
    
    if not events:
        keyboard = [[InlineKeyboardButton("◀️ Назад в админ-панель", callback_data='admin_back')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📭 Нет мероприятий для управления.",
            reply_markup=reply_markup
        )
        return
    
    # Создаем кнопки для каждого мероприятия
    keyboard = []
    for event in events:
        event_id, title, date, time, location, max_vol, desc, is_active, registration_open, registered = event
        button_text = f"🆔{event_id}: {title[:20]}"
        if len(title) > 20:
            button_text += "..."
        button_text += f" ({date})"
        
        # Иконки статуса
        status_icon = "✅" if is_active == 1 else "❌"
        reg_icon = "📝" if registration_open == 1 else "🔒"
        
        button_text = f"{status_icon}{reg_icon} {button_text}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f'manage_{event_id}')])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад в админ-панель", callback_data='admin_back')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🔧 *Управление мероприятиями*\n\n"
        "Выберите мероприятие для управления:\n"
        "✅❌ - активность мероприятия\n"
        "📝🔒 - статус записи\n\n"
        f"Всего мероприятий: {len(events)}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def manage_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Управление конкретным мероприятием"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    try:
        # Извлекаем event_id из callback_data
        if query.data.startswith('manage_'):
            event_id = int(query.data.split('_')[1])
        else:
            # Если это действие, обновляем страницу
            await admin_manage_events(update, context)
            return
    except:
        # Если ошибка, просто возвращаемся к списку
        await admin_manage_events(update, context)
        return
    
    event = get_event_details(event_id)
    if not event:
        await query.edit_message_text("❌ Мероприятие не найдено.")
        return
    
    title, desc, date, time, location, max_vol, is_active, registration_open = event
    
    # Получаем количество записанных
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM registrations WHERE event_id = ?', (event_id,))
    registered = cur.fetchone()[0]
    conn.close()
    
    # Формируем текст
    text = f"🔧 *Управление мероприятием*\n\n"
    text += f"🆔 *ID:* {event_id}\n"
    text += f"🎯 *Название:* {title}\n"
    if desc:
        text += f"📝 *Описание:* {desc}\n"
    text += f"📅 *Дата:* {date}\n"
    text += f"⏰ *Время:* {time}\n"
    if location:
        text += f"📍 *Место:* {location}\n"
    text += f"👥 *Участников:* {registered}/{max_vol if max_vol > 0 else '∞'}\n"
    text += f"🏷️ *Статус:* {'✅ Активно' if is_active == 1 else '❌ Неактивно'}\n"
    text += f"📝 *Запись:* {'✅ Открыта' if registration_open == 1 else '❌ Закрыта'}\n"
    
    # Создаем кнопки управления
    keyboard = []
    
    # Кнопка для активации/деактивации мероприятия
    if is_active == 1:
        keyboard.append([InlineKeyboardButton("❌ Деактивировать мероприятие", callback_data=f'toggle_active_{event_id}')])
    else:
        keyboard.append([InlineKeyboardButton("✅ Активировать мероприятие", callback_data=f'toggle_active_{event_id}')])
    
    # Кнопка для открытия/закрытия записи
    if registration_open == 1:
        keyboard.append([InlineKeyboardButton("🔒 Закрыть запись", callback_data=f'toggle_reg_{event_id}')])
    else:
        keyboard.append([InlineKeyboardButton("📝 Открыть запись", callback_data=f'toggle_reg_{event_id}')])
    
    # Кнопка для скачивания таблицы мероприятия
    keyboard.append([InlineKeyboardButton("📥 Скачать таблицу мероприятия", callback_data=f'download_event_{event_id}')])
    
    # Кнопки для редактирования
    keyboard.append([InlineKeyboardButton("✏️ Изменить данные", callback_data=f'edit_{event_id}')])
    
    # Кнопка удаления
    keyboard.append([InlineKeyboardButton("🗑️ Удалить мероприятие", callback_data=f'delete_{event_id}')])
    
    # Кнопка просмотра записавшихся
    keyboard.append([InlineKeyboardButton("👥 Просмотреть записавшихся", callback_data=f'view_{event_id}')])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад к списку", callback_data='admin_manage')])
    keyboard.append([InlineKeyboardButton("🏠 В админ-панель", callback_data='admin_back')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# ========== ОТДЕЛЬНЫЕ ОБРАБОТЧИКИ ДЛЯ КНОПОК ==========
async def toggle_registration_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает кнопку открытия/закрытия записи"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    try:
        event_id = int(query.data.split('_')[2])
    except:
        await query.answer("❌ Ошибка: неверный ID мероприятия", show_alert=True)
        return
    
    event = get_event_details(event_id)
    if not event:
        await query.answer("❌ Мероприятие не найдено", show_alert=True)
        return
    
    title = event[0]
    
    # Переключаем запись
    is_now_open = toggle_event_registration(event_id)
    if is_now_open:
        message = f"📝 Запись на мероприятие '{title}' открыта."
    else:
        message = f"🔒 Запись на мероприятие '{title}' закрыта."
    
    await query.answer(message, show_alert=True)
    
    # Обновляем страницу
    await asyncio.sleep(0.5)
    await manage_event(update, context)

async def toggle_active_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает кнопку активации/деактивации мероприятия"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    try:
        event_id = int(query.data.split('_')[2])
    except:
        await query.answer("❌ Ошибка: неверный ID мероприятия", show_alert=True)
        return
    
    event = get_event_details(event_id)
    if not event:
        await query.answer("❌ Мероприятие не найдено", show_alert=True)
        return
    
    title = event[0]
    
    # Переключаем активность
    is_now_active = toggle_event_active_status(event_id)
    if is_now_active:
        message = f"✅ Мероприятие '{title}' активировано."
    else:
        message = f"❌ Мероприятие '{title}' деактивировано."
    
    await query.answer(message, show_alert=True)
    
    # Обновляем страницу
    await asyncio.sleep(0.5)
    await manage_event(update, context)

async def download_event_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает кнопку скачивания таблицы мероприятия"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    try:
        event_id = int(query.data.split('_')[2])
    except:
        await query.answer("❌ Ошибка: неверный ID мероприятия", show_alert=True)
        return
    
    event = get_event_details(event_id)
    if not event:
        await query.answer("❌ Мероприятие не найдено", show_alert=True)
        return
    
    title = event[0]
    
    # Создаем CSV файл для мероприятия
    event_file = get_event_csv(event_id)
    
    if event_file:
        try:
            with open(event_file, 'rb') as f:
                await context.bot.send_document(
                    chat_id=query.from_user.id,
                    document=f,
                    filename=f'мероприятие_{event_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
                    caption=f"📊 Таблица участников мероприятия: {title}"
                )
            
            # Удаляем временный файл
            os.remove(event_file)
            
            await query.answer("✅ Таблица отправлена вам в личные сообщения!", show_alert=True)
            
        except Exception as e:
            print(f"❌ Ошибка при отправке CSV: {e}")
            await query.answer("❌ Ошибка при отправке файла", show_alert=True)
    else:
        await query.answer("❌ Ошибка при создании файла", show_alert=True)

async def delete_event_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает кнопку удаления мероприятия"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    try:
        event_id = int(query.data.split('_')[1])
    except:
        await query.answer("❌ Ошибка: неверный ID мероприятия", show_alert=True)
        return
    
    event = get_event_details(event_id)
    if not event:
        await query.answer("❌ Мероприятие не найдено", show_alert=True)
        return
    
    title = event[0]
    
    # Подтверждение удаления
    keyboard = [
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f'confirm_delete_{event_id}')],
        [InlineKeyboardButton("❌ Нет, отменить", callback_data=f'manage_{event_id}')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"⚠️ *Вы уверены, что хотите удалить мероприятие?*\n\n"
        f"🎯 *Название:* {title}\n\n"
        f"Это действие удалит:\n"
        f"• Само мероприятие\n"
        f"• Все записи на него\n"
        f"• Все данные из таблицы CSV\n\n"
        f"*Действие необратимо!*",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def confirm_delete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает подтверждение удаления мероприятия"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    try:
        event_id = int(query.data.split('_')[2])
    except:
        await query.answer("❌ Ошибка: неверный ID мероприятия", show_alert=True)
        return
    
    event = get_event_details(event_id)
    if not event:
        await query.answer("❌ Мероприятие не найдено", show_alert=True)
        return
    
    title = event[0]
    
    # Удаляем мероприятие
    if delete_event(event_id):
        message = f"🗑️ Мероприятие '{title}' удалено."
        # Возвращаемся к списку
        await admin_manage_events(update, context)
    else:
        message = f"❌ Ошибка при удалении мероприятия."
        await query.answer(message, show_alert=True)
        await asyncio.sleep(0.5)
        await admin_manage_events(update, context)

async def view_event_participants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает участников мероприятия"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    try:
        event_id = int(query.data.split('_')[1])
    except:
        await query.answer("❌ Ошибка: неверный ID мероприятия", show_alert=True)
        return
    
    event = get_event_details(event_id)
    if not event:
        await query.edit_message_text("❌ Мероприятие не найдено.")
        return
    
    title = event[0]
    
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        SELECT registrations.id, registrations.comment, 
               users.full_name, users.group_name, users.phone_number, users.username
        FROM registrations
        JOIN users ON registrations.user_id = users.telegram_id
        WHERE registrations.event_id = ?
        ORDER BY registrations.registration_date
    ''', (event_id,))
    registrations = cur.fetchall()
    conn.close()
    
    if not registrations:
        text = f"👥 *Записанные на мероприятие:* {title}\n\n"
        text += "Пока никто не записался."
    else:
        text = f"👥 *Записанные на мероприятие:* {title}\n"
        text += f"Всего записей: {len(registrations)}\n\n"
        
        for i, reg in enumerate(registrations, 1):
            reg_id, comment, full_name, group_name, phone, username = reg
            text += f"{i}. *{full_name}*\n"
            text += f"   ID записи: {reg_id}\n"
            if group_name:
                text += f"   Группа: {group_name}\n"
            if phone:
                text += f"   Телефон: {phone}\n"
            if username:
                text += f"   @{username.replace('@', '')}\n"
            if comment:
                text += f"   💬 Комментарий: {comment}\n"
            text += "\n"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад к управлению", callback_data=f'manage_{event_id}')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def edit_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает редактирование мероприятия"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    try:
        event_id = int(query.data.split('_')[1])
    except:
        await query.answer("❌ Ошибка: неверный ID мероприятия", show_alert=True)
        return
    
    context.user_data['editing_event_id'] = event_id
    context.user_data['editing_field'] = None
    
    event = get_event_details(event_id)
    if not event:
        await query.edit_message_text("❌ Мероприятие не найдено.")
        return
    
    title = event[0]
    
    keyboard = [
        [InlineKeyboardButton("✏️ Название", callback_data=f'edit_field_title_{event_id}')],
        [InlineKeyboardButton("📝 Описание", callback_data=f'edit_field_desc_{event_id}')],
        [InlineKeyboardButton("📅 Дата", callback_data=f'edit_field_date_{event_id}')],
        [InlineKeyboardButton("⏰ Время", callback_data=f'edit_field_time_{event_id}')],
        [InlineKeyboardButton("📍 Место", callback_data=f'edit_field_location_{event_id}')],
        [InlineKeyboardButton("👥 Макс. участников", callback_data=f'edit_field_max_{event_id}')],
        [InlineKeyboardButton("◀️ Назад", callback_data=f'manage_{event_id}')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"✏️ *Редактирование мероприятия:* {title}\n\n"
        "Выберите поле для редактирования:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def edit_event_field_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает редактирование поля мероприятия"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    try:
        field = query.data.split('_')[2]
        event_id = int(query.data.split('_')[3])
    except:
        await query.edit_message_text("❌ Ошибка")
        return
    
    event = get_event_details(event_id)
    if not event:
        await query.edit_message_text("❌ Мероприятие не найдено.")
        return
    
    title, desc, date, time, location, max_vol, is_active, registration_open = event
    
    field_names = {
        'title': 'Название',
        'desc': 'Описание',
        'date': 'Дату (ГГГГ-ММ-ДД)',
        'time': 'Время (ЧЧ:ММ)',
        'location': 'Место',
        'max': 'Максимальное количество участников'
    }
    
    field_values = {
        'title': title,
        'desc': desc,
        'date': date,
        'time': time,
        'location': location,
        'max': str(max_vol)
    }
    
    field_name = field_names.get(field, 'поле')
    current_value = field_values.get(field, '')
    
    await query.edit_message_text(
        f"✏️ *Редактирование {field_name}*\n\n"
        f"Текущее значение: `{current_value}`\n\n"
        f"Отправьте новое значение.\n"
        f"Для отмены отправьте /cancel",
        parse_mode='Markdown'
    )
    
    context.user_data['editing_event_id'] = event_id
    context.user_data['editing_field'] = field
    
    return EDIT_EVENT_DETAILS

async def save_event_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняет отредактированное поле мероприятия"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ У вас нет прав доступа.")
        return ConversationHandler.END
    
    text = update.message.text.strip()
    
    if text.lower() == '/cancel':
        await update.message.reply_text("✅ Редактирование отменено.")
        return ConversationHandler.END
    
    event_id = context.user_data.get('editing_event_id')
    field = context.user_data.get('editing_field')
    
    if not event_id or not field:
        await update.message.reply_text("❌ Ошибка: данные не найдены.")
        return ConversationHandler.END
    
    event = get_event_details(event_id)
    if not event:
        await update.message.reply_text("❌ Мероприятие не найдено.")
        return ConversationHandler.END
    
    title = event[0]
    
    try:
        # Валидация в зависимости от поля
        if field == 'date':
            try:
                datetime.strptime(text, '%Y-%m-%d')
            except ValueError:
                await update.message.reply_text(
                    "❌ Неверный формат даты! Используйте ГГГГ-ММ-ДД\n"
                    "Пример: 2024-04-10\n\n"
                    "Попробуйте еще раз или отправьте /cancel для отмены"
                )
                return EDIT_EVENT_DETAILS
        
        elif field == 'time':
            try:
                datetime.strptime(text, '%H:%M')
            except ValueError:
                await update.message.reply_text(
                    "❌ Неверный формат времени! Используйте ЧЧ:ММ\n"
                    "Пример: 14:00\n\n"
                    "Попробуйте еще раз или отправьте /cancel для отмены"
                )
                return EDIT_EVENT_DETAILS
        
        elif field == 'max':
            if not text.isdigit() and text != '0':
                await update.message.reply_text(
                    "❌ Введите число для максимального количества участников!\n"
                    "Или 0 для неограниченного количества.\n\n"
                    "Попробуйте еще раз или отправьте /cancel для отмены"
                )
                return EDIT_EVENT_DETAILS
        
        # Обновляем поле
        db_field = {
            'title': 'title',
            'desc': 'description',
            'date': 'date',
            'time': 'time',
            'location': 'location',
            'max': 'max_volunteers'
        }.get(field)
        
        if db_field:
            update_event(event_id, db_field, text)
        
        await update.message.reply_text(
            f"✅ Поле мероприятия '{title}' успешно обновлено!\n"
            f"Новое значение: `{text}`",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ Ошибка при обновлении: {e}\n\n"
            "Попробуйте еще раз или отправьте /cancel для отмены"
        )
        return EDIT_EVENT_DETAILS
    
    # Очищаем контекст
    if 'editing_event_id' in context.user_data:
        del context.user_data['editing_event_id']
    if 'editing_field' in context.user_data:
        del context.user_data['editing_field']
    
    return ConversationHandler.END

async def admin_table(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет CSV таблицу админу"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ У вас нет прав доступа.")
        return
    
    if not os.path.exists(CSV_FILE):
        await update.message.reply_text("❌ Таблица еще не создана.")
        return
    
    try:
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
    
    cur.execute("SELECT COUNT(*) FROM events WHERE is_active = 1")
    active_events = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM events WHERE is_active = 0")
    inactive_events = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM events WHERE registration_open = 1 AND is_active = 1")
    open_events = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM registrations")
    regs_count = cur.fetchone()[0]
    
    # Популярные мероприятия
    cur.execute('''
        SELECT events.title, COUNT(registrations.id) as count
        FROM events
        LEFT JOIN registrations ON events.id = registrations.event_id
        WHERE events.is_active = 1
        GROUP BY events.id
        ORDER BY count DESC
        LIMIT 5
    ''')
    popular_events = cur.fetchall()
    
    conn.close()
    
    # Формируем текст
    text = "👑 *Статистика для админа*\n\n"
    text += f"👥 Пользователей: {users_count}\n"
    text += f"📅 Всего мероприятий: {active_events + inactive_events}\n"
    text += f"   ✅ Активных: {active_events}\n"
    text += f"   ❌ Неактивных: {inactive_events}\n"
    text += f"   📝 С открытой записью: {open_events}\n"
    text += f"📝 Всего записей: {regs_count}\n"
    text += f"📊 Записей в CSV: {count_csv_lines()}\n\n"
    
    text += "🔥 *Самые популярные мероприятия:*\n"
    for title, count in popular_events:
        text += f"• {title}: {count} записей\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /cancel"""
    await update.message.reply_text("✅ Операция отменена.")
    
    # Сбрасываем флаги
    if 'adding_event' in context.user_data:
        del context.user_data['adding_event']
    if 'editing_event_id' in context.user_data:
        del context.user_data['editing_event_id']
    if 'editing_field' in context.user_data:
        del context.user_data['editing_field']
    if 'registering_event_id' in context.user_data:
        del context.user_data['registering_event_id']
    
    return ConversationHandler.END

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-панель"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ У вас нет прав доступа.")
        return
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить мероприятие", callback_data='admin_add_event')],
        [InlineKeyboardButton("🔧 Управление мероприятиями", callback_data='admin_manage')],
        [InlineKeyboardButton("📋 Все мероприятия", callback_data='admin_list_events_btn')],
        [InlineKeyboardButton("📊 Статистика", callback_data='admin_stats_btn')],
        [InlineKeyboardButton("📥 Скачать общую таблицу", callback_data='admin_table_btn')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "👑 *Админ-панель*\n\n"
        "Выберите действие для управления волонтерскими мероприятиями:"
    )
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# ========== ИСПРАВЛЕННЫЕ ФУНКЦИИ КНОПОК ==========
async def admin_add_event_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки добавления мероприятия (из админ-панели)"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    await query.edit_message_text(
        "📝 *Добавление нового мероприятия*\n\n"
        "Отправьте данные в формате:\n\n"
        "`Название, Описание, Дата (ГГГГ-ММ-ДД), Время (ЧЧ:ММ), Место, Макс. участников`\n\n"
        "*Пример:*\n"
        "`Уборка парка, Субботник в центральном парке, 2024-04-10, 14:00, Центральный парк, 30`\n\n"
        "📌 *Примечания:*\n"
        "- Дата в формате ГГГГ-ММ-ДД\n"
        "- Время в формате ЧЧ:ММ\n"
        "- Макс. участников: число или 0 для неограниченного\n"
        "- Описание не обязательно\n\n"
        "Для отмены отправьте /cancel",
        parse_mode='Markdown'
    )
    
    context.user_data['adding_event'] = True

async def admin_list_events_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки списка мероприятий"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    events = get_all_events_admin()
    
    if not events:
        text = "📭 Нет мероприятий."
    else:
        text = "📋 *Все мероприятия:*\n\n"
        for event in events:
            event_id, title, date, time, location, max_vol, desc, is_active, registration_open, registered = event
            status = "✅ Активно" if is_active == 1 else "❌ Неактивно"
            reg_status = "✅ Открыта" if registration_open == 1 else "❌ Закрыта"
            max_text = f"{max_vol}" if max_vol > 0 else "∞"
            
            text += f"🆔 *{event_id}*\n"
            text += f"🎯 *{title}*\n"
            text += f"   📅 {date} ⏰ {time}\n"
            if location:
                text += f"   📍 {location}\n"
            text += f"   👥 {registered}/{max_text} записей\n"
            text += f"   🏷️ Статус: {status}\n"
            text += f"   📝 Запись: {reg_status}\n\n"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад в админ-панель", callback_data='admin_back')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_stats_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки статистики"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    # Статистика из БД
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM users")
    users_count = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM events WHERE is_active = 1")
    active_events = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM events WHERE is_active = 0")
    inactive_events = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM events WHERE registration_open = 1 AND is_active = 1")
    open_events = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM registrations")
    regs_count = cur.fetchone()[0]
    
    # Популярные мероприятия
    cur.execute('''
        SELECT events.title, COUNT(registrations.id) as count
        FROM events
        LEFT JOIN registrations ON events.id = registrations.event_id
        WHERE events.is_active = 1
        GROUP BY events.id
        ORDER BY count DESC
        LIMIT 5
    ''')
    popular_events = cur.fetchall()
    
    conn.close()
    
    # Формируем текст
    text = "👑 *Статистика для админа*\n\n"
    text += f"👥 Пользователей: {users_count}\n"
    text += f"📅 Всего мероприятий: {active_events + inactive_events}\n"
    text += f"   ✅ Активных: {active_events}\n"
    text += f"   ❌ Неактивных: {inactive_events}\n"
    text += f"   📝 С открытой записью: {open_events}\n"
    text += f"📝 Всего записей: {regs_count}\n"
    text += f"📊 Записей в CSV: {count_csv_lines()}\n\n"
    
    text += "🔥 *Самые популярные мероприятия:*\n"
    for title, count in popular_events:
        text += f"• {title}: {count} записей\n"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад в админ-панель", callback_data='admin_back')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_table_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки скачивания общей таблицы"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    if not os.path.exists(CSV_FILE):
        await query.edit_message_text("❌ Таблица еще не создана.")
        return
    
    try:
        with open(CSV_FILE, 'rb') as f:
            await context.bot.send_document(
                chat_id=query.from_user.id,
                document=f,
                filename=f'волонтеры_{datetime.now().strftime("%Y-%m-%d")}.csv',
                caption=f"📊 Общая таблица волонтеров\nВсего записей: {count_csv_lines()}"
            )
        
        # Возвращаемся к админ-панели
        keyboard = [[InlineKeyboardButton("◀️ Назад в админ-панель", callback_data='admin_back')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "✅ Общая таблица отправлена вам в личные сообщения!",
            reply_markup=reply_markup
        )
        
        print(f"✅ Общая таблица отправлена админу {ADMIN_ID}")
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка при отправке таблицы: {e}")

async def admin_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в админ-панель"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить мероприятие", callback_data='admin_add_event')],
        [InlineKeyboardButton("🔧 Управление мероприятиями", callback_data='admin_manage')],
        [InlineKeyboardButton("📋 Все мероприятия", callback_data='admin_list_events_btn')],
        [InlineKeyboardButton("📊 Статистика", callback_data='admin_stats_btn')],
        [InlineKeyboardButton("📥 Скачать общую таблицу", callback_data='admin_table_btn')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "👑 *Админ-панель*\n\n"
        "Выберите действие для управления волонтерскими мероприятиями:"
    )
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# ========== ОБРАБОТЧИК СООБЩЕНИЙ ДЛЯ ДОБАВЛЕНИЯ МЕРОПРИЯТИЙ ==========
async def handle_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает сообщения от админа для добавления мероприятий"""
    # Проверяем, что это админ и он в режиме добавления мероприятия
    if update.effective_user.id != ADMIN_ID:
        return
    
    if context.user_data.get('adding_event'):
        await save_new_event(update, context)
    else:
        # Если сообщение не связано с добавлением мероприятия, игнорируем
        pass

# ========== ОБРАБОТЧИК ОШИБОК ==========
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    try:
        raise context.error
    except Exception as e:
        print(f"⚠️ Ошибка: {e}")
        
        # Отправляем сообщение админу об ошибке
        if ADMIN_ID:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"⚠️ Ошибка в боте: {type(e).__name__}: {e}"
                )
            except:
                pass
    
    return ConversationHandler.END

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========
def main():
    print("=" * 50)
    print("🤖 Волонтерский бот запускается...")
    print(f"👑 Админ ID: {ADMIN_ID}")
    print(f"💾 База данных: {DB_NAME}")
    print(f"📊 CSV таблица: {CSV_FILE}")
    print("=" * 50)
    
    # Инициализируем БД и CSV
    init_db()
    init_csv()
    
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Создаем ConversationHandler для редактирования данных
    edit_info_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_info_start, pattern='^edit_info$')],
        states={
            EDITING_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_user_info)],
        },
        fallbacks=[CommandHandler('cancel', cancel_command)]
    )
    
    # Создаем ConversationHandler для добавления мероприятий (из команд)
    add_event_handler = ConversationHandler(
        entry_points=[CommandHandler('addevent', admin_add_event)],
        states={
            ADDING_EVENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_event)],
        },
        fallbacks=[CommandHandler('cancel', cancel_command)]
    )
    
    # Создаем ConversationHandler для редактирования мероприятий
    edit_event_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_event_field_start, pattern='^edit_field_')],
        states={
            EDIT_EVENT_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_event_field)],
        },
        fallbacks=[CommandHandler('cancel', cancel_command)]
    )
    
    # Создаем ConversationHandler для записи с комментарием
    register_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(register_for_event, pattern='^register_')],
        states={
            ADDING_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_registration_with_comment)],
        },
        fallbacks=[CommandHandler('cancel', cancel_command)]
    )
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("events", admin_list_events))
    application.add_handler(CommandHandler("table", admin_table))
    application.add_handler(CommandHandler("stats", admin_stats))
    
    # Регистрируем ConversationHandlers
    application.add_handler(edit_info_handler)
    application.add_handler(add_event_handler)
    application.add_handler(edit_event_handler)
    application.add_handler(register_handler)
    
    # Регистрируем обработчики callback-запросов (ОБЫЧНЫЕ)
    application.add_handler(CallbackQueryHandler(list_events, pattern='^list_events$'))
    application.add_handler(CallbackQueryHandler(event_detail, pattern='^event_'))
    application.add_handler(CallbackQueryHandler(cancel_registration, pattern='^cancel_reg_'))
    application.add_handler(CallbackQueryHandler(my_info, pattern='^my_info$'))
    application.add_handler(CallbackQueryHandler(my_registrations, pattern='^my_registrations$'))
    application.add_handler(CallbackQueryHandler(main_menu, pattern='^main_menu$'))
    
    # Админ обработчики кнопок
    application.add_handler(CallbackQueryHandler(admin_add_event_btn, pattern='^admin_add_event$'))
    application.add_handler(CallbackQueryHandler(admin_manage_events, pattern='^admin_manage$'))
    application.add_handler(CallbackQueryHandler(admin_list_events_btn, pattern='^admin_list_events_btn$'))
    application.add_handler(CallbackQueryHandler(admin_stats_btn, pattern='^admin_stats_btn$'))
    application.add_handler(CallbackQueryHandler(admin_table_btn, pattern='^admin_table_btn$'))
    application.add_handler(CallbackQueryHandler(admin_back, pattern='^admin_back$'))
    
    # ОТДЕЛЬНЫЕ обработчики для управления мероприятиями
    application.add_handler(CallbackQueryHandler(manage_event, pattern='^manage_'))
    application.add_handler(CallbackQueryHandler(toggle_registration_handler, pattern='^toggle_reg_'))
    application.add_handler(CallbackQueryHandler(toggle_active_handler, pattern='^toggle_active_'))
    application.add_handler(CallbackQueryHandler(download_event_handler, pattern='^download_event_'))
    application.add_handler(CallbackQueryHandler(delete_event_handler, pattern='^delete_'))
    application.add_handler(CallbackQueryHandler(confirm_delete_handler, pattern='^confirm_delete_'))
    application.add_handler(CallbackQueryHandler(view_event_participants, pattern='^view_'))
    application.add_handler(CallbackQueryHandler(edit_event_start, pattern='^edit_'))
    
    # Обработчик сообщений для добавления мероприятий из кнопок
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.User(user_id=ADMIN_ID),
        handle_admin_message
    ))
    
    print("✅ Бот запущен и ожидает сообщений...")
    print("=" * 50)
    
    # Запускаем бота с параметрами для Railway
    try:
        print("🔄 Запускаем бота с параметрами для Railway...")
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
            close_loop=False
        )
    except KeyboardInterrupt:
        print("🛑 Бот остановлен пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()