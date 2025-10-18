import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
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
        
        # Callback кнопки
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
    
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
                    referrer_id = None  # Нельзя быть рефералом самому себе
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
        
        keyboard = [
            [InlineKeyboardButton("👤 Мой профиль", callback_data="profile")],
            [InlineKeyboardButton("📖 Правила", callback_data="rules")],
            [InlineKeyboardButton("📢 Канал с батлами", url=config.CHANNEL_LINK)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка присланных фото"""
        user = update.effective_user
        photo = update.message.photo[-1]
        
        # Проверка: активен ли раунд
        current_round = db.get_current_round()
        if not current_round or current_round['status'] != 'active':
            await update.message.reply_text(
                "❌ Сейчас нет активного раунда. Дождись начала нового батла!"
            )
            return
        
        # Проверка: не отправлял ли уже фото в этом раунде
        if db.user_has_photo_in_round(user.id, current_round['id']):
            await update.message.reply_text(
                "❌ Ты уже отправил фото в этом раунде!"
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
            # Проверяем, первое ли это фото пользователя
            user_photos_count = db.count_user_photos(user.id)
            if user_photos_count == 1:  # Первое фото
                db.add_referral_votes(user_data['referrer_id'], config.VOTES_PER_REFERRAL)
        
        await update.message.reply_text(
            "✅ Фотография отправлена на модерацию!\n\n"
            "🏁 Бот сообщит о начале фотобатла, так что не блокируй его"
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
                keyboard = [[InlineKeyboardButton("📢 Подписаться на канал", url=config.CHANNEL_LINK)]]
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
        
        # Профиль пользователя
        elif data == 'profile':
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
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_start")]]
            await query.edit_message_text(profile_text, reply_markup=InlineKeyboardMarkup(keyboard))
        
        # Правила
        elif data == 'rules':
            rules_text = """
📖 ПРАВИЛА ФОТОБАТЛА:

1️⃣ Отправь свою фотографию где видно лицо
2️⃣ Фото должно быть вертикальным или квадратным
3️⃣ Используй только собственные изображения
4️⃣ Админы проверят и одобрят твое фото
5️⃣ Когда наберется минимум 8 участников, начнется батл
6️⃣ Батл проходит между двумя фото - побеждает та, что наберет больше голосов
7️⃣ Чтобы пройти в следующий раунд, нужно набрать минимум 8 голосов
8️⃣ Приглашай друзей по реферальной ссылке - за каждого друга, который отправит фото, получишь 3 голоса!

🔔 Для голосования нужно быть подписанным на канал

Удачи! 🔥
"""
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_start")]]
            await query.edit_message_text(rules_text, reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif data == 'back_to_start':
            await self.start_command(update, context)
    
    async def update_vote_count_delayed(self, battle_id: int, message):
        """Обновление счетчика голосов через минуту"""
        await asyncio.sleep(60)  # Ждем минуту
        
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
        
        admin_text = f"""
👑 АДМИН-ПАНЕЛЬ

📊 Текущий раунд: {current_round['number'] if current_round else 'Не создан'}
📸 На модерации: {pending_count}
✅ Одобрено фото: {approved_count}

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
        
        # Проверяем, нет ли уже активного раунда
        current_round = db.get_current_round()
        if current_round:
            await update.message.reply_text("❌ Уже есть активный раунд! Сначала завершите его командой /end_battle")
            return
        
        # Создаем новый раунд (номер 1)
        round_id = db.create_round(round_number=1)
        
        # Уведомляем всех пользователей
        users = db.get_all_users()
        message_text = """
🔥 Начался новый раунд фотобатла!

📸 Отправь свою фотографию для участия!
⏱ Срочно жду пару фоток!!!!!!!
"""
        
        for user in users:
            try:
                await self.app.bot.send_message(chat_id=user['telegram_id'], text=message_text)
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
        
        # Получаем победителей текущего раунда
        winners = db.get_round_winners(current_round['id'], min_votes=config.MIN_VOTES)
        
        if len(winners) < 2:
            await update.message.reply_text(
                f"❌ Недостаточно победителей! Минимум 2 фото с {config.MIN_VOTES}+ голосами."
            )
            return
        
        # Завершаем текущий раунд
        db.end_round(current_round['id'])
        
        # Создаем новый раунд
        next_round_number = current_round['number'] + 1
        new_round_id = db.create_round(round_number=next_round_number)
        
        # Публикуем батлы с победителями
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
                InlineKeyboardButton("◀️ Лево", callback_data=f"vote_{battle_id}_{photo1['id']}"),
                InlineKeyboardButton("Право ▶️", callback_data=f"vote_{battle_id}_{photo2['id']}")
            ],
            [InlineKeyboardButton("🔍 Найти себя", url=f"https://t.me/{config.BOT_USERNAME}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        caption = f"""
🔥 ФОТОБАТЛ №{battle_id}

◀️ Лево: 0 голосов
Право ▶️: 0 голосов

Голосуй за лучшее фото!
"""
        
        try:
            # Отправляем первое фото с кнопками
            message = await self.app.bot.send_photo(
                chat_id=config.CHANNEL_ID,
                photo=photo1['file_id'],
                caption=caption,
                reply_markup=reply_markup
            )
            
            # Отправляем второе фото
            await self.app.bot.send_photo(
                chat_id=config.CHANNEL_ID,
                photo=photo2['file_id']
            )
            
            # Сохраняем message_id для обновления счетчика
            db.update_battle_message_id(battle_id, message.message_id)
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
        
        # Получаем финальных победителей
        winners = db.get_round_winners(current_round['id'], min_votes=config.MIN_VOTES)
        
        # Завершаем раунд
        db.end_round(current_round['id'])
        
        # Формируем сообщение с результатами
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
        
        # Уведомляем победителей
        for winner in winners:
            try:
                await self.app.bot.send_message(
                    chat_id=winner['user_id'],
                    text=f"🎉 Поздравляем! Ты прошел в финал с {winner['votes']} голосами!"
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
