import sqlite3
import hashlib
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_file='java_tutor.db'):
        """Initialize database connection"""
        self.db_file = db_file
        self.init_database()
    
    def get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """Initialize database tables"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Existing tables...
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_login TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    session_id TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY (username) REFERENCES users(username)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS learning_progress (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    questions_asked INTEGER DEFAULT 0,
                    quizzes_taken INTEGER DEFAULT 0,
                    topics_covered TEXT,
                    last_activity TEXT,
                    FOREIGN KEY (username) REFERENCES users(username)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    user_message TEXT NOT NULL,
                    ai_response TEXT NOT NULL,
                    response_time REAL,
                    tokens_generated INTEGER,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (username) REFERENCES users(username)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS quiz_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    quiz_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    total_questions INTEGER,
                    correct_answers INTEGER,
                    score_percentage REAL,
                    completed_at TEXT NOT NULL,
                    FOREIGN KEY (username) REFERENCES users(username)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    total_messages INTEGER DEFAULT 0,
                    total_quizzes INTEGER DEFAULT 0,
                    total_quiz_questions INTEGER DEFAULT 0,
                    total_correct_answers INTEGER DEFAULT 0,
                    avg_response_time REAL DEFAULT 0,
                    total_session_time INTEGER DEFAULT 0,
                    topics_mastered TEXT,
                    last_updated TEXT NOT NULL,
                    FOREIGN KEY (username) REFERENCES users(username)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    activity_date TEXT NOT NULL,
                    messages_sent INTEGER DEFAULT 0,
                    quizzes_taken INTEGER DEFAULT 0,
                    time_spent_seconds INTEGER DEFAULT 0,
                    FOREIGN KEY (username) REFERENCES users(username),
                    UNIQUE(username, activity_date)
                )
            ''')
            
            # NEW: Quiz answers tracking table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS quiz_answers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    quiz_id TEXT NOT NULL,
                    question_text TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    selected_option INTEGER,
                    correct_option INTEGER,
                    is_correct BOOLEAN,
                    answered_at TEXT NOT NULL,
                    FOREIGN KEY (username) REFERENCES users(username)
                )
            ''')
            
            # NEW: Recommendations table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS recommendations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    quiz_id TEXT NOT NULL,
                    weak_topics TEXT NOT NULL,
                    recommendations_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (username) REFERENCES users(username)
                )
            ''')
            
            conn.commit()
            conn.close()
            
            logger.info(f"Database initialized successfully: {self.db_file}")
            
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise
    
    def hash_password(self, password):
        """Hash password using SHA256"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def create_user(self, username, password):
        """Create a new user"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            hashed_password = self.hash_password(password)
            created_at = datetime.now().isoformat()
            
            cursor.execute('''
                INSERT INTO users (username, password, created_at)
                VALUES (?, ?, ?)
            ''', (username, hashed_password, created_at))
            
            cursor.execute('''
                INSERT INTO learning_progress (username, last_activity)
                VALUES (?, ?)
            ''', (username, created_at))
            
            cursor.execute('''
                INSERT INTO user_stats (username, last_updated)
                VALUES (?, ?)
            ''', (username, created_at))
            
            conn.commit()
            conn.close()
            
            logger.info(f"User created: {username}")
            return True
            
        except sqlite3.IntegrityError:
            logger.warning(f"Username already exists: {username}")
            return False
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return False
    
    def verify_user(self, username, password):
        """Verify user credentials"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            hashed_password = self.hash_password(password)
            
            cursor.execute('''
                SELECT * FROM users 
                WHERE username = ? AND password = ?
            ''', (username, hashed_password))
            
            user = cursor.fetchone()
            
            if user:
                cursor.execute('''
                    UPDATE users 
                    SET last_login = ? 
                    WHERE username = ?
                ''', (datetime.now().isoformat(), username))
                conn.commit()
            
            conn.close()
            
            return user is not None
            
        except Exception as e:
            logger.error(f"Error verifying user: {e}")
            return False
    
    def user_exists(self, username):
        """Check if user exists"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT username FROM users WHERE username = ?
            ''', (username,))
            
            user = cursor.fetchone()
            conn.close()
            
            return user is not None
            
        except Exception as e:
            logger.error(f"Error checking user existence: {e}")
            return False
    
    # Chat history methods remain the same...
    def save_chat_message(self, username, user_message, ai_response, response_time=0, tokens_generated=0):
        """Save chat message to history"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            timestamp = datetime.now().isoformat()
            
            cursor.execute('''
                INSERT INTO chat_history 
                (username, user_message, ai_response, response_time, tokens_generated, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (username, user_message, ai_response, response_time, tokens_generated, timestamp))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Chat saved for {username}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving chat: {e}")
            return False
    
    def get_chat_history(self, username, limit=50):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT user_message, ai_response, response_time, timestamp
                FROM chat_history
                WHERE username = ?
                ORDER BY timestamp ASC
                LIMIT ?
            ''', (username, limit))
            
            rows = cursor.fetchall()
            conn.close()
            
            history = []
            for row in rows:
                history.append({
                    'user': row['user_message'],
                    'ai': row['ai_response'],
                    'response_time': row['response_time'],
                    'timestamp': row['timestamp']
                })
            
            return history
            
        except Exception as e:
            logger.error(f"Error getting chat history: {e}")
            return []
        
    def clear_chat_history(self, username):
        """Clear only chat history (not quiz history)"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM chat_history WHERE username = ?', (username,))
            
            cursor.execute('''
                UPDATE user_stats
                SET total_messages = 0,
                    avg_response_time = 0,
                    last_updated = ?
                WHERE username = ?
            ''', (datetime.now().isoformat(), username))
            
            cursor.execute('''
                UPDATE daily_activity
                SET messages_sent = 0
                WHERE username = ?
            ''', (username,))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Chat history cleared for: {username}")
            return True
            
        except Exception as e:
            logger.error(f"Error clearing chat history: {e}")
            return False
    
    # Quiz methods
    def save_quiz_result(self, username, quiz_id, topic, total_questions, correct_answers):
        """Save quiz result"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            score_percentage = (correct_answers / total_questions * 100) if total_questions > 0 else 0
            completed_at = datetime.now().isoformat()
            
            cursor.execute('''
                INSERT INTO quiz_history 
                (username, quiz_id, topic, total_questions, correct_answers, score_percentage, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (username, quiz_id, topic, total_questions, correct_answers, score_percentage, completed_at))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Quiz result saved for {username}: {correct_answers}/{total_questions}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving quiz result: {e}")
            return False
    
    def get_quiz_history(self, username, limit=20):
        """Get quiz history for user"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT topic, total_questions, correct_answers, score_percentage, completed_at
                FROM quiz_history
                WHERE username = ?
                ORDER BY completed_at DESC
                LIMIT ?
            ''', (username, limit))
            
            history = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in history]
            
        except Exception as e:
            logger.error(f"Error getting quiz history: {e}")
            return []
    
    def get_quiz_stats_by_topic(self, username):
        """Get quiz statistics grouped by topic"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT 
                    topic,
                    COUNT(*) as quizzes_taken,
                    AVG(score_percentage) as avg_score,
                    MAX(score_percentage) as best_score,
                    SUM(total_questions) as total_questions,
                    SUM(correct_answers) as total_correct
                FROM quiz_history
                WHERE username = ?
                GROUP BY topic
                ORDER BY avg_score DESC
            ''', (username,))
            
            stats = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in stats]
            
        except Exception as e:
            logger.error(f"Error getting quiz stats by topic: {e}")
            return []
    
    # NEW: Quiz answer tracking methods
    def save_quiz_answer(self, username, quiz_id, question_text, topic, selected_option, correct_option, is_correct):
        """Save individual quiz answer"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            answered_at = datetime.now().isoformat()
            
            cursor.execute('''
                INSERT INTO quiz_answers 
                (username, quiz_id, question_text, topic, selected_option, correct_option, is_correct, answered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (username, quiz_id, question_text, topic, selected_option, correct_option, is_correct, answered_at))
            
            conn.commit()
            conn.close()
            
            return True
            
        except Exception as e:
            logger.error(f"Error saving quiz answer: {e}")
            return False
    
    def get_quiz_answers(self, username, quiz_id):
        """Get all answers for a specific quiz"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT question_text, topic, selected_option, correct_option, is_correct
                FROM quiz_answers
                WHERE username = ? AND quiz_id = ?
                ORDER BY answered_at ASC
            ''', (username, quiz_id))
            
            answers = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in answers]
            
        except Exception as e:
            logger.error(f"Error getting quiz answers: {e}")
            return []
    
    # NEW: Recommendation methods
    def save_recommendations(self, username, quiz_id, weak_topics, recommendations_json):
        """Save recommendations for a quiz"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            created_at = datetime.now().isoformat()
            
            cursor.execute('''
                INSERT INTO recommendations 
                (username, quiz_id, weak_topics, recommendations_json, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (username, quiz_id, json.dumps(weak_topics), json.dumps(recommendations_json), created_at))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Recommendations saved for {username}, quiz {quiz_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving recommendations: {e}")
            return False
    
    def get_recommendations(self, username, quiz_id):
        """Get recommendations for a specific quiz"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT weak_topics, recommendations_json, created_at
                FROM recommendations
                WHERE username = ? AND quiz_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            ''', (username, quiz_id))
            
            rec = cursor.fetchone()
            conn.close()
            
            if rec:
                return {
                    'weak_topics': json.loads(rec['weak_topics']),
                    'recommendations': json.loads(rec['recommendations_json']),
                    'created_at': rec['created_at']
                }
            return None
            
        except Exception as e:
            logger.error(f"Error getting recommendations: {e}")
            return None
    
    def get_recent_recommendations(self, username, limit=5):
        """Get recent recommendations for user"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT quiz_id, weak_topics, recommendations_json, created_at
                FROM recommendations
                WHERE username = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (username, limit))
            
            recs = cursor.fetchall()
            conn.close()
            
            result = []
            for rec in recs:
                result.append({
                    'quiz_id': rec['quiz_id'],
                    'weak_topics': json.loads(rec['weak_topics']),
                    'recommendations': json.loads(rec['recommendations_json']),
                    'created_at': rec['created_at']
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting recent recommendations: {e}")
            return []
    
    # User stats methods remain the same...
    def update_user_stats(self, username, messages=0, quizzes=0, quiz_questions=0, 
                         correct_answers=0, response_time=0, session_time=0, topics=None):
        """Update aggregated user statistics"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM user_stats WHERE username = ?', (username,))
            current = cursor.fetchone()
            
            if not current:
                cursor.execute('''
                    INSERT INTO user_stats 
                    (username, total_messages, total_quizzes, total_quiz_questions, 
                     total_correct_answers, avg_response_time, total_session_time, 
                     topics_mastered, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (username, messages, quizzes, quiz_questions, correct_answers, 
                      response_time, session_time, json.dumps(topics or []), 
                      datetime.now().isoformat()))
            else:
                new_total_messages = current['total_messages'] + messages
                new_avg_response = ((current['avg_response_time'] * current['total_messages'] + 
                                   response_time * messages) / new_total_messages 
                                  if new_total_messages > 0 else 0)
                
                cursor.execute('''
                    UPDATE user_stats
                    SET total_messages = total_messages + ?,
                        total_quizzes = total_quizzes + ?,
                        total_quiz_questions = total_quiz_questions + ?,
                        total_correct_answers = total_correct_answers + ?,
                        avg_response_time = ?,
                        total_session_time = total_session_time + ?,
                        last_updated = ?
                    WHERE username = ?
                ''', (messages, quizzes, quiz_questions, correct_answers, 
                      new_avg_response, session_time, datetime.now().isoformat(), username))
            
            conn.commit()
            conn.close()
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating user stats: {e}")
            return False
    
    def get_user_stats(self, username):
        """Get aggregated user statistics"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM user_stats WHERE username = ?
            ''', (username,))
            
            stats = cursor.fetchone()
            conn.close()
            
            if stats:
                result = dict(stats)
                if result.get('topics_mastered'):
                    result['topics_mastered'] = json.loads(result['topics_mastered'])
                return result
            return None
            
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return None
    
    def get_daily_activity(self, username, days=30):
        """Get daily activity for user"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT activity_date, messages_sent, quizzes_taken, time_spent_seconds
                FROM daily_activity
                WHERE username = ?
                AND activity_date >= date('now', '-' || ? || ' days')
                ORDER BY activity_date DESC
            ''', (username, days))
            
            activity = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in activity]
            
        except Exception as e:
            logger.error(f"Error getting daily activity: {e}")
            return []
    
    def get_user_info(self, username):
        """Get comprehensive user information"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT u.username, u.created_at, u.last_login,
                       s.total_messages, s.total_quizzes, s.total_quiz_questions,
                       s.total_correct_answers, s.avg_response_time, s.total_session_time
                FROM users u
                LEFT JOIN user_stats s ON u.username = s.username
                WHERE u.username = ?
            ''', (username,))
            
            user = cursor.fetchone()
            conn.close()
            
            if user:
                return dict(user)
            return None
            
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            return None