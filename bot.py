import os
import sys
import sqlite3
import csv
import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ========== ПРОВЕРКА НА ОДИН ЭКЗЕМПЛЯР ==========
def check_single_instance():
    """Проверяет, что запущен только один экземпляр бота"""
    lock_file = '/tmp/bot.lock'
    
    # Проверяем существование lock файла
    if os.path.exists(lock_file):
        try:
            # Читаем PID из файла
            with open(lock_file, 'r') as f:
                old_pid = int(f.read().strip())
            
            # Проверяем, жив ли процесс
            try:
                os.kill(old_pid, 0)  # Процесс существует
                print(f"❌ Бот уже запущен с PID {old_pid}. Останавливаем...")
                return False
            except OSError:
                # Процесс умер, удаляем старый lock файл
                os.remove(lock_file)
                print(f"⚠️ Удален старый lock файл от умершего процесса {old_pid}")
        except:
            # Ошибка чтения файла, удаляем его
            if os.path.exists(lock_file):
                os.remove(lock_file)
    
    # Создаем новый lock файл
    with open(lock_file, 'w') as f:
        f.write(str(os.getpid()))
    
    # Удаляем lock файл при выходе
    import atexit
    atexit.register(lambda: os.remove(lock_file) if os.path.exists(lock_file) else None)
    
    return True

# ========== НАСТРОЙКИ ==========
TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
ADMIN_ID = 123456789  # ⬅️ ЗАМЕНИТЕ НА ВАШ TELEGRAM ID!

if TOKEN == 'YOUR_BOT_TOKEN_HERE':
    raise ValueError("❌ Токен бота не найден! Установите BOT_TOKEN в Railway")

DB_NAME = "volunteer_bot.db"
CSV_FILE = "volunteers.csv"

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
            is_active BOOLEAN DEFAULT 1
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
                'Статус записи'
            ])
        print(f"✅ Создан CSV файл: {CSV_FILE}")

def save_to_csv(user_data, event_data):
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
    """Считает количество записей в CSV"""
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            return sum(1 for line in f) - 1
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
    """Показывает список активных мероприятий"""
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
            "📭 *На данный момент нет активных мероприятий.*\n\n"
            "Загляните позже!",
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
    events_text = "📅 *Доступные мероприятия:*\n\n"
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

async def edit_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрашивает данные пользователя"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "✏️ *Заполните ваши данные*\n\n"
        "Отправьте сообщение в формате:\n\n"
        "`ФИО, Группа, Дата рождения (ДД.ММ.ГГГГ), Телефон, @username`\n\n"
        "*Пример:*\n"
        "`Иванов Иван Иванович, ИВТ-20-1, 15.05.2000, +79161234567, @ivanov`\n\n"
        "📌 *Все поля обязательны для записи на мероприятия.*\n"
        "📌 *Данные сохранятся и не нужно будет вводить их заново.*",
        parse_mode='Markdown'
    )
    
    context.user_data['awaiting_info'] = True

async def save_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняет данные пользователя"""
    if context.user_data.get('awaiting_info'):
        text = update.message.text.strip()
        
        # Проверяем отмену
        if text.lower() == '/cancel':
            context.user_data['awaiting_info'] = False
            await update.message.reply_text("✅ Заполнение данных отменено.")
            return
        
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
                        "Пример: 15.05.2000"
                    )
                    return
                
                # Проверяем username
                if not username.startswith('@'):
                    await update.message.reply_text(
                        "❌ Username должен начинаться с @\n"
                        "Пример: @ivanov"
                    )
                    return
                
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
        else:
            await update.message.reply_text(
                "❌ *Неверный формат!*\n\n"
                "Пожалуйста, отправьте данные в формате:\n"
                "`ФИО, Группа, Дата рождения, Телефон, @username`\n\n"
                "Пример:\n"
                "`Иванов Иван Иванович, ИВТ-20-1, 15.05.2000, +79161234567, @ivanov`",
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
    cur.execute('SELECT full_name, group_name, birth_date, phone_number, username FROM users WHERE telegram_id = ?', (user_id,))
    user = cur.fetchone()
    
    if not user:
        await query.edit_message_text("❌ Ваши данные не найдены. Пожалуйста, сначала заполните данные.")
        conn.close()
        return
    
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
        
        await query.edit_message_text(
            f"❌ *Не хватает данных для записи:*\n• {', '.join(missing)}\n\n"
            f"Пожалуйста, заполните данные перед записью.",
            reply_markup=InlineKeyboardMarkup(keyboard)
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
    cur.execute('SELECT COUNT(*) FROM registrations WHERE event_id = ?', (event_id,))
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
        'birth_date': birth_date,
        'phone': phone,
        'username': username
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
        return
    
    await update.message.reply_text(
        "📝 *Добавление нового мероприятия*\n\n"
        "Отправьте данные в формате:\n\n"
        "`Название, Дата (ГГГГ-ММ-ДД), Время (ЧЧ:ММ), Место, Макс. участников`\n\n"
        "*Пример:*\n"
        "`Уборка парка, 2024-04-10, 14:00, Центральный парк, 30`\n\n"
        "📌 *Примечания:*\n"
        "- Дата в формате ГГГГ-ММ-ДД\n"
        "- Время в формате ЧЧ:ММ\n"
        "- Макс. участников: число или 0 для неограниченного\n"
        "- Для отмены отправьте /cancel",
        parse_mode='Markdown'
    )
    
    context.user_data['adding_event'] = True

async def save_new_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняет новое мероприятие из сообщения"""
    if context.user_data.get('adding_event'):
        text = update.message.text.strip()
        
        if text.lower() == '/cancel':
            context.user_data['adding_event'] = False
            await update.message.reply_text("❌ Добавление мероприятия отменено.")
            return
        
        parts = [part.strip() for part in text.split(',')]
        
        if len(parts) >= 5:
            try:
                title = parts[0]
                date = parts[1]
                time = parts[2]
                location = parts[3]
                max_volunteers = int(parts[4]) if parts[4].isdigit() else 0
                description = parts[5] if len(parts) > 5 else ""
                
                # Проверяем формат даты
                try:
                    datetime.strptime(date, '%Y-%m-%d')
                except ValueError:
                    await update.message.reply_text("❌ Неверный формат даты! Используйте ГГГГ-ММ-ДД")
                    return
                
                # Проверяем формат времени
                try:
                    datetime.strptime(time, '%H:%M')
                except ValueError:
                    await update.message.reply_text("❌ Неверный формат времени! Используйте ЧЧ:ММ")
                    return
                
                # Сохраняем в БД
                conn = sqlite3.connect(DB_NAME)
                cur = conn.cursor()
                cur.execute('''
                    INSERT INTO events (title, description, date, time, location, max_volunteers, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                ''', (title, description, date, time, location, max_volunteers))
                event_id = cur.lastrowid
                conn.commit()
                conn.close()
                
                # Формируем ответ
                text = (
                    "✅ *Мероприятие добавлено!*\n\n"
                    f"🎯 *Название:* {title}\n"
                    f"📅 *Дата:* {date}\n"
                    f"⏰ *Время:* {time}\n"
                    f"📍 *Место:* {location}\n"
                    f"👥 *Макс. участников:* {max_volunteers if max_volunteers > 0 else 'не ограничено'}\n"
                )
                
                if description:
                    text += f"📝 *Описание:* {description}\n"
                
                text += f"\n🆔 *ID мероприятия:* {event_id}"
                
                await update.message.reply_text(text, parse_mode='Markdown')
                
                print(f"✅ Добавлено мероприятие: {title} (ID: {event_id})")
                
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {e}")
        
        context.user_data['adding_event'] = False

async def admin_list_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список мероприятий админу"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ У вас нет прав доступа.")
        return
    
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        SELECT id, title, date, time, location, max_volunteers, is_active,
               (SELECT COUNT(*) FROM registrations WHERE event_id = events.id) as registered
        FROM events
        ORDER BY date, time
    ''')
    events = cur.fetchall()
    conn.close()
    
    if not events:
        text = "📭 Нет мероприятий."
    else:
        text = "📋 *Все мероприятия:*\n\n"
        for event in events:
            event_id, title, date, time, location, max_vol, is_active, registered = event
            status = "✅ Активно" if is_active else "❌ Неактивно"
            max_text = f"{max_vol}" if max_vol > 0 else "∞"
            
            text += f"🆔 *{event_id}* - {status}\n"
            text += f"🎯 *{title}*\n"
            text += f"   📅 {date} ⏰ {time}\n"
            if location:
                text += f"   📍 {location}\n"
            text += f"   👥 {registered}/{max_text} записей\n\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

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
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /cancel"""
    if 'adding_event' in context.user_data:
        context.user_data['adding_event'] = False
        await update.message.reply_text("✅ Добавление мероприятия отменено.")
    elif 'awaiting_info' in context.user_data:
        context.user_data['awaiting_info'] = False
        await update.message.reply_text("✅ Заполнение данных отменено.")
    else:
        await update.message.reply_text("❌ Нечего отменять.")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-панель"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ У вас нет прав доступа.")
        return
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить мероприятие", callback_data='admin_add_event_btn')],
        [InlineKeyboardButton("📋 Все мероприятия", callback_data='admin_list_events_btn')],
        [InlineKeyboardButton("📊 Статистика", callback_data='admin_stats_btn')],
        [InlineKeyboardButton("📥 Скачать таблицу", callback_data='admin_download_btn')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "👑 *Админ-панель*\n\n"
        "Выберите действие для управления волонтерскими мероприятиями:"
    )
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# ========== ИСПРАВЛЕННЫЕ ФУНКЦИИ КНОПОК ==========
async def admin_add_event_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки добавления мероприятия"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    # Правильный вызов
    update_obj = Update(update_id=update.update_id, callback_query=query)
    await admin_add_event(update_obj, context)

async def admin_list_events_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки списка мероприятий"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    update_obj = Update(update_id=update.update_id, callback_query=query)
    await admin_list_events(update_obj, context)

async def admin_stats_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки статистики"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    update_obj = Update(update_id=update.update_id, callback_query=query)
    await admin_stats(update_obj, context)

async def admin_download_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки скачивания таблицы"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    update_obj = Update(update_id=update.update_id, callback_query=query)
    await admin_table(update_obj, context)

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
    
    return

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========
def main():
    # Проверяем, что запущен только один экземпляр
    if not check_single_instance():
        print("❌ Обнаружено несколько экземпляров бота. Останавливаем...")
        sys.exit(1)
    
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
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("addevent", admin_add_event))
    application.add_handler(CommandHandler("events", admin_list_events))
    application.add_handler(CommandHandler("table", admin_table))
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("cancel", cancel_command))
    
    # Регистрируем обработчики callback-запросов
    application.add_handler(CallbackQueryHandler(list_events, pattern='^list_events$'))
    application.add_handler(CallbackQueryHandler(event_detail, pattern='^event_'))
    application.add_handler(CallbackQueryHandler(register_for_event, pattern='^register_'))
    application.add_handler(CallbackQueryHandler(cancel_registration, pattern='^cancel_'))
    application.add_handler(CallbackQueryHandler(my_info, pattern='^my_info$'))
    application.add_handler(CallbackQueryHandler(edit_info, pattern='^edit_info$'))
    application.add_handler(CallbackQueryHandler(my_registrations, pattern='^my_registrations$'))
    application.add_handler(CallbackQueryHandler(main_menu, pattern='^main_menu$'))
    
    # Админ обработчики кнопок
    application.add_handler(CallbackQueryHandler(admin_add_event_btn, pattern='^admin_add_event_btn$'))
    application.add_handler(CallbackQueryHandler(admin_list_events_btn, pattern='^admin_list_events_btn$'))
    application.add_handler(CallbackQueryHandler(admin_stats_btn, pattern='^admin_stats_btn$'))
    application.add_handler(CallbackQueryHandler(admin_download_btn, pattern='^admin_download_btn$'))
    
    # Обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_user_info))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_event))
    
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