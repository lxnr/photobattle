import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ChatMember
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.error import TelegramError
from database import Database
import config
import asyncio

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

db = Database()


class PhotoBattleBot:
    def __init__(self):
        self.app = Application.builder().token(config.BOT_TOKEN).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        # Команды
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("admin", self.admin_panel))
        self.app.add_handler(CommandHandler("start_round", self.start_round))
        self.app.add_handler(CommandHandler("next_round", self.next_round))
        self.app.add_handler(CommandHandler("end_battle", self.end_battle))
        self.app.add_handler(CommandHandler("stats", self.stats))
        self.app.add_handler(CommandHandler("add_admin", self.add_admin))
        self.app.add_handler(CommandHandler("remove_admin", self.remove_admin))
        self.app.add_handler(CommandHandler("list_admins", self.list_admins))
        
        # Обработка фото
        self.app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        
        # Обработка текстовых сообщений (для меню)
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        
        # Callback кнопки
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
    
    def get_main_menu(self):
        """Создает главное меню с кнопками внизу"""
        keyboard = [
            [KeyboardButton("🔥 принять участие"), KeyboardButton("🎤 получить голоса")],
            [KeyboardButton("👤 профиль"), KeyboardButton("💬 помощь")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    async def check_subscription(self, user_id: int) -> bool:
        """Проверка подписки на канал"""
        try:
            member = await self.app.bot.get_chat_member(config.CHANNEL_ID, user_id)
            return member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]
        except TelegramError:
            return False
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start с реферальной системой"""
        user = update.effective_user
        args = context.args
        
        # Проверка на реферала
        referrer_id = None
        if args and args[0].startswith('ref'):
            try:
                referrer_id = int(args[0].replace('ref', ''))
                if referrer_id == user.id:
                    referrer_id = None
            except ValueError:
                pass
        
        # Регистрация пользователя
        is_new = db.add_user(user.id, user.username, referrer_id)
        
        # Получаем реферальную ссылку
        ref_link = f"https://t.me/{config.BOT_USERNAME}?start=ref{user.id}"
        
        welcome_text = f"""
👋 Привет! Здесь ты можешь принять участие в фотобатле!

📸 Чтобы участвовать, просто отправь мне свою фотографию где видно лицо, которая должна быть вертикальной или квадратной.

❗️ Используй только собственные изображения

🔥 Твоя реферальная ссылка:
{ref_link}

📊 Пригласи друзей и получи дополнительные голоса!
За каждого реферала, который отправит фото, ты получишь 3 голоса.
"""
        
        await update.message.reply_text(welcome_text, reply_markup=self.get_main_menu())
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текстовых сообщений из меню"""
        text = update.message.text
        user_id = update.effective_user.id
        
        if text == "🔥 принять участие":
            current_round = db.get_current_round()
            if not current_round or current_round['status'] != 'active':
                await update.message.reply_text(
                    "❌ Сейчас нет активного раунда. Дождись начала нового батла!",
                    reply_markup=self.get_main_menu()
                )
            else:
                await update.message.reply_text(
                    "📸 Отправь свое фото для участия в батле!\n\n"
                    "Требования:\n"
                    "• Видно лицо\n"
                    "• Вертикальное или квадратное фото\n"
                    "• Только собственное фото",
                    reply_markup=self.get_main_menu()
                )
        
        elif text == "🎤 получить голоса":
            ref_link = f"https://t.me/{config.BOT_USERNAME}?start=ref{user_id}"
            user_stats = db.get_user_stats(user_id)
            
            votes_text = f"""
🎤 Голоса для фотобатла можно получить двумя способами:

1️⃣ Пригласи друзей принять участие в фотобатле через твою ссылку (указана ниже). Если их заявка будет одобрена, ты получишь 3 голоса 🎤

2️⃣ Приобрети голоса за деньги (1 голос = 5₽)

📊 У тебя сейчас: {user_stats['extra_votes']} дополнительных голосов

🔗 Твоя реферальная ссылка:
{ref_link}

💡 Чем больше голосов - тем выше твои шансы на победу!
"""
            keyboard = [
                [InlineKeyboardButton("💳 купить голоса", callback_data="buy_votes")]
            ]
            await update.message.reply_text(
                votes_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        elif text == "👤 профиль":
            user_stats = db.get_user_stats(user_id)
            ref_link = f"https://t.me/{config.BOT_USERNAME}?start=ref{user_id}"
            
            profile_text = f"""
👤 Твой профиль:

🏆 Выиграно фотобатлов: {user_stats['wins']}
📸 Сыграно фотобатлов: {user_stats['played']}
🔥 Приглашено активных рефералов: {user_stats['active_referrals']}

📊 Дополнительных голосов: {user_stats['extra_votes']}

🔗 Твоя реферальная ссылка:
{ref_link}

💡 Реферал становится активным после отправки фото
"""
            await update.message.reply_text(profile_text, reply_markup=self.get_main_menu())
        
        elif text == "💬 помощь":
            help_text = """
💬 ПОМОЩЬ И ПРАВИЛА

📖 Правила фотобатла:
1️⃣ Отправь свою фотографию где видно лицо
2️⃣ Фото должно быть вертикальным или квадратным
3️⃣ Используй только собственные изображения
4️⃣ Админы проверят и одобрят твое фото
5️⃣ Батл проходит между двумя фото
6️⃣ Побеждает фото с большим количеством голосов
7️⃣ Для прохода в следующий раунд нужно минимум 8 голосов

🔔 Для голосования нужно быть подписанным на канал

❓ Вопросы? Напиши админу: @admin
"""
            keyboard = [
                [InlineKeyboardButton("📢 Канал с батлами", url=config.CHANNEL_LINK)]
            ]
            await update.message.reply_text(
                help_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка присланных фото"""
        user = update.effective_user
        photo = update.message.photo[-1]
        
        # Проверка: активен ли раунд
        current_round = db.get_current_round()
        if not current_round or current_round['status'] != 'active':
            await update.message.reply_text(
                "❌ Сейчас нет активного раунда. Дождись начала нового батла!",
                reply_markup=self.get_main_menu()
            )
            return
        
        # Проверка: не отправлял ли уже фото в этом раунде
        if db.user_has_photo_in_round(user.id, current_round['id']):
            await update.message.reply_text(
                "❌ Ты уже отправил фото в этом раунде!",
                reply_markup=self.get_main_menu()
            )
            return
        
        # Сохраняем фото на модерацию
        photo_id = db.add_photo(
            user_id=user.id,
            file_id=photo.file_id,
            round_id=current_round['id']
        )
        
        # Если это реферал и первое фото - начисляем голоса рефереру
        user_data = db.get_user(user.id)
        if user_data and user_data['referrer_id']:
            user_photos_count = db.count_user_photos(user.id)
            if user_photos_count == 1:
                db.add_referral_votes(user_data['referrer_id'], config.VOTES_PER_REFERRAL)
        
        await update.message.reply_text(
            "✅ Фотография отправлена на модерацию!\n\n"
            "🏁 Бот сообщит о начале фотобатла, так что не блокируй его",
            reply_markup=self.get_main_menu()
        )
        
        # Отправляем фото админам на модерацию
        await self.send_photo_to_admins(photo_id, photo.file_id, user)
    
    async def send_photo_to_admins(self, photo_id: int, file_id: str, user):
        """Отправка фото админам для модерации"""
        keyboard = [
            [
                InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{photo_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{photo_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        caption = f"""
🆔 ID фото: {photo_id}
👤 Пользователь: @{user.username or 'без username'} (ID: {user.id})

Модерация фото:
"""
        
        admin_ids = db.get_all_admins()
        for admin_id in admin_ids:
            try:
                await self.app.bot.send_photo(
                    chat_id=admin_id,
                    photo=file_id,
                    caption=caption,
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Ошибка отправки фото админу {admin_id}: {e}")
    
    async def check_and_publish_battles(self, round_id: int):
        """Проверка и автоматическая публикация батлов при наборе пар"""
        # Получаем одобренные фото которые еще не в батлах
        approved_photos = db.get_unpaired_photos(round_id)
        
        # Проверяем сколько пар можно создать
        pairs_count = len(approved_photos) // 2
        
        if pairs_count == 0:
            return
        
        # Получаем сколько уже есть пар в этом раунде
        existing_battles = db.count_battles_in_round(round_id)
        
        # Максимум 10 пар
        if existing_battles >= config.MAX_PAIRS:
            return
        
        # Сколько еще можем создать пар
        available_slots = config.MAX_PAIRS - existing_battles
        pairs_to_create = min(pairs_count, available_slots)
        
        # Создаем и публикуем пары
        import random
        random.shuffle(approved_photos)
        
        for i in range(pairs_to_create):
            photo1 = approved_photos[i * 2]
            photo2 = approved_photos[i * 2 + 1]
            
            battle_id = db.create_battle(round_id, photo1['id'], photo2['id'])
            await self.publish_battle(battle_id, photo1, photo2)
            
            logger.info(f"Автоматически создан батл #{battle_id}")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий на кнопки"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        # Модерация фото (только для админов)
        if data.startswith(('approve_', 'reject_')):
            if not db.is_admin(user_id):
                await query.answer("❌ Доступно только админам!", show_alert=True)
                return
            
            action, photo_id = data.split('_')
            photo_id = int(photo_id)
            
            if action == 'approve':
                db.update_photo_status(photo_id, 'approved')
                await query.edit_message_caption(
                    caption=query.message.caption + "\n\n✅ ОДОБРЕНО"
                )
                
                # Проверяем можем ли создать новые батлы
                photo = db.get_photo_by_id(photo_id)
                if photo:
                    await self.check_and_publish_battles(photo['round_id'])
                
            else:  # reject
                db.update_photo_status(photo_id, 'rejected')
                await query.edit_message_caption(
                    caption=query.message.caption + "\n\n❌ ОТКЛОНЕНО"
                )
        
        # Голосование в батле
        elif data.startswith('vote_'):
            parts = data.split('_')
            battle_id = int(parts[1])
            photo_id = int(parts[2])
            
            # Проверка подписки на канал
            is_subscribed = await self.check_subscription(user_id)
            if not is_subscribed:
                await query.answer(
                    "❌ Чтобы голосовать, нужно подписаться на канал!",
                    show_alert=True
                )
                return
            
            # Проверка: голосовал ли уже в этом батле
            if db.user_voted_in_battle(user_id, battle_id):
                await query.answer(
                    "❌ Вы уже проголосовали в этом батле",
                    show_alert=True
                )
                return
            
            # Сохраняем голос
            db.add_vote(user_id, battle_id, photo_id)
            
            # Показываем уведомление
            await query.answer(
                "🔥 Голос учтён\n\n"
                "❗️ При отписке от канала голос не будет засчитан\n\n"
                "⏱ Голос зачислится в течение минуты",
                show_alert=True
            )
            
            # Обновляем счетчик голосов через минуту
            asyncio.create_task(self.update_vote_count_delayed(battle_id, query.message))
        
        # Покупка голосов
        elif data == 'buy_votes':
            await query.answer("Функция в разработке", show_alert=True)
        
        # Кнопка "Назад"
        elif data == 'back_to_start':
            ref_link = f"https://t.me/{config.BOT_USERNAME}?start=ref{user_id}"
            
            welcome_text = f"""
👋 Привет! Здесь ты можешь принять участие в фотобатле!

📸 Чтобы участвовать, просто отправь мне свою фотографию где видно лицо, которая должна быть вертикальной или квадратной.

❗️ Используй только собственные изображения

🔥 Твоя реферальная ссылка:
{ref_link}

📊 Пригласи друзей и получи дополнительные голоса!
"""
            try:
                await query.edit_message_text(welcome_text)
            except:
                await query.message.reply_text(welcome_text, reply_markup=self.get_main_menu())
    
    async def update_vote_count_delayed(self, battle_id: int, message):
        """Обновление счетчика голосов через минуту"""
        await asyncio.sleep(60)
        
        try:
            votes = db.get_battle_votes(battle_id)
            await self.update_battle_message(message, battle_id, votes)
        except Exception as e:
            logger.error(f"Ошибка обновления счетчика голосов: {e}")
    
    async def update_battle_message(self, message, battle_id: int, votes: dict):
        """Обновление сообщения с батлом (счетчик голосов)"""
        caption = f"""
🔥 ФОТОБАТЛ №{battle_id}

◀️ Лево: {votes['photo1']} голосов
Право ▶️: {votes['photo2']} голосов

Голосуй за лучшее фото!
"""
        
        try:
            await message.edit_caption(caption=caption, reply_markup=message.reply_markup)
        except Exception as e:
            logger.error(f"Ошибка обновления счетчика: {e}")
    
    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Админ-панель"""
        user_id = update.effective_user.id
        
        if not db.is_admin(user_id):
            await update.message.reply_text("❌ Доступ запрещен!")
            return
        
        current_round = db.get_current_round()
        pending_count = db.count_photos_by_status('pending', current_round['id'] if current_round else None)
        approved_count = db.count_photos_by_status('approved', current_round['id'] if current_round else None)
        battles_count = db.count_battles_in_round(current_round['id']) if current_round else 0
        
        admin_text = f"""
👑 АДМИН-ПАНЕЛЬ

📊 Текущий раунд: {current_round['number'] if current_round else 'Не создан'}
📸 На модерации: {pending_count}
✅ Одобрено фото: {approved_count}
⚔️ Опубликовано пар: {battles_count}/{config.MAX_PAIRS}

Команды:
/start_round - Начать 1 раунд батла (набор фото)
/next_round - Начать следующий раунд с победителями
/end_battle - Завершить батл полностью
/stats - Статистика бота
/add_admin [ID] - Добавить админа
/remove_admin [ID] - Удалить админа
/list_admins - Список админов
"""
        
        await update.message.reply_text(admin_text)
    
    async def start_round(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начать новый 1 раунд батла (только админ)"""
        user_id = update.effective_user.id
        
        if not db.is_admin(user_id):
            return
        
        current_round = db.get_current_round()
        if current_round:
            await update.message.reply_text("❌ Уже есть активный раунд! Сначала завершите его командой /end_battle")
            return
        
        round_id = db.create_round(round_number=1)
        
        users = db.get_all_users()
        message_text = """
🔥 Начался новый раунд фотобатла!

📸 Отправь свою фотографию для участия!
⏱ Срочно жду пару фоток!!!!!!!
"""
        
        for user in users:
            try:
                await self.app.bot.send_message(
                    chat_id=user['telegram_id'], 
                    text=message_text,
                    reply_markup=self.get_main_menu()
                )
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления пользователю {user['telegram_id']}: {e}")
        
        await update.message.reply_text(f"✅ Раунд 1 начат! Ожидаем фото от участников.")
    
    async def next_round(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начать следующий раунд с победителями (только админ)"""
        user_id = update.effective_user.id
        
        if not db.is_admin(user_id):
            return
        
        current_round = db.get_current_round()
        if not current_round:
            await update.message.reply_text("❌ Нет активного раунда!")
            return
        
        winners = db.get_round_winners(current_round['id'], min_votes=config.MIN_VOTES)
        
        if len(winners) < 2:
            await update.message.reply_text(
                f"❌ Недостаточно победителей! Минимум 2 фото с {config.MIN_VOTES}+ голосами."
            )
            return
        
        db.end_round(current_round['id'])
        
        next_round_number = current_round['number'] + 1
        new_round_id = db.create_round(round_number=next_round_number)
        
        await self.publish_battles_from_winners(new_round_id, winners)
        
        await update.message.reply_text(
            f"✅ Раунд {next_round_number} начат!\n"
            f"Участников: {len(winners)}\n"
            f"Пар: {len(winners) // 2}"
        )
    
    async def publish_battles_from_winners(self, round_id: int, winners: list):
        """Публикация батлов из списка победителей"""
        import random
        random.shuffle(winners)
        
        for i in range(0, len(winners) - 1, 2):
            photo1 = winners[i]
            photo2 = winners[i + 1]
            
            battle_id = db.create_battle(round_id, photo1['id'], photo2['id'])
            await self.publish_battle(battle_id, photo1, photo2)
    
    async def publish_battle(self, battle_id: int, photo1: dict, photo2: dict):
        """Публикация батла в канал"""
        keyboard = [
            [
                InlineKeyboardButton("лево 4", callback_data=f"vote_{battle_id}_{photo1['id']}"),
                InlineKeyboardButton("право 4", callback_data=f"vote_{battle_id}_{photo2['id']}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        caption = f"""
🔥 ФОТОБАТЛЫ

⚜️ 1 раунд
💰 ПРИЗ: 777₽ или 350⭐

👉ссылка для голосования👈

🗣 нужно собрать минимум 8 голосов

✨нажми, чтобы принять участие

🧑‍💼 итоги завтра в 14:00 по МСК
"""
        
        try:
            # Отправляем первое фото
            await self.app.bot.send_photo(
                chat_id=config.CHANNEL_ID,
                photo=photo1['file_id']
            )
            
            # Отправляем второе фото с кнопками
            message = await self.app.bot.send_photo(
                chat_id=config.CHANNEL_ID,
                photo=photo2['file_id'],
                caption=caption,
                reply_markup=reply_markup
            )
            
            db.update_battle_message_id(battle_id, message.message_id)
            logger.info(f"Опубликован батл #{battle_id} в канале")
        except Exception as e:
            logger.error(f"Ошибка публикации батла: {e}")
    
    async def end_battle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Завершить батл полностью и подвести итоги"""
        user_id = update.effective_user.id
        
        if not db.is_admin(user_id):
            return
        
        current_round = db.get_current_round()
        if not current_round:
            await update.message.reply_text("❌ Нет активного раунда!")
            return
        
        winners = db.get_round_winners(current_round['id'], min_votes=config.MIN_VOTES)
        
        db.end_round(current_round['id'])
        
        result_text = f"🏆 Фотобатл завершен!\n\n"
        
        if winners:
            result_text += f"Победителей: {len(winners)}\n\n"
            result_text += "Топ участников:\n"
            for idx, winner in enumerate(winners[:10], 1):
                username = winner.get('username', 'Аноним')
                result_text += f"{idx}. @{username} - {winner['votes']} голосов\n"
        else:
            result_text += "Нет победителей в этом раунде."
        
        await update.message.reply_text(result_text)
        
        for winner in winners:
            try:
                await self.app.bot.send_message(
                    chat_id=winner['user_id'],
                    text=f"🎉 Поздравляем! Ты прошел в финал с {winner['votes']} голосами!",
                    reply_markup=self.get_main_menu()
                )
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления победителю: {e}")
    
    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика бота"""
        stats = db.get_bot_stats()
        
        stats_text = f"""
📊 СТАТИСТИКА БОТА:

👥 Всего пользователей: {stats['total_users']}
📸 Всего фото: {stats['total_photos']}
⚔️ Всего батлов: {stats['total_battles']}
🗳 Всего голосов: {stats['total_votes']}
👑 Админов: {stats['total_admins']}
"""
        
        await update.message.reply_text(stats_text)
    
    async def add_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Добавить нового админа"""
        user_id = update.effective_user.id
        
        if not db.is_admin(user_id):
            await update.message.reply_text("❌ Доступ запрещен!")
            return
        
        if not context.args:
            await update.message.reply_text("Использование: /add_admin [telegram_id]")
            return
        
        try:
            new_admin_id = int(context.args[0])
            db.add_admin(new_admin_id)
            await update.message.reply_text(f"✅ Админ {new_admin_id} добавлен!")
        except ValueError:
            await update.message.reply_text("❌ Неверный ID!")
    
    async def remove_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Удалить админа"""
        user_id = update.effective_user.id
        
        if not db.is_admin(user_id):
            await update.message.reply_text("❌ Доступ запрещен!")
            return
        
        if not context.args:
            await update.message.reply_text("Использование: /remove_admin [telegram_id]")
            return
        
        try:
            admin_id = int(context.args[0])
            db.remove_admin(admin_id)
            await update.message.reply_text(f"✅ Админ {admin_id} удален!")
        except ValueError:
            await update.message.reply_text("❌ Неверный ID!")
    
    async def list_admins(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Список всех админов"""
        user_id = update.effective_user.id
        
        if not db.is_admin(user_id):
            await update.message.reply_text("❌ Доступ запрещен!")
            return
        
        admins = db.get_all_admins()
        admin_list = "\n".join([f"• {admin_id}" for admin_id in admins])
        
        await update.message.reply_text(f"👑 Список админов:\n\n{admin_list}")
    
    def run(self):
        """Запуск бота"""
        logger.info("Бот запущен!")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    bot = PhotoBattleBot()
    bot.run()
