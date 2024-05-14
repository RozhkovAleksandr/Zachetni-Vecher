import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.filters import Text
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils import executor

# Настройки
API_TOKEN = 'YOUR_TOKEN'  # Токен вашего бота
ADMIN_ID = 123456789  # Ваш ID в Telegram для администрирования

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Инициализация базы данных
conn = sqlite3.connect('events.db')
cursor = conn.cursor()

# Создание таблиц в базе данных
cursor.execute('''
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    creator_id INTEGER,
    status TEXT DEFAULT 'pending'
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS participants (
    event_id INTEGER,
    user_id INTEGER,
    PRIMARY KEY (event_id, user_id),
    FOREIGN KEY (event_id) REFERENCES events(id)
)
''')
conn.commit()

# Команды
@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    await message.reply("Добро пожаловать в бот мероприятий!\n"
                        "Команды:\n"
                        "/create_event - Создать новое мероприятие\n"
                        "/list_events - Список доступных мероприятий\n"
                        "/my_events - Список мероприятий, в которых вы участвуете")

@dp.message_handler(commands=['create_event'])
async def create_event(message: types.Message):
    await message.reply("Введите название нового мероприятия:")
    dp.register_message_handler(get_event_name, state='awaiting_event_name')

async def get_event_name(message: types.Message):
    event_name = message.text
    await message.reply("Введите описание мероприятия:")
    dp.register_message_handler(get_event_description, state='awaiting_event_description', event_name=event_name)

async def get_event_description(message: types.Message, event_name):
    event_description = message.text
    cursor.execute('INSERT INTO events (name, description, creator_id) VALUES (?, ?, ?)',
                   (event_name, event_description, message.from_user.id))
    conn.commit()
    await message.reply("Ваше мероприятие отправлено на модерацию.")

    # Уведомление администратора
    event_id = cursor.lastrowid
    await bot.send_message(ADMIN_ID, f"Новое мероприятие на модерацию:\n\n"
                                     f"Название: {event_name}\n"
                                     f"Описание: {event_description}\n"
                                     f"Создатель: {message.from_user.mention}\n"
                                     f"/approve_{event_id} - Одобрить\n"
                                     f"/reject_{event_id} - Отклонить")

@dp.message_handler(Text(startswith='/approve_'))
async def approve_event(message: types.Message):
    event_id = int(message.text.split('_')[1])
    cursor.execute('UPDATE events SET status = ? WHERE id = ?', ('approved', event_id))
    conn.commit()
    cursor.execute('SELECT name, creator_id FROM events WHERE id = ?', (event_id,))
    event = cursor.fetchone()
    await message.answer(f"Мероприятие '{event[0]}' одобрено.")
    await bot.send_message(event[1], f"Ваше мероприятие '{event[0]}' одобрено!")

@dp.message_handler(Text(startswith='/reject_'))
async def reject_event(message: types.Message):
    event_id = int(message.text.split('_')[1])
    cursor.execute('SELECT name, creator_id FROM events WHERE id = ?', (event_id,))
    event = cursor.fetchone()
    cursor.execute('DELETE FROM events WHERE id = ?', (event_id,))
    conn.commit()
    await message.answer(f"Мероприятие '{event[0]}' отклонено.")
    await bot.send_message(event[1], f"Ваше мероприятие '{event[0]}' отклонено.")

@dp.message_handler(commands=['list_events'])
async def list_events(message: types.Message):
    cursor.execute('SELECT id, name, description FROM events WHERE status = "approved"')
    events = cursor.fetchall()
    if not events:
        await message.reply("Нет доступных мероприятий.")
        return

    for event in events:
        event_id, name, description = event
        keyboard = InlineKeyboardMarkup().add(
            InlineKeyboardButton(f"Присоединиться к '{name}'", callback_data=f'join_{event_id}')
        )
        await message.reply(f"Название: {name}\nОписание: {description}", reply_markup=keyboard)


@dp.callback_query_handler(Text(startswith='join_'))
async def join_event(callback_query: types.CallbackQuery):
    event_id = int(callback_query.data.split('_')[1])
    user_id = callback_query.from_user.id

    # Проверка, что пользователь уже не присоединился к мероприятию
    cursor.execute('SELECT * FROM participants WHERE event_id = ? AND user_id = ?', (event_id, user_id))
    if cursor.fetchone():
        await callback_query.answer('Вы уже участвуете в этом мероприятии.')
        return

    # Присоединение пользователя к мероприятию
    cursor.execute('INSERT INTO participants (event_id, user_id) VALUES (?, ?)', (event_id, user_id))
    conn.commit()
    await callback_query.answer('Вы успешно присоединились к мероприятию!')
    cursor.execute('SELECT name FROM events WHERE id = ?', (event_id,))
    event_name = cursor.fetchone()[0]
    await bot.send_message(user_id, f"Вы присоединились к мероприятию '{event_name}'.")

@dp.message_handler(commands=['my_events'])
async def my_events(message: types.Message):
    user_id = message.from_user.id
    cursor.execute('''
        SELECT e.name, e.description
        FROM participants p
        JOIN events e ON e.id = p.event_id
        WHERE p.user_id = ? AND e.status = "approved"
    ''', (user_id,))
    events = cursor.fetchall()
    if not events:
        await message.reply("Вы не участвуете ни в одном мероприятии.")
    else:
        response = "Ваши мероприятия:\n\n"
        for event in events:
            name, description = event
            response += f"Название: {name}\nОписание: {description}\n\n"
        await message.reply(response)

@dp.message_handler(Text(startswith='/delete_'))
async def delete_event_by_admin(message: types.Message):
    event_id = int(message.text.split('_')[1])
    cursor.execute('SELECT name, creator_id FROM events WHERE id = ?', (event_id,))
    event = cursor.fetchone()
    if event:
        cursor.execute('DELETE FROM events WHERE id = ?', (event_id,))
        cursor.execute('DELETE FROM participants WHERE event_id = ?', (event_id,))
        conn.commit()
        await message.answer(f"Мероприятие '{event[0]}' удалено.")
        await bot.send_message(event[1], f"Ваше мероприятие '{event[0]}' было удалено администратором.")
    else:
        await message.answer("Мероприятие не найдено.")

@dp.message_handler(commands=['list_pending'])
async def list_pending_events(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("Эта команда доступна только администратору.")
        return

    cursor.execute('SELECT id, name, description FROM events WHERE status = "pending"')
    pending_events = cursor.fetchall()
    if not pending_events:
        await message.reply("Нет ожидающих одобрения мероприятий.")
    else:
        for event in pending_events:
            event_id, name, description = event
            await message.reply(f"Название: {name}\nОписание: {description}\n\n"
                                f"/approve_{event_id} - Одобрить\n"
                                f"/reject_{event_id} - Отклонить\n"
                                f"/delete_{event_id} - Удалить")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)