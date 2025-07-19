import os
from dotenv import load_dotenv
import telebot
from mistralai import Mistral
from flask import Flask, request
import logging
import sys

# --- Настройка логирования ---
LOG_FILE = "bot.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# --- Чтение переменных окружения ---
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

if not TELEGRAM_BOT_TOKEN or not MISTRAL_API_KEY:
    logger.error("Отсутствует необходимый API-ключ или токен бота!")
    raise ValueError("Отсутствует необходимый API-ключ или токен бота!")

MODEL_TEXT = "mistral-large-latest"
MODEL_IMAGE = "mistral-medium-2505"

# --- Инициализация ---
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
client = Mistral(api_key=MISTRAL_API_KEY)

app = Flask(__name__)


# --- Функции ---
def generate_text(prompt):
    try:
        response = client.chat.complete(
            model=MODEL_TEXT,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Ошибка генерации текста: {str(e)}")
        raise


def generate_image(prompt):
    try:
        image_agent = client.beta.agents.create(
            model=MODEL_IMAGE,
            name="Image Generation Agent",
            description="Agent used to generate images.",
            instructions="Use the image generation tool when you have to create images.",
            tools=[{"type": "image_generation"}],
            completion_args={
                "temperature": 0.3,
                "top_p": 0.95,
            }
        )

        chat_response = client.beta.agents.run(
            agent=image_agent,
            messages=[{"role": "user", "content": prompt}]
        )

        for chunk in chat_response.outputs[-1].content:
            if hasattr(chunk, 'file_id'):
                file_bytes = client.files.download(file_id=chunk.file_id).read()
                with open("generated_image.png", "wb") as f:
                    f.write(file_bytes)
                return "generated_image.png"
        return None
    except Exception as e:
        logger.error(f"Ошибка генерации изображения: {str(e)}")
        raise


# --- Обработчики команд ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    logger.info(f"Пользователь {message.from_user.id} использовал /start")
    bot.reply_to(message, "Привет! Я бот, который может генерировать посты с текстом и изображением.\n"
                          "Просто напиши мне промпт или используй /help.")


@bot.message_handler(commands=['help'])
def show_help(message):
    help_text = (
        "Как пользоваться:\n"
        "1. Напиши любой текст — я сгенерирую пост с текстом и изображением.\n"
        "2. Используй команды:\n"
        "   - /start — начать работу\n"
        "   - /help — это меню"
    )
    logger.info(f"Пользователь {message.from_user.id} использовал /help")
    bot.reply_to(message, help_text)


@bot.message_handler(func=lambda message: True)
def handle_prompt(message):
    logger.info(f"Получено сообщение от пользователя {message.from_user.id}: {message.text}")

    prompt = message.text.strip()

    if not prompt:
        logger.warning(f"Пустой промпт от пользователя {message.from_user.id}")
        bot.reply_to(message, "Пожалуйста, введи промпт.")
        return

    bot.reply_to(message, "Генерирую текст и изображение...")

    try:
        text_result = generate_text(prompt)
        image_path = generate_image(prompt)

        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as photo_file:
                bot.send_photo(
                    message.chat.id,
                    photo=photo_file,
                    caption=text_result
                )
            os.remove(image_path)  # Удаляем временный файл после отправки
        else:
            bot.send_message(message.chat.id, text_result)
        logger.info(f"Успешный ответ пользователю {message.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения от пользователя {message.from_user.id}: {str(e)}")
        bot.reply_to(message, f"Произошла ошибка: {str(e)}")


# --- Вебхук ---
@app.route('/' + TELEGRAM_BOT_TOKEN, methods=['POST'])
def webhook():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return 'OK', 200


@app.route('/')
def index():
    return 'Бот работает.'


# --- Установка вебхука ---
def set_webhook():
    domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN") or "localhost"
    url = f"https://{domain}/{TELEGRAM_BOT_TOKEN}"
    bot.set_webhook(url=url)
    logger.info(f"✅ Webhook установлен: {url}")


if __name__ == "__main__":
    set_webhook()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
