import time
import json
from datetime import datetime
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler
from bs4 import BeautifulSoup
import logging
import threading

# Telegram bot configuration
telegram_bot_token = '7241698952:AAF_-xoUSOVmJHSaJE_9d1--OUBqzZKTo6o'

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Убедитесь, что формат включает корректные поля
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# URL to monitor
monitoring_url = "https://carnewschina.com/category/electric-vehicles/"

# Dictionary to store chat IDs
chat_ids = {}

# Заголовки с User-Agent
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.198 Safari/537.36'
}

# Function to send Telegram message
def send_telegram_message(chat_id, message):
    url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML'
    }
    try:
        response = requests.post(url, data=payload)
        response.raise_for_status()
        logger.info(f"Сообщение отправлено: {message[:100]}...")  # Логируем первые 100 символов сообщения для отладки
    except requests.RequestException as e:
        logger.error(f"Не удалось отправить сообщение: {e}")

# Функция для разбиения длинного текста на части по 4000 символов
def split_long_message(text, max_length=4000):
    """Разбивает текст на части длиной не более max_length символов."""
    return [text[i:i+max_length] for i in range(0, len(text), max_length)]

# Function to get article links from the main page
def get_links_from_content(url):
    try:
        response = requests.get(url, headers=headers)  # Добавляем заголовки при запросе
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        articles = []

        # Ищем все статьи в блоке с классом "td_block_inner tdb-block-inner td-fix-index"
        for article_block in soup.select('.td_block_inner.tdb-block-inner.td-fix-index .entry-title.td-module-title'):
            link_tag = article_block.find('a', href=True)
            if link_tag:
                link = link_tag['href']
                title = link_tag.get_text(strip=True)
                articles.append((title, link))

        logger.debug(f"Extracted {len(articles)} links from {url}")
        return articles
    except requests.RequestException as e:
        logger.error(f"Не удалось получить содержимое с {url}: {e}")
        return None

# Function to extract the full text and images of the article
def extract_article_content_and_images(article_url):
    try:
        response = requests.get(article_url, headers=headers)  # Добавляем заголовки при запросе
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Ищем текст статьи в блоке с классом "tdb-block-inner td-fix-index"
        article_text_parts = []
        for p in soup.select('.tdb-block-inner.td-fix-index p'):
            text = p.get_text(strip=True)
            if text:
                article_text_parts.append(text)

        article_text = "\n\n".join(article_text_parts)  # Разделяем абзацы

        # Ищем изображения в блоке с классом "wp-block-image size-large"
        image_links = []
        for img in soup.select('.tdb-block-inner.td-fix-index .wp-block-image.size-large img'):
            img_url = img.get('src')
            if img_url:
                image_links.append(img_url)

        logger.debug(f"Extracted article content and images from {article_url}")
        return article_text, image_links
    except requests.RequestException as e:
        logger.error(f"Ошибка при извлечении текста статьи и изображений с {article_url}: {e}")
        return None, None

# Initialize previous articles for tracking
previous_articles = []

# Function to send the latest article when the bot starts
def send_latest_article(chat_id):
    try:
        new_articles = get_links_from_content(monitoring_url)
        if new_articles:
            latest_article = new_articles[0]  # Получаем последнюю статью
            title, link = latest_article
            article_text, image_links = extract_article_content_and_images(link)
            if article_text:
                # Отправляем текст статьи, разбивая его на части, если он превышает 4000 символов
                message = (f"<b>Последняя статья:</b> <a href='{link}'>{title}</a>\n\n"
                           f"<b>Текст статьи:</b>\n")
                send_telegram_message(chat_id, message)

                # Разбиваем текст на части и отправляем их
                article_parts = split_long_message(article_text)
                for part in article_parts:
                    send_telegram_message(chat_id, part)

                # Отправляем изображения отдельно (без форматирования)
                if image_links:
                    images_message = "\n".join(image_links)  # Отправляем ссылки без разметки
                    send_telegram_message(chat_id, f"<b>Изображения:</b>\n{images_message}")
            else:
                logger.warning("Не удалось извлечь текст последней статьи.")
        else:
            logger.warning("Нет доступных статей для отправки.")
    except Exception as e:
        logger.error(f"Ошибка при отправке последней статьи: {e}")

def start_monitoring():
    logger.info("Мониторинг начался")
    time.sleep(10)
    while True:
        try:
            logger.info(f"Checking URL: {monitoring_url}")
            new_articles = get_links_from_content(monitoring_url)
            if new_articles is None:
                logger.warning(f"Articles for URL {monitoring_url} are None, skipping")
                continue
            if not previous_articles:
                previous_articles.extend(new_articles)
                logger.info(f"Initial articles for {monitoring_url}: {new_articles}")
                continue
            new_article_titles = {article[0] for article in new_articles}
            old_article_titles = {article[0] for article in previous_articles}
            new_titles = new_article_titles - old_article_titles
            if new_titles:
                for title in new_titles:
                    article = next(article for article in new_articles if article[0] == title)
                    article_text, image_links = extract_article_content_and_images(article[1])  # Извлекаем текст статьи и изображения
                    if article_text:
                        change_time = datetime.now()

                        # Отправляем текст статьи
                        message = (f"<b>Новая статья:</b> <a href='{article[1]}'>{article[0]}</a>\n\n"
                                   f"<b>Текст статьи:</b>\n")
                        send_telegram_message(chat_id, message)

                        # Разбиваем текст на части и отправляем их
                        article_parts = split_long_message(article_text)
                        for part in article_parts:
                            send_telegram_message(chat_id, part)

                        # Отправляем ссылки на изображения (без форматирования)
                        if image_links:
                            images_message = "\n".join(image_links)  # Отправляем ссылки без разметки
                            send_telegram_message(chat_id, f"<b>Изображения:</b>\n{images_message}")

                previous_articles.extend(new_articles)
                logger.info(f"Updated articles for {monitoring_url}")
            else:
                logger.info(f"No new articles detected for {monitoring_url}")
            time.sleep(60)  # Задержка в 60 секунд между проверками
        except Exception as e:
            logger.error(f"Ошибка во время мониторинга: {e}")
            time.sleep(60)  # Задержка в случае ошибки, чтобы не перегружать сайт

# Function to handle the start command
async def start(update: Update, context):
    chat_ids[update.message.chat_id] = update.message.chat_id
    await update.message.reply_text("Мониторинг запущен. Вы будете уведомлены о новых статьях.")
    send_latest_article(update.message.chat_id)  # Отправляем последнюю статью при запуске бота

def main():
    application = Application.builder().token(telegram_bot_token).build()
    application.add_handler(CommandHandler("start", start))

    # Start the monitoring in a separate thread
    monitoring_thread = threading.Thread(target=start_monitoring)
    monitoring_thread.start()

    # Run the application
    application.run_polling()

if __name__ == '__main__':
    main()
