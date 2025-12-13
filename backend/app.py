from flask import Flask, request, jsonify, render_template, redirect, session
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import time
import json
from datetime import datetime
from model_handler import JavaTutorModel
from metrics_tracker import MetricsTracker
from database import Database
from functools import wraps
import logging
import secrets
import subprocess
import tempfile
import os
import shutil

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, 
            template_folder='../frontend',
            static_folder='../frontend',
            static_url_path='')

# Enable CORS for cross-origin requests
CORS(app, supports_credentials=True)

# Session configuration - CRITICAL FOR LOGIN TO WORK
app.secret_key = secrets.token_hex(32)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False  # Set True if using HTTPS
app.config['SESSION_COOKIE_PATH'] = '/'

logger.info("✅ Session management configured")

# Initialize SocketIO
socketio = SocketIO(app, 
                    cors_allowed_origins="*",
                    async_mode='threading',
                    logger=False,
                    engineio_logger=False,
                    ping_timeout=120,
                    ping_interval=25)

# Initialize database and model
db = Database()
model = None
active_users = {}
active_generations = {}
user_metrics = {}

logger.info("✅ Database initialized")

# ==================== HELPER FUNCTIONS ====================

def get_user_metrics(username):
    """Get or create metrics tracker for a user"""
    if username not in user_metrics:
        user_metrics[username] = MetricsTracker(database=db, username=username)
    return user_metrics[username]

def initialize_model():
    """Initialize the AI model (lazy loading)"""
    global model
    if model is None:
        logger.info("Loading AI model...")
        model = JavaTutorModel()
        logger.info("✅ Model loaded successfully!")
    return model

def require_login(f):
    """Decorator to protect routes that need authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return jsonify({'error': 'Please login first'}), 401
        return f(*args, **kwargs)
    return decorated_function

# ==================== PAGE ROUTES (HTML) ====================

@app.route('/')
def home_page():
    """Main page - show login or dashboard"""
    # If user is logged in, show main app
    if 'username' in session:
        return render_template('index.html')
    # Otherwise, redirect to login
    return redirect('/login')

@app.route('/login')
def show_login_page():
    """Show the login page"""
    # If already logged in, redirect to dashboard
    if 'username' in session:
        return redirect('/')
    return render_template('login.html')

@app.route('/signup')
def show_signup_page():
    """Show the signup page"""
    return render_template('signup.html')

# ==================== AUTHENTICATION API ====================

@app.route('/api/signup', methods=['POST'])
def handle_signup():
    """Create new user account"""
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        # Validate input
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        
        if len(username) < 3:
            return jsonify({'error': 'Username must be at least 3 characters'}), 400
        
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        
        # Check if username already exists
        if db.user_exists(username):
            return jsonify({'error': 'Username already exists'}), 400
        
        # Create user
        success = db.create_user(username, password)
        
        if success:
            logger.info(f"✅ New user registered: {username}")
            return jsonify({
                'success': True,
                'message': 'Account created successfully!',
                'username': username
            }), 201
        else:
            return jsonify({'error': 'Failed to create account'}), 500
        
    except Exception as e:
        logger.error(f"❌ Signup error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/login', methods=['POST'])
def handle_login():
    """Login user and create session"""
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        # Validate input
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        
        # Verify credentials
        if not db.verify_user(username, password):
            return jsonify({'error': 'Invalid username or password'}), 401
        
        # Create session
        session['username'] = username
        session.modified = True
        
        logger.info(f"✅ User logged in: {username}")
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'username': username
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Login error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/logout', methods=['POST'])
def handle_logout():
    """Logout user and clear session"""
    username = session.get('username', 'Unknown')
    session.clear()
    logger.info(f"✅ User logged out: {username}")
    return jsonify({'success': True, 'message': 'Logged out successfully'}), 200

@app.route('/api/check-auth', methods=['GET'])
def check_if_logged_in():
    """Check if user is logged in"""
    if 'username' in session:
        return jsonify({
            'authenticated': True,
            'username': session['username']
        }), 200
    return jsonify({'authenticated': False}), 200

# ==================== CHAT API ====================

@socketio.on('connect')
def handle_websocket_connect():
    """Handle WebSocket connection"""
    if 'username' not in session:
        logger.warning("⚠️ Unauthorized WebSocket connection attempt")
        return False  # Reject connection
    
    username = session['username']
    sid = request.sid
    
    active_users[sid] = {
        'username': username,
        'connected_at': datetime.now().isoformat()
    }
    
    logger.info(f"✅ User connected via WebSocket: {username}")
    
    emit('connected', {
        'message': 'Connected to Java Tutor AI',
        'username': username,
        'timestamp': datetime.now().isoformat()
    })

@socketio.on('chat_message')
def handle_chat_message(data):
    """Handle incoming chat message and stream AI response"""
    sid = request.sid
    
    if sid not in active_users:
        logger.error(f"❌ Unauthenticated chat attempt")
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
        
        # Stream response token by token
        logger.info(f"🚀 Generating AI response...")
        for token in tutor_model.generate_response_stream_with_stop(
            user_message, 
            conversation_history,
            stop_flag
        ):
            if stop_flag['should_stop']:
                logger.info(f"⏹️ Generation stopped by user")
                emit('generation_stopped', {
                    'message': 'Generation stopped',
                    'partial_response': full_response
                })
                break
            
            full_response += token
            
            # Send token to client
            emit('token', {
                'token': token,
                'done': False
            })
            
            socketio.sleep(0)
        
        logger.info(f"✅ Generation complete")
        
        # Calculate metrics
        response_time = time.time() - start_time
        
        # Save to database
        if not stop_flag['should_stop']:
            metrics.track_chat(
                user_message=user_message,
                ai_response=full_response,
                response_time=response_time
            )
            
            # Send completion signal
            emit('token', {
                'token': '',
                'done': True,
                'response_time': round(response_time, 3),
                'full_response': full_response
            })
            logger.info(f"📊 Response saved to database")
        
    except Exception as e:
        logger.error(f"❌ Chat error: {str(e)}", exc_info=True)
        emit('error', {'message': f'An error occurred: {str(e)}'})
    
    finally:
        if sid in active_generations:
            del active_generations[sid]

@app.route('/api/chat/clear', methods=['POST'])
@require_login
def clear_chat_history():
    """Clear user's chat history"""
    try:
        username = session['username']
        
        success = db.clear_chat_history(username)
        
        if success:
            if username in user_metrics:
                user_metrics[username] = MetricsTracker(database=db, username=username)
            
            logger.info(f"✅ Chat history cleared for {username}")
            return jsonify({'success': True, 'message': 'Chat cleared'}), 200
        else:
            return jsonify({'success': False, 'error': 'Failed to clear'}), 500
        
    except Exception as e:
        logger.error(f"❌ Error clearing chat: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/chat/history', methods=['GET'])
@require_login
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
        logger.error(f"❌ Error getting chat history: {e}")
        return jsonify({'error': str(e)}), 500

# ==================== QUIZ API ====================

@app.route('/api/quiz/start', methods=['POST'])
@require_login
def start_new_quiz():
    """Start a new quiz"""
    try:
        data = request.json
        topic = data.get('topic', 'Overall')
        num_questions = data.get('num_questions', 5)
        
        tutor_model = initialize_model()
        quiz_data = tutor_model.start_quiz(topic, num_questions)
        
        if quiz_data:
            return jsonify(quiz_data)
        else:
            return jsonify({'error': 'Failed to start quiz'}), 400
            
    except Exception as e:
        logger.error(f"❌ Quiz start error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/quiz/submit', methods=['POST'])
@require_login
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
        
        metrics = get_user_metrics(username)
        
        metrics.track_quiz_answer(
            is_correct=result.get('is_correct', False),
            topic=result.get('topic', 'Unknown')
        )
        
        # Save to database
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
        
        # If quiz complete, save final results
        if result.get('is_complete') and result.get('final_results'):
            final = result['final_results']
            metrics.track_quiz_completion(
                quiz_id=quiz_id,
                topic=final['topic'],
                total_questions=final['total'],
                correct_answers=final['score']
            )
            logger.info(f"✅ Quiz completed: {final['score']}/{final['total']}")
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Quiz submit error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/quiz/recommendations', methods=['POST'])
@require_login
def generate_quiz_recommendations():
    """Generate study recommendations based on quiz performance"""
    try:
        username = session['username']
        data = request.json
        
        quiz_id = data.get('quiz_id')
        quiz_topic = data.get('topic', 'Unknown')
        incorrect_answers = data.get('incorrect_answers', [])
        quiz_questions = data.get('questions', [])
        
        logger.info(f"📊 Generating recommendations for {username}")
        
        tutor_model = initialize_model()
        
        quiz_data = {
            'quiz_id': quiz_id,
            'topic': quiz_topic,
            'questions': quiz_questions
        }
        
        recommendations = tutor_model.generate_recommendations(quiz_data, incorrect_answers)
        
        db.save_recommendations(
            username=username,
            quiz_id=quiz_id,
            weak_topics=recommendations['weak_topics'],
            recommendations_json=recommendations['recommendations']
        )
        
        logger.info(f"✅ Recommendations generated")
        
        return jsonify({
            'success': True,
            'recommendations': recommendations
        })
        
    except Exception as e:
        logger.error(f"❌ Error generating recommendations: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== STATS & METRICS API ====================

@app.route('/api/stats', methods=['GET'])
@require_login
def get_quick_stats():
    """Get quick stats for header"""
    try:
        username = session['username']
        metrics = get_user_metrics(username)
        return jsonify(metrics.get_quick_stats())
    except Exception as e:
        logger.error(f"❌ Stats error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/metrics', methods=['GET'])
@require_login
def get_all_metrics():
    """Get all metrics for dashboard"""
    try:
        username = session['username']
        metrics = get_user_metrics(username)
        return jsonify(metrics.get_all_metrics())
    except Exception as e:
        logger.error(f"❌ Metrics error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ==================== CODE EXECUTION API ====================

@app.route('/api/code/run', methods=['POST'])
@require_login
def run_java_code():
    """Execute Java code in Docker container"""
    try:
        username = session['username']
        data = request.json
        code = data.get('code', '').strip()
        user_input = data.get('input', '')
        
        if not code:
            return jsonify({
                'success': False,
                'error': 'No code provided',
                'output': '',
                'execution_time': 0
            }), 400
        
        logger.info(f"🚀 Running code for: {username}")
        
        # Create temporary directory
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Write code to file
            java_file = os.path.join(temp_dir, 'Main.java')
            with open(java_file, 'w', encoding='utf-8') as f:
                f.write(code)
            
            # Docker command
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
                '-i',
                'eclipse-temurin:17-jdk',
                'sh', '-c',
                'cp /app/Main.java /tmp/ && javac Main.java && timeout 10s java Main'
            ]
            
            start_time = time.time()
            
            result = subprocess.run(
                docker_cmd,
                input=user_input,
                capture_output=True,
                text=True,
                timeout=15
            )
            
            execution_time = time.time() - start_time
            
            success = result.returncode == 0
            output = result.stdout
            error = result.stderr
            
            logger.info(f"✅ Code executed. Success: {success}")
            
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
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.error(f"Failed to clean up: {e}")
    
    except subprocess.TimeoutExpired:
        logger.warning(f"⏱️ Code execution timeout")
        return jsonify({
            'success': False,
            'error': 'Execution timeout (10 seconds)',
            'output': '',
            'execution_time': 10
        })
    
    except Exception as e:
        logger.error(f"❌ Code execution error: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Error: {str(e)}',
            'output': '',
            'execution_time': 0
        }), 500

# ==================== HEALTH CHECK ====================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'model_loaded': model is not None,
        'timestamp': datetime.now().isoformat()
    })

# ==================== START SERVER ====================

if __name__ == '__main__':
    import signal
    import sys
    
    def signal_handler(sig, frame):
        print('\n🛑 Shutting down server...')
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    logger.info("🚀 Starting Flask server...")
    logger.info("Press Ctrl+C to stop")
    
    try:
        socketio.run(
            app,
            host='0.0.0.0',
            port=80,
            debug=False,
            use_reloader=False,
            allow_unsafe_werkzeug=True
        )
    except KeyboardInterrupt:
        print('\n🛑 Server stopped')
        sys.exit(0)