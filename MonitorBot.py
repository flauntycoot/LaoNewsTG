import time
import requests
from bs4 import BeautifulSoup
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler
import threading
import openai

# Telegram bot configuration
telegram_bot_token = '7241698952:AAF_-xoUSOVmJHSaJE_9d1--OUBqzZKTo6o'
chat_ids = {}
openai.api_key = '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'
# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Headers with User-Agent
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.198 Safari/537.36'
}

# URLs for monitoring
monitoring_urls = {
    "Electric Vehicles": "https://carnewschina.com/category/electric-vehicles/",
    "EREV": "https://carnewschina.com/category/erev/"
}

# Send message to Telegram
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
        logger.info(f"Message sent: {message[:100]}...")
    except requests.RequestException as e:
        logger.error(f"Failed to send message: {e}")

# Translate and Summarize Article Content
def translate_and_summarize(content, target_language="Russian"):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant for translating and summarizing text."},
                {"role": "user", "content": f"Translate this article to {target_language} and provide a summary: {content}"}
            ]
        )
        result = response['choices'][0]['message']['content']
        return result
    except Exception as e:
        logger.error(f"Failed to translate and summarize: {e}")
        return None

# Get article links from a category page
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
                if not link.startswith('http'):
                    link = f'https://{link}'
                articles.append((title, link))

        return articles
    except requests.RequestException as e:
        logger.error(f"Failed to retrieve content from {url}: {e}")
        return None

# Get article content and image URLs
def get_article_content(article_url):
    try:
        response = requests.get(article_url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Get main text
        content = []
        for paragraph in soup.select('.tdb-block-inner.td-fix-index p'):
            content.append(paragraph.get_text())

        # Get image URLs
        image_urls = []
        for img_tag in soup.select('.tdb-block-inner.td-fix-index .wp-block-image.size-large img'):
            img_url = img_tag['src']
            image_urls.append(img_url)

        return '\n'.join(content), image_urls
    except requests.RequestException as e:
        logger.error(f"Failed to retrieve article content from {article_url}: {e}")
        return None, []

def send_article_message(chat_id, title, link, content, image_urls):
    translated_summary = translate_and_summarize(content)
    if translated_summary:
        content = translated_summary

    message = f"<b>{title}</b>\n{link}\n\n{content}"

    while len(message) > 4000:
        part = message[:4000]
        send_telegram_message(chat_id, part)
        message = message[4000:]

    send_telegram_message(chat_id, message)

    if image_urls:
        images_message = "Images:\n" + '\n'.join([f"{i + 1}. {url}" for i, url in enumerate(image_urls)])
        send_telegram_message(chat_id, images_message)
    fixed_link_message = "Make summary:\nhttps://chatgpt.com/c/ad04340a-54ed-4154-8c90-320292b57a03"
    send_telegram_message(chat_id, fixed_link_message)

# Monitor new articles for each URL
def monitor_articles(url_key, url):
    logger.info(f"Monitoring started for {url_key}")
    previous_articles = []

    while True:
        try:
            logger.info(f"Checking URL: {url}")
            new_articles = get_links_from_content(url)

            if new_articles is None:
                logger.warning(f"Articles for URL {url} are None, skipping")
                continue

            def format_list_comparison(old, new, current):
                max_len = max(len(old), len(new), len(current))
                formatted = f"{'Old List'.ljust(30)}| {'New List'.ljust(30)}| {'Current List'.ljust(30)}\n"
                formatted += "-" * 90 + "\n"
                for i in range(max_len):
                    old_item = (old[i][0][:30] if i < len(old) else '').ljust(30)
                    new_item = (new[i][0][:30] if i < len(new) else '').ljust(30)
                    current_item = (current[i][0][:30] if i < len(current) else '').ljust(30)
                    formatted += f"{i+1:2}. {old_item} | {new_item} | {current_item}\n"
                return formatted

            logger.info(format_list_comparison(previous_articles, new_articles, new_articles))

            if previous_articles != new_articles:
                latest_article_title = new_articles[0][0]
                latest_article_link = new_articles[0][1]
                
                article_content, image_urls = get_article_content(latest_article_link)
                if article_content:
                    send_article_message(chat_ids[next(iter(chat_ids))], latest_article_title, latest_article_link, article_content, image_urls)
                    logger.info(f"New message sent for article: {latest_article_title}")

                previous_articles = new_articles
            else:
                logger.info("No new articles found.")

            time.sleep(60)
        except Exception as e:
            logger.error(f"Error during monitoring for {url_key}: {e}")
            time.sleep(60)

# Telegram bot /start command
async def start(update: Update, context):
    chat_ids[update.message.chat_id] = update.message.chat_id
    await update.message.reply_text("Monitoring started. You will be notified of new articles.")
    send_latest_article(update.message.chat_id)

# Send the latest article when starting the bot
def send_latest_article(chat_id):
    try:
        for url_key, url in monitoring_urls.items():
            new_articles = get_links_from_content(url)
            if new_articles:
                latest_article_title = new_articles[0][0]
                latest_article_link = new_articles[0][1]

                article_content, image_urls = get_article_content(latest_article_link)
                if article_content:
                    send_article_message(chat_id, latest_article_title, latest_article_link, article_content, image_urls)
            else:
                logger.warning(f"No articles available to send for {url_key}.")
    except Exception as e:
        logger.error(f"Error sending latest article: {e}")

def main():
    application = Application.builder().token(telegram_bot_token).build()
    application.add_handler(CommandHandler("start", start))

    for url_key, url in monitoring_urls.items():
        monitoring_thread = threading.Thread(target=monitor_articles, args=(url_key, url))
        monitoring_thread.start()

    application.run_polling()

if __name__ == '__main__':
    main()