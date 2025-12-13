// API Configuration
// ==================== AUTH CHECK ====================
// Check if user is logged in when page loads

(async function checkAuth() {
    try {
        const response = await fetch('/api/check-auth', {
            credentials: 'include'
        });
        const data = await response.json();
        
        if (!data.authenticated) {
            console.log('⚠️ Not authenticated, redirecting to login...');
            window.location.href = '/login';
            return;
        }
        
        console.log('✅ Authenticated as:', data.username);
        // Store username for display
        window.currentUser = data.username;
        
    } catch (error) {
        console.error('❌ Auth check failed:', error);
        window.location.href = '/login';
    }
})();

// Rest of your app.js code below...

const API_BASE_URL = '/api';

// WebSocket connection
let socket = null;
let isGenerating = false;

// State Management
let conversationHistory = [];
let currentQuiz = null;
let currentQuestionIndex = 0;
let selectedOption = null;
let responseTimes = [];
let currentMessageDiv = null;
let currentUserMessage = '';
let quizIncorrectAnswers = [];
let currentQuizQuestions = [];
let quizChart = null;
let radarChart = null;

// DOM Elements
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const clearBtn = document.getElementById('clear-btn');
const loadingOverlay = document.getElementById('loading-overlay');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 App initializing...');
    checkAuthentication();
    setupEventListeners();
    initializeWebSocket();
    loadChatHistory();
    updateStats();
    setInterval(updateStats, 10000);
});

// Initialize WebSocket connection
function initializeWebSocket() {
    console.log('🔌 Initializing WebSocket...');
    socket = io({
        transports: ['websocket', 'polling'],
        upgrade: true
    });
    
    socket.on('connect', () => {
        console.log('✅ WebSocket connected, socket.id:', socket.id);
        showNotification('Connected to server', 'success');
    });
    
    socket.on('disconnect', () => {
        console.log('❌ WebSocket disconnected');
        showNotification('Disconnected from server', 'warning');
    });
    
    socket.on('connected', (data) => {
        console.log('📨 Welcome message received:', data);
    });
    
    // Chat streaming events
    socket.on('token', (data) => {
        console.log('📝 Token received:', {
            token: data.token ? data.token.substring(0, 20) + '...' : 'empty',
            done: data.done,
            hasCurrentDiv: !!currentMessageDiv
        });
        handleStreamingToken(data);
    });
    
    socket.on('stats_update', (data) => {
        updateStatsFromSocket(data);
    });
    
    socket.on('error', (data) => {
        console.error('❌ Socket error:', data);
        showNotification(data.message || 'An error occurred', 'error');
        enableChatInput();
    });
    
    // Keepalive
    setInterval(() => {
        if (socket.connected) {
            socket.emit('ping');
        }
    }, 30000);
}

// Check if user is authenticated
async function checkAuthentication() {
    try {
        const response = await fetch(`${API_BASE_URL}/check-auth`, {
            credentials: 'same-origin'
        });
        const data = await response.json();
        
        if (!data.authenticated) {
            window.location.href = '/login';
            return;
        }
        
        console.log('✅ Authenticated as:', data.username);
        document.getElementById('username').textContent = data.username;
        
    } catch (error) {
        console.error('Auth check failed:', error);
        window.location.href = '/login';
    }
}

// Setup Event Listeners
function setupEventListeners() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });
    
    sendBtn.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });
    clearBtn.addEventListener('click', clearChat);
    
    document.getElementById('start-quiz-btn').addEventListener('click', startQuiz);
    document.getElementById('submit-answer-btn').addEventListener('click', submitAnswer);
    document.getElementById('next-question-btn').addEventListener('click', nextQuestion);
    document.getElementById('finish-quiz-btn').addEventListener('click', finishQuiz);
    document.getElementById('new-quiz-btn').addEventListener('click', resetQuiz);
    document.getElementById('run-code-btn').addEventListener('click', runCode);
    document.getElementById('clear-code-btn').addEventListener('click', clearCode);
    document.getElementById('clear-output-btn').addEventListener('click', clearOutput);
    document.getElementById('code-template').addEventListener('change', loadTemplate);
    document.getElementById('clear-input-btn').addEventListener('click', clearInput);
    
    const slider = document.getElementById('quiz-questions');
    const sliderValue = document.getElementById('quiz-questions-value');
    slider.addEventListener('input', () => {
        sliderValue.textContent = slider.value;
    });
    
    document.getElementById('logout-btn').addEventListener('click', logout);
}

// Load stored chat history from backend and rebuild conversationHistory & UI
async function loadChatHistory() {
    try {
        console.log('📥 loadChatHistory(): requesting /api/chat/history');
        const res = await fetch(`${API_BASE_URL}/chat/history?limit=200`, {
            method: 'GET',
            credentials: 'same-origin'
        });

        console.log('📥 History response status:', res.status);

        if (res.status === 401) {
            console.warn('🔒 loadChatHistory: not authenticated (401). Redirecting to login.');
            window.location.href = '/login';
            return;
        }

        const data = await res.json();
        console.log('📥 History payload:', data);

        if (!data || !data.history || data.history.length === 0) {
            console.warn('⚠️ loadChatHistory: no history in response');
            return;
        }

        // Keep welcome message if present
        const welcome = chatMessages.querySelector('.welcome-message');
        chatMessages.innerHTML = '';
        if (welcome) chatMessages.appendChild(welcome);

        // Clear and rebuild conversation history
        conversationHistory = [];

        // Process history items (they come in chronological order)
        for (const item of data.history) {
            if (!item || typeof item !== 'object') {
                console.warn('⚠️ loadChatHistory: invalid item', item);
                continue;
            }
            
            const userMsg = item.user || item.user_message;
            const aiMsg = item.ai || item.ai_response;
            
            if (!userMsg || !aiMsg) {
                console.warn('⚠️ loadChatHistory: missing user or ai message', item);
                continue;
            }
            
            // Add messages to UI
            addMessage(userMsg, 'user');
            addMessage(aiMsg, 'ai');
            
            // Add to conversation history (as pairs for the model)
            conversationHistory.push([userMsg, aiMsg]);
        }

        // Scroll to bottom
        chatMessages.scrollTop = chatMessages.scrollHeight;
        console.log('✅ History loaded, conversationHistory length:', conversationHistory.length);
        
    } catch (err) {
        console.error('❌ loadChatHistory failed:', err);
    }
}

// Chat Functions
async function sendMessage() {
    const message = chatInput.value.trim();
    if (!message || isGenerating) {
        console.log('⚠️ Cannot send: empty message or already generating');
        return;
    }
    
    console.log('📤 Sending message:', message);
    
    // Save current message BEFORE clearing
    currentUserMessage = message;
    
    // Add user message to UI
    addMessage(message, 'user');
    chatInput.value = '';
    
    // Disable input while processing
    isGenerating = true;
    chatInput.disabled = true;
    chatInput.placeholder = 'AI is typing...';
    sendBtn.disabled = true;
    sendBtn.textContent = 'Generating...';
    
    // Create placeholder for streaming response
    currentMessageDiv = document.createElement('div');
    currentMessageDiv.className = 'message ai streaming';
    
    const header = document.createElement('div');
    header.className = 'message-header';
    header.innerHTML = '🤖 AI Tutor <span class="typing-indicator">●●●</span>';
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.innerHTML = '<span class="cursor">▋</span>';
    
    currentMessageDiv.appendChild(header);
    currentMessageDiv.appendChild(contentDiv);
    chatMessages.appendChild(currentMessageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    console.log('✅ Message div created and added to DOM');
    
    window.currentStreamStart = Date.now();
    window.currentFullResponse = '';
    
    // Send message via WebSocket
    console.log('📡 Emitting chat_message event...');
    socket.emit('chat_message', {
        message: message,
        history: conversationHistory
    });
    console.log('✅ Event emitted');
}

function handleStreamingToken(data) {
    console.log('🎯 handleStreamingToken called', {
        hasCurrentDiv: !!currentMessageDiv,
        done: data.done,
        tokenLength: data.token ? data.token.length : 0
    });
    
    if (!currentMessageDiv) {
        console.error('❌ currentMessageDiv is null!');
        return;
    }
    
    const header = currentMessageDiv.querySelector('.message-header');
    const contentDiv = currentMessageDiv.querySelector('.message-content');
    
    if (!header || !contentDiv) {
        console.error('❌ Could not find header or contentDiv!');
        return;
    }
    
    if (data.done) {
        console.log('✅ Stream complete');
        
        // Remove cursor
        const cursor = contentDiv.querySelector('.cursor');
        if (cursor) cursor.remove();
        
        // Remove typing indicator
        const typingIndicator = header.querySelector('.typing-indicator');
        if (typingIndicator) typingIndicator.remove();
        
        // Calculate total time
        const totalTime = (Date.now() - window.currentStreamStart) / 1000;
        responseTimes.push(totalTime);
        
        // Update average response time display
        updateAverageResponseTime();
        
        // Add response time
        const timeSpan = document.createElement('span');
        timeSpan.style.fontSize = '0.8em';
        timeSpan.style.opacity = '0.7';
        timeSpan.textContent = ` (${totalTime.toFixed(1)}s)`;
        header.appendChild(timeSpan);

        console.log('💾 Stream finished — history not pushed (handled by backend)');

        
        // Mark as complete
        currentMessageDiv.classList.remove('streaming');
        currentMessageDiv = null;
        
        // Re-enable input
        enableChatInput();
        
        // Update stats
        updateStats();
        
    } else if (data.token) {
        // Append token to full response
        window.currentFullResponse += data.token;
        console.log('➕ Token added, total length:', window.currentFullResponse.length);
        
        // Remove cursor temporarily
        const cursor = contentDiv.querySelector('.cursor');
        if (cursor) cursor.remove();
        
        // Update content with formatted message and cursor
        contentDiv.innerHTML = formatMessage(window.currentFullResponse) + '<span class="cursor">▋</span>';
        
        // Auto-scroll to bottom
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
}

function enableChatInput() {
    console.log('🔓 Enabling chat input');
    isGenerating = false;
    chatInput.disabled = false;
    chatInput.placeholder = '💭 Ask me anything about Java...';
    sendBtn.disabled = false;
    sendBtn.textContent = 'Send';
    chatInput.focus();
}

function addMessage(content, type, responseTime = null) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;
    
    const header = document.createElement('div');
    header.className = 'message-header';
    header.innerHTML = type === 'user' ? '👤 You' : '🤖 AI Tutor';
    
    if (responseTime) {
        const timeSpan = document.createElement('span');
        timeSpan.style.fontSize = '0.8em';
        timeSpan.style.opacity = '0.7';
        timeSpan.textContent = ` (${responseTime.toFixed(1)}s)`;
        header.appendChild(timeSpan);
    }
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.innerHTML = formatMessage(content);
    
    messageDiv.appendChild(header);
    messageDiv.appendChild(contentDiv);
    chatMessages.appendChild(messageDiv);
    
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function formatMessage(text) {
    // Format code blocks
    text = text.replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
    text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    // Format line breaks
    text = text.replace(/\n/g, '<br>');
    
    return text;
}

async function clearChat() {
    // Confirm before clearing
    if (!confirm('Are you sure you want to clear all chat history? This action cannot be undone.')) {
        return;
    }
    
    try {
        console.log('🗑️ Clearing chat history...');
        
        // Disable clear button while processing
        clearBtn.disabled = true;
        clearBtn.textContent = 'Clearing...';
        
        // Call backend API to clear chat history from database
        const response = await fetch(`${API_BASE_URL}/chat/clear`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'same-origin'
        });
        
        if (response.status === 401) {
            alert('Session expired. Please login again.');
            window.location.href = '/login';
            return;
        }
        
        const data = await response.json();
        
        if (data.success) {
            // Clear UI
            const welcome = chatMessages.querySelector('.welcome-message');
            chatMessages.innerHTML = '';
            if (welcome) {
                chatMessages.appendChild(welcome);
            }
            
            // Clear in-memory conversation history
            conversationHistory = [];
            
            // Clear response times
            responseTimes = [];
            
            // Reset average response time display
            const avgDisplay = document.getElementById('avg-response-time');
            if (avgDisplay) {
                avgDisplay.innerHTML = '⚡ Avg: 0.0s';
                avgDisplay.title = '';
            }
            
            // Update stats to reflect cleared data
            await updateStats();
            
            console.log('✅ Chat history cleared successfully');
        } else {
            console.error('❌ Failed to clear chat:', data.error);
            alert('Failed to clear chat history: ' + (data.error || 'Unknown error'));
        }
        
    } catch (error) {
        console.error('❌ Error clearing chat:', error);
        alert('Failed to clear chat history. Please try again.');
    } finally {
        // Re-enable clear button
        clearBtn.disabled = false;
        clearBtn.textContent = 'Clear Chat';
    }
}

// Quiz Functions
async function startQuiz() {
    const topic = document.getElementById('quiz-topic').value;
    const numQuestions = document.getElementById('quiz-questions').value;
    const startBtn = document.getElementById('start-quiz-btn');
    
    startBtn.disabled = true;
    startBtn.textContent = 'Loading...';
    
    // Reset tracking
    quizIncorrectAnswers = [];
    currentQuizQuestions = [];
    
    try {
        const response = await fetch(`${API_BASE_URL}/quiz/start`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                topic: topic,
                num_questions: parseInt(numQuestions)
            }),
            credentials: 'same-origin'
        });
        
        if (response.status === 401) {
            alert('Session expired. Please login again.');
            window.location.href = '/login';
            return;
        }
        
        const data = await response.json();
        
        if (data.error) {
            alert(data.error);
            return;
        }
        
        currentQuiz = data;
        currentQuestionIndex = 0;
        
        document.getElementById('quiz-start').style.display = 'none';
        document.getElementById('quiz-screen').style.display = 'block';
        
        displayQuestion(data.current_question);
        
    } catch (error) {
        console.error('Error:', error);
        alert('Failed to start quiz. Please try again.');
    } finally {
        startBtn.disabled = false;
        startBtn.textContent = '🚀 Start Quiz';
    }
}

function displayQuestion(questionData) {
    document.getElementById('quiz-progress-text').textContent = 
        `Question ${questionData.question_number} of ${questionData.total_questions}`;
    
    const progress = (questionData.question_number / questionData.total_questions) * 100;
    document.getElementById('progress-fill').style.width = `${progress}%`;
    
    document.getElementById('question-text').textContent = questionData.question;
    
    const optionsContainer = document.getElementById('options-container');
    optionsContainer.innerHTML = '';
    
    questionData.options.forEach((option, index) => {
        const optionDiv = document.createElement('div');
        optionDiv.className = 'option';
        optionDiv.textContent = option;
        optionDiv.addEventListener('click', () => selectOption(index, optionDiv));
        optionsContainer.appendChild(optionDiv);
    });
    
    selectedOption = null;
    document.getElementById('submit-answer-btn').style.display = 'block';
    document.getElementById('next-question-btn').style.display = 'none';
    document.getElementById('finish-quiz-btn').style.display = 'none';
    document.getElementById('feedback-box').style.display = 'none';
}

function selectOption(index, element) {
    document.querySelectorAll('.option').forEach(opt => {
        opt.classList.remove('selected');
    });
    
    element.classList.add('selected');
    selectedOption = index;
}

async function submitAnswer() {
    if (selectedOption === null) {
        alert('Please select an answer');
        return;
    }
    
    const submitBtn = document.getElementById('submit-answer-btn');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Checking...';
    
    try {
        const response = await fetch(`${API_BASE_URL}/quiz/submit`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                quiz_id: currentQuiz.quiz_id,
                question_index: currentQuestionIndex,
                selected_option: selectedOption
            }),
            credentials: 'same-origin'
        });
        
        if (response.status === 401) {
            alert('Session expired. Please login again.');
            window.location.href = '/login';
            return;
        }
        
        const data = await response.json();
        
        // Track incorrect answer
        if (!data.is_correct) {
            const currentQuestion = document.getElementById('question-text').textContent;
            quizIncorrectAnswers.push({
                question: currentQuestion,
                selected: selectedOption,
                correct: data.correct_option
            });
        }
        
        // Track all questions
        currentQuizQuestions.push({
            question: document.getElementById('question-text').textContent,
            correct: data.correct_option
        });
        
        const feedbackBox = document.getElementById('feedback-box');
        feedbackBox.className = `feedback-box ${data.is_correct ? 'correct' : 'incorrect'}`;
        feedbackBox.innerHTML = `
            <strong>${data.is_correct ? '✅ Correct!' : '❌ Incorrect'}</strong><br>
            ${data.explanation}
        `;
        feedbackBox.style.display = 'block';
        
        document.getElementById('submit-answer-btn').style.display = 'none';

        if (data.is_complete) {
            document.getElementById('finish-quiz-btn').style.display = 'block';
            currentQuiz.final_results = data.final_results;
        } else {
            document.getElementById('next-question-btn').style.display = 'block';
            currentQuiz.next_question = data.next_question;
            submitBtn.disabled = false;
            submitBtn.textContent = 'Submit Answer';
        }
        
        currentQuestionIndex++;
        updateStats();
        
    } catch (error) {
        console.error('Error:', error);
        alert('Failed to submit answer. Please try again.');
        submitBtn.disabled = false;
    }
}

async function generateRecommendations() {
    if (!currentQuiz || !currentQuiz.quiz_id) {
        console.error('No active quiz');
        return null;
    }
    
    showLoading();
    
    try {
        console.log('📊 Generating recommendations...');
        
        const response = await fetch(`${API_BASE_URL}/quiz/recommendations`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                quiz_id: currentQuiz.quiz_id,
                topic: currentQuiz.topic,
                incorrect_answers: quizIncorrectAnswers,
                questions: currentQuizQuestions
            }),
            credentials: 'same-origin'
        });
        
        if (response.status === 401) {
            window.location.href = '/login';
            return null;
        }
        
        const data = await response.json();
        
        if (data.success) {
            console.log('✅ Recommendations generated:', data.recommendations);
            return data.recommendations;
        } else {
            console.error('Failed to generate recommendations:', data.error);
            return null;
        }
        
    } catch (error) {
        console.error('Error generating recommendations:', error);
        return null;
    } finally {
        hideLoading();
    }
}

// NEW: Display recommendations in UI
function displayRecommendations(recommendations) {
    const recommendationsDiv = document.getElementById('quiz-recommendations');
    
    if (!recommendations || !recommendations.recommendations || recommendations.recommendations.length === 0) {
        recommendationsDiv.innerHTML = `
            <div class="recommendation-header">
                <h3>🌟 Excellent Work!</h3>
                <p>${recommendations?.overall_message || 'Perfect score! Keep up the great work!'}</p>
            </div>
        `;
        return;
    }
    
    let html = `
        <div class="recommendation-header">
            <h3>📚 Study Recommendations</h3>
            <p>${recommendations.overall_message}</p>
        </div>
        <div class="recommendations-list">
    `;
    
    recommendations.recommendations.forEach((rec, index) => {
        const priorityClass = rec.priority === 'high' ? 'priority-high' : 'priority-medium';
        const priorityIcon = rec.priority === 'high' ? '🔴' : '🟡';
        
        html += `
            <div class="recommendation-card ${priorityClass}">
                <div class="recommendation-header-card">
                    <span class="priority-badge">${priorityIcon} ${rec.priority.toUpperCase()} PRIORITY</span>
                    <h4>${rec.topic}</h4>
                </div>
                <p class="recommendation-description">${rec.description}</p>
                <ul class="study-points">
                    ${rec.study_points.map(point => `<li>${point}</li>`).join('')}
                </ul>
                <button class="btn btn-secondary btn-small" onclick="askAboutTopic('${rec.topic}')">
                    💬 Ask AI Tutor
                </button>
            </div>
        `;
    });
    
    html += '</div>';
    recommendationsDiv.innerHTML = html;
}

// NEW: Ask AI tutor about specific topic
function askAboutTopic(topic) {
    // Switch to chat tab
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.tab === 'chat') {
            btn.classList.add('active');
        }
    });
    
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById('chat-tab').classList.add('active');
    
    // Pre-fill chat input with topic question
    const chatInput = document.getElementById('chat-input');
    chatInput.value = `Can you explain ${topic} in Java with examples?`;
    chatInput.focus();
    
    // Scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function nextQuestion() {
    if (currentQuiz && currentQuiz.next_question) {
        displayQuestion(currentQuiz.next_question);
    }
}

async function finishQuiz() {
    if (!currentQuiz || !currentQuiz.final_results) return;
    
    const results = currentQuiz.final_results;
    
    document.getElementById('quiz-screen').style.display = 'none';
    
    const resultsScreen = document.getElementById('quiz-results');
    resultsScreen.style.display = 'block';
    
    document.getElementById('final-score').textContent = `${results.score}/${results.total}`;
    document.getElementById('final-percentage').textContent = `${results.percentage}%`;
    
    let badge = '';
    if (results.percentage >= 90) badge = '🌟 Excellent!';
    else if (results.percentage >= 70) badge = '👍 Good Job!';
    else if (results.percentage >= 50) badge = '📚 Keep Learning!';
    else badge = '💪 Practice More!';
    
    document.getElementById('performance-badge').textContent = badge;
    
    // NEW: Generate and display recommendations
    const recommendations = await generateRecommendations();
    if (recommendations) {
        displayRecommendations(recommendations);
    }
    
    loadDashboard();
}

function resetQuiz() {
    currentQuiz = null;
    currentQuestionIndex = 0;
    selectedOption = null;
    quizIncorrectAnswers = [];
    currentQuizQuestions = [];
    
    document.getElementById('quiz-results').style.display = 'none';
    document.getElementById('quiz-start').style.display = 'block';
}

// Stats Functions
async function updateStats() {
    try {
        const response = await fetch(`${API_BASE_URL}/stats`, {
            credentials: 'same-origin'
        });
        
        if (response.status === 401) {
            return;
        }
        
        const data = await response.json();
        
        // Update all stat elements with the same ID
        document.querySelectorAll('#stat-messages').forEach(el => {
            el.textContent = data.total_messages || 0;
        });
        document.getElementById('stat-quizzes').textContent = data.total_quizzes || 0;
        document.getElementById('stat-time').textContent = data.session_time || '0h 0m';
        document.getElementById('stat-topics').textContent = data.topics_covered || 0;
        
    } catch (error) {
        console.error('Failed to update stats:', error);
    }
}

// Dashboard Functions
async function loadDashboard() {
    console.log('📊 Loading enhanced dashboard...');
    
    // Show loading state
    showDashboardLoading();
    
    try {
        const metricsResponse = await fetch(`${API_BASE_URL}/metrics`, {
            credentials: 'same-origin'
        });
        
        if (metricsResponse.status === 401) {
            window.location.href = '/login';
            return;
        }
        
        const metrics = await metricsResponse.json();
        console.log('📊 Metrics loaded:', metrics);
        
        // Update all dashboard components
        updateOverviewCards(metrics);
        updateQuickStats(metrics);
        updateActivityTimeline(metrics);
        updateAchievements(metrics);
        updateGoals(metrics);
        updateStreak(metrics);
        
        // Create charts
        await createCharts(metrics);
        
    } catch (error) {
        console.error('Failed to load dashboard:', error);
        showDashboardError();
    }
}

function showDashboardLoading() {
    // Add subtle loading state without blocking UI
    document.querySelectorAll('.overview-card .card-value').forEach(el => {
        el.style.opacity = '0.5';
    });
}

function showDashboardError() {
    console.error('Dashboard error - showing fallback');
}

// Update Overview Cards
function updateOverviewCards(metrics) {
    // Animate number changes
    animateValue('overview-messages', 0, metrics.chat.total_messages, 800);
    animateValue('overview-quizzes', 0, metrics.quiz.total_quizzes, 800);
    
    document.getElementById('overview-accuracy').textContent = metrics.quiz.accuracy + '%';
    document.getElementById('overview-time').textContent = metrics.session.duration_formatted;
    
    // Restore opacity
    document.querySelectorAll('.overview-card .card-value').forEach(el => {
        el.style.opacity = '1';
    });
}

// Animate number counting
function animateValue(id, start, end, duration) {
    const element = document.getElementById(id);
    if (!element) return;
    
    const range = end - start;
    const increment = range / (duration / 16);
    let current = start;
    
    const timer = setInterval(() => {
        current += increment;
        if ((increment > 0 && current >= end) || (increment < 0 && current <= end)) {
            current = end;
            clearInterval(timer);
        }
        element.textContent = Math.floor(current);
    }, 16);
}

// Update Quick Stats
function updateQuickStats(metrics) {
    document.getElementById('quick-questions').textContent = metrics.quiz.total_questions;
    document.getElementById('quick-correct').textContent = metrics.quiz.correct_answers;
    document.getElementById('quick-topics').textContent = metrics.chat.total_topics;
    document.getElementById('quick-response').textContent = 
        (metrics.performance.avg_response_time * 1000).toFixed(0) + 'ms';
}

// Update Activity Timeline
function updateActivityTimeline(metrics) {
    const timeline = document.getElementById('activity-timeline');
    
    let activities = [];
    
    // Add recent quizzes
    if (metrics.history && metrics.history.recent_quizzes) {
        metrics.history.recent_quizzes.slice(0, 3).forEach(quiz => {
            activities.push({
                icon: '🧠',
                title: `Completed ${quiz.topic} Quiz`,
                time: formatTimeAgo(quiz.completed_at),
                score: `${quiz.correct_answers}/${quiz.total_questions}`,
                timestamp: new Date(quiz.completed_at)
            });
        });
    }
    
    // Add recent chats
    if (metrics.history && metrics.history.recent_chats) {
        metrics.history.recent_chats.slice(0, 2).forEach(chat => {
            activities.push({
                icon: '💬',
                title: 'Had a conversation',
                time: formatTimeAgo(chat.timestamp),
                score: null,
                timestamp: new Date(chat.timestamp)
            });
        });
    }
    
    // Sort by timestamp
    activities.sort((a, b) => b.timestamp - a.timestamp);
    
    // Display activities
    if (activities.length === 0) {
        timeline.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📭</div>
                <div class="empty-state-text">No recent activity yet. Start learning!</div>
            </div>
        `;
        return;
    }
    
    timeline.innerHTML = activities.slice(0, 5).map(activity => `
        <div class="activity-item">
            <div class="activity-icon">${activity.icon}</div>
            <div class="activity-content">
                <div class="activity-title">${activity.title}</div>
                <div class="activity-time">${activity.time}</div>
            </div>
            ${activity.score ? `<div class="activity-score">${activity.score}</div>` : ''}
        </div>
    `).join('');
}

// Format time ago
function formatTimeAgo(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);
    
    if (seconds < 60) return 'Just now';
    if (seconds < 3600) return Math.floor(seconds / 60) + ' minutes ago';
    if (seconds < 86400) return Math.floor(seconds / 3600) + ' hours ago';
    if (seconds < 604800) return Math.floor(seconds / 86400) + ' days ago';
    return date.toLocaleDateString();
}

// Update Achievements
function updateAchievements(metrics) {
    const achievements = [
        {
            icon: '🌟',
            name: 'First Message',
            unlocked: metrics.chat.total_messages >= 1
        },
        {
            icon: '🎯',
            name: 'Quiz Master',
            unlocked: metrics.quiz.total_quizzes >= 5
        },
        {
            icon: '🔥',
            name: '7-Day Streak',
            unlocked: false // TODO: Implement streak tracking
        },
        {
            icon: '💯',
            name: 'Perfect Score',
            unlocked: metrics.quiz.accuracy === 100 && metrics.quiz.total_quizzes > 0
        }
    ];
    
    const grid = document.getElementById('achievements-grid');
    grid.innerHTML = achievements.map(achievement => `
        <div class="achievement-badge ${achievement.unlocked ? '' : 'locked'}">
            <div class="badge-icon">${achievement.icon}</div>
            <div class="badge-name">${achievement.name}</div>
        </div>
    `).join('');
}

// Update Weekly Goals
function updateGoals(metrics) {
    // Chat goal (10 messages)
    const chatProgress = Math.min((metrics.chat.total_messages / 10) * 100, 100);
    document.getElementById('goal-chat-text').textContent = `${metrics.chat.total_messages}/10`;
    document.getElementById('goal-chat-fill').style.width = chatProgress + '%';
    
    // Quiz goal (5 quizzes)
    const quizProgress = Math.min((metrics.quiz.total_quizzes / 5) * 100, 100);
    document.getElementById('goal-quiz-text').textContent = `${metrics.quiz.total_quizzes}/5`;
    document.getElementById('goal-quiz-fill').style.width = quizProgress + '%';
    
    // Topics goal (8 topics)
    const topicsProgress = Math.min((metrics.chat.total_topics / 8) * 100, 100);
    document.getElementById('goal-topics-text').textContent = `${metrics.chat.total_topics}/8`;
    document.getElementById('goal-topics-fill').style.width = topicsProgress + '%';
}

// Update Streak
function updateStreak(metrics) {
    // Simple calculation: days since first use
    const daysSinceStart = Math.floor(metrics.session.duration_seconds / 86400) + 1;
    document.getElementById('streak-days').textContent = daysSinceStart;
}

// Create Charts using Chart.js
async function createCharts(metrics) {
    // Destroy existing charts
    if (quizChart) quizChart.destroy();
    if (radarChart) radarChart.destroy();
    
    // Quiz Performance Chart
    await createQuizPerformanceChart(metrics);
    
    // Topic Radar Chart
    await createTopicRadarChart(metrics);
}

async function createQuizPerformanceChart(metrics) {
    const ctx = document.getElementById('quizPerformanceChart');
    if (!ctx) return;
    
    let labels = [];
    let scores = [];
    
    if (metrics.history && metrics.history.recent_quizzes && metrics.history.recent_quizzes.length > 0) {
        // Get last 10 quizzes
        const quizzes = metrics.history.recent_quizzes.slice(0, 10).reverse();
        
        labels = quizzes.map((q, i) => `Quiz ${i + 1}`);
        scores = quizzes.map(q => q.score_percentage);
    } else {
        // Default empty data
        labels = ['No Data'];
        scores = [0];
    }
    
    quizChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Score %',
                data: scores,
                borderColor: '#667eea',
                backgroundColor: 'rgba(102, 126, 234, 0.1)',
                borderWidth: 3,
                fill: true,
                tension: 0.4,
                pointRadius: 6,
                pointHoverRadius: 8,
                pointBackgroundColor: '#667eea',
                pointBorderColor: '#fff',
                pointBorderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: '#667eea',
                    padding: 12,
                    titleColor: '#fff',
                    bodyColor: '#fff',
                    borderColor: '#fff',
                    borderWidth: 2,
                    displayColors: false,
                    callbacks: {
                        label: function(context) {
                            return 'Score: ' + context.parsed.y.toFixed(1) + '%';
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    },
                    ticks: {
                        callback: function(value) {
                            return value + '%';
                        }
                    }
                },
                x: {
                    grid: {
                        display: false
                    }
                }
            }
        }
    });
}

async function createTopicRadarChart(metrics) {
    const ctx = document.getElementById('topicRadarChart');
    if (!ctx) return;
    
    // Calculate topic strengths
    const topicStats = metrics.history?.quiz_stats_by_topic || [];
    
    let labels = [];
    let scores = [];
    
    if (topicStats.length > 0) {
        labels = topicStats.map(t => t.topic);
        scores = topicStats.map(t => t.avg_score || 0);
    } else {
        // Default data
        labels = ['Basics', 'OOP', 'Advanced', 'Frameworks'];
        scores = [0, 0, 0, 0];
    }
    
    radarChart = new Chart(ctx, {
        type: 'radar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Mastery Level',
                data: scores,
                backgroundColor: 'rgba(102, 126, 234, 0.2)',
                borderColor: '#667eea',
                borderWidth: 2,
                pointBackgroundColor: '#667eea',
                pointBorderColor: '#fff',
                pointBorderWidth: 2,
                pointRadius: 5,
                pointHoverRadius: 7
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                r: {
                    beginAtZero: true,
                    max: 100,
                    ticks: {
                        stepSize: 25,
                        callback: function(value) {
                            return value + '%';
                        }
                    },
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    }
                }
            }
        }
    });
}

// Keep the old displayMetrics for backward compatibility
function displayMetrics(metrics) {
    // Just call the new enhanced functions
    updateOverviewCards(metrics);
    updateQuickStats(metrics);
    updateActivityTimeline(metrics);
    updateAchievements(metrics);
    updateGoals(metrics);
    updateStreak(metrics);
    createCharts(metrics);
}
function showLoading() {
    loadingOverlay.classList.add('active');
}

function hideLoading() {
    loadingOverlay.classList.remove('active');
}

async function logout() {
    if (!confirm('Are you sure you want to logout?')) {
        return;
    }
    
    showLoading();
    
    try {
        await fetch(`${API_BASE_URL}/logout`, { method: 'POST' });
        window.location.href = '/login';
    } catch (error) {
        console.error('Logout failed:', error);
        alert('Failed to logout. Please try again.');
        hideLoading();
    }
}

function updateAverageResponseTime() {
    if (responseTimes.length > 0) {
        const avgTime = responseTimes.reduce((a, b) => a + b, 0) / responseTimes.length;
        const minTime = Math.min(...responseTimes);
        const maxTime = Math.max(...responseTimes);
        
        const display = document.getElementById('avg-response-time');
        display.innerHTML = `⚡ Avg: ${avgTime.toFixed(1)}s (Min: ${minTime.toFixed(1)}s, Max: ${maxTime.toFixed(1)}s)`;
        display.title = `Based on ${responseTimes.length} response(s)`;
    }
}

function updateStatsFromSocket(data) {
    document.querySelectorAll('#stat-messages').forEach(el => {
        el.textContent = data.total_messages || 0;
    });
    document.getElementById('stat-quizzes').textContent = data.total_quizzes || 0;
    document.getElementById('stat-topics').textContent = data.topics_covered || 0;
}

// ==================== CODE PLAYGROUND ====================
// Add these variables at the top with other global variables:

let monacoEditor = null;
let isCodeRunning = false;

// Code Templates
const codeTemplates = {
    hello: `public class Main {
    public static void main(String[] args) {
        System.out.println("Hello, World!");
    }
}`,
    
    class: `public class Main {
    // Instance variables
    private String name;
    private int age;
    
    // Constructor
    public Main(String name, int age) {
        this.name = name;
        this.age = age;
    }
    
    // Getter and Setter methods
    public String getName() {
        return name;
    }
    
    public void setName(String name) {
        this.name = name;
    }
    
    // Main method
    public static void main(String[] args) {
        Main obj = new Main("Java Learner", 20);
        System.out.println("Name: " + obj.getName());
        System.out.println("Age: " + obj.age);
    }
}`,
    
    scanner: `import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        
        System.out.print("Enter your name: ");
        String name = scanner.nextLine();
        
        System.out.print("Enter your age: ");
        int age = scanner.nextInt();
        
        System.out.println("\\nHello, " + name + "!");
        System.out.println("You are " + age + " years old.");
        
        scanner.close();
    }
}`,
    
    array: `public class Main {
    public static void main(String[] args) {
        // Array declaration and initialization
        int[] numbers = {10, 20, 30, 40, 50};
        
        // Print array elements
        System.out.println("Array elements:");
        for (int i = 0; i < numbers.length; i++) {
            System.out.println("Index " + i + ": " + numbers[i]);
        }
        
        // Calculate sum
        int sum = 0;
        for (int num : numbers) {
            sum += num;
        }
        System.out.println("\\nSum: " + sum);
        System.out.println("Average: " + (sum / numbers.length));
    }
}`,
    
    oop: `// Inheritance Example
class Animal {
    protected String name;
    
    public Animal(String name) {
        this.name = name;
    }
    
    public void makeSound() {
        System.out.println(name + " makes a sound");
    }
}

class Dog extends Animal {
    public Dog(String name) {
        super(name);
    }
    
    @Override
    public void makeSound() {
        System.out.println(name + " barks: Woof! Woof!");
    }
}

public class Main {
    public static void main(String[] args) {
        Animal animal = new Animal("Generic Animal");
        animal.makeSound();
        
        Dog dog = new Dog("Buddy");
        dog.makeSound();
        
        // Polymorphism
        Animal polymorphicDog = new Dog("Max");
        polymorphicDog.makeSound();
    }
}`,
    
    exception: `public class Main {
    public static void main(String[] args) {
        // Try-catch example
        try {
            int[] numbers = {1, 2, 3};
            System.out.println("Accessing index 0: " + numbers[0]);
            System.out.println("Accessing index 5: " + numbers[5]); // This will throw exception
        } catch (ArrayIndexOutOfBoundsException e) {
            System.out.println("Error: Array index out of bounds!");
            System.out.println("Message: " + e.getMessage());
        } finally {
            System.out.println("\\nFinally block always executes!");
        }
        
        // Division by zero
        try {
            int result = divide(10, 0);
            System.out.println("Result: " + result);
        } catch (ArithmeticException e) {
            System.out.println("\\nError: " + e.getMessage());
        }
    }
    
    public static int divide(int a, int b) {
        return a / b;
    }
}`
};

// Add to setupEventListeners function:

// Initialize Monaco Editor when Code tab is activated
function switchTab(tabName) {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');
    
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(`${tabName}-tab`).classList.add('active');
    
    if (tabName === 'dashboard') {
        loadDashboard();
    } else if (tabName === 'code') {
        // Initialize Monaco Editor if not already done
        if (!monacoEditor) {
            initMonacoEditor();
        }
    }
}

// Initialize Monaco Editor
function initMonacoEditor() {
    console.log('🎨 Initializing Monaco Editor...');
    
    // Load Monaco Editor from CDN
    require.config({ paths: { vs: 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs' }});
    
    require(['vs/editor/editor.main'], function() {
        const container = document.getElementById('monaco-editor');
        
        monacoEditor = monaco.editor.create(container, {
            value: codeTemplates.hello,
            language: 'java',
            theme: 'vs-dark',
            automaticLayout: true,
            fontSize: 14,
            minimap: { enabled: true },
            scrollBeyondLastLine: false,
            lineNumbers: 'on',
            roundedSelection: true,
            cursorStyle: 'line',
            formatOnPaste: true,
            formatOnType: true,
            suggestOnTriggerCharacters: true,
            acceptSuggestionOnEnter: 'on',
            tabSize: 4,
            wordWrap: 'on'
        });
        
        // Update line count on change
        monacoEditor.onDidChangeModelContent(() => {
            updateLineCount();
        });
        
        // Keyboard shortcut: Ctrl+Enter to run
        monacoEditor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => {
            runCode();
        });
        
        console.log('✅ Monaco Editor initialized');
        updateLineCount();
    });
}

// Update line count
function updateLineCount() {
    if (!monacoEditor) return;
    const lineCount = monacoEditor.getModel().getLineCount();
    document.getElementById('code-lines').textContent = `${lineCount} lines`;
}

// Load template
function loadTemplate(event) {
    const template = event.target.value;
    if (template && codeTemplates[template]) {
        if (monacoEditor) {
            monacoEditor.setValue(codeTemplates[template]);
        }
        // Reset dropdown
        event.target.value = '';
    }
}

// Clear code
function clearCode() {
    if (confirm('Are you sure you want to clear the code?')) {
        if (monacoEditor) {
            monacoEditor.setValue('');
        }
    }
}

// Clear output
function clearOutput() {
    const output = document.getElementById('code-output');
    output.innerHTML = `
        <div class="output-placeholder">
            <div class="placeholder-icon">💡</div>
            <div class="placeholder-text">Run your code to see output here</div>
            <div class="placeholder-hint">Press Run Code or Ctrl+Enter</div>
        </div>
    `;
}

function clearInput() {
    document.getElementById('code-input').value = '';
}

// Run code
async function runCode() {
    if (!monacoEditor || isCodeRunning) return;
    
    const code = monacoEditor.getValue().trim();
    
    if (!code) {
        showNotification('Please write some code first!', 'warning');
        return;
    }
    
    // Get user input
    const userInput = document.getElementById('code-input').value;
    
    // Update UI
    isCodeRunning = true;
    const runBtn = document.getElementById('run-code-btn');
    const originalText = runBtn.innerHTML;
    runBtn.innerHTML = '⏳ Running...';
    runBtn.disabled = true;
    runBtn.classList.add('running');
    
    const output = document.getElementById('code-output');
    output.innerHTML = `
        <div class="code-loading">
            <div class="code-loading-spinner"></div>
            <span>Compiling and executing your code...</span>
        </div>
    `;
    
    try {
        console.log('🚀 Executing code with input...');
        
        const response = await fetch(`${API_BASE_URL}/code/run`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'same-origin',
            body: JSON.stringify({ 
                code: code,
                input: userInput  // Send input to backend
            })
        });
        
        if (response.status === 401) {
            window.location.href = '/login';
            return;
        }
        
        const result = await response.json();
        
        console.log('✅ Execution result:', result);
        
        displayOutput(result, userInput);
        
    } catch (error) {
        console.error('❌ Execution error:', error);
        displayOutput({
            success: false,
            error: 'Failed to execute code. Please try again.',
            output: '',
            execution_time: 0
        }, userInput);
    } finally {
        // Reset UI
        isCodeRunning = false;
        runBtn.innerHTML = originalText;
        runBtn.disabled = false;
        runBtn.classList.remove('running');
    }
}

// Display output
function displayOutput(result, userInput = '') {
    const output = document.getElementById('code-output');
    let html = '';
    
    // Show input if provided
    if (userInput && userInput.trim()) {
        html += `
            <div class="output-input">
                <div class="output-input-label">📥 Input Provided:</div>
                <div class="output-input-content">${escapeHtml(userInput)}</div>
            </div>
        `;
    }
    
    // Execution info
    if (result.execution_time) {
        html += `<div class="output-info">⏱️ Execution time: ${result.execution_time.toFixed(2)}s</div>`;
    }
    
    // Success or error message
    if (result.success) {
        html += `<div class="output-success">✅ Compilation and execution successful!</div>`;
    } else {
        html += `<div class="output-error">❌ Compilation or execution failed</div>`;
    }
    
    // Output content
    if (result.output) {
        html += `<div class="output-content">${escapeHtml(result.output)}</div>`;
    }
    
    // Error details
    if (result.error) {
        html += `<div class="output-error"><strong>Error Details:</strong>\n${escapeHtml(result.error)}</div>`;
    }
    
    // If no output
    if (!result.output && !result.error) {
        html += `<div class="output-info">ℹ️ No output generated</div>`;
    }
    
    output.innerHTML = html;
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Show notification helper
function showNotification(message, type = 'info') {
    // Simple notification - you can enhance this
    console.log(`[${type.toUpperCase()}] ${message}`);
    alert(message);
}
