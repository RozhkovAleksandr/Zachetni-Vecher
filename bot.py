import sqlite3
import telebot
from telebot import types

bot = telebot.TeleBot('7063035298:AAGWZFZhS6b216kdQZVM41smvkMAGMDfwzw')
ADMIN_CHAT_ID = 1147185372

conn = sqlite3.connect('events.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS events (event_id INTEGER PRIMARY KEY, description TEXT, organizer_link TEXT)''')
conn.commit()

@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("👋 Создать мероприятие")
    btn2 = types.KeyboardButton("❓ Посмотреть мероприятия")
    btn3 = types.KeyboardButton("👑 Поддержка")
    markup.add(btn1, btn2, btn3)
    bot.send_message(message.chat.id, text="Привет, {0.first_name}! Я бот для создания мероприятия. Пока тестовый вариант. Если что не понятно, пиши /help".format(message.from_user), reply_markup=markup)
    
@bot.message_handler(commands=['help'])
def help(message):
    bot.reply_to(message, "Доступные команды:\n/start - начало работы\n/delete_event - удалить мероприятие (только для админа)")  
    

def send_to_admin(message):
    user_id = message.from_user.id
    bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"Новое сообщение от пользователя с ID {user_id}:\n{message.text}")
    bot.send_message(message.chat.id, "Сообщение отправлено")
    
def add_event(message):
    event_description = message.text
    user = message.from_user
    if user.username:
        organizer_link = f"@{user.username}"
    else:
        organizer_link = f"tg://user?id={user.id}"
    
    cursor.execute("INSERT INTO events (description, organizer_link) VALUES (?, ?)", (event_description, organizer_link))
    conn.commit()
    bot.send_message(message.chat.id, "Мероприятие успешно добавлено")
    
    
@bot.message_handler(commands=['events'])
def get_events(message):
    cursor.execute("SELECT * FROM events")
    events = cursor.fetchall()
    if events:
        for event in events:
            event_id, description, organizer_link = event
            bot.send_message(ADMIN_CHAT_ID, f"Мероприятие ID: {event_id}\n Описание: {description}\n Организатор: {organizer_link}")
    else:
        bot.send_message(ADMIN_CHAT_ID, "Нет добавленных мероприятий")
        
@bot.message_handler(commands=['delete_event'])
def delete_event_command(message):
    if message.chat.id == ADMIN_CHAT_ID:
        msg = bot.send_message(message.chat.id, "Введите ID мероприятия, которое нужно удалить:")
        bot.register_next_step_handler(msg, delete_event)
    else:
        bot.send_message(message.chat.id, "Эта команда доступна только администратору.")

def delete_event(message):
    try:
        event_id = int(message.text)
        cursor.execute("DELETE FROM events WHERE event_id = ?", (event_id,))
        conn.commit()
        bot.send_message(ADMIN_CHAT_ID, f"Мероприятие с ID {event_id} удалено.")
    except ValueError:
        bot.send_message(message.chat.id, "Пожалуйста, введите корректный ID мероприятия.")
    except Exception as e:
        bot.send_message(message.chat.id, f"Произошла ошибка при удалении мероприятия: {e}")        


@bot.message_handler(content_types=['text'])
def func(message):
    if(message.text == "👋 Создать мероприятие"):
        if message.from_user.username:
            organizer_link = f"@{message.from_user.username}"
        else:
            organizer_link = f"tg://user?id={message.from_user.id}"
        cursor.execute("SELECT COUNT(*) FROM events WHERE organizer_link = ?", (organizer_link,))
        count = cursor.fetchone()[0]
        
        if count < 2 or message.from_user.id == ADMIN_CHAT_ID:
            bot.send_message(message.chat.id, text="Привет! Напишите описание мероприятия. \n Распиши следующее: дата и время мероприятия, что будет")
            bot.register_next_step_handler(message, add_event)
        else:
            bot.send_message(message.chat.id, "Вы уже добавили максимальное количество мероприятий")
    elif message.text == "❓ Посмотреть мероприятия":
        get_events(message)
    
    elif message.text == "👑 Поддержка":
        bot.send_message(message.chat.id, "Если есть вопросы, пожелания или просто хочется поговорить, то я жду Вашего сообщения")
        bot.register_next_step_handler(message, send_to_admin)
        
    
    else:

        bot.send_message(message.chat.id, "Не понял команду")

bot.polling(none_stop=True)