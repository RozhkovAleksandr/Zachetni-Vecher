import sqlite3
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ParseMode
from aiogram.dispatcher.filters import Text
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Настройки
API_TOKEN = '7063035298:AAGWZFZhS6b216kdQZVM41smvkMAGMDfwzw'
ADMIN_ID = 1147185372  # Замените на ID администратора

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
                        "/list_events - Список доступных мероприятий")

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
    await bot.send_message(ADMIN_ID, f"Новое мероприятие на модерацию:\n\n"
                                     f"Название: {event_name}\n"
                                     f"Описание: {event_description}\n"
                                     f"Создатель: {message.from_user.mention}\n"
                                     f"/approve_{cursor.lastrowid} - Одобрить\n"
                                     f"/reject_{cursor.lastrowid} - Отклонить")

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
    cursor.execute('SELECT id, name, description FROM events