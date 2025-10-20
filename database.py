import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import config


class Database:
    def __init__(self):
        try:
            self.conn = psycopg2.connect(
                host=config.DB_HOST,
                database=config.DB_NAME,
                user=config.DB_USER,
                password=config.DB_PASSWORD,
                port=config.DB_PORT
            )
            self.conn.autocommit = True
            self.create_tables()
            self.init_admins()
        except Exception as e:
            print(f"❌ Ошибка подключения к БД: {e}")
            raise
    
    def create_tables(self):
        """Создание всех таблиц БД"""
        with self.conn.cursor() as cur:
            # Таблица для хранения ID сообщений батлов
            cur.execute("""
                CREATE TABLE IF NOT EXISTS battle_messages (
                    id SERIAL PRIMARY KEY,
                    battle_id INTEGER REFERENCES battles(id),
                    message_id BIGINT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Таблица пользователей
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    username VARCHAR(255),
                    referrer_id BIGINT,
                    extra_votes INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Таблица админов
            cur.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Таблица раундов
            cur.execute("""
                CREATE TABLE IF NOT EXISTS rounds (
                    id SERIAL PRIMARY KEY,
                    number INTEGER NOT NULL,
                    status VARCHAR(50) DEFAULT 'active',
                    min_votes INTEGER DEFAULT 8,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ended_at TIMESTAMP
                )
            """)
            
            # Таблица фотографий
            cur.execute("""
                CREATE TABLE IF NOT EXISTS photos (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    file_id VARCHAR(255) NOT NULL,
                    round_id INTEGER REFERENCES rounds(id),
                    status VARCHAR(50) DEFAULT 'pending',
                    votes INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(telegram_id)
                )
            """)
            
            # Таблица батлов
            cur.execute("""
                CREATE TABLE IF NOT EXISTS battles (
                    id SERIAL PRIMARY KEY,
                    round_id INTEGER REFERENCES rounds(id),
                    photo1_id INTEGER REFERENCES photos(id),
                    photo2_id INTEGER REFERENCES photos(id),
                    message_id BIGINT,
                    status VARCHAR(50) DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Таблица голосов
            cur.execute("""
                CREATE TABLE IF NOT EXISTS votes (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    battle_id INTEGER REFERENCES battles(id),
                    photo_id INTEGER REFERENCES photos(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(telegram_id),
                    UNIQUE(user_id, battle_id)
                )
            """)
            
            # Индексы для оптимизации
            cur.execute("CREATE INDEX IF NOT EXISTS idx_photos_round ON photos(round_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_photos_user ON photos(user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_battles_round ON battles(round_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_votes_battle ON votes(battle_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_votes_user ON votes(user_id)")
            
            # Таблица для хранения ID сообщений батлов
            cur.execute("""
                CREATE TABLE IF NOT EXISTS battle_messages (
                    id SERIAL PRIMARY KEY,
                    battle_id INTEGER REFERENCES battles(id),
                    message_id BIGINT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_battle_messages ON battle_messages(battle_id)")
    
    def init_admins(self):
        """Инициализация начальных админов из config"""
        with self.conn.cursor() as cur:
            for admin_id in config.ADMIN_IDS:
                cur.execute("""
                    INSERT INTO admins (telegram_id)
                    VALUES (%s)
                    ON CONFLICT (telegram_id) DO NOTHING
                """, (admin_id,))
    
    def is_admin(self, telegram_id: int) -> bool:
        """Проверить, является ли пользователь админом"""
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM admins WHERE telegram_id = %s", (telegram_id,))
            return cur.fetchone()[0] > 0
    
    def add_admin(self, telegram_id: int):
        """Добавить админа"""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO admins (telegram_id)
                VALUES (%s)
                ON CONFLICT (telegram_id) DO NOTHING
            """, (telegram_id,))
    
    def remove_admin(self, telegram_id: int):
        """Удалить админа"""
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM admins WHERE telegram_id = %s", (telegram_id,))
    
    def get_all_admins(self):
        """Получить список всех админов"""
        with self.conn.cursor() as cur:
            cur.execute("SELECT telegram_id FROM admins")
            return [row[0] for row in cur.fetchall()]
    
    def add_user(self, telegram_id: int, username: str = None, referrer_id: int = None):
        """Добавление нового пользователя"""
        with self.conn.cursor() as cur:
            try:
                cur.execute("""
                    INSERT INTO users (telegram_id, username, referrer_id)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (telegram_id) DO UPDATE
                    SET username = EXCLUDED.username
                    RETURNING (xmax = 0) AS inserted
                """, (telegram_id, username, referrer_id))
                result = cur.fetchone()
                return result[0] if result else False
            except Exception as e:
                print(f"Ошибка добавления пользователя: {e}")
                return False
    
    def get_user(self, telegram_id: int):
        """Получить пользователя по telegram_id"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
            return cur.fetchone()
    
    def get_all_users(self):
        """Получить всех пользователей"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users")
            return cur.fetchall()
    
    def add_referral_votes(self, referrer_id: int, votes: int):
        """Добавить дополнительные голоса рефереру"""
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE users 
                SET extra_votes = extra_votes + %s
                WHERE telegram_id = %s
            """, (votes, referrer_id))
    
    def count_user_photos(self, user_id: int) -> int:
        """Подсчитать количество фото пользователя"""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM photos
                WHERE user_id = %s AND status != 'rejected'
            """, (user_id,))
            return cur.fetchone()[0]
    
    def create_round(self, round_number: int = 1):
        """Создать новый раунд"""
        with self.conn.cursor() as cur:
            # Завершаем предыдущий раунд
            cur.execute("UPDATE rounds SET status = 'ended', ended_at = NOW() WHERE status = 'active'")
            
            # Создаем новый раунд
            cur.execute("""
                INSERT INTO rounds (number, status, min_votes)
                VALUES (%s, 'active', %s)
                RETURNING id
            """, (round_number, config.MIN_VOTES))
            
            return cur.fetchone()[0]
    
    def get_current_round(self):
        """Получить текущий активный раунд"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM rounds WHERE status = 'active' ORDER BY id DESC LIMIT 1")
            return cur.fetchone()
    
    def end_round(self, round_id: int):
        """Завершить раунд"""
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE rounds 
                SET status = 'ended', ended_at = NOW()
                WHERE id = %s
            """, (round_id,))
    
    def update_round_status(self, round_id: int, status: str):
        """Обновить статус раунда"""
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE rounds 
                SET status = %s
                WHERE id = %s
            """, (status, round_id))
    
    def add_photo(self, user_id: int, file_id: str, round_id: int):
        """Добавить фото на модерацию"""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO photos (user_id, file_id, round_id, status)
                VALUES (%s, %s, %s, 'pending')
                RETURNING id
            """, (user_id, file_id, round_id))
            return cur.fetchone()[0]
    
    def get_photo_by_id(self, photo_id: int):
        """Получить фото по ID"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM photos WHERE id = %s", (photo_id,))
            return cur.fetchone()
    
    def update_photo_status(self, photo_id: int, status: str):
        """Обновить статус фото (approved/rejected)"""
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE photos SET status = %s WHERE id = %s
            """, (status, photo_id))
    
    def user_has_photo_in_round(self, user_id: int, round_id: int):
        """Проверить, отправлял ли пользователь фото в этом раунде"""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM photos
                WHERE user_id = %s AND round_id = %s AND status != 'rejected'
            """, (user_id, round_id))
            return cur.fetchone()[0] > 0
    
    def count_photos_by_status(self, status: str, round_id: int = None):
        """Подсчет фото по статусу"""
        with self.conn.cursor() as cur:
            if round_id:
                cur.execute("""
                    SELECT COUNT(*) FROM photos
                    WHERE status = %s AND round_id = %s
                """, (status, round_id))
            else:
                cur.execute("SELECT COUNT(*) FROM photos WHERE status = %s", (status,))
            return cur.fetchone()[0]
    
    def count_approved_photos(self, round_id: int):
        """Подсчет одобренных фото в раунде"""
        return self.count_photos_by_status('approved', round_id)
    
    def get_approved_photos(self, round_id: int, limit: int = None):
        """Получить одобренные фото"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = """
                SELECT * FROM photos
                WHERE round_id = %s AND status = 'approved'
                ORDER BY created_at
            """
            if limit:
                query += f" LIMIT {limit}"
            
            cur.execute(query, (round_id,))
            return cur.fetchall()
    
    def get_unpaired_photos(self, round_id: int):
        """Получить одобренные фото которые еще не в батлах"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT p.* FROM photos p
                WHERE p.round_id = %s 
                  AND p.status = 'approved'
                  AND p.id NOT IN (
                      SELECT photo1_id FROM battles WHERE round_id = %s
                      UNION
                      SELECT photo2_id FROM battles WHERE round_id = %s
                  )
                ORDER BY p.created_at
            """, (round_id, round_id, round_id))
            return cur.fetchall()
    
    def count_battles_in_round(self, round_id: int):
        """Подсчитать количество батлов в раунде"""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM battles WHERE round_id = %s
            """, (round_id,))
            return cur.fetchone()[0]
    
    def get_round_battles(self, round_id: int):
        """Получить все батлы раунда"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM battles
                WHERE round_id = %s
                ORDER BY id
            """, (round_id,))
            return cur.fetchall()
    
    def create_battle(self, round_id: int, photo1_id: int, photo2_id: int):
        """Создать батл между двумя фото"""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO battles (round_id, photo1_id, photo2_id, status)
                VALUES (%s, %s, %s, 'active')
                RETURNING id
            """, (round_id, photo1_id, photo2_id))
            return cur.fetchone()[0]
    
    def update_battle_message_id(self, battle_id: int, message_id: int):
        """Сохранить message_id батла"""
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE battles SET message_id = %s WHERE id = %s
            """, (message_id, battle_id))
    
    def add_vote(self, user_id: int, battle_id: int, photo_id: int):
        """Добавить голос"""
        with self.conn.cursor() as cur:
            try:
                # Добавляем голос
                cur.execute("""
                    INSERT INTO votes (user_id, battle_id, photo_id)
                    VALUES (%s, %s, %s)
                """, (user_id, battle_id, photo_id))
                
                # Увеличиваем счетчик голосов у фото
                cur.execute("""
                    UPDATE photos SET votes = votes + 1 WHERE id = %s
                """, (photo_id,))
                
                return True
            except psycopg2.IntegrityError:
                # Пользователь уже голосовал в этом батле
                return False
    
    def user_voted_in_battle(self, user_id: int, battle_id: int):
        """Проверить, голосовал ли пользователь в этом батле"""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM votes
                WHERE user_id = %s AND battle_id = %s
            """, (user_id, battle_id))
            return cur.fetchone()[0] > 0
    
    def get_battle_votes(self, battle_id: int):
        """Получить количество голосов в батле"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    b.photo1_id,
                    b.photo2_id,
                    COALESCE(SUM(CASE WHEN v.photo_id = b.photo1_id THEN 1 ELSE 0 END), 0) as photo1_votes,
                    COALESCE(SUM(CASE WHEN v.photo_id = b.photo2_id THEN 1 ELSE 0 END), 0) as photo2_votes
                FROM battles b
                LEFT JOIN votes v ON v.battle_id = b.id
                WHERE b.id = %s
                GROUP BY b.id, b.photo1_id, b.photo2_id
            """, (battle_id,))
            
            result = cur.fetchone()
            if not result:
                return {'photo1': 0, 'photo2': 0}
            
            return {
                'photo1': result['photo1_votes'],
                'photo2': result['photo2_votes']
            }
    
    def get_round_winners(self, round_id: int, min_votes: int = 8):
        """Получить победителей раунда (фото с минимальным кол-вом голосов)"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT p.*, u.username
                FROM photos p
                JOIN users u ON u.telegram_id = p.user_id
                WHERE p.round_id = %s 
                  AND p.status = 'approved'
                  AND p.votes >= %s
                ORDER BY p.votes DESC
            """, (round_id, min_votes))
            return cur.fetchall()
    
    def get_round_photos_with_votes(self, round_id: int):
        """Получить все фото раунда с количеством голосов"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT p.*, u.username
                FROM photos p
                JOIN users u ON u.telegram_id = p.user_id
                WHERE p.round_id = %s 
                  AND p.status = 'approved'
                ORDER BY p.votes DESC
            """, (round_id,))
            return cur.fetchall()
    
    def get_user_stats(self, telegram_id: int):
        """Статистика пользователя"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Получаем extra_votes из таблицы пользователей
            cur.execute("""
                SELECT extra_votes FROM users WHERE telegram_id = %s
            """, (telegram_id,))
            user = cur.fetchone()
            extra_votes = user['extra_votes'] if user else 0
            
            # Количество активных рефералов
            cur.execute("""
                SELECT COUNT(DISTINCT u.telegram_id) as active_referrals
                FROM users u
                WHERE u.referrer_id = %s
                  AND EXISTS (
                      SELECT 1 FROM photos p 
                      WHERE p.user_id = u.telegram_id 
                        AND p.status != 'rejected'
                  )
            """, (telegram_id,))
            active_referrals = cur.fetchone()['active_referrals']
            
            # Количество сыгранных батлов
            cur.execute("""
                SELECT COUNT(DISTINCT b.id) as played
                FROM battles b
                JOIN photos p ON (p.id = b.photo1_id OR p.id = b.photo2_id)
                WHERE p.user_id = %s AND b.status = 'ended'
            """, (telegram_id,))
            played = cur.fetchone()['played']
            
            # Количество побед
            cur.execute("""
                SELECT COUNT(*) as wins
                FROM (
                    SELECT 
                        b.id,
                        p1.votes as votes1,
                        p2.votes as votes2,
                        p1.user_id as user1,
                        p2.user_id as user2
                    FROM battles b
                    JOIN photos p1 ON p1.id = b.photo1_id
                    JOIN photos p2 ON p2.id = b.photo2_id
                    WHERE b.status = 'ended'
                ) sub
                WHERE (votes1 > votes2 AND user1 = %s) OR (votes2 > votes1 AND user2 = %s)
            """, (telegram_id, telegram_id))
            wins = cur.fetchone()['wins']
            
            return {
                'active_referrals': active_referrals,
                'played': played,
                'wins': wins,
                'extra_votes': extra_votes
            }
    
    def get_round_by_id(self, round_id: int):
        """Получить раунд по ID"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM rounds WHERE id = %s", (round_id,))
            return cur.fetchone()
    
    def save_battle_messages(self, battle_id: int, message_ids: list):
        """Сохранить ID сообщений батла"""
        with self.conn.cursor() as cur:
            for msg_id in message_ids:
                cur.execute("""
                    INSERT INTO battle_messages (battle_id, message_id)
                    VALUES (%s, %s)
                """, (battle_id, msg_id))
    
    def add_battle_message(self, battle_id: int, message_id: int):
        """Добавить ID сообщения батла"""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO battle_messages (battle_id, message_id)
                VALUES (%s, %s)
            """, (battle_id, message_id))
    
    def get_round_messages(self, round_id: int):
        """Получить все ID сообщений раунда"""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT bm.message_id
                FROM battle_messages bm
                JOIN battles b ON b.id = bm.battle_id
                WHERE b.round_id = %s
            """, (round_id,))
            return [row[0] for row in cur.fetchall()]
    
    def get_user_photo_in_round(self, user_id: int, round_id: int):
        """Получить фото пользователя в раунде"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM photos
                WHERE user_id = %s AND round_id = %s
                ORDER BY created_at DESC
                LIMIT 1
            """, (user_id, round_id))
            return cur.fetchone()
    
    def get_battle_by_photo(self, photo_id: int):
        """Получить батл по ID фото"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM battles
                WHERE photo1_id = %s OR photo2_id = %s
                ORDER BY created_at DESC
                LIMIT 1
            """, (photo_id, photo_id))
            return cur.fetchone()
    
    def use_extra_votes(self, user_id: int, photo_id: int, votes_count: int):
        """Использовать дополнительные голоса на свое фото"""
        with self.conn.cursor() as cur:
            # Убираем голоса у пользователя
            cur.execute("""
                UPDATE users
                SET extra_votes = GREATEST(extra_votes - %s, 0)
                WHERE telegram_id = %s
            """, (votes_count, user_id))
            
            # Добавляем голоса к фото
            cur.execute("""
                UPDATE photos
                SET votes = votes + %s
                WHERE id = %s
            """, (votes_count, photo_id))
    
    def get_bot_stats(self):
        """Общая статистика бота"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT COUNT(*) as total_users FROM users")
            total_users = cur.fetchone()['total_users']
            
            cur.execute("SELECT COUNT(*) as total_photos FROM photos")
            total_photos = cur.fetchone()['total_photos']
            
            cur.execute("SELECT COUNT(*) as total_battles FROM battles")
            total_battles = cur.fetchone()['total_battles']
            
            cur.execute("SELECT COUNT(*) as total_votes FROM votes")
            total_votes = cur.fetchone()['total_votes']
            
            cur.execute("SELECT COUNT(*) as total_admins FROM admins")
            total_admins = cur.fetchone()['total_admins']
            
            return {
                'total_users': total_users,
                'total_photos': total_photos,
                'total_battles': total_battles,
                'total_votes': total_votes,
                'total_admins': total_admins
            }
