import sqlite3
import telebot
from telebot import types
import datetime
import schedule
import time
from threading import Thread
import requests
from config import ADMIN_CHAT_ID, bot

conn = sqlite3.connect('events.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS events (event_id INTEGER PRIMARY KEY, description TEXT, organizer_link TEXT, end_time TEXT)''')
conn.commit()

def check_and_delete_events():
    """ Удаление мероприятий, время которых истекло """
    cursor.execute("SELECT event_id, end_time, organizer_link FROM events")
    current_time = datetime.datetime.now()
    for event_id, end_time_str, organizer_link in cursor.fetchall():
        end_time = datetime.datetime.strptime(end_time_str, '%Y-%m-%d %H:%M:%S')
        if current_time >= end_time:
            if organizer_link.startswith('@'):
                try:
                    user_info = bot.get_chat(organizer_link)
                    user_id = user_info.id
                except Exception as e:
                    user_id = None
                    print(f"Не удалось получить информацию о пользователе {organizer_link}: {e}")
            else:
                prefix = 'tg://user?id='
                user_id = int(organizer_link[len(prefix):]) if organizer_link.startswith(prefix) else None
            
            cursor.execute("DELETE FROM events WHERE event_id = ?", (event_id,))
            conn.commit()
            
            # Уведомление администратора
            bot.send_message(ADMIN_CHAT_ID, f"Мероприятие с ID {event_id} было автоматически удалено, так как его время истекло.")

            # Уведомление пользователя, если его ID известен
            if user_id:
                bot.send_message(user_id, f"Ваше мероприятие с ID {event_id} было автоматически удалено, так как его время истекло.")
            else:
                print(f"Не удалось отправить сообщение пользователю {organizer_link} о удалении мероприятия с ID {event_id}.")

def schedule_checker():
    """ Функция для запуска планировщика в отдельном потоке """
    while True:
        schedule.run_pending()
        time.sleep(1)

# Настраиваем планировщик для ежеминутной проверки
schedule.every().minute.do(check_and_delete_events)
Thread(target=schedule_checker).start()

@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("👋 Создать мероприятие")
    btn2 = types.KeyboardButton("❓ Список мероприятия")
    btn3 = types.KeyboardButton("🗑 Удалить мероприятие")
    btn4 = types.KeyboardButton("👑 Поддержка")
    btn5 = types.KeyboardButton("📄 Мои мероприятия")
    markup.add(btn1, btn2, btn3, btn5, btn4)
    bot.send_message(message.chat.id, text=f"Привет, {message.from_user.first_name}! Я бот для поиска и создания мероприятиий", reply_markup=markup)
    
@bot.message_handler(commands=['help'])
def help(message):
    bot.reply_to(message, "Доступные команды:\n/start - начало работы\n")

def send_to_admin(message):
    user = message.from_user
    
    if message.text in ["👋 Создать мероприятие", "❓ Список мероприятия", "🗑 Удалить мероприятие", "👑 Поддержка", "📄 Мои мероприятия"]:
        handle_text(message)
    else:
        if user.username:
            user_mention = f"@{user.username}" 
        else:
            user_mention = f'<a href="tg://user?id={user.id}">{user.first_name}</a>' 
    
        text_to_admin = (f"Новое сообщение от пользователя {user_mention} (ID {user.id}):\n"
                         f"{message.text}")
    
        bot.send_message(chat_id=ADMIN_CHAT_ID, text=text_to_admin, parse_mode='HTML')
        bot.send_message(message.chat.id, "Сообщение отправлено")
    
def add_event_description(message):
    if message.text in ["👋 Создать мероприятие", "❓ Список мероприятия", "🗑 Удалить мероприятие", "👑 Поддержка", "📄 Мои мероприятия"]:
        return handle_text(message)
    user_id = message.from_user.id
    organizer_link = f"@{message.from_user.username}" if message.from_user.username else f"tg://user?id={user_id}"
    
    if user_id != ADMIN_CHAT_ID:
        cursor.execute("SELECT COUNT(*) FROM events WHERE organizer_link = ?", (organizer_link,))
        event_count = cursor.fetchone()[0]
        if event_count >= 3:
            bot.send_message(message.chat.id, 'У Вас уже есть 3 активных мероприятия. Нельзя создать больше. Если необходимость есть, то пишите в "👑 Поддержку"')
            return start(message)
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    cancel_button = types.KeyboardButton("Отмена")
    markup.add(cancel_button)
    
    bot.send_message(
        message.chat.id,
        "Введите время начала мероприятия в формате ГГГГ-ММ-ДД ЧЧ:ММ:СС (например, 2024-05-20 18:30:00).",
        reply_markup=markup
    )
    bot.register_next_step_handler(message, add_event_time, message.text)

def add_event_time(message, description):
    if message.text == "Отмена":
        bot.send_message(message.chat.id, "Создание мероприятия отменено.", reply_markup=types.ReplyKeyboardRemove())
        return start(message)
    
    try:
        end_time = datetime.datetime.strptime(message.text, '%Y-%m-%d %H:%M:%S')
        current_time = datetime.datetime.now()
        
        if end_time <= current_time:
            bot.send_message(message.chat.id, "Время начала мероприятия должно быть в будущем. Попробуйте снова.")
            return bot.register_next_step_handler(message, add_event_time, description)
        
        user_id = message.from_user.id
        organizer_link = f"@{message.from_user.username}" if message.from_user.username else f"tg://user?id={user_id}"
        
        cursor.execute("INSERT INTO events (description, organizer_link, end_time) VALUES (?, ?, ?)", 
                       (description, organizer_link, message.text))
        conn.commit()
        
        bot.send_message(message.chat.id, "Мероприятие успешно добавлено", reply_markup=types.ReplyKeyboardRemove())
        return start(message)
    
    except ValueError:
        bot.send_message(message.chat.id, "Неправильный формат времени. Пожалуйста, введите время в правильном формате ГГГГ-ММ-ДД ЧЧ:ММ:СС.")
        return bot.register_next_step_handler(message, add_event_time, description)
    
    except ValueError:
        bot.send_message(message.chat.id, "Неправильный формат времени. Пожалуйста, введите время в правильном формате ГГГГ-ММ-ДД ЧЧ:ММ:СС.")
        bot.register_next_step_handler(message, add_event_time, description)

@bot.message_handler(commands=['events'])
def get_events(message):
    current_time = datetime.datetime.now()
    cursor.execute("SELECT * FROM events")
    events = cursor.fetchall()
    
    if events:
        response = "Текущее время: {}\n\nСписок текущих мероприятий:\n".format(current_time.strftime("%Y-%m-%d %H:%M:%S"))
        for event in events:
            event_id, description, organizer_link, end_time = event
            response += f"Мероприятие ID: {event_id}\nОписание: {description}\nОрганизатор: {organizer_link}\nНачало: {end_time}\n\n"
        bot.send_message(message.chat.id, response)
    else:
        bot.send_message(message.chat.id, "Нет добавленных мероприятий")

@bot.message_handler(commands=['delete_event'])
def delete_event_command(message):
    user_id = message.from_user.id
    if user_id == ADMIN_CHAT_ID:       
        reply_markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        cancel_button = types.KeyboardButton("Отмена")
        reply_markup.add(cancel_button)

        msg = bot.send_message(message.chat.id, "Выберите ID мероприятия для удаления или нажмите 'Отмена':", reply_markup=reply_markup)
        bot.register_next_step_handler(msg, delete_event, user_id)
    else:
        if message.from_user.username:
            organizer_link = f"@{message.from_user.username}"
        else:
            organizer_link = f"tg://user?id={user_id}"
        
        cursor.execute("SELECT event_id, description FROM events WHERE organizer_link = ?", (organizer_link,))
        user_events = cursor.fetchall()
        
        if user_events:
            reply_markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            for event in user_events:
                event_button = types.KeyboardButton(str(event[0]))
                reply_markup.add(event_button)
            
            cancel_button = types.KeyboardButton("Отмена")
            reply_markup.add(cancel_button)

            msg = bot.send_message(message.chat.id, "Выберите ID мероприятия для удаления или нажмите 'Отмена':", reply_markup=reply_markup)
            bot.register_next_step_handler(msg, delete_event, user_id)
        else:
            bot.send_message(message.chat.id, "У вас нет мероприятий, которые можно удалить.")

@bot.message_handler(commands=['send_message'])
def start_sending_message(message):
    if message.chat.id == ADMIN_CHAT_ID: 
        msg = bot.send_message(message.chat.id, "Введите ID пользователя, которому хотите отправить сообщение:")
        bot.register_next_step_handler(msg, get_user_id)
    else:
        bot.send_message(message.chat.id, "У вас нет прав для использования этой команды.")

def get_user_id(message):
    if message.text.isdigit():
        user_id = int(message.text)
        msg = bot.send_message(message.chat.id, "Введите текст сообщения:")
        bot.register_next_step_handler(msg, send_user_message, user_id)
    else:
        bot.send_message(message.chat.id, "ID пользователя должен быть числом. Попробуйте ещё раз.")
        return

def send_user_message(message, user_id):
    try:
        bot.send_message(user_id, message.text)
        bot.send_message(ADMIN_CHAT_ID, f"Сообщение успешно отправлено пользователю с ID {user_id}.")
    except Exception as e:
        bot.send_message(ADMIN_CHAT_ID, f"Ошибка при отправке сообщения пользователю с ID {user_id}: {str(e)}")

def delete_event(message, user_id):
    if message.text == "Отмена":
        start(message)
        return

    try:
        event_id = int(message.text.strip())

        if user_id == ADMIN_CHAT_ID:
            cursor.execute("DELETE FROM events WHERE event_id = ?", (event_id,))
            if cursor.rowcount > 0:
                conn.commit()
                bot.send_message(message.chat.id, f"Мероприятие с ID {event_id} удалено.")
            else:
                bot.send_message(message.chat.id, "Мероприятие не найдено.")
        else:
            if message.from_user.username:
                organizer_link = f"@{message.from_user.username}"
            else:
                organizer_link = f"tg://user?id={user_id}"

            cursor.execute("SELECT * FROM events WHERE event_id = ? AND organizer_link = ?", (event_id, organizer_link))
            if cursor.fetchone():
                cursor.execute("DELETE FROM events WHERE event_id = ? AND organizer_link = ?", (event_id, organizer_link))
                conn.commit()
                bot.send_message(message.chat.id, f"Ваше мероприятие с ID {event_id} удалено.")
            else:
                bot.send_message(message.chat.id, "Вы не можете удалить это мероприятие или оно не существует.")
        
        start(message)

    except ValueError:
        bot.send_message(message.chat.id, "Пожалуйста, введите корректный ID мероприятия.")
    except Exception as e:
        bot.send_message(message.chat.id, f"Произошла ошибка: {str(e)}")
        
def my_events(message):
    user_id = message.from_user.id
    if message.from_user.username:
        organizer_link = f"@{message.from_user.username}"
    else:
        organizer_link = f"tg://user?id={user_id}"
    
    cursor.execute("SELECT event_id, description, end_time FROM events WHERE organizer_link = ?", (organizer_link,))
    events = cursor.fetchall()
    
    if not events:
        bot.send_message(message.chat.id, "У вас нет созданных мероприятий.")
        return
    
    response = "Ваши мероприятия:\n"
    for event_id, description, end_time in events:
        response += f"ID: {event_id}, Описание: {description}, Начало: {end_time}\n"
    
    bot.send_message(message.chat.id, response)
    

@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.text == "👋 Создать мероприятие":
        bot.send_message(message.chat.id, text="Привет! Напишите описание мероприятия.")
        bot.register_next_step_handler(message, add_event_description)
    elif message.text == "❓ Список мероприятия":
        get_events(message)
    elif message.text == "🗑 Удалить мероприятие":
        delete_event_command(message)
    elif message.text == "👑 Поддержка":
        bot.send_message(message.chat.id, "Если есть вопросы, пожелания или просто хочется поговорить, то я жду Вашего сообщения.")
        bot.register_next_step_handler(message, send_to_admin)
    elif message.text == "📄 Мои мероприятия":
        my_events(message)
    else:
        bot.send_message(message.chat.id, "Не понял команду, попробуйте ещё раз или используйте /start для начала работы.")

if __name__ == "__main__":
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except requests.exceptions.ReadTimeout:
            print("Произошла ошибка ReadTimeout — переподключение через 5 секунд")
            time.sleep(5)
        except KeyboardInterrupt:
            print("Бот остановлен вручную")
            break
        except Exception as e:
            print(f"Непредвиденная ошибка: {e}")
            time.sleep(5)