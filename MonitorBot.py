import time
import json
import feedparser
from datetime import datetime
import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from bs4 import BeautifulSoup
import logging
import re
import os
import threading

# Telegram bot configuration
telegram_bot_token = '7241698952:AAF_-xoUSOVmJHSaJE_9d1--OUBqzZKTo6o'
deepl_api_key = 'd5ac1cce-be7b-470f-a54e-2e62afdfdf37:fx'

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Path to the URL storage file
url_file_path = os.path.expanduser("~root/LaoNewsTG/urls.json")

# List of URLs to monitor
urls = {}

# Dictionary to store chat IDs
chat_ids = {}

# Function to load URLs from the file
def load_urls():
    global urls
    if os.path.exists(url_file_path):
        with open(url_file_path, 'r') as file:
            urls.update(json.load(file))
    else:
        urls.update({})

# Function to save URLs to the file
def save_urls():
    with open(url_file_path, 'w') as file:
        json.dump(urls, file)

# Function to send Telegram message
def send_telegram_message(chat_id, message, reply_markup=None):
    url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML',
        'reply_markup': reply_markup
    }
    try:
        response = requests.post(url, data=payload)
        response.raise_for_status()
        logger.info(f"Сообщение отправлено: {message}")
    except requests.RequestException as e:
        logger.error(f"Не удалось отправить сообщение: {e}")

# Function to parse RSS feed
def parse_rss_feed(url):
    try:
        feed = feedparser.parse(url)
        articles = [(entry.title, entry.link) for entry in feed.entries]
        logger.debug(f"Parsed {len(articles)} articles from {url}")
        return articles
    except Exception as e:
        logger.error(f"Не удалось разобрать RSS-ленту с {url}: {e}")
        return None

# Function to get article links from the main content on the website
def get_links_and_spans_from_content(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        articles = []

        # Найдем все теги <a> внутри конкретных блоков (например, статьи)
        for article_block in soup.find_all('div', class_='tdb-block-inner td-fix-index'):
            for a in article_block.find_all('a', href=True):
                link = a['href']
                if re.match(r'^https?://', link):
                    articles.append((a.get_text(strip=True), link))
        
        logger.debug(f"Extracted {len(articles)} links from {url}")
        return articles
    except requests.RequestException as e:
        logger.error(f"Не удалось получить содержимое с {url}: {e}")
        return None

# Функция для создания статического меню (custom keyboard)
def generate_static_keyboard():
    keyboard = [
        [KeyboardButton("Добавить URL"), KeyboardButton("Удалить URL")],
        [KeyboardButton("Список URL"), KeyboardButton("Очистить URL")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Function to handle the start command and show static buttons
async def start(update: Update, context):
    reply_markup = generate_static_keyboard()
    await update.message.reply_text('Пожалуйста, выберите:', reply_markup=reply_markup)
    chat_ids[update.message.chat_id] = update.message.chat_id
    logger.info(f"Chat ID {update.message.chat_id} added.")

# Function to validate URL format
def is_valid_url(url):
    regex = re.compile(
        r'^(?:http|ftp)s?://' # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' # domain...
        r'localhost|' # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|' # ...or ipv4
        r'\[?[A-F0-9]*:[A-F0-9:]+\]?)' # ...or ipv6
        r'(?::\d+)?' # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return re.match(regex, url) is not None

# Function to add URL with keywords
async def add_url(update: Update, context):
    url_and_keywords = update.message.text.split('|')
    if len(url_and_keywords) == 2:
        url, keywords = url_and_keywords
        url = url.strip()
        keywords = [kw.strip() for kw in keywords.split(',')]
        if is_valid_url(url):
            if url not in urls:
                urls[url] = {"type": "rss" if "rss" in url else "html", "latest": None, "keywords": keywords}
                save_urls()  # Save URLs after adding a new one
                await update.message.reply_text(f"Добавлен URL: {url} с ключевыми словами: {', '.join(keywords)}", reply_markup=generate_static_keyboard())
                logger.info(f"Добавлен URL: {url} с ключевыми словами: {', '.join(keywords)}")
            else:
                await update.message.reply_text(f"URL уже в списке: {url}", reply_markup=generate_static_keyboard())
        else:
            await update.message.reply_text("Неверный формат URL. Пожалуйста, укажите правильный URL.", reply_markup=generate_static_keyboard())
    else:
        await update.message.reply_text("Пожалуйста, укажите URL и ключевые слова, разделенные символом '|'", reply_markup=generate_static_keyboard())

# Function to remove URL
async def remove_url(update: Update, context):
    try:
        index = int(update.message.text) - 1
        if 0 <= index < len(urls):
            removed_url = list(urls.keys())[index]
            urls.pop(removed_url)
            save_urls()  # Save URLs after removing one
            await update.message.reply_text(f"Удален URL: {removed_url}", reply_markup=generate_static_keyboard())
            logger.info(f"Удален URL: {removed_url}")
        else:
            await update.message.reply_text(f"Недействительный индекс: {index + 1}", reply_markup=generate_static_keyboard())
    except ValueError:
        await update.message.reply_text("Пожалуйста, укажите правильный номер.", reply_markup=generate_static_keyboard())

# Function to list URLs
async def list_urls(update: Update, context):
    if urls:
        url_list = "\n".join([f"{i+1}. {url} (Ключевые слова: {', '.join(data['keywords'])})" for i, (url, data) in enumerate(urls.items())])
        await update.message.reply_text("Отслеживаемые URL:\n" + url_list, reply_markup=generate_static_keyboard())
    else:
        await update.message.reply_text("Нет отслеживаемых URL.", reply_markup=generate_static_keyboard())

# Function to clear URLs
async def clear_urls(update: Update, context):
    urls.clear()
    save_urls()  # Save after clearing URLs
    await update.message.reply_text("Все URL были очищены.", reply_markup=generate_static_keyboard())
    logger.info("Все URL были очищены.")

# Function to translate text using DeepL API
def translate_text(text, target_lang='ru'):
    url = "https://api-free.deepl.com/v2/translate"
    headers = {"Authorization": f"DeepL-Auth-Key {deepl_api_key}"}
    data = {
        "text": text,
        "target_lang": target_lang,
    }
    try:
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        translated_text = response.json()['translations'][0]['text']
        logger.info(f"Текст переведен: {translated_text[:100]}...")
        return translated_text
    except requests.RequestException as e:
        logger.error(f"Ошибка перевода текста через DeepL: {e}")
        return "Ошибка перевода текста."

# Function to handle translation request
async def handle_translation(update: Update, context):
    url = context.user_data.get('article_url')
    if url:
        logger.info(f"Translating article at URL: {url}")
        try:
            response = requests.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            article_text = ' '.join(p.get_text() for p in soup.find_all('p'))
            translated_text = translate_text(article_text)
            message = (f"<b>Переведенная статья:</b>\n{translated_text}\n\n"
                       f"<b>Оригинал:</b> <a href='{url}'>Читать на сайте</a>\n\n"
                       f"<b>Опубликовать на:</b> <a href='https://telegra.ph/'>Telegra.ph</a>")
            await update.callback_query.message.reply_text(message)
        except requests.RequestException as e:
            logger.error(f"Ошибка при получении статьи для перевода: {e}")
            await update.callback_query.message.reply_text("Ошибка при получении статьи для перевода.")
    else:
        await update.callback_query.message.reply_text("Не удалось найти статью для перевода.")

# Function to handle button presses for translation
async def translation_button(update: Update, context):
    query = update.callback_query
    context.user_data['article_url'] = query.data.split('_')[1]
    await handle_translation(update, context)

# Function to handle user messages based on the context of the action (add/remove/keywords)
async def handle_message(update: Update, context):
    action = update.message.text
    chat_ids[update.message.chat_id] = update.message.chat_id

    if action == "Добавить URL":
        context.user_data['action'] = 'add'
        await update.message.reply_text("Отправьте URL для добавления:", reply_markup=generate_static_keyboard())
    elif action == "Удалить URL":
        url_list = "\n".join([f"{i+1}. {url}" for i, url in enumerate(urls.keys())])
        context.user_data['action'] = 'remove'
        await update.message.reply_text(f"Отправьте номер URL для удаления:\n{url_list}", reply_markup=generate_static_keyboard())
    elif action == "Список URL":
        await list_urls(update, context)
    elif action == "Очистить URL":
        await clear_urls(update, context)
    else:
        await update.message.reply_text("Пожалуйста, используйте кнопки для выбора действия.", reply_markup=generate_static_keyboard())

# Initialize previous articles for all URLs
previous_articles = {}

def start_monitoring():
    logger.info("Мониторинг начался")
    time.sleep(10)
    while True:
        try:
            urls_copy = list(urls.items())  # Make a copy of the dictionary items for iteration
            for url, url_data in urls_copy:
                logger.info(f"Checking URL: {url}")
                if url_data["type"] == "rss":
                    new_articles = parse_rss_feed(url)
                else:
                    new_articles = get_links_and_spans_from_content(url)
                if new_articles is None:
                    logger.warning(f"Articles for URL {url} are None, skipping")
                    continue
                if url not in previous_articles:
                    previous_articles[url] = new_articles
                    logger.info(f"Initial articles for {url}: {new_articles}")
                    continue
                new_article_titles = {article[0] for article in new_articles}
                old_article_titles = {article[0] for article in previous_articles[url]}
                new_titles = new_article_titles - old_article_titles
                if new_titles:
                    for title in new_titles:
                        article = next(article for article in new_articles if article[0] == title)
                        if any(keyword.lower() in title.lower() for keyword in url_data.get('keywords', [])):
                            change_time = datetime.now()
                            message = (f"<b>Новая статья:</b> <a href='{article[1]}'>{article[0]}</a>\n"
                                       f"<b>Время:</b> {change_time}")
                            logger.info(f"Detected new article for {url} at {change_time}")
                            with open('change_log.txt', 'a') as log_file:
                                log_file.write(message + '\n')
                            
                            # Create a keyboard with a "Translate" button
                            translate_button = InlineKeyboardButton("Перевести", callback_data=f'translate_{article[1]}')
                            reply_markup = InlineKeyboardMarkup([[translate_button]])

                            # Send Telegram notification to all users
                            for chat_id in chat_ids.values():
                                logger.info(f"Sending notification to {chat_id}")
                                send_telegram_message(chat_id, message, reply_markup=reply_markup)
                    
                    previous_articles[url] = new_articles
                    logger.info(f"Updated articles for {url}")
                else:
                    logger.info(f"No new articles detected for {url}")
                time.sleep(30)
        except Exception as e:
            logger.error(f"Ошибка во время мониторинга: {e}")
            time.sleep(30)

def main():
    # Load URLs from the file at startup
    load_urls()
    application = Application.builder().token(telegram_bot_token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(translation_button, pattern=r'^translate_'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start the monitoring in a separate thread
    monitoring_thread = threading.Thread(target=start_monitoring)
    monitoring_thread.start()

    # Run the application
    application.run_polling()

if __name__ == '__main__':
    main()
