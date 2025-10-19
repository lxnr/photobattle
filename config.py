import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot
BOT_TOKEN = os.getenv('BOT_TOKEN', '7796078474:AAE7JfMHeZEjyl9yhW8CwSK3NvHlEOZYby8')
BOT_USERNAME = 'photobattl3bot'

# Админы (можно добавлять через запятую)
ADMIN_IDS = [int(x.strip()) for x in os.getenv('ADMIN_IDS', '1164427393').split(',')]

# Канал для публикации батлов
CHANNEL_ID = os.getenv('CHANNEL_ID', '@photozalupa1488')
CHANNEL_LINK = os.getenv('CHANNEL_LINK', 'https://t.me/photozalupa1488')

# База данных PostgreSQL
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'photobattle')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

# Настройки батла
MIN_VOTES = int(os.getenv('MIN_VOTES', '8'))  # Минимум голосов для прохода в след раунд
VOTES_PER_REFERRAL = int(os.getenv('VOTES_PER_REFERRAL', '3'))  # Голосов за 1 реферала
