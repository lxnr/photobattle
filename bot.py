import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ChatMember, InputMediaPhoto
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
from datetime import datetime, timedelta
import pytz

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

db = Database()

# Глобальная переменная для приза
CURRENT_PRIZE = "777₽ или 350⭐"

# Часовой пояс Москвы
MSK = pytz.timezone('Europe/Moscow')

class PhotoBattleBot:
    def __init__(self):
        self.app = Application.builder().token(config.BOT_TOKEN).build()
        self.setup_handlers()
        self.round_tasks = {}
        self.round_end_times = {}
    
    def setup_handlers(self):
        # Команды
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("admin", self.admin_panel))
        self.app.add_handler(CommandHandler("start_round", self.start_round))
        self.app.add_handler(CommandHandler("next_round", self.next_round))
        self.app.add_handler(CommandHandler("end_battle", self.end_battle))
        self.app.add_handler(CommandHandler("stats", self.stats))
        self.app.add_handler(CommandHandler("set_prize", self.set_prize))
        
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
    
    def get_admin_menu(self):
        """Админ-панель с кнопками"""
        keyboard = [
            [InlineKeyboardButton("🎮 Начать раунд", callback_data="admin_start_round")],
            [InlineKeyboardButton("⏭ Следующий раунд", callback_data="admin_next_round")],
            [InlineKeyboardButton("🏁 Завершить батл", callback_data="admin_end_battle")],
            [InlineKeyboardButton("💰 Изменить приз", callback_data="admin_set_prize")],
            [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton("👥 Список админов", callback_data="admin_list")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    async def check_subscription(self, user_id: int) -> bool:
        """Проверка подписки на канал"""
        try:
            member = await self.app.bot.get_chat_member(config.CHANNEL_ID, user_id)
            return member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]
        except TelegramError as e:
            logger.error(f"Ошибка проверки подписки для {user_id}: {e}")
            return False
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start с реферальной системой"""
        user = update.effective_user
        args = context.args
        
        referrer_id = None
        if args and args[0].startswith('ref'):
            try:
                referrer_id = int(args[0].replace('ref', ''))
                if referrer_id == user.id:
                    referrer_id = None
            except ValueError:
                pass
        
        db.add_user(user.id, user.username, referrer_id)
        
        ref_link = f"https://t.me/{config.BOT_USERNAME}?start=ref{user.id}"
        
        welcome_text = f"""
👋 Привет! Здесь ты можешь принять участие в фотобатле!

📸 Чтобы участвовать, просто отправь мне свою фотографию

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
            await update.message.reply_text(
                "📸 Отправь свое фото для участия в батле!\n\n"
                "❗️ Используй только собственное фото",
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
                [InlineKeyboardButton("💳 купить голоса", url="https://t.me/lixxxer")]
            ]
            await update.message.reply_text(
                votes_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        elif text == "👤 профиль":
            user_stats = db.get_user_stats(user_id)
            ref_link = f"https://t.me/{config.BOT_USERNAME}?start=ref{user_id}"
            
            # Проверяем есть ли активное участие в раунде
            current_round = db.get_current_round()
            can_use_votes = False
            if current_round:
                user_photo = db.get_user_photo_in_round(user_id, current_round['id'])
                if user_photo and user_photo['status'] == 'approved' and user_stats['extra_votes'] > 0:
                    can_use_votes = True
            
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
            
            keyboard = []
            if can_use_votes:
                keyboard.append([InlineKeyboardButton("✨ использовать голоса", callback_data="use_votes")])
            
            await update.message.reply_text(
                profile_text, 
                reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
            )
        
        elif text == "💬 помощь":
            help_text = """
📸 Здесь ты можешь подать заявку на участие в фотобатле

📦 Бот сообщит о начале фотобатла, так что не блокируй его

❓ Если у тебя есть вопросы, не стесняйся спрашивать
"""
            keyboard = [
                [
                    InlineKeyboardButton("канал", url=config.CHANNEL_LINK),
                    InlineKeyboardButton("выплаты", url="https://t.me/photozalupawins")
                ],
                [
                    InlineKeyboardButton("связаться", url="https://t.me/lixxxer"),
                    InlineKeyboardButton("правила", callback_data="show_rules")
                ]
            ]
            await update.message.reply_text(
                help_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка присланных фото"""
        user = update.effective_user
        photo = update.message.photo[-1]
        
        # Проверяем, есть ли активный раунд
        current_round = db.get_current_round()
        
        # Если раунд есть и это не первый раунд - сохраняем фото для следующего первого раунда
        if current_round and current_round['number'] > 1:
            # Сохраняем фото в очередь для следующего первого раунда
            photo_id = db.add_photo_to_queue(user.id, photo.file_id)
            await update.message.reply_text(
                "✅ Фотография сохранена!\n\n"
                "🏁 Твое фото будет участвовать в следующем батле (первый раунд)",
                reply_markup=self.get_main_menu()
            )
            await self.send_photo_to_admins(photo_id, photo.file_id, user, is_queue=True)
            return
        
        # Если нет раунда - создаем очередь фото
        if not current_round:
            # Проверяем, не отправлял ли уже пользователь фото в очередь
            if db.user_has_photo_in_queue(user.id):
                await update.message.reply_text(
                    "❌ Ты уже отправил фото! Дождись начала батла.",
                    reply_markup=self.get_main_menu()
                )
                return
            
            photo_id = db.add_photo_to_queue(user.id, photo.file_id)
            await update.message.reply_text(
                "✅ Фотография отправлена на модерацию!\n\n"
                "🏁 Бот сообщит о начале фотобатла, так что не блокируй его",
                reply_markup=self.get_main_menu()
            )
            await self.send_photo_to_admins(photo_id, photo.file_id, user, is_queue=True)
            
            # Начисляем голоса рефереру
            user_data = db.get_user(user.id)
            if user_data and user_data['referrer_id']:
                user_photos_count = db.count_user_photos(user.id)
                if user_photos_count == 1:
                    db.add_referral_votes(user_data['referrer_id'], config.VOTES_PER_REFERRAL)
            return
        
        # Первый раунд активен
        if db.user_has_photo_in_round(user.id, current_round['id']):
            await update.message.reply_text(
                "❌ Ты уже отправил фото в этом раунде!",
                reply_markup=self.get_main_menu()
            )
            return
        
        photo_id = db.add_photo(
            user_id=user.id,
            file_id=photo.file_id,
            round_id=current_round['id']
        )
        
        logger.info(f"Фото #{photo_id} от пользователя {user.id} добавлено на модерацию")
        
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
        
        await self.send_photo_to_admins(photo_id, photo.file_id, user)
    
    async def send_photo_to_admins(self, photo_id: int, file_id: str, user, is_queue: bool = False):
        """Отправка фото админам для модерации"""
        keyboard = [
            [
                InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{photo_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{photo_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        queue_text = " (в очереди)" if is_queue else ""
        caption = f"""
🆔 ID фото: {photo_id}{queue_text}
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
        """Проверка и автоматическая публикация батлов"""
        try:
            unpaired_photos = db.get_unpaired_photos(round_id)
            logger.info(f"Раунд {round_id}: найдено {len(unpaired_photos)} фото без пары")
            
            pairs_count = len(unpaired_photos) // 2
            if pairs_count == 0:
                return
            
            logger.info(f"Создаем {pairs_count} новых пар")
            
            import random
            random.shuffle(unpaired_photos)
            
            # Устанавливаем время окончания раунда при публикации первого батла
            if round_id not in self.round_end_times:
                end_time = datetime.now(MSK) + timedelta(hours=2)
                self.round_end_times[round_id] = end_time
                logger.info(f"Установлено время окончания раунда {round_id}: {end_time.strftime('%H:%M')} МСК")
            
            for i in range(pairs_count):
                photo1 = unpaired_photos[i * 2]
                photo2 = unpaired_photos[i * 2 + 1]
                
                battle_id = db.create_battle(round_id, photo1['id'], photo2['id'])
                logger.info(f"Создан батл #{battle_id}")
                
                success = await self.publish_battle(battle_id, photo1, photo2, round_id)
                if success:
                    logger.info(f"✅ Батл #{battle_id} опубликован")
                    
                    # Отправляем уведомления пользователям с кнопкой "найти себя"
                    current_round = db.get_round_by_id(round_id)
                    if current_round and current_round['number'] == 1:
                        for photo in [photo1, photo2]:
                            try:
                                battle_link = f"{config.CHANNEL_LINK}/{battle_id}"
                                keyboard = [[InlineKeyboardButton("🔍 найти себя", url=battle_link)]]
                                
                                await self.app.bot.send_message(
                                    chat_id=photo['user_id'],
                                    text=f"▶️ 1 раунд фотобатла начался\n\n"
                                         f"❗️ нужно собрать минимум 8 голосов и обогнать соперника, чтобы пройти в следующий раунд\n\n"
                                         f"📝 Чтобы увеличить свои шансы на победу, попроси друзей проголосовать за тебя",
                                    reply_markup=InlineKeyboardMarkup(keyboard)
                                )
                            except:
                                pass
                
                await asyncio.sleep(2)
        
        except Exception as e:
            logger.error(f"Ошибка в check_and_publish_battles: {e}", exc_info=True)
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий на кнопки"""
        query = update.callback_query
        user_id = query.from_user.id
        data = query.data
        
        # Правила
        if data == 'show_rules':
            await query.answer()
            rules_text = """
<b>ПРАВИЛА ФОТОБАТЛА</b>

• нельзя использовать чужие фотографии!

• фотография должна содержать изображение человека;

• фотография не должна содержать материал 18+;

• использование более 1 аккаунта одним человеком;

• попытка обмана/обман администрации;

• то, что мне может не понравиться.
"""
            await query.message.reply_text(rules_text, parse_mode='HTML')
            return
        
        # Использование голосов
        if data == 'use_votes':
            await query.answer()
            
            current_round = db.get_current_round()
            if not current_round:
                await query.answer("Нет активного раунда", show_alert=True)
                return
            
            user_photo = db.get_user_photo_in_round(user_id, current_round['id'])
            if not user_photo or user_photo['status'] != 'approved':
                await query.answer("Ваше фото не участвует в батле", show_alert=True)
                return
            
            user_stats = db.get_user_stats(user_id)
            if user_stats['extra_votes'] <= 0:
                await query.answer("У вас нет дополнительных голосов", show_alert=True)
                return
            
            votes_to_use = user_stats['extra_votes']
            db.use_extra_votes(user_id, user_photo['id'], votes_to_use)
            
            await query.answer(
                f"✨ Использовано {votes_to_use} дополнительных голосов!",
                show_alert=True
            )
            
            # Обновляем кнопки в канале
            battle = db.get_battle_by_photo(user_photo['id'])
            if battle and battle['message_id']:
                try:
                    votes = db.get_battle_votes(battle['id'])
                    await self.update_battle_buttons(battle['id'], battle['message_id'], votes, battle['photo1_id'], battle['photo2_id'])
                except Exception as e:
                    logger.error(f"Ошибка обновления кнопок: {e}")
            
            return
        
        # Админские кнопки
        if data.startswith('admin_'):
            await query.answer()
            
            if not db.is_admin(user_id):
                await query.answer("❌ Доступно только админам!", show_alert=True)
                return
            
            if data == 'admin_start_round':
                await self.start_round(update, context)
            elif data == 'admin_next_round':
                await self.next_round(update, context)
            elif data == 'admin_end_battle':
                await self.end_battle(update, context)
            elif data == 'admin_set_prize':
                await query.message.reply_text(
                    "💰 Чтобы изменить приз, используйте команду:\n"
                    "/set_prize Ваш новый приз\n\n"
                    "Пример: /set_prize 1000₽ или 500⭐"
                )
            elif data == 'admin_stats':
                await self.stats(update, context)
            elif data == 'admin_list':
                admins = db.get_all_admins()
                admin_list = "\n".join([f"• {admin_id}" for admin_id in admins])
                await query.message.reply_text(f"👑 Список админов:\n\n{admin_list}")
            return
        
        # Модерация фото
        if data.startswith(('approve_', 'reject_')):
            await query.answer()
            
            if not db.is_admin(user_id):
                await query.answer("❌ Доступно только админам!", show_alert=True)
                return
            
            action, photo_id = data.split('_')
            photo_id = int(photo_id)
            
            if action == 'approve':
                photo = db.get_photo_by_id(photo_id)
                if not photo:
                    await query.answer("Фото не найдено", show_alert=True)
                    return
                
                db.update_photo_status(photo_id, 'approved')
                await query.edit_message_caption(
                    caption=query.message.caption + "\n\n✅ ОДОБРЕНО"
                )
                
                try:
                    await self.app.bot.send_message(
                        chat_id=photo['user_id'],
                        text="✅ Ваше фото одобрено и участвует в батле!\n\n"
                             "Следите за каналом - скоро начнется голосование!",
                        reply_markup=self.get_main_menu()
                    )
                except:
                    pass
                
                logger.info(f"Фото #{photo_id} одобрено")
                
                if photo['round_id']:
                    await self.check_and_publish_battles(photo['round_id'])
                
            else:
                db.update_photo_status(photo_id, 'rejected')
                await query.edit_message_caption(
                    caption=query.message.caption + "\n\n❌ ОТКЛОНЕНО"
                )
            return
        
        # Голосование
        if data.startswith('vote_'):
            is_subscribed = await self.check_subscription(user_id)
            if not is_subscribed:
                await query.answer(
                    "❌ Чтобы голосовать, нужно подписаться на канал!",
                    show_alert=True
                )
                return
            
            parts = data.split('_')
            battle_id = int(parts[1])
            photo_id = int(parts[2])
            
            if db.user_voted_in_battle(user_id, battle_id):
                await query.answer(
                    "❌ Вы уже проголосовали в этом батле!",
                    show_alert=True
                )
                return
            
            success = db.add_vote(user_id, battle_id, photo_id)
            
            if success:
                votes = db.get_battle_votes(battle_id)
                
                battle = db.get_battle_by_id(battle_id)
                await self.update_battle_buttons(battle_id, query.message.message_id, votes, battle['photo1_id'], battle['photo2_id'])
                
                await query.answer(
                    "🔥 Голос учтён!\n\n"
                    "❗️ При отписке от канала голос не будет засчитан\n\n"
                    "⏱ Голос зачислится в течение минуты",
                    show_alert=True
                )
            else:
                await query.answer(
                    "❌ Ошибка при голосовании. Попробуйте снова.",
                    show_alert=True
                )
    
    async def update_battle_buttons(self, battle_id: int, message_id: int, votes: dict, photo1_id: int, photo2_id: int):
        """Обновление кнопок с количеством голосов"""
        try:
            keyboard = [
                [
                    InlineKeyboardButton(f"лево {votes['photo1']}", callback_data=f"vote_{battle_id}_{photo1_id}"),
                    InlineKeyboardButton(f"право {votes['photo2']}", callback_data=f"vote_{battle_id}_{photo2_id}")
                ]
            ]
            
            await self.app.bot.edit_message_reply_markup(
                chat_id=config.CHANNEL_ID,
                message_id=message_id,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Ошибка обновления кнопок: {e}")
    
    async def publish_battle(self, battle_id: int, photo1: dict, photo2: dict, round_id: int) -> bool:
        """Публикация батла в канал"""
        try:
            current_round = db.get_round_by_id(round_id)
            round_number = current_round['number'] if current_round else 1
            
            min_votes_required = config.MIN_VOTES * round_number
            
            end_time = self.round_end_times.get(round_id)
            if end_time:
                time_str = end_time.strftime("%H:%M")
            else:
                time_str = "скоро"
            
            # photo1 СЛЕВА, photo2 СПРАВА
            media = [
                InputMediaPhoto(media=photo1['file_id']),
                InputMediaPhoto(media=photo2['file_id'])
            ]
            
            messages = await self.app.bot.send_media_group(
                chat_id=config.CHANNEL_ID,
                media=media
            )
            
            for msg in messages:
                db.add_battle_message(battle_id, msg.message_id)
            
            # Кнопка "лево" = photo1, "право" = photo2
            keyboard = [
                [
                    InlineKeyboardButton("лево", callback_data=f"vote_{battle_id}_{photo1['id']}"),
                    InlineKeyboardButton("право", callback_data=f"vote_{battle_id}_{photo2['id']}")
                ]
            ]
            
            caption = f"""
🔥 МОНСТРЫ ТТ

⚜️ {round_number} раунд
💰 ПРИЗ: {CURRENT_PRIZE}

👉<a href="https://t.me/{config.BOT_USERNAME}">ссылка для голосования</a>👈

🗣 нужно собрать минимум {min_votes_required} голосов

✨<a href="https://t.me/{config.BOT_USERNAME}">нажми, чтобы принять участие</a>

🧑‍💼 итоги сегодня в {time_str} по МСК
"""
            
            msg = await self.app.bot.send_message(
                chat_id=config.CHANNEL_ID,
                text=caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            
            db.update_battle_message_id(battle_id, msg.message_id)
            db.add_battle_message(battle_id, msg.message_id)
            
            logger.info(f"✅ Батл #{battle_id} опубликован")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка публикации батла #{battle_id}: {e}", exc_info=True)
            return False
    
    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Админ-панель"""
        user_id = update.effective_user.id
        
        if not db.is_admin(user_id):
            await update.message.reply_text("❌ Доступ запрещен!")
            return
        
        current_round = db.get_current_round()
        pending = db.count_photos_by_status('pending', current_round['id'] if current_round else None)
        approved = db.count_photos_by_status('approved', current_round['id'] if current_round else None)
        battles = db.count_battles_in_round(current_round['id']) if current_round else 0
        
        admin_text = f"""
👑 АДМИН-ПАНЕЛЬ

📊 Текущий раунд: {current_round['number'] if current_round else 'Не создан'}
📸 На модерации: {pending}
✅ Одобрено: {approved}
⚔️ Батлов: {battles}
💰 Текущий приз: {CURRENT_PRIZE}

Используйте кнопки ниже для управления:
"""
        
        await update.message.reply_text(admin_text, reply_markup=self.get_admin_menu())
    
    async def start_round(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начать новый раунд"""
        user_id = update.effective_user.id if update.effective_user else None
        
        if user_id and not db.is_admin(user_id):
            return
        
        current_round = db.get_current_round()
        if current_round:
            msg = "❌ Уже есть активный раунд!"
            if update.message:
                await update.message.reply_text(msg)
            elif update.callback_query:
                await update.callback_query.message.reply_text(msg)
            return
        
        # Переносим фото из очереди в новый раунд
        round_id = db.create_round(round_number=1)
        db.move_queue_to_round(round_id)
        
        logger.info(f"Создан раунд #{round_id}")
        
        task = asyncio.create_task(self.round_timer(round_id, hours=2))
        self.round_tasks[round_id] = task
        
        # Публикуем батлы
        await self.check_and_publish_battles(round_id)
        
        msg = f"✅ Раунд 1 начат!"
        if update.message:
            await update.message.reply_text(msg)
        elif update.callback_query:
            await update.callback_query.message.reply_text(msg)
    
    async def round_timer(self, round_id: int, hours: int = 2):
        """Таймер раунда"""
        try:
            await asyncio.sleep(hours * 3600)
            current_round = db.get_round_by_id(round_id)
            if current_round and current_round['status'] == 'active':
                logger.info(f"Таймер раунда {round_id} истек")
        except asyncio.CancelledError:
            logger.info(f"Таймер раунда {round_id} отменен")
    
    def get_battle_winners(self, round_id: int):
        """Получить победителей батлов в раунде"""
        battles = db.get_round_battles(round_id)
        winners = []
        losers = []
        
        for battle in battles:
            votes = db.get_battle_votes(battle['id'])
            photo1 = db.get_photo_by_id(battle['photo1_id'])
            photo2 = db.get_photo_by_id(battle['photo2_id'])
            
            # Получаем username для обоих фото
            user1 = db.get_user(photo1['user_id'])
            user2 = db.get_user(photo2['user_id'])
            
            photo1_with_username = {**photo1, 'username': user1['username'] if user1 else None}
            photo2_with_username = {**photo2, 'username': user2['username'] if user2 else None}
            
            if votes['photo1'] > votes['photo2']:
                winners.append({**photo1_with_username, 'votes': votes['photo1']})
                losers.append({**photo2_with_username, 'votes': votes['photo2']})
            elif votes['photo2'] > votes['photo1']:
                winners.append({**photo2_with_username, 'votes': votes['photo2']})
                losers.append({**photo1_with_username, 'votes': votes['photo1']})
            else:
                import random
                if random.choice([True, False]):
                    winners.append({**photo1_with_username, 'votes': votes['photo1']})
                    losers.append({**photo2_with_username, 'votes': votes['photo2']})
                else:
                    winners.append({**photo2_with_username, 'votes': votes['photo2']})
                    losers.append({**photo1_with_username, 'votes': votes['photo1']})
        
        return winners, losers
    
    async def delete_round_messages(self, round_id: int):
        """Удаление сообщений раунда"""
        try:
            messages = db.get_round_messages(round_id)
            for msg_id in messages:
                try:
                    await self.app.bot.delete_message(
                        chat_id=config.CHANNEL_ID,
                        message_id=msg_id
                    )
                    await asyncio.sleep(0.1)
                except:
                    pass
            logger.info(f"Удалено {len(messages)} сообщений")
        except Exception as e:
            logger.error(f"Ошибка удаления сообщений: {e}")
    
    async def next_round(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Следующий раунд"""
        user_id = update.effective_user.id if update.effective_user else None
        
        if user_id and not db.is_admin(user_id):
            return
        
        current_round = db.get_current_round()
        if not current_round:
            msg = "❌ Нет активного раунда!"
            if update.message:
                await update.message.reply_text(msg)
            elif update.callback_query:
                await update.callback_query.message.reply_text(msg)
            return
        
        try:
            winners, losers = self.get_battle_winners(current_round['id'])
            
            for winner in winners:
                try:
                    await self.app.bot.send_message(
                        chat_id=winner['user_id'],
                        text=f"✅ Поздравляем! Твое фото прошло в следующий раунд!\n\n"
                             f"📊 Ты набрал {winner['votes']} голосов и победил в своей паре!",
                        reply_markup=self.get_main_menu()
                    )
                except:
                    pass
            
            for loser in losers:
                try:
                    await self.app.bot.send_message(
                        chat_id=loser['user_id'],
                        text=f"😔 К сожалению, твое фото не прошло в следующий раунд\n\n"
                             f"📊 Ты набрал {loser['votes']} голосов, но соперник набрал больше\n\n"
                             f"💪 Не расстраивайся! Участвуй в следующем батле!",
                        reply_markup=self.get_main_menu()
                    )
                except:
                    pass
            
            await self.delete_round_messages(current_round['id'])
            
            if len(winners) == 1:
                winner = winners[0]
                db.end_round(current_round['id'])
                
                try:
                    await self.app.bot.send_message(
                        chat_id=winner['user_id'],
                        text=f"🏆 ПОЗДРАВЛЯЕМ! ТЫ ПОБЕДИТЕЛЬ ФОТОБАТЛА!\n\n"
                             f"💰 Твой приз: {CURRENT_PRIZE}\n\n"
                             f"🎉 Свяжись с админом @lixxxer для получения приза!",
                        reply_markup=self.get_main_menu()
                    )
                except:
                    pass
                
                username = f"@{winner['username']}" if winner.get('username') else "Аноним"
                msg = f"✅ Батл завершен! Победитель: {username} ({winner['votes']} голосов)"
            
            elif len(winners) < 2:
                db.end_round(current_round['id'])
                msg = "⚠️ Недостаточно победителей для следующего раунда. Батл завершен."
            
            else:
                next_round_number = current_round['number'] + 1
                new_round_id = db.create_round(round_number=next_round_number)
                db.update_round_status(current_round['id'], 'completed')
                
                task = asyncio.create_task(self.round_timer(new_round_id, hours=2))
                self.round_tasks[new_round_id] = task
                
                await self.publish_battles_from_winners(new_round_id, winners)
                
                msg = f"✅ Раунд {next_round_number} начат! Участников: {len(winners)}"
            
            if update.message:
                await update.message.reply_text(msg)
            elif update.callback_query:
                await update.callback_query.message.reply_text(msg)
                
        except Exception as e:
            logger.error(f"Ошибка в next_round: {e}", exc_info=True)
    
    async def publish_battles_from_winners(self, round_id: int, winners: list):
        """Публикация батлов из победителей"""
        import random
        random.shuffle(winners)
        
        for i in range(0, len(winners) - 1, 2):
            photo1 = winners[i]
            photo2 = winners[i + 1]
            
            battle_id = db.create_battle(round_id, photo1['id'], photo2['id'])
            await self.publish_battle(battle_id, photo1, photo2, round_id)
            await asyncio.sleep(2)
    
    async def end_battle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Завершить батл"""
        user_id = update.effective_user.id if update.effective_user else None
        
        if user_id and not db.is_admin(user_id):
            return
        
        current_round = db.get_current_round()
        if not current_round:
            msg = "❌ Нет активного раунда!"
            if update.message:
                await update.message.reply_text(msg)
            elif update.callback_query:
                await update.callback_query.message.reply_text(msg)
            return
        
        try:
            if current_round['id'] in self.round_tasks:
                self.round_tasks[current_round['id']].cancel()
            
            round_photos = db.get_round_photos_with_votes(current_round['id'])
            
            if not round_photos:
                msg = "❌ Нет фото в текущем раунде"
                if update.message:
                    await update.message.reply_text(msg)
                elif update.callback_query:
                    await update.callback_query.message.reply_text(msg)
                return
            
            round_photos.sort(key=lambda x: x['votes'], reverse=True)
            winner = round_photos[0]
            
            db.end_round(current_round['id'])
            await self.delete_round_messages(current_round['id'])
            
            try:
                await self.app.bot.send_message(
                    chat_id=winner['user_id'],
                    text=f"🏆 ПОЗДРАВЛЯЕМ! ТЫ ПОБЕДИТЕЛЬ ФОТОБАТЛА!\n\n"
                         f"💰 Твой приз: {CURRENT_PRIZE}\n\n"
                         f"📊 Ты набрал {winner['votes']} голосов!\n\n"
                         f"🎉 Свяжись с админом @lixxxer для получения приза!",
                    reply_markup=self.get_main_menu()
                )
            except:
                pass
            
            username = f"@{winner['username']}" if winner.get('username') else "Аноним"
            result_text = f"🏆 Фотобатл завершен!\n\n"
            result_text += f"👑 Победитель: {username}\n"
            result_text += f"📊 Голосов: {winner['votes']}\n\n"
            
            if len(round_photos) > 1:
                result_text += "Топ участников:\n"
                for idx, photo in enumerate(round_photos[:10], 1):
                    emoji = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
                    username = f"@{photo['username']}" if photo.get('username') else "Аноним"
                    result_text += f"{emoji} {username} - {photo['votes']} голосов\n"
            
            if update.message:
                await update.message.reply_text(result_text)
            elif update.callback_query:
                await update.callback_query.message.reply_text(result_text)
                
        except Exception as e:
            logger.error(f"Ошибка в end_battle: {e}", exc_info=True)
    
    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика"""
        stats = db.get_bot_stats()
        
        stats_text = f"""
📊 СТАТИСТИКА:

👥 Пользователей: {stats['total_users']}
📸 Фото: {stats['total_photos']}
⚔️ Батлов: {stats['total_battles']}
🗳 Голосов: {stats['total_votes']}
"""
        
        if update.message:
            await update.message.reply_text(stats_text)
        elif update.callback_query:
            await update.callback_query.message.reply_text(stats_text)
    
    async def set_prize(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Изменить приз"""
        global CURRENT_PRIZE
        
        if not db.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Доступ запрещен!")
            return
        
        if not context.args:
            await update.message.reply_text("Использование: /set_prize Ваш приз\nПример: /set_prize 1000₽")
            return
        
        CURRENT_PRIZE = " ".join(context.args)
        await update.message.reply_text(f"✅ Приз изменен на: {CURRENT_PRIZE}")
    
    def run(self):
        """Запуск бота"""
        logger.info("🤖 Бот запущен!")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    try:
        bot = PhotoBattleBot()
        bot.run()
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
