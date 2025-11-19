from datetime import datetime
from collections import defaultdict
import statistics

class MetricsTracker:
    def __init__(self, database=None, username=None):
        """
        Initialize metrics tracker
        If database and username provided, will save to database
        """
        self.db = database
        self.username = username
        self.session_start = datetime.now()
        
        # In-memory session metrics (temporary)
        self.chat_metrics = {
            'total_messages': 0,
            'response_times': [],
            'topics_discussed': defaultdict(int),
            'conversations': []
        }
        
        # Quiz metrics
        self.quiz_metrics = {
            'total_quizzes': 0,
            'total_questions': 0,
            'correct_answers': 0,
            'quizzes_by_topic': defaultdict(int),
            'quiz_history': []
        }
        
        # Performance metrics
        self.performance_metrics = {
            'min_response_time': float('inf'),
            'max_response_time': 0,
            'avg_response_time': 0
        }
        
        # Topic tracking
        self.java_keywords = {
            'basics': ['variable', 'data type', 'string', 'array', 'loop', 'if', 'else', 'switch'],
            'oop': ['class', 'object', 'inheritance', 'polymorphism', 'encapsulation', 'abstraction', 'interface'],
            'advanced': ['exception', 'thread', 'collection', 'generics', 'lambda', 'stream', 'concurrent'],
            'frameworks': ['spring', 'hibernate', 'maven', 'gradle', 'junit', 'boot']
        }
        
        # Load persisted stats if database available
        if self.db and self.username:
            self._load_persisted_stats()
    
    def _load_persisted_stats(self):
        """Load persisted stats from database"""
        try:
            stats = self.db.get_user_stats(self.username)
            if stats:
                # Merge persisted stats with session stats
                self.chat_metrics['total_messages'] = stats.get('total_messages', 0)
                self.quiz_metrics['total_quizzes'] = stats.get('total_quizzes', 0)
                self.quiz_metrics['total_questions'] = stats.get('total_quiz_questions', 0)
                self.quiz_metrics['correct_answers'] = stats.get('total_correct_answers', 0)
                self.performance_metrics['avg_response_time'] = stats.get('avg_response_time', 0)
        except Exception as e:
            print(f"Error loading persisted stats: {e}")
    
    def track_chat(self, user_message, ai_response, response_time):
        """Track chat interaction and save to database"""
        # Update in-memory metrics
        self.chat_metrics['total_messages'] += 1
        self.chat_metrics['response_times'].append(response_time)
        
        # Track topics mentioned
        message_lower = (user_message + ' ' + ai_response).lower()
        for category, keywords in self.java_keywords.items():
            for keyword in keywords:
                if keyword in message_lower:
                    self.chat_metrics['topics_discussed'][keyword] += 1
        
        # Store conversation
        self.chat_metrics['conversations'].append({
            'timestamp': datetime.now().isoformat(),
            'user_message': user_message[:200],
            'response_time': response_time
        })
        
        # Update performance metrics
        if response_time < self.performance_metrics['min_response_time']:
            self.performance_metrics['min_response_time'] = response_time
        if response_time > self.performance_metrics['max_response_time']:
            self.performance_metrics['max_response_time'] = response_time
        
        # Calculate average
        if self.chat_metrics['response_times']:
            self.performance_metrics['avg_response_time'] = statistics.mean(
                self.chat_metrics['response_times']
            )
        
        # Save to database if available
        if self.db and self.username:
            try:
                # Save chat message
                tokens = len(ai_response.split())  # Approximate token count
                self.db.save_chat_message(
                    username=self.username,
                    user_message=user_message,
                    ai_response=ai_response,
                    response_time=response_time,
                    tokens_generated=tokens
                )
                
                # Update aggregated stats
                self.db.update_user_stats(
                    username=self.username,
                    messages=1,
                    response_time=response_time
                )
            except Exception as e:
                print(f"Error saving chat to database: {e}")
    
    def track_quiz_start(self, topic, num_questions):
        """Track quiz start"""
        # self.quiz_metrics['total_quizzes'] += 1
        self.quiz_metrics['quizzes_by_topic'][topic] += 1
        
        # Store for later completion tracking
        self.quiz_metrics['quiz_history'].append({
            'topic': topic,
            'num_questions': num_questions,
            'started_at': datetime.now().isoformat()
        })
    
    def track_quiz_answer(self, is_correct, topic):
        """Track quiz answer"""
        self.quiz_metrics['total_questions'] += 1
        if is_correct:
            self.quiz_metrics['correct_answers'] += 1
    
    def track_quiz_completion(self, quiz_id, topic, total_questions, correct_answers):
        """Track quiz completion and save to database"""
        self.quiz_metrics['total_quizzes'] += 1
        # Save to database if available
        if self.db and self.username:
            try:
                self.db.save_quiz_result(
                    username=self.username,
                    quiz_id=quiz_id,
                    topic=topic,
                    total_questions=total_questions,
                    correct_answers=correct_answers
                )
                
                # Update aggregated stats
                self.db.update_user_stats(
                    username=self.username,
                    quizzes=1,
                    quiz_questions=total_questions,
                    correct_answers=correct_answers
                )
            except Exception as e:
                print(f"Error saving quiz result to database: {e}")
    
    def get_session_duration(self):
        """Get session duration in seconds"""
        duration = datetime.now() - self.session_start
        return duration.total_seconds()
    
    def get_quick_stats(self):
        """Get quick stats for header"""
        duration = self.get_session_duration()
        hours = int(duration // 3600)
        minutes = int((duration % 3600) // 60)
        
        return {
            'total_messages': self.chat_metrics['total_messages'],
            'total_quizzes': self.quiz_metrics['total_quizzes'],
            'session_time': f"{hours}h {minutes}m",
            'topics_covered': len(self.chat_metrics['topics_discussed'])
        }
    
    def get_all_metrics(self):
        """Get all metrics for dashboard (combines session + persisted)"""
        duration = self.get_session_duration()
        hours = int(duration // 3600)
        minutes = int((duration % 3600) // 60)
        
        # Calculate quiz accuracy
        quiz_accuracy = 0
        if self.quiz_metrics['total_questions'] > 0:
            quiz_accuracy = (self.quiz_metrics['correct_answers'] / 
                           self.quiz_metrics['total_questions'] * 100)
        
        # Get top topics
        sorted_topics = sorted(
            self.chat_metrics['topics_discussed'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        metrics = {
            'session': {
                'start_time': self.session_start.isoformat(),
                'duration_seconds': duration,
                'duration_formatted': f"{hours}h {minutes}m"
            },
            'chat': {
                'total_messages': self.chat_metrics['total_messages'],
                'topics_discussed': dict(sorted_topics),
                'total_topics': len(self.chat_metrics['topics_discussed'])
            },
            'quiz': {
                'total_quizzes': self.quiz_metrics['total_quizzes'],
                'total_questions': self.quiz_metrics['total_questions'],
                'correct_answers': self.quiz_metrics['correct_answers'],
                'accuracy': round(quiz_accuracy, 1),
                'quizzes_by_topic': dict(self.quiz_metrics['quizzes_by_topic'])
            },
            'performance': {
                'avg_response_time': round(self.performance_metrics['avg_response_time'], 3),
                'min_response_time': round(self.performance_metrics['min_response_time'], 3) if self.performance_metrics['min_response_time'] != float('inf') else 0,
                'max_response_time': round(self.performance_metrics['max_response_time'], 3),
                'total_responses': len(self.chat_metrics['response_times'])
            }
        }
        
        # Add persisted data if available
        if self.db and self.username:
            try:
                # Get historical data
                chat_history = self.db.get_chat_history(self.username, limit=10)
                quiz_history = self.db.get_quiz_history(self.username, limit=10)
                quiz_stats = self.db.get_quiz_stats_by_topic(self.username)
                
                metrics['history'] = {
                    'recent_chats': chat_history,
                    'recent_quizzes': quiz_history,
                    'quiz_stats_by_topic': quiz_stats
                }
            except Exception as e:
                print(f"Error loading historical data: {e}")
        
        return metrics