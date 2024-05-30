import logging
import os
from datetime import datetime
import io

import telebot
from telebot import types
import yadisk

# Логирование
logging.basicConfig(level=logging.INFO)

# Токены Telegram бота и Яндекс Диска
TELEGRAM_TOKEN = ""
YANDEX_TOKEN = ""

# Создание экземпляра Yandex.Disk API
y = yadisk.YaDisk(token=YANDEX_TOKEN)

# Проверка токена
if not y.check_token():
    raise ValueError("Неверный токен Яндекс Диска")

# Создание бота
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Словарь для хранения выбранных пользователем папок для загрузки файлов
user_folders = {}


# --- Обработчик команды /start ---
@bot.message_handler(commands=['start'])
def start_command(message):
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    markup.row("🔍 Поиск", "📁 Каталог")
    markup.row("❓ FAQ")
    msg = bot.send_message(message.chat.id, "Привет! Я бот для сохранения файлов на Яндекс Диск.", reply_markup=markup)
    bot.register_next_step_handler(msg, process_folder_choice)


def process_folder_choice(message):
    folder = message.text.strip()
    if folder == "🔍 Поиск":
        search_command(message)
    elif folder == "📁 Каталог":
        catalog_command(message)
    elif folder == "❓ FAQ":
        faq_command(message)
    else:
        user_folders[message.chat.id] = folder
        bot.send_message(message.chat.id, f"Папка для загрузки файлов установлена: {folder}")
        bot.send_message(message.chat.id, "Теперь отправьте файл, который вы хотите загрузить в эту папку.")

# --- Обработчик любого файла ---
@bot.message_handler(content_types=['document'])
def handle_file(message):
    user_id = message.chat.id
    file_id = message.document.file_id
    file_info = bot.get_file(file_id)
    file_name = message.document.file_name

    folder = user_folders.get(user_id)


    try:
        # Проверяем существование папки на Яндекс Диске (для корневого каталога не нужно)
        if folder and not y.exists(f"/{folder}"): 
            y.mkdir(f"/{folder}")

        # Загрузка файла на Яндекс Диск
        file_data = bot.download_file(file_info.file_path)
        
        # Строим правильный путь для корневого каталога и подкаталогов
        if folder:
            upload_path = f"/{folder}/{file_name}" 
        else:
            upload_path = file_name  # Только имя файла для корневого каталога

        y.upload(io.BytesIO(file_data), upload_path)
        bot.send_message(user_id, f"Файл '{file_name}' успешно сохранен в {'корневом каталоге' if not folder else f'папке \'{folder}\''} на Яндекс Диск.")
    except Exception as e:
        logging.error(f"Произошла ошибка при сохранении файла: {e}")
        bot.send_message(user_id, f"Произошла ошибка при сохранении файла. Попробуйте позже.")

# --- Обработчик команды /catalog ---
@bot.message_handler(commands=['catalog'])
def catalog_command(message):
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    markup.add("Отмена")
    markup.add("Корневой каталог")
    try:
        folders = y.listdir("/")
        for folder in folders:
            markup.add(folder['name'])
    except Exception as e:
        logging.error(f"Произошла ошибка при получении списка папок: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка при получении списка папок. Попробуйте позже.")
        return
    msg = bot.send_message(message.chat.id, "Выберите папку:", reply_markup=markup)
    bot.register_next_step_handler(msg, process_catalog_choice)


def process_catalog_choice(message):
    folder = message.text.strip()
    if folder == "Отмена":
        start_command(message)  # Возвращаемся к начальному состоянию
        return
    elif folder == "Корневой каталог":
        user_folders[message.chat.id] = ""
    else:
        user_folders[message.chat.id] = folder
    bot.send_message(message.chat.id, f"Выбран каталог: {folder}")
    bot.send_message(message.chat.id, "Теперь отправьте файл, который вы хотите загрузить в эту папку.")



# --- Обработчик команды /search ---
@bot.message_handler(commands=['search'])
def search_command(message):
    user_id = message.chat.id
    folder = user_folders.get(user_id)
    if folder:
        msg = bot.send_message(message.chat.id, "Введите имя файла для поиска:")
        bot.register_next_step_handler(msg, process_search)
    else:
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
        markup.add("Да", "Нет")
        msg = bot.send_message(message.chat.id, "Вы не выбрали каталог для поиска файлов. Хотите выполнить поиск в корневом каталоге?", reply_markup=markup)
        bot.register_next_step_handler(msg, process_root_search)


def process_root_search(message):
    if message.text.lower() == "да":
        user_folders[message.chat.id] = ""  # Пустая строка означает корневой каталог
        process_search(message)  # Запускаем поиск
    else:
        bot.send_message(message.chat.id, "Ок, выполнение поиска отменено.")


def process_search(message):
    query = message.text
    user_id = message.chat.id
    folder = user_folders.get(user_id)

    try:
        if not folder:  # Если каталог не выбран, ищем в корневом каталоге
            files = y.listdir("/")
        else:
            files = y.listdir(f"/{folder}")

        search_results = [file for file in files if query.lower() in file["name"].lower()]

        if search_results:
            if len(search_results) == 1:
                file = search_results[0]
                if not folder:  # Если был выбран корневой каталог, просто используем имя файла
                    direct_link = y.get_download_link(file["name"])
                else:
                    direct_link = y.get_download_link(f"/{folder}/{file['name']}")
                bot.send_message(message.chat.id, f"Найден файл: {direct_link}")
            else:
                file_list = "\n".join([f"- {file['name']} ({file['path']})" for file in search_results])
                bot.send_message(message.chat.id, f"Найдено несколько файлов:\n{file_list}")
        else:
            bot.send_message(message.chat.id, "Файлы не найдены.")
    except Exception as e:
        logging.error(f"Произошла ошибка при поиске файлов: {e}")
        bot.send_message(message.chat.id, f"Произошла ошибка при поиске файлов. Попробуйте позже.")


# --- Обработчик команды /faq ---
@bot.message_handler(commands=['faq'])
def faq_command(message):
    faq_text = """
    Список часто задаваемых вопросов (FAQ):
    1. Как загрузить файл на Яндекс Диск?
    Ответ: Просто отправьте файл в чат, и он будет загружен в текущую выбранную папку.
    
    2. Как найти файл на Яндекс Диске?
    Ответ: Используйте команду /search, чтобы выполнить поиск по файлам в выбранной папке.
    
    3. Как изменить текущий каталог для загрузки файлов?
    Ответ: Используйте команду /catalog, чтобы выб
рать другой каталог.
    """
    bot.send_message(message.chat.id, faq_text)


# --- Запуск бота ---
if __name__ == '__main__':
    bot.polling(none_stop=True)
