from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_cors import CORS
from flask_socketio import SocketIO, emit, disconnect
import time
import json
from datetime import datetime
from model_handler import JavaTutorModel
from metrics_tracker import MetricsTracker
from database import Database
from functools import wraps
import logging
import secrets
import threading
import subprocess
import tempfile
import os
import shutil

class FilteredLogger(logging.Filter):
    def filter(self, record):
        return "write() before start_response" not in record.getMessage()

werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.addFilter(FilteredLogger())

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, 
            template_folder='../frontend',
            static_folder='../frontend',
            static_url_path='')
CORS(app)

# Secret key for session management
app.secret_key = secrets.token_hex(32)

# TESTING MODE: Session expires when browser closes
app.config['SESSION_PERMANENT'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = 300  # 5 minutes
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True

logger.info("Session management configured for testing mode")

# Initialize SocketIO with eventlet
socketio = SocketIO(app, 
                    cors_allowed_origins="*",
                    async_mode='threading',
                    logger=False,  # Changed to False to reduce noise
                    engineio_logger=False,  # Changed to False
                    ping_timeout=120,  # Increased timeout
                    ping_interval=25)

# Initialize database
db = Database()
logger.info("Database initialized")

# Initialize model and metrics tracker
model = None
metrics = MetricsTracker()

# Active users tracking
active_users = {}
active_generations = {}  # Track ongoing generations for stop functionality
user_metrics={}

def get_user_metrics(username):
    """Get or create metrics tracker for a user"""
    if username not in user_metrics:
        user_metrics[username] = MetricsTracker(database=db, username=username)
    return user_metrics[username]

def initialize_model():
    """Initialize the DeepSeek model (lazy loading)"""
    global model
    if model is None:
        logger.info("Loading DeepSeek model...")
        model = JavaTutorModel()
        logger.info("Model loaded successfully!")
    return model

# ==================== AUTHENTICATION ROUTES ====================

@app.route('/')
def index():
    """Redirect to login page or main app"""
    if request.args.get('logout') == 'true':
        session.clear()
        return redirect(url_for('login_page'))
    
    if 'username' in session:
        return render_template('index.html')
    return redirect(url_for('login_page'))

@app.route('/login')
def login_page():
    """Serve login page"""
    return render_template('login.html')

@app.route('/signup')
def signup_page():
    """Serve signup page"""
    return render_template('signup.html')

@app.route('/api/signup', methods=['POST'])
def signup():
    """Handle user signup"""
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        
        if len(username) < 3:
            return jsonify({'error': 'Username must be at least 3 characters'}), 400
        
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        
        if db.user_exists(username):
            return jsonify({'error': 'Username already exists'}), 400
        
        success = db.create_user(username, password)
        
        if success:
            logger.info(f"New user registered: {username}")
            return jsonify({'message': 'Signup successful', 'username': username}), 201
        else:
            return jsonify({'error': 'Failed to create user'}), 500
        
    except Exception as e:
        logger.error(f"Signup error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login():
    """Handle user login"""
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        
        if not db.verify_user(username, password):
            return jsonify({'error': 'Invalid username or password'}), 401
        
        session['username'] = username
        logger.info(f"User logged in: {username}")
        
        return jsonify({'message': 'Login successful', 'username': username}), 200
        
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    """Handle user logout"""
    username = session.get('username', 'Unknown')
    session.pop('username', None)
    logger.info(f"User logged out: {username}")
    return jsonify({'message': 'Logout successful'}), 200

@app.route('/api/check-auth', methods=['GET'])
def check_auth():
    """Check if user is authenticated"""
    if 'username' in session:
        return jsonify({'authenticated': True, 'username': session['username']}), 200
    return jsonify({'authenticated': False}), 200

# ==================== PROTECTED API ROUTES ====================

def require_auth(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function

# ==================== WEBSOCKET HANDLERS ====================

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    if 'username' not in session:
        logger.warning("Unauthorized WebSocket connection attempt")
        return False  # Reject connection
    
    username = session['username']
    sid = request.sid
    
    active_users[sid] = {
        'username': username,
        'connected_at': datetime.now().isoformat()
    }
    
    logger.info(f"User connected: {username} (sid: {sid})")
    
    emit('connected', {
        'message': 'Connected to Java Tutor AI',
        'username': username,
        'timestamp': datetime.now().isoformat()
    })
    
    broadcast_active_users()

@socketio.on('chat_message')
def handle_chat_message(data):
    """Handle chat message with streaming response"""
    sid = request.sid
    
    if sid not in active_users:
        logger.error(f"Chat message from unauthenticated user: {sid}")
        emit('error', {'message': 'Not authenticated'})
        return
    
    username = active_users[sid]['username']
    user_message = data.get('message', '').strip()
    conversation_history = data.get('history', [])
    
    if not user_message:
        emit('error', {'message': 'Message cannot be empty'})
        return
    
    logger.info(f"📨 Chat from {username}: {user_message[:50]}...")
    
    try:
        # Initialize model
        tutor_model = initialize_model()
        
        # Get user's metrics tracker
        metrics = get_user_metrics(username)
        
        # Create stop flag
        stop_flag = {'should_stop': False}
        active_generations[sid] = stop_flag
        
        start_time = time.time()
        full_response = ""
        token_count = 0
        
        # Stream response
        logger.info(f"🚀 Starting generation for {username}...")
        for token in tutor_model.generate_response_stream_with_stop(
            user_message, 
            conversation_history,
            stop_flag
        ):
            if stop_flag['should_stop']:
                logger.info(f"⏹️ Generation stopped by user: {username}")
                emit('generation_stopped', {
                    'message': 'Generation stopped by user',
                    'partial_response': full_response
                })
                break
            
            full_response += token
            token_count += 1
            
            # Send token to client
            emit('token', {
                'token': token,
                'done': False
            })
            
            # Give eventlet a chance to switch contexts
            socketio.sleep(0)
        
        logger.info(f"✅ Generation complete for {username}. Tokens sent: {token_count}")
        
        # Calculate metrics
        response_time = time.time() - start_time
        
        # Track metrics (saves to database automatically)
        if not stop_flag['should_stop']:
            metrics.track_chat(
                user_message=user_message,
                ai_response=full_response,
                response_time=response_time
            )
            
            # Send completion
            emit('token', {
                'token': '',
                'done': True,
                'response_time': round(response_time, 3),
                'full_response': full_response
            })
            logger.info(f"📊 Response time: {response_time:.2f}s, saved to database")
        
    except Exception as e:
        logger.error(f"❌ Chat error for {username}: {str(e)}", exc_info=True)
        emit('error', {'message': f'An error occurred: {str(e)}'})
    
    finally:
        # Clean up
        if sid in active_generations:
            del active_generations[sid]

@socketio.on('ping')
def handle_ping():
    """Handle ping for connection keepalive"""
    emit('pong', {'timestamp': datetime.now().isoformat()})

@socketio.on_error_default
def default_error_handler(e):
    """Handle all SocketIO errors"""
    logger.error(f"SocketIO error: {str(e)}", exc_info=True)
    emit('error', {'message': 'An error occurred. Please try again.'})

def broadcast_active_users():
    """Broadcast active user count to all connected clients"""
    user_count = len(active_users)
    usernames = [user['username'] for user in active_users.values()]

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'model_loaded': model is not None,
        'timestamp': datetime.now().isoformat()
    })
    
@app.route('/api/chat/clear', methods=['POST'])
@require_auth
def clear_chat():
    """Clear chat history for user"""
    try:
        username = session['username']
        
        # Clear chat history from database
        success = db.clear_chat_history(username)
        
        if success:
            # Reset in-memory metrics for this user
            if username in user_metrics:
                user_metrics[username] = MetricsTracker(database=db, username=username)
            
            logger.info(f"Chat history cleared for {username}")
            return jsonify({
                'message': 'Chat history cleared successfully',
                'success': True
            }), 200
        else:
            return jsonify({
                'error': 'Failed to clear chat history',
                'success': False
            }), 500
        
    except Exception as e:
        logger.error(f"Error clearing chat: {e}")
        return jsonify({
            'error': str(e),
            'success': False
        }), 500

@app.route('/api/quiz/start', methods=['POST'])
@require_auth
def start_quiz():
    """Start a new quiz"""
    try:
        data = request.json
        topic = data.get('topic', 'Overall')
        num_questions = data.get('num_questions', 5)
        
        tutor_model = initialize_model()
        quiz_data = tutor_model.start_quiz(topic, num_questions)
        
        if quiz_data:
            metrics.track_quiz_start(topic, num_questions)
            return jsonify(quiz_data)
        else:
            return jsonify({'error': 'Failed to start quiz'}), 400
            
    except Exception as e:
        logger.error(f"Quiz start error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/quiz/submit', methods=['POST'])
@require_auth
def submit_quiz_answer():
    """Submit a quiz answer"""
    try:
        username = session['username']
        data = request.json
        quiz_id = data.get('quiz_id')
        question_index = data.get('question_index')
        selected_option = data.get('selected_option')
        
        tutor_model = initialize_model()
        result = tutor_model.submit_answer(quiz_id, question_index, selected_option)
        
        # Get user metrics
        metrics = get_user_metrics(username)
        
        # Track quiz answer
        metrics.track_quiz_answer(
            is_correct=result.get('is_correct', False),
            topic=result.get('topic', 'Unknown')
        )
        
        # NEW: Save individual answer to database
        if quiz_id in tutor_model.active_quizzes:
            current_quiz = tutor_model.active_quizzes[quiz_id]
            current_question = current_quiz['questions'][question_index]
            
            db.save_quiz_answer(
                username=username,
                quiz_id=quiz_id,
                question_text=current_question['question'],
                topic=result.get('topic', 'Unknown'),
                selected_option=selected_option,
                correct_option=current_question['correct'],
                is_correct=result.get('is_correct', False)
            )
        
        # If quiz is complete, save to database
        if result.get('is_complete') and result.get('final_results'):
            final = result['final_results']
            metrics.track_quiz_completion(
                quiz_id=quiz_id,
                topic=final['topic'],
                total_questions=final['total'],
                correct_answers=final['score']
            )
            logger.info(f"📝 Quiz completed by {username}: {final['score']}/{final['total']}")
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Quiz submit error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/metrics', methods=['GET'])
@require_auth
def get_metrics():
    """Get all metrics for dashboard (combines session + persisted)"""
    try:
        username = session['username']
        metrics = get_user_metrics(username)
        
        return jsonify(metrics.get_all_metrics())
    except Exception as e:
        logger.error(f"Metrics error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# @app.route('/api/topics', methods=['GET'])
# def get_topics():
#     """Get list of available quiz topics"""
#     topics = [
#         {'id': 'overall', 'name': 'Overall', 'description': 'Mixed questions from all topics'},
#         {'id': 'basics', 'name': 'Java Basics', 'description': 'Variables, loops, data types'},
#         {'id': 'oop', 'name': 'OOP Concepts', 'description': 'Classes, inheritance, polymorphism'},
#         {'id': 'advanced', 'name': 'Advanced Java', 'description': 'Collections, exceptions, threads'},
#         {'id': 'frameworks', 'name': 'Frameworks', 'description': 'Spring, Hibernate, Maven'}
#     ]
#     return jsonify(topics)

@app.route('/api/stats', methods=['GET'])
@require_auth
def get_stats():
    """Get quick stats for header display"""
    try:
        username = session['username']
        metrics = get_user_metrics(username)
        
        return jsonify(metrics.get_quick_stats())
    except Exception as e:
        logger.error(f"Stats error: {str(e)}")
        return jsonify({'error': str(e)}), 500
    
@app.route('/api/chat/history', methods=['GET'])
@require_auth
def get_chat_history():
    """Get user's chat history"""
    try:
        username = session['username']
        limit = request.args.get('limit', 50, type=int)
        
        history = db.get_chat_history(username, limit=limit)
        
        return jsonify({
            'history': history,
            'total': len(history)
        })
        
    except Exception as e:
        logger.error(f"Error getting chat history: {e}")
        return jsonify({'error': str(e)}), 500
    
@app.route('/api/quiz/recommendations', methods=['POST'])
@require_auth
def get_quiz_recommendations():
    """Generate study recommendations based on quiz performance"""
    try:
        username = session['username']
        data = request.json
        
        quiz_id = data.get('quiz_id')
        quiz_topic = data.get('topic', 'Unknown')
        incorrect_answers = data.get('incorrect_answers', [])
        quiz_questions = data.get('questions', [])
        
        logger.info(f"📊 Generating recommendations for {username}, quiz {quiz_id}")
        
        # Initialize model
        tutor_model = initialize_model()
        
        # Prepare quiz data
        quiz_data = {
            'quiz_id': quiz_id,
            'topic': quiz_topic,
            'questions': quiz_questions
        }
        
        # Generate recommendations
        recommendations = tutor_model.generate_recommendations(quiz_data, incorrect_answers)
        
        # Save to database
        db.save_recommendations(
            username=username,
            quiz_id=quiz_id,
            weak_topics=recommendations['weak_topics'],
            recommendations_json=recommendations['recommendations']
        )
        
        logger.info(f"✅ Recommendations generated for {username}")
        
        return jsonify({
            'success': True,
            'recommendations': recommendations
        })
        
    except Exception as e:
        logger.error(f"❌ Error generating recommendations: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/recommendations/history', methods=['GET'])
@require_auth
def get_recommendations_history():
    """Get user's recommendation history"""
    try:
        username = session['username']
        limit = request.args.get('limit', 10, type=int)
        
        history = db.get_recent_recommendations(username, limit=limit)
        
        return jsonify({
            'success': True,
            'recommendations': history
        })
        
    except Exception as e:
        logger.error(f"Error getting recommendations history: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/code/run', methods=['POST'])
@require_auth
def run_code():
    """Execute Java code in Docker container with input support"""
    try:
        username = session['username']
        data = request.json
        code = data.get('code', '').strip()
        user_input = data.get('input', '')  # Get user input
        
        if not code:
            return jsonify({
                'success': False,
                'error': 'No code provided',
                'output': '',
                'execution_time': 0
            }), 400
        
        logger.info(f"🚀 Running code for user: {username}")
        if user_input:
            logger.info(f"📥 Input provided: {len(user_input.splitlines())} line(s)")
        
        # Create temporary directory
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Write code to Main.java file
            java_file = os.path.join(temp_dir, 'Main.java')
            with open(java_file, 'w', encoding='utf-8') as f:
                f.write(code)
            
            # Build Docker command
            docker_cmd = [
                'docker', 'run',
                '--rm',
                '--network', 'none',
                '--memory', '256m',
                '--cpus', '0.5',
                '--read-only',
                '--tmpfs', '/tmp:rw,noexec,nosuid,size=50m',
                '-v', f'{temp_dir}:/app:ro',
                '-w', '/tmp',
                '-i',  # Interactive mode for stdin
                'eclipse-temurin:17-jdk',
                'sh', '-c',
                'cp /app/Main.java /tmp/ && javac Main.java && timeout 10s java Main'
            ]
            
            # Execute with input via stdin
            start_time = time.time()
            
            result = subprocess.run(
                docker_cmd,
                input=user_input,  # Pass input via stdin
                capture_output=True,
                text=True,
                timeout=15
            )
            
            execution_time = time.time() - start_time
            
            # Check if successful
            success = result.returncode == 0
            output = result.stdout
            error = result.stderr
            
            logger.info(f"✅ Code executed for {username}. Success: {success}, Time: {execution_time:.2f}s")
            
            # Clean error messages
            if error:
                error_lines = [line for line in error.split('\n') 
                              if line.strip() and not line.startswith('Picked up')]
                error = '\n'.join(error_lines)
            
            return jsonify({
                'success': success,
                'output': output.strip(),
                'error': error.strip() if error else None,
                'execution_time': round(execution_time, 2)
            })
            
        finally:
            # Clean up temporary directory
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.error(f"Failed to clean up temp dir: {e}")
    
    except subprocess.TimeoutExpired:
        logger.warning(f"⏱️ Code execution timeout for {username}")
        return jsonify({
            'success': False,
            'error': 'Execution timeout (10 seconds limit exceeded)',
            'output': '',
            'execution_time': 10
        })
    
    except Exception as e:
        logger.error(f"❌ Code execution error for {username}: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}',
            'output': '',
            'execution_time': 0
        }), 500

if __name__ == '__main__':
    import signal
    import sys
    
    def signal_handler(sig, frame):
        """Handle Ctrl+C gracefully"""
        print('\n🛑 Shutting down server...')
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    logger.info("Starting Flask server with WebSocket support...")
    logger.info("Press Ctrl+C to stop the server")
    
    try:
        socketio.run(
            app,
            host='0.0.0.0',
            port=5000,
            debug=False,
            use_reloader=False,
            allow_unsafe_werkzeug=True,
            log_output=True  # Changed to True to see server logs
        )
    except KeyboardInterrupt:
        print('\n🛑 Server stopped by user')
        sys.exit(0)
