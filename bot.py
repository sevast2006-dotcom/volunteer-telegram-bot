# ========== АДМИН: ДОБАВЛЕНИЕ МЕРОПРИЯТИЙ ==========
async def admin_add_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса добавления мероприятия"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ У вас нет прав доступа.")
        return
    
    await update.message.reply_text(
        "📝 *Добавление нового мероприятия*\n\n"
        "Отправьте данные в формате:\n\n"
        "`Название, Дата (ГГГГ-ММ-ДД), Время (ЧЧ:ММ), Место, Макс. участников, Описание`\n\n"
        "*Пример:*\n"
        "`Уборка парка, 2024-04-10, 14:00, Центральный парк, 30, Общеуниверситетский субботник`\n\n"
        "📌 *Примечания:*\n"
        "- Дата в формате ГГГГ-ММ-ДД\n"
        "- Время в формате ЧЧ:ММ\n"
        "- Макс. участников: число или 0 для неограниченного\n"
        "- Описание можно пропустить\n"
        "- Для отмены отправьте /cancel",
        parse_mode='Markdown'
    )
    
    # Устанавливаем состояние ожидания данных мероприятия
    context.user_data['adding_event'] = True

async def save_new_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняет новое мероприятие из сообщения"""
    if context.user_data.get('adding_event'):
        text = update.message.text.strip()
        
        # Проверяем отмену
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
                from datetime import datetime
                try:
                    datetime.strptime(date, '%Y-%m-%d')
                except ValueError:
                    await update.message.reply_text(
                        "❌ Неверный формат даты! Используйте ГГГГ-ММ-ДД\n"
                        "Пример: 2024-04-10"
                    )
                    return
                
                # Проверяем формат времени
                try:
                    datetime.strptime(time, '%H:%M')
                except ValueError:
                    await update.message.reply_text(
                        "❌ Неверный формат времени! Используйте ЧЧ:ММ\n"
                        "Пример: 14:00"
                    )
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
                
                keyboard = [
                    [InlineKeyboardButton("📝 Добавить еще", callback_data='admin_add_event_btn')],
                    [InlineKeyboardButton("📋 Список мероприятий", callback_data='admin_list_events')],
                    [InlineKeyboardButton("🏠 В админ-панель", callback_data='admin_panel')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                
                print(f"✅ Добавлено мероприятие: {title} (ID: {event_id})")
                
            except ValueError as e:
                await update.message.reply_text(
                    f"❌ Ошибка в данных: {e}\n\n"
                    "Проверьте правильность ввода:\n"
                    "- Дата: ГГГГ-ММ-ДД\n"
                    "- Время: ЧЧ:ММ\n"
                    "- Макс. участников: число\n\n"
                    "Попробуйте снова или отправьте /cancel для отмены."
                )
                return
            except Exception as e:
                await update.message.reply_text(
                    f"❌ Ошибка при сохранении: {e}\n\n"
                    "Попробуйте снова или отправьте /cancel для отмены."
                )
                return
        else:
            await update.message.reply_text(
                "❌ Недостаточно данных! Нужно минимум 5 полей:\n\n"
                "`Название, Дата, Время, Место, Макс. участников`\n\n"
                "Попробуйте снова или отправьте /cancel для отмены.",
                parse_mode='Markdown'
            )
            return
        
        # Сбрасываем состояние
        context.user_data['adding_event'] = False

async def admin_list_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список всех мероприятий админу"""
    if update.message:
        user_id = update.effective_user.id
        query = None
    else:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
    
    if user_id != ADMIN_ID:
        if query:
            await query.edit_message_text("⛔ У вас нет прав доступа.")
        else:
            await update.message.reply_text("⛔ У вас нет прав доступа.")
        return
    
    # Получаем все мероприятия
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
    
    # Создаем кнопки управления
    keyboard = [
        [InlineKeyboardButton("➕ Добавить мероприятие", callback_data='admin_add_event_btn')],
        [InlineKeyboardButton("✏️ Редактировать", callback_data='admin_edit_events')],
        [InlineKeyboardButton("📊 Статистика", callback_data='admin_stats')],
        [InlineKeyboardButton("🏠 В админ-панель", callback_data='admin_panel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if query:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_edit_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает мероприятия для редактирования"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("⛔ У вас нет прав доступа.")
        return
    
    # Получаем активные мероприятия
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        SELECT id, title, date FROM events 
        WHERE date >= date('now')
        ORDER BY date
    ''')
    events = cur.fetchall()
    conn.close()
    
    if not events:
        await query.edit_message_text("📭 Нет активных мероприятий для редактирования.")
        return
    
    # Создаем кнопки для каждого мероприятия
    keyboard = []
    for event_id, title, date in events:
        button_text = f"{title[:20]}... ({date})" if len(title) > 20 else f"{title} ({date})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f'edit_event_{event_id}')])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='admin_list_events')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "✏️ *Выберите мероприятие для редактирования:*",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def edit_event_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает детали мероприятия для редактирования"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    try:
        event_id = int(query.data.split('_')[2])
    except:
        await query.edit_message_text("❌ Ошибка: неверный ID мероприятия")
        return
    
    # Получаем информацию о мероприятии
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT title, description, date, time, location, max_volunteers, is_active FROM events WHERE id = ?', (event_id,))
    event = cur.fetchone()
    conn.close()
    
    if not event:
        await query.edit_message_text("❌ Мероприятие не найдено.")
        return
    
    title, desc, date, time, location, max_vol, is_active = event
    
    text = f"✏️ *Редактирование мероприятия*\n\n"
    text += f"🆔 ID: {event_id}\n"
    text += f"🎯 Название: {title}\n"
    text += f"📅 Дата: {date}\n"
    text += f"⏰ Время: {time}\n"
    text += f"📍 Место: {location if location else 'Не указано'}\n"
    text += f"👥 Макс. участников: {max_vol if max_vol > 0 else 'не ограничено'}\n"
    if desc:
        text += f"📝 Описание: {desc}\n"
    text += f"📊 Статус: {'✅ Активно' if is_active else '❌ Неактивно'}\n\n"
    
    # Кнопки действий
    keyboard = [
        [InlineKeyboardButton("✅ Активировать", callback_data=f'activate_{event_id}')],
        [InlineKeyboardButton("❌ Деактивировать", callback_data=f'deactivate_{event_id}')],
        [InlineKeyboardButton("🗑️ Удалить", callback_data=f'delete_{event_id}')],
        [InlineKeyboardButton("🔙 К списку", callback_data='admin_edit_events')],
        [InlineKeyboardButton("🏠 В админ-панель", callback_data='admin_panel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def toggle_event_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Активирует/деактивирует мероприятие"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    try:
        if query.data.startswith('activate_'):
            event_id = int(query.data.split('_')[1])
            new_status = 1
            action = "активировано"
        elif query.data.startswith('deactivate_'):
            event_id = int(query.data.split('_')[1])
            new_status = 0
            action = "деактивировано"
        else:
            return
    except:
        await query.answer("❌ Ошибка", show_alert=True)
        return
    
    # Обновляем статус
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('UPDATE events SET is_active = ? WHERE id = ?', (new_status, event_id))
    conn.commit()
    
    # Получаем название для сообщения
    cur.execute('SELECT title FROM events WHERE id = ?', (event_id,))
    title = cur.fetchone()[0]
    conn.close()
    
    await query.answer(f"✅ Мероприятие '{title}' {action}", show_alert=True)
    
    # Возвращаемся к редактированию
    query.data = f'edit_event_{event_id}'
    await edit_event_detail(update, context)

async def delete_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаляет мероприятие"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    try:
        event_id = int(query.data.split('_')[1])
    except:
        await query.answer("❌ Ошибка", show_alert=True)
        return
    
    # Получаем информацию о мероприятии перед удалением
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT title FROM events WHERE id = ?', (event_id,))
    result = cur.fetchone()
    
    if not result:
        await query.answer("❌ Мероприятие не найдено", show_alert=True)
        conn.close()
        return
    
    title = result[0]
    
    # Проверяем, есть ли записи на мероприятие
    cur.execute('SELECT COUNT(*) FROM registrations WHERE event_id = ?', (event_id,))
    registrations_count = cur.fetchone()[0]
    
    if registrations_count > 0:
        await query.answer(
            f"❌ Нельзя удалить! На мероприятии {registrations_count} записей",
            show_alert=True
        )
        conn.close()
        return
    
    # Удаляем мероприятие
    cur.execute('DELETE FROM events WHERE id = ?', (event_id,))
    conn.commit()
    conn.close()
    
    await query.answer(f"✅ Мероприятие '{title}' удалено", show_alert=True)
    await admin_list_events(update, context)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-панель с кнопками"""
    if update.message:
        user_id = update.effective_user.id
        query = None
    else:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
    
    if user_id != ADMIN_ID:
        if query:
            await query.edit_message_text("⛔ У вас нет прав доступа.")
        else:
            await update.message.reply_text("⛔ У вас нет прав доступа.")
        return
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить мероприятие", callback_data='admin_add_event_btn')],
        [InlineKeyboardButton("📋 Все мероприятия", callback_data='admin_list_events')],
        [InlineKeyboardButton("📊 Статистика", callback_data='admin_stats')],
        [InlineKeyboardButton("📥 Скачать таблицу", callback_data='admin_download')],
        [InlineKeyboardButton("👥 Участники мероприятий", callback_data='admin_participants')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "👑 *Админ-панель*\n\n"
        "Выберите действие для управления волонтерскими мероприятиями:"
    )
    
    if query:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_add_event_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки добавления мероприятия"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    # Вызываем функцию добавления мероприятия
    await admin_add_event(Update(message=query.message), context)

async def admin_participants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает участников мероприятий"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    # Получаем мероприятия с участниками
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        SELECT events.id, events.title, events.date,
               COUNT(registrations.id) as participants_count
        FROM events
        LEFT JOIN registrations ON events.id = registrations.event_id
        WHERE events.date >= date('now')
        GROUP BY events.id
        ORDER BY events.date
    ''')
    events = cur.fetchall()
    conn.close()
    
    if not events:
        text = "📭 Нет активных мероприятий с участниками."
    else:
        text = "👥 *Участники мероприятий:*\n\n"
        for event_id, title, date, count in events:
            text += f"🎯 *{title}*\n"
            text += f"   📅 {date}\n"
            text += f"   👥 Участников: {count}\n"
            text += f"   📋 Список: /participants_{event_id}\n\n"
    
    keyboard = [
        [InlineKeyboardButton("📋 Все мероприятия", callback_data='admin_list_events')],
        [InlineKeyboardButton("🏠 В админ-панель", callback_data='admin_panel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_participants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает участников конкретного мероприятия"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ У вас нет прав доступа.")
        return
    
    try:
        # Извлекаем ID мероприятия из команды
        command = update.message.text
        if command.startswith('/participants_'):
            event_id = int(command.split('_')[1])
        else:
            return
    except:
        await update.message.reply_text("❌ Неверный формат команды")
        return
    
    # Получаем информацию о мероприятии
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT title, date FROM events WHERE id = ?', (event_id,))
    event = cur.fetchone()
    
    if not event:
        await update.message.reply_text("❌ Мероприятие не найдено.")
        conn.close()
        return
    
    title, date = event
    
    # Получаем участников
    cur.execute('''
        SELECT users.telegram_id, users.full_name, users.group_name, users.phone_number
        FROM registrations
        JOIN users ON registrations.user_id = users.telegram_id
        WHERE registrations.event_id = ?
        ORDER BY users.full_name
    ''', (event_id,))
    participants = cur.fetchall()
    conn.close()
    
    if not participants:
        text = f"📭 На мероприятии *{title}* ({date}) пока нет участников."
    else:
        text = f"👥 *Участники мероприятия:*\n🎯 *{title}*\n📅 *{date}*\n\n"
        
        for i, (tg_id, full_name, group_name, phone) in enumerate(participants, 1):
            text += f"{i}. *{full_name}*\n"
            text += f"   Группа: {group_name if group_name else 'Не указана'}\n"
            text += f"   Телефон: {phone if phone else 'Не указан'}\n"
            text += f"   Telegram ID: {tg_id}\n\n"
        
        text += f"📊 Всего участников: {len(participants)}"
    
    await update.message.reply_text(text, parse_mode='Markdown')

# ========== ОБНОВЛЕННЫЙ MAIN ==========
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
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("addevent", admin_add_event))
    application.add_handler(CommandHandler("events", admin_list_events))
    application.add_handler(CommandHandler("table", admin_table))
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("cancel", cancel_command))
    
    # Команды для просмотра участников
    application.add_handler(MessageHandler(
        filters.Regex(r'^/participants_\d+$'), 
        show_participants
    ))
    
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
    
    # Админ обработчики
    application.add_handler(CallbackQueryHandler(admin_panel, pattern='^admin_panel$'))
    application.add_handler(CallbackQueryHandler(admin_add_event_btn, pattern='^admin_add_event_btn$'))
    application.add_handler(CallbackQueryHandler(admin_list_events, pattern='^admin_list_events$'))
    application.add_handler(CallbackQueryHandler(admin_edit_events, pattern='^admin_edit_events$'))
    application.add_handler(CallbackQueryHandler(edit_event_detail, pattern='^edit_event_'))
    application.add_handler(CallbackQueryHandler(toggle_event_status, pattern='^(activate|deactivate)_'))
    application.add_handler(CallbackQueryHandler(delete_event, pattern='^delete_'))
    application.add_handler(CallbackQueryHandler(admin_download_callback, pattern='^admin_download$'))
    application.add_handler(CallbackQueryHandler(admin_stats, pattern='^admin_stats$'))
    application.add_handler(CallbackQueryHandler(admin_participants, pattern='^admin_participants$'))
    
    # Обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_user_info))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_event))
    
    print("✅ Бот запущен и ожидает сообщений...")
    print("=" * 50)
    
    # Запускаем бота
    application.run_polling()

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

if __name__ == "__main__":
    main()