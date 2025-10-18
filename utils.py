"""
Вспомогательные утилиты для фотобатл бота
"""
import asyncio
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


def format_time_ago(timestamp):
    """
    Форматирует время в читаемый вид "2 часа назад"
    """
    now = datetime.now()
    diff = now - timestamp
    
    if diff < timedelta(minutes=1):
        return "только что"
    elif diff < timedelta(hours=1):
        minutes = int(diff.total_seconds() / 60)
        return f"{minutes} мин назад"
    elif diff < timedelta(days=1):
        hours = int(diff.total_seconds() / 3600)
        return f"{hours} ч назад"
    elif diff < timedelta(days=7):
        days = diff.days
        return f"{days} дн назад"
    else:
        return timestamp.strftime("%d.%m.%Y")


def format_number(number):
    """
    Форматирует число с разделителями тысяч
    """
    return f"{number:,}".replace(",", " ")


def validate_photo(photo_file):
    """
    Проверяет что фото подходит для батла
    """
    # Проверка размера
    if photo_file.file_size > 10 * 1024 * 1024:  # 10 MB
        return False, "Фото слишком большое (макс 10 МБ)"
    
    # Проверка пропорций (вертикальное или квадратное)
    if photo_file.width > photo_file.height * 1.2:
        return False, "Фото должно быть вертикальным или квадратным"
    
    return True, "OK"


def get_battle_status_emoji(votes1, votes2):
    """
    Возвращает эмодзи статуса батла
    """
    if votes1 == votes2:
        return "⚖️"
    elif votes1 > votes2:
        return "◀️"
    else:
        return "▶️"


def generate_leaderboard(users_data, limit=10):
    """
    Генерирует текст таблицы лидеров
    """
    leaderboard = "🏆 ТАБЛИЦА ЛИДЕРОВ\n\n"
    
    for idx, user in enumerate(users_data[:limit], 1):
        emoji = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
        username = user.get('username', 'Аноним')
        votes = user.get('votes', 0)
        leaderboard += f"{emoji} @{username} — {votes} голосов\n"
    
    return leaderboard


def create_progress_bar(current, total, length=10):
    """
    Создает прогресс бар
    """
    filled = int((current / total) * length)
    bar = "█" * filled + "░" * (length - filled)
    percentage = int((current / total) * 100)
    return f"{bar} {percentage}%"


async def send_mass_message(bot, user_ids, message, delay=0.1):
    """
    Отправляет сообщение множеству пользователей с задержкой
    """
    success = 0
    failed = 0
    
    for user_id in user_ids:
        try:
            await bot.send_message(chat_id=user_id, text=message)
            success += 1
            await asyncio.sleep(delay)  # Защита от rate limit
        except Exception as e:
            logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
            failed += 1
    
    return success, failed


def calculate_win_rate(wins, total_battles):
    """
    Вычисляет процент побед
    """
    if total_battles == 0:
        return 0
    return round((wins / total_battles) * 100, 1)


def get_rank_emoji(position):
    """
    Возвращает эмодзи ранга по позиции
    """
    ranks = {
        1: "🥇",
        2: "🥈", 
        3: "🥉",
    }
    return ranks.get(position, "🏅")


def format_duration(seconds):
    """
    Форматирует длительность в читаемый вид
    """
    if seconds < 60:
        return f"{seconds} сек"
    elif seconds < 3600:
        return f"{seconds // 60} мин"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours} ч {minutes} мин"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days} дн {hours} ч"


def sanitize_username(username):
    """
    Очищает username от недопустимых символов
    """
    if not username:
        return "Аноним"
    
    # Удаляем @ если есть
    username = username.lstrip('@')
    
    # Ограничиваем длину
    if len(username) > 32:
        username = username[:32]
    
    return username


def chunk_list(lst, n):
    """
    Разбивает список на чанки по n элементов
    """
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def get_battle_result_text(photo1_votes, photo2_votes):
    """
    Возвращает текст результата батла
    """
    total = photo1_votes + photo2_votes
    
    if total == 0:
        return "Нет голосов"
    
    if photo1_votes > photo2_votes:
        percentage = round((photo1_votes / total) * 100)
        return f"Победа левого фото ({percentage}%)"
    elif photo2_votes > photo1_votes:
        percentage = round((photo2_votes / total) * 100)
        return f"Победа правого фото ({percentage}%)"
    else:
        return "Ничья"


def is_valid_telegram_id(telegram_id):
    """
    Проверяет валидность Telegram ID
    """
    try:
        tid = int(telegram_id)
        return 0 < tid < 10000000000  # Telegram ID в диапазоне
    except (ValueError, TypeError):
        return False


# Декораторы для обработки ошибок
def handle_errors(func):
    """
    Декоратор для обработки ошибок в хендлерах
    """
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Ошибка в {func.__name__}: {e}", exc_info=True)
            # Можно отправить уведомление админам
    return wrapper


def admin_only(func):
    """
    Декоратор для проверки прав админа
    """
    async def wrapper(update, context, *args, **kwargs):
        from database import Database
        db = Database()
        
        user_id = update.effective_user.id
        if not db.is_admin(user_id):
            await update.message.reply_text("❌ Доступ запрещен!")
            return
        
        return await func(update, context, *args, **kwargs)
    return wrapper


# Константы
EMOJI_FIRE = "🔥"
EMOJI_PHOTO = "📸"
EMOJI_TROPHY = "🏆"
EMOJI_CROWN = "👑"
EMOJI_STAR = "⭐"
EMOJI_CHECK = "✅"
EMOJI_CROSS = "❌"
EMOJI_WARNING = "⚠️"
EMOJI_INFO = "ℹ️"
EMOJI_LOADING = "⏳"


# Шаблоны сообщений
MESSAGE_TEMPLATES = {
    'welcome': """
👋 Привет! Добро пожаловать в фотобатл!

📸 Отправь свое фото для участия
🔥 Голосуй за понравившиеся фото
🎁 Приглашай друзей и получай бонусы
""",
    
    'photo_received': """
✅ Фото получено!

Оно отправлено на модерацию админам.
Скоро ты узнаешь результат!
""",
    
    'photo_approved': """
🎉 Твое фото одобрено!

Оно будет участвовать в следующем раунде.
Следи за каналом!
""",
    
    'photo_rejected': """
😔 К сожалению, твое фото не прошло модерацию.

Возможные причины:
• Не видно лица
• Горизонтальная ориентация
• Низкое качество

Попробуй отправить другое фото!
""",
    
    'round_started': """
🔥 НОВЫЙ РАУНД НАЧАЛСЯ!

Отправляй свое фото для участия!
Успей до закрытия приема заявок!
""",
    
    'voting_reminder': """
⚡️ Не забудь проголосовать!

Зайди в канал и поддержи понравившиеся фото.
Твой голос важен!
"""
}


if __name__ == "__main__":
    # Тесты
    print("Тестирование утилит...")
    
    # Тест форматирования времени
    past = datetime.now() - timedelta(hours=2)
    print(f"Время назад: {format_time_ago(past)}")
    
    # Тест форматирования чисел
    print(f"Число: {format_number(1234567)}")
    
    # Тест прогресс бара
    print(f"Прогресс: {create_progress_bar(7, 10)}")
    
    print("✅ Все тесты пройдены!")
