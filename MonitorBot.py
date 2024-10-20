import time
import requests
from bs4 import BeautifulSoup
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler
import threading

# Telegram bot configuration
telegram_bot_token = '7241698952:AAF_-xoUSOVmJHSaJE_9d1--OUBqzZKTo6o'
chat_ids = {}

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Заголовки с User-Agent
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.198 Safari/537.36'
}

# URL для мониторинга
monitoring_url = "https://carnewschina.com/category/electric-vehicles/"

# Функция для отправки сообщения в Telegram
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
        logger.info(f"Сообщение отправлено: {message[:100]}...")
    except requests.RequestException as e:
        logger.error(f"Не удалось отправить сообщение: {e}")

# Функция для получения ссылок на статьи с сайта
def get_links_from_content(url):
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        articles = []

        for article_block in soup.select('.td_block_inner.tdb-block-inner.td-fix-index .entry-title.td-module-title'):
            link_tag = article_block.find('a', href=True)
            if link_tag:
                title = link_tag.get_text(strip=True)
                link = link_tag['href']
                # Проверяем, что ссылка содержит схему (http/https)
                if not link.startswith('http'):
                    link = f'https://{link}'  # Добавляем схему, если ее нет
                articles.append((title, link))

        return articles
    except requests.RequestException as e:
        logger.error(f"Не удалось получить содержимое с {url}: {e}")
        return None

# Функция для получения текста статьи и ссылок на изображения
def get_article_content(article_url):
    try:
        response = requests.get(article_url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Получаем основной текст статьи
        content = []
        for paragraph in soup.select('.tdb-block-inner.td-fix-index p'):
            content.append(paragraph.get_text())

        # Получаем ссылки на изображения
        image_urls = []
        for img_tag in soup.select('.tdb-block-inner.td-fix-index .wp-block-image.size-large img'):
            img_url = img_tag['src']
            image_urls.append(img_url)

        return '\n'.join(content), image_urls
    except requests.RequestException as e:
        logger.error(f"Не удалось получить содержимое статьи с {article_url}: {e}")
        return None, []

# Функция для отправки новой статьи в чат
def send_article_message(chat_id, title, link, content, image_urls):
    message = f"<b>{title}</b>\n{link}\n\n{content}"

    # Разбиваем сообщение на части, если оно превышает 4000 символов
    while len(message) > 4000:
        part = message[:4000]
        send_telegram_message(chat_id, part)
        message = message[4000:]

    # Отправляем последнюю часть сообщения
    send_telegram_message(chat_id, message)

    # Отправляем ссылки на изображения отдельным сообщением
    if image_urls:
        images_message = "Изображения:\n" + '\n'.join(image_urls)
        send_telegram_message(chat_id, images_message)

# Функция для мониторинга новых статей
def start_monitoring():
    logger.info("Мониторинг начался")
    time.sleep(10)
    previous_articles = []

    while True:
        try:
            logger.info(f"Checking URL: {monitoring_url}")
            new_articles = get_links_from_content(monitoring_url)

            if new_articles is None:
                logger.warning(f"Articles for URL {monitoring_url} are None, skipping")
                continue

            # Формируем строку для логирования списков в три столбца с заголовками
            def format_list_comparison(old, new, current):
                max_len = max(len(old), len(new), len(current))
                formatted = "Старый список          | Новый список           | Актуальный список\n"
                formatted += "-" * 80 + "\n"
                for i in range(max_len):
                    old_item = (old[i][0][:30] if i < len(old) else '').ljust(30)
                    new_item = (new[i][0][:30] if i < len(new) else '').ljust(30)
                    current_item = (current[i][0][:30] if i < len(current) else '').ljust(30)
                    formatted += f"{i+1:2}. {old_item} | {new_item} | {current_item}\n"
                return formatted

            # Логируем списки в три столбца с обрезкой заголовков до 30 символов
            logger.info(format_list_comparison(previous_articles, new_articles, new_articles))

            # Проверка на наличие новых статей
            if previous_articles != new_articles:
                latest_article_title = new_articles[0][0]  # Заголовок последней статьи
                latest_article_link = new_articles[0][1]  # Ссылка на последнюю статью
                
                article_content, image_urls = get_article_content(latest_article_link)
                if article_content:
                    send_article_message(chat_ids[next(iter(chat_ids))], latest_article_title, latest_article_link, article_content, image_urls)
                    logger.info(f"Новое сообщение отправлено о статье: {latest_article_title}")

                # Обновляем список статей для следующего цикла
                previous_articles = new_articles
            else:
                logger.info("Новых статей не найдено.")

            time.sleep(60)  # Проверяем раз в минуту
        except Exception as e:
            logger.error(f"Ошибка во время мониторинга: {e}")
            time.sleep(60)

# Функция для команды /start
async def start(update: Update, context):
    chat_ids[update.message.chat_id] = update.message.chat_id
    await update.message.reply_text("Мониторинг запущен. Вы будете уведомлены о новых статьях.")
    send_latest_article(update.message.chat_id)  # Отправляем последнюю статью при запуске бота

# Функция для отправки последней статьи при запуске
def send_latest_article(chat_id):
    try:
        new_articles = get_links_from_content(monitoring_url)
        if new_articles:
            latest_article_title = new_articles[0][0]  # Заголовок последней статьи
            latest_article_link = new_articles[0][1]   # Ссылка на последнюю статью

            article_content, image_urls = get_article_content(latest_article_link)
            if article_content:
                send_article_message(chat_id, latest_article_title, latest_article_link, article_content, image_urls)
        else:
            logger.warning("Нет доступных статей для отправки.")
    except Exception as e:
        logger.error(f"Ошибка при отправке последней статьи: {e}")

def main():
    application = Application.builder().token(telegram_bot_token).build()
    application.add_handler(CommandHandler("start", start))

    # Стартуем мониторинг в отдельном потоке
    monitoring_thread = threading.Thread(target=start_monitoring)
    monitoring_thread.start()

    # Запуск приложения
    application.run_polling()

if __name__ == '__main__':
    main()
