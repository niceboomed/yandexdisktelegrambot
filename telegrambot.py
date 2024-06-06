import logging
import os
from datetime import datetime
import io

import telebot
from telebot import types
import yadisk
import ftplib

# Логирование
logging.basicConfig(level=logging.INFO)

# Токены Telegram бота и Яндекс Диска
TELEGRAM_TOKEN = ""
YANDEX_TOKEN = ""

# Данные для FTP-сервера 
FTP_HOST = ""
FTP_USER = ""
FTP_PASSWORD = ""

# Создание экземпляра Yandex.Disk API
y = yadisk.YaDisk(token=YANDEX_TOKEN)

# Проверка токена Яндекс Диска
if not y.check_token():
    raise ValueError("Неверный токен Яндекс Диска")

# Создание бота
bot = telebot.TeleBot(TELEGRAM_TOKEN)


# Словарь для хранения настроек пользователей
user_settings = {}

# --- Функция для инициализации настроек пользователя ---
def init_user_settings(chat_id):
    if chat_id not in user_settings:
        user_settings[chat_id] = {
            'storage': 'yadisk',  # По умолчанию - Яндекс Диск
            'folder': ''  # По умолчанию - корневой каталог
        }
# --- Функция для возврата в главное меню ---
def return_to_main_menu(chat_id):
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.row("Поиск 🔍", "Каталог 📁")
    markup.row("Настройки ⚙️", "FAQ ❓")
    bot.send_message(chat_id, "Выберите действие:", reply_markup=markup)

# --- Обработчик команды /start ---
@bot.message_handler(commands=['start'])
def start_command(message):
    # Инициализация настроек пользователя
    user_settings[message.chat.id] = {
        'storage': 'yadisk',  # По умолчанию - Яндекс Диск
        'folder': ''  # По умолчанию - корневой каталог
    }
    return_to_main_menu(message.chat.id)

# --- Обработчик текстовых сообщений (для кнопок) ---
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    chat_id = message.chat.id
    text = message.text

    if text == "Поиск 🔍":
        search_command(message)
    elif text == "Каталог 📁":
        catalog_command(message)
    elif text == "Настройки ⚙️":
        settings_command(message)
    elif text == "FAQ ❓":
        faq_command(message)
    else:
        bot.send_message(chat_id, "Некорректная команда. Пожалуйста, используйте кнопки ниже.")
        return_to_main_menu(chat_id)

# --- Обработчик команды /settings ---
@bot.message_handler(commands=['settings'])
def settings_command(message):
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.row("Яндекс Диск", "FTP")
    msg = bot.send_message(message.chat.id, "Выберите место для хранения файлов:", reply_markup=markup)
    bot.register_next_step_handler(msg, process_storage_choice)

def process_storage_choice(message):
    chat_id = message.chat.id
    if message.text is None:
        bot.send_message(chat_id, "Некорректный выбор. Пожалуйста, выберите заново.")
        return settings_command(message)

    storage = message.text.strip()
    current_storage = user_settings.get(chat_id, {}).get('storage')

    if storage == "Яндекс Диск":
        if current_storage == 'yadisk':
            bot.send_message(chat_id, "Вы уже используете Яндекс Диск в качестве хранилища.")
        else:
            user_settings[chat_id]['storage'] = 'yadisk'
            bot.send_message(chat_id, "Хранилище установлено: Яндекс Диск")
    elif storage == "FTP":
        if current_storage == 'ftp':
            bot.send_message(chat_id, "Вы уже используете FTP в качестве хранилища.")
        else:
            user_settings[chat_id]['storage'] = 'ftp'
            bot.send_message(chat_id, "Хранилище установлено: FTP")
    else:
        bot.send_message(chat_id, "Некорректный выбор. Пожалуйста, выберите заново.")
        return settings_command(message)

    return_to_main_menu(chat_id)

# --- Обработчик любого файла ---
@bot.message_handler(content_types=['document'])
def handle_file(message):
    user_id = message.chat.id
    file_id = message.document.file_id
    file_info = bot.get_file(file_id)
    file_name = message.document.file_name

    storage = user_settings[user_id]['storage']
    folder = user_settings[user_id]['folder']

    try:
        if storage == 'yadisk':
            # --- Логика загрузки на Яндекс Диск ---
            if folder and not y.exists(f"/{folder}"):
                y.mkdir(f"/{folder}")

            file_data = bot.download_file(file_info.file_path)
            upload_path = f"/{folder}/{file_name}" if folder else file_name
            y.upload(io.BytesIO(file_data), upload_path)
            bot.send_message(user_id, f"Файл '{file_name}' успешно сохранен в {'корневом каталоге' if not folder else f'папке \'{folder}\''} на Яндекс Диск.")

        elif storage == 'ftp':
            # --- Логика загрузки на FTP-сервер ---
            with ftplib.FTP(FTP_HOST, FTP_USER, FTP_PASSWORD) as ftp:
                if folder:
                    try:
                        ftp.cwd(folder)
                    except ftplib.error_perm:
                        # Создание каталога если не существует
                        ftp.mkd(folder)
                        ftp.cwd(folder)

                file_data = bot.download_file(file_info.file_path)
                ftp.storbinary(f'STOR {file_name}', io.BytesIO(file_data))
                bot.send_message(user_id, f"Файл '{file_name}' успешно сохранен в {'корневом каталоге' if not folder else f'папке \'{folder}\''} на FTP-сервер.")
        else:
            bot.send_message(user_id, "Ошибка: не выбран способ хранения.")
    except Exception as e:
        logging.error(f"Произошла ошибка при сохранении файла: {e}")
        bot.send_message(user_id, f"Произошла ошибка при сохранении файла. Попробуйте позже.")

    return_to_main_menu(user_id)

# --- Обработчик команды /catalog ---
@bot.message_handler(commands=['catalog'])
def catalog_command(message):
    storage = user_settings[message.chat.id]['storage']
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    markup.add("Отмена")
    markup.add("Корневой каталог")

    if storage == 'yadisk':
        try:
            folders = y.listdir("/")
            for folder in folders:
                if folder['type'] == 'dir':
                    markup.add(folder['name'])
        except Exception as e:
            logging.error(f"Произошла ошибка при получении списка папок: {e}")
            bot.send_message(message.chat.id, "Произошла ошибка при получении списка папок. Попробуйте позже.")
            return

    elif storage == 'ftp':
        try:
            with ftplib.FTP(FTP_HOST, FTP_USER, FTP_PASSWORD) as ftp:
                folders = []
                ftp.retrlines('LIST', folders.append)
                for folder in folders:
                    parts = folder.split()
                    if parts[0].startswith('d'):
                        folder_name = parts[-1]
                        markup.add(folder_name)
        except Exception as e:
            logging.error(f"Произошла ошибка при получении списка папок на FTP: {e}")
            bot.send_message(message.chat.id, "Произошла ошибка при получении списка папок на FTP. Попробуйте позже.")
            return
    else:
        bot.send_message(message.chat.id, "Ошибка: не выбран способ хранения.")
        return

    msg = bot.send_message(message.chat.id, "Выберите папку или напишите название новой:", reply_markup=markup)
    bot.register_next_step_handler(msg, process_catalog_choice)

def process_catalog_choice(message):
    if message.text is None:
        bot.send_message(message.chat.id, "Некорректный выбор. Пожалуйста, выберите заново.")
        return catalog_command(message)

    folder = message.text.strip()
    if folder == "Отмена":
        return_to_main_menu(message.chat.id)
        return
    elif folder == "Корневой каталог":
        user_settings[message.chat.id]['folder'] = ""
    else:
        user_settings[message.chat.id]['folder'] = folder

    bot.send_message(message.chat.id, f"Выбран каталог: {folder}")
    bot.send_message(message.chat.id, "Теперь отправьте файл, который вы хотите загрузить в эту папку.")
    return_to_main_menu(message.chat.id)


# --- Обработчик команды /search ---
@bot.message_handler(commands=['search'])
def search_command(message):
    user_id = message.chat.id
    storage = user_settings[user_id]['storage']
    folder = user_settings[user_id]['folder']

    if storage == 'yadisk':
        msg = bot.send_message(message.chat.id, "Введите имя файла для поиска:")
        bot.register_next_step_handler(msg, process_search_yadisk)

    elif storage == 'ftp':
        msg = bot.send_message(message.chat.id, "Введите имя файла для поиска везде:")
        bot.register_next_step_handler(msg, process_search_ftp)

    else:
        bot.send_message(user_id, "Ошибка: не выбран способ хранения.")
        return_to_main_menu(user_id)

# Поиска файла на Яндекс Диске
def process_search_yadisk(message):
    query = message.text
    user_id = message.chat.id

    try:
        search_path = user_settings[user_id]['folder']
        search_results = search_yadisk_recursive(search_path, query)
        if search_results:
            response_text = "Найдены файлы:\n"
            for file in search_results:
                path = file["path"]
                download_link = y.get_download_link(path)
                response_text += f"- {file['name']} ({path})\nСсылка: {download_link}\n\n"
            bot.send_message(user_id, response_text)
        else:
            bot.send_message(user_id, "Файлы не найдены.")
    except Exception as e:
        logging.error(f"Произошла ошибка при поиске файлов на Яндекс Диске: {e}")
        bot.send_message(user_id, f"Произошла ошибка при поиске файлов на Яндекс Диске. Попробуйте позже.")
    return_to_main_menu(user_id)

# Рекурсивный поиск на Яндекс Диске
def search_yadisk_recursive(folder, query):
    all_files = []
    files = y.listdir(folder)
    for file in files:
        if file['type'] == 'dir':
            all_files.extend(search_yadisk_recursive(file['path'], query))
        elif query.lower() in file['name'].lower():
            all_files.append(file)
    return all_files

# Функция для поиска файла на FTP
def process_search_ftp(message):
    query = message.text
    user_id = message.chat.id

    try:
        with ftplib.FTP(FTP_HOST, FTP_USER, FTP_PASSWORD) as ftp:
            search_results = search_ftp_recursive(ftp, query)

            if search_results:
                for file in search_results:
                    file_name = file.split("/")[-1]  # Получаем имя файла с расширением
                    with io.BytesIO() as file_data:
                        ftp.retrbinary(f"RETR {file}", file_data.write)
                        file_data.seek(0)
                        with open(file_name, 'wb') as f:
                            f.write(file_data.getvalue())
                        bot.send_document(user_id, open(file_name, 'rb'))
            else:
                bot.send_message(message.chat.id, "Файлы не найдены.")
    except Exception as e:
        logging.error(f"Произошла ошибка при поиске файлов на FTP: {e}")
        bot.send_message(message.chat.id, f"Произошла ошибка при поиске файлов на FTP. Попробуйте позже.")
    return_to_main_menu(user_id)

# Функция для рекурсивного поиска на FTP
def search_ftp_recursive(ftp, query, folder="/"):
    all_files = []
    files = ftp.nlst(folder)
    for file in files:
        if "." not in file:  # if it's a folder
            all_files.extend(search_ftp_recursive(ftp, query, f"{folder}/{file}"))
        elif query.lower() in file.lower():
            all_files.append(f"{folder}/{file}")
    return all_files

# --- Обработчик команды /faq ---
@bot.message_handler(commands=['faq'])
def faq_command(message):
    faq_text = """
    Список часто задаваемых вопросов (FAQ):
    1. Как загрузить файл?
    Ответ: Просто отправьте файл в чат, и он будет загружен в текущую выбранную папку.
    
    2. Как найти файл?
    Ответ: Используйте команду /search, чтобы выполнить поиск по файлам в выбранной папке.
    
    3. Как изменить текущий каталог для загрузки файлов?
    Ответ: Используйте команду /catalog, чтобы выбрать другой каталог.
    
    4. Как изменить хранилище (Яндекс Диск или FTP)?
    Ответ: Используйте команду /settings для настройки хранилища.
    """
    bot.send_message(message.chat.id, faq_text)
    return_to_main_menu(message.chat.id)

# --- Запуск бота ---
if __name__ == '__main__':
    bot.polling(none_stop=True)
