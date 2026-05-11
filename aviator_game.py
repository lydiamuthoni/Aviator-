from flask import Flask, request, jsonify, render_template_string, session
from flask_cors import CORS
from pymongo import MongoClient
from bson import ObjectId
import hashlib
import secrets
import random
import threading
import time
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)  # Secret key for session management
CORS(app, supports_credentials=True)

# ============================================
# MONGODB CONNECTION
# ============================================
# PASTE YOUR MONGODB CONNECTION STRING BELOW:
MONGO_URI = "mongodb+srv://Sunny:<DRpM7nLo6aVVSSxs>@cluster0.amkty7g.mongodb.net/?appName=Cluster0"  # <-- REPLACE WITH YOUR ACTUAL CONNECTION STRING
# For MongoDB Atlas, use: "mongodb+srv://username:password@cluster.mongodb.net/"

try:
    client = MongoClient(MONGO_URI)
    db = client['aviator_game_db']
    users_collection = db['users']
    game_sessions_collection = db['game_sessions']
    
    # Create unique index on username
    users_collection.create_index('username', unique=True)
    print("✅ MongoDB connected successfully!")
except Exception as e:
    print(f"⚠️ MongoDB connection warning: {e}")
    print("Will run in demo mode (in-memory storage)")
    # Fallback to in-memory storage if MongoDB not available
    class MockCollection:
        def __init__(self):
            self.data = {}
            self.counter = 1
        
        def find_one(self, query):
            username = query.get('username')
            if username and username in self.data:
                return self.data[username]
            return None
        
        def insert_one(self, document):
            doc_id = self.counter
            document['_id'] = doc_id
            self.data[document['username']] = document
            self.counter += 1
            return type('obj', (object,), {'inserted_id': doc_id})()
        
        def update_one(self, filter, update, upsert=False):
            username = filter.get('username')
            if username in self.data:
                self.data[username].update(update.get('$set', {}))
            return type('obj', (object,), {'modified_count': 1})()
    
    users_collection = MockCollection()
    game_sessions_collection = MockCollection()

# ============================================
# UNIFORM GAME LOGIC (SAME FOR ALL USERS)
# ============================================
class UniformGameEngine:
    """Ensures all connected users see the SAME multiplier at the SAME time"""
    
    def __init__(self):
        self.current_multiplier = 1.00
        self.game_active = True
        self.game_start_time = None
        self.crash_point = None
        self.last_update_time = time.time()
        self.lock = threading.Lock()
        self.crash_history = []
        self.start_new_game()
    
    def start_new_game(self):
        """Start a new game round with a random crash point"""
        with self.lock:
            self.current_multiplier = 1.00
            self.game_active = True
            self.game_start_time = time.time()
            # Generate random crash point between 1.05x and 50x
            # More likely to crash between 1.5x and 10x
            rand = random.random()
            if rand < 0.3:  # 30% chance early crash
                self.crash_point = random.uniform(1.05, 2.0)
            elif rand < 0.7:  # 40% chance medium crash
                self.crash_point = random.uniform(2.0, 5.0)
            elif rand < 0.9:  # 20% chance high crash
                self.crash_point = random.uniform(5.0, 15.0)
            else:  # 10% chance extremely high
                self.crash_point = random.uniform(15.0, 50.0)
            
            self.last_update_time = time.time()
            
            # Save game session to database
            try:
                game_sessions_collection.insert_one({
                    'start_time': datetime.now(),
                    'crash_point': self.crash_point,
                    'status': 'active'
                })
            except:
                pass
    
    def update_multiplier(self):
        """Update multiplier based on elapsed time (uniform for all users)"""
        with self.lock:
            if not self.game_active:
                return self.crash_point
            
            elapsed = time.time() - self.game_start_time
            # Exponential growth but smooth
            self.current_multiplier = 1.00 + (elapsed * 0.15)
            
            # Check if game should crash
            if self.current_multiplier >= self.crash_point:
                self.game_active = False
                self.current_multiplier = self.crash_point
                # Schedule next game in 3 seconds
                threading.Timer(3.0, self.start_new_game).start()
            
            return self.current_multiplier
    
    def get_game_state(self):
        """Get current game state (same for all users)"""
        with self.lock:
            if self.game_active:
                # Update multiplier based on time
                elapsed = time.time() - self.game_start_time
                self.current_multiplier = 1.00 + (elapsed * 0.15)
                if self.current_multiplier >= self.crash_point:
                    self.game_active = False
                    self.current_multiplier = self.crash_point
                    threading.Timer(3.0, self.start_new_game).start()
            
            return {
                'multiplier': round(self.current_multiplier, 2),
                'game_active': self.game_active,
                'crash_point': round(self.crash_point, 2) if self.crash_point else None,
                'next_game_in': 0 if self.game_active else max(0, 3 - (time.time() - self.game_start_time - (self.crash_point / 0.15)))
            }

# Initialize the uniform game engine
game_engine = UniformGameEngine()

# Start background thread to update game state
def game_loop():
    """Background thread to continuously update game state"""
    while True:
        game_engine.update_multiplier()
        time.sleep(0.05)  # Update 20 times per second

threading.Thread(target=game_loop, daemon=True).start()

# ============================================
# HELPER FUNCTIONS
# ============================================
def hash_password(password):
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def login_required(f):
    """Decorator to check if user is logged in"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"success": False, "message": "Please login first"}), 401
        return f(*args, **kwargs)
    return decorated_function

# ============================================
# HTML/CSS/JS FRONTEND
# ============================================
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>Aviator Game - Multiplayer Edition</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            background: linear-gradient(135deg, #0a0f1e 0%, #0c1222 100%);
            font-family: 'Segoe UI', 'Poppins', system-ui, sans-serif;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 1rem;
        }

        @keyframes slideIn {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }

        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.05); }
        }

        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            25% { transform: translateX(-5px); }
            75% { transform: translateX(5px); }
        }

        .container {
            background: rgba(12, 20, 35, 0.9);
            backdrop-filter: blur(12px);
            border-radius: 2rem;
            padding: 2rem;
            width: 100%;
            max-width: 500px;
            box-shadow: 0 25px 45px rgba(0, 0, 0, 0.5);
            animation: slideIn 0.5s ease-out;
        }

        .game-header {
            text-align: center;
            margin-bottom: 2rem;
        }

        .game-icon {
            display: inline-flex;
            background: linear-gradient(135deg, #ff8c00, #ff2e00);
            padding: 0.8rem;
            border-radius: 30px;
            margin-bottom: 1rem;
            animation: pulse 2s ease-in-out infinite;
        }

        h1 {
            font-size: 2rem;
            background: linear-gradient(120deg, #FFD966, #FFA500, #FF5E00);
            background-clip: text;
            -webkit-background-clip: text;
            color: transparent;
        }

        .tagline {
            color: #9aaec7;
            font-size: 0.85rem;
        }

        .input-group {
            margin-bottom: 1.2rem;
        }

        .input-label {
            display: block;
            margin-bottom: 0.5rem;
            color: #dfe9ff;
            font-size: 0.85rem;
            font-weight: 600;
        }

        .input-field {
            width: 100%;
            background: rgba(0, 0, 0, 0.5);
            border: 2px solid rgba(255, 165, 0, 0.3);
            border-radius: 1rem;
            padding: 0.8rem 1rem;
            color: white;
            font-size: 1rem;
            outline: none;
            transition: all 0.2s;
        }

        .input-field:focus {
            border-color: #ffa500;
            box-shadow: 0 0 0 3px rgba(255, 165, 0, 0.2);
        }

        .btn {
            width: 100%;
            padding: 0.9rem;
            border-radius: 1rem;
            font-weight: 700;
            font-size: 1rem;
            cursor: pointer;
            transition: all 0.2s;
            border: none;
            margin-top: 0.5rem;
        }

        .btn-primary {
            background: linear-gradient(95deg, #ff8c00, #ff5400);
            color: white;
        }

        .btn-primary:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(255, 80, 0, 0.4);
        }

        .btn-secondary {
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 165, 0, 0.5);
            color: #ffc285;
        }

        .btn-danger {
            background: linear-gradient(95deg, #dc3545, #c82333);
            color: white;
        }

        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }

        .message {
            margin-top: 1rem;
            padding: 0.8rem;
            border-radius: 1rem;
            text-align: center;
            font-size: 0.85rem;
        }

        .error { background: rgba(220, 53, 69, 0.2); color: #ff9f8f; border: 1px solid rgba(220, 53, 69, 0.5); }
        .success { background: rgba(40, 167, 69, 0.2); color: #8effb2; border: 1px solid rgba(40, 167, 69, 0.5); }
        .info { background: rgba(23, 162, 184, 0.2); color: #90caf9; border: 1px solid rgba(23, 162, 184, 0.5); }

        .multiplier-display {
            text-align: center;
            padding: 2rem;
            background: rgba(0, 0, 0, 0.4);
            border-radius: 1.5rem;
            margin: 1rem 0;
        }

        .multiplier-value {
            font-size: 4rem;
            font-weight: 800;
            color: #ffa500;
            text-shadow: 0 0 30px rgba(255, 165, 0, 0.5);
        }

        .crash-warning {
            color: #ff6b6b;
            animation: shake 0.5s ease-in-out;
        }

        .stats {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 1rem;
            margin: 1rem 0;
        }

        .stat-card {
            background: rgba(0, 0, 0, 0.4);
            padding: 0.8rem;
            border-radius: 1rem;
            text-align: center;
        }

        .stat-label {
            font-size: 0.7rem;
            color: #9aaec7;
        }

        .stat-value {
            font-size: 1.2rem;
            font-weight: 700;
            color: #ffa500;
        }

        .action-buttons {
            display: flex;
            gap: 1rem;
            margin: 1rem 0;
        }

        .tab-buttons {
            display: flex;
            gap: 1rem;
            margin-bottom: 1.5rem;
        }

        .tab-btn {
            flex: 1;
            padding: 0.7rem;
            background: rgba(0, 0, 0, 0.4);
            border: none;
            border-radius: 0.8rem;
            color: white;
            cursor: pointer;
            transition: all 0.2s;
        }

        .tab-btn.active {
            background: linear-gradient(95deg, #ff8c00, #ff5400);
        }

        .hide {
            display: none;
        }

        @media (max-width: 480px) {
            .container { padding: 1.5rem; }
            .multiplier-value { font-size: 2.5rem; }
            .stats { gap: 0.5rem; }
        }
    </style>
</head>
<body>
    <div id="app"></div>

    <script>
        const API_BASE = '';
        
        // Show appropriate screen based on login state
        async function checkLoginState() {
            try {
                const response = await fetch(`${API_BASE}/api/check_session`, {
                    credentials: 'include'
                });
                const data = await response.json();
                if (data.logged_in) {
                    showGameLobby(data.user);
                } else {
                    showAuthScreen();
                }
            } catch (error) {
                showAuthScreen();
            }
        }
        
        function showAuthScreen() {
            const app = document.getElementById('app');
            app.innerHTML = `
                <div class="container">
                    <div class="game-header">
                        <div class="game-icon">
                            <svg width="48" height="48" viewBox="0 0 24 24" fill="none">
                                <path d="M3 12L21 3L15 12L21 21L3 12Z" fill="#FFB347"/>
                                <circle cx="12" cy="12" r="2" fill="#FF8C00"/>
                            </svg>
                        </div>
                        <h1>AVIATOR GAME</h1>
                        <div class="tagline">Multiplayer · Same multiplier for all</div>
                    </div>
                    
                    <div class="tab-buttons">
                        <button class="tab-btn active" onclick="switchTab('login')">LOGIN</button>
                        <button class="tab-btn" onclick="switchTab('register')">REGISTER</button>
                    </div>
                    
                    <div id="loginTab">
                        <div class="input-group">
                            <label class="input-label">USERNAME</label>
                            <input type="text" id="loginUsername" class="input-field" placeholder="Enter username">
                        </div>
                        <div class="input-group">
                            <label class="input-label">PASSWORD</label>
                            <input type="password" id="loginPassword" class="input-field" placeholder="Enter password">
                        </div>
                        <button class="btn btn-primary" onclick="handleLogin()">LOGIN & FLY ✈️</button>
                    </div>
                    
                    <div id="registerTab" class="hide">
                        <div class="input-group">
                            <label class="input-label">USERNAME</label>
                            <input type="text" id="regUsername" class="input-field" placeholder="Choose username">
                        </div>
                        <div class="input-group">
                            <label class="input-label">EMAIL</label>
                            <input type="email" id="regEmail" class="input-field" placeholder="Enter email">
                        </div>
                        <div class="input-group">
                            <label class="input-label">PASSWORD</label>
                            <input type="password" id="regPassword" class="input-field" placeholder="Choose password">
                        </div>
                        <div class="input-group">
                            <label class="input-label">CONFIRM PASSWORD</label>
                            <input type="password" id="regConfirmPassword" class="input-field" placeholder="Confirm password">
                        </div>
                        <button class="btn btn-primary" onclick="handleRegister()">REGISTER 🎮</button>
                    </div>
                    
                    <div id="messageArea"></div>
                </div>
            `;
        }
        
        function switchTab(tab) {
            const loginTab = document.getElementById('loginTab');
            const registerTab = document.getElementById('registerTab');
            const tabs = document.querySelectorAll('.tab-btn');
            
            tabs.forEach(btn => btn.classList.remove('active'));
            
            if (tab === 'login') {
                loginTab.classList.remove('hide');
                registerTab.classList.add('hide');
                tabs[0].classList.add('active');
            } else {
                loginTab.classList.add('hide');
                registerTab.classList.remove('hide');
                tabs[1].classList.add('active');
            }
        }
        
        async function handleLogin() {
            const username = document.getElementById('loginUsername').value.trim();
            const password = document.getElementById('loginPassword').value;
            const messageArea = document.getElementById('messageArea');
            
            if (!username || !password) {
                showMessage('Please enter username and password', 'error', messageArea);
                return;
            }
            
            try {
                const response = await fetch(`${API_BASE}/api/login`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({ username, password })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    showMessage(data.message, 'success', messageArea);
                    setTimeout(() => checkLoginState(), 1000);
                } else {
                    showMessage(data.message, 'error', messageArea);
                }
            } catch (error) {
                showMessage('Connection error', 'error', messageArea);
            }
        }
        
        async function handleRegister() {
            const username = document.getElementById('regUsername').value.trim();
            const email = document.getElementById('regEmail').value.trim();
            const password = document.getElementById('regPassword').value;
            const confirmPassword = document.getElementById('regConfirmPassword').value;
            const messageArea = document.getElementById('messageArea');
            
            if (!username || !email || !password) {
                showMessage('All fields are required', 'error', messageArea);
                return;
            }
            
            if (password !== confirmPassword) {
                showMessage('Passwords do not match', 'error', messageArea);
                return;
            }
            
            if (password.length < 4) {
                showMessage('Password must be at least 4 characters', 'error', messageArea);
                return;
            }
            
            try {
                const response = await fetch(`${API_BASE}/api/register`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, email, password })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    showMessage(data.message, 'success', messageArea);
                    setTimeout(() => switchTab('login'), 1500);
                } else {
                    showMessage(data.message, 'error', messageArea);
                }
            } catch (error) {
                showMessage('Registration failed', 'error', messageArea);
            }
        }
        
        function showMessage(msg, type, element) {
            element.innerHTML = `<div class="message ${type}">${msg}</div>`;
            setTimeout(() => {
                if (element.innerHTML.includes(msg)) {
                    element.innerHTML = '';
                }
            }, 3000);
        }
        
        function showGameLobby(user) {
            const app = document.getElementById('app');
            app.innerHTML = `
                <div class="container">
                    <div class="game-header">
                        <div class="game-icon">
                            <svg width="48" height="48" viewBox="0 0 24 24" fill="none">
                                <path d="M3 12L21 3L15 12L21 21L3 12Z" fill="#FFB347"/>
                                <circle cx="12" cy="12" r="2" fill="#FF8C00"/>
                            </svg>
                        </div>
                        <h1>FLIGHT LOBBY</h1>
                        <div class="tagline">Welcome, ${escapeHtml(user.username)}!</div>
                    </div>
                    
                    <div class="stats">
                        <div class="stat-card">
                            <div class="stat-label">BALANCE</div>
                            <div class="stat-value">$${user.balance || 1000}</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-label">GAMES PLAYED</div>
                            <div class="stat-value" id="gamesPlayed">${user.games_played || 0}</div>
                        </div>
                    </div>
                    
                    <div class="multiplier-display">
                        <div class="stat-label">CURRENT MULTIPLIER</div>
                        <div class="multiplier-value" id="multiplierValue">1.00x</div>
                        <div class="stat-label" id="gameStatus" style="margin-top: 0.5rem;">🚀 Game in progress</div>
                    </div>
                    
                    <div class="action-buttons">
                        <button class="btn btn-primary" id="cashoutBtn" style="flex:1;">💰 CASH OUT</button>
                    </div>
                    
                    <div class="stats" style="margin-top: 1rem;">
                        <div class="stat-card">
                            <div class="stat-label">LAST CASHOUT</div>
                            <div class="stat-value" id="lastCashout">-</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-label">MULTIPLIER AT CASHOUT</div>
                            <div class="stat-value" id="lastMultiplier">-</div>
                        </div>
                    </div>
                    
                    <button class="btn btn-secondary" onclick="logout()" style="margin-top: 1rem;">🚪 LOGOUT</button>
                    <div id="gameMessage"></div>
                </div>
            `;
            
            let lastMultiplier = 0;
            let cashedOut = false;
            let currentBet = 10;
            
            const cashoutBtn = document.getElementById('cashoutBtn');
            const multiplierSpan = document.getElementById('multiplierValue');
            const gameStatusSpan = document.getElementById('gameStatus');
            const gameMessage = document.getElementById('gameMessage');
            const lastCashoutSpan = document.getElementById('lastCashout');
            const lastMultiplierSpan = document.getElementById('lastMultiplier');
            
            // Poll for game state updates (uniform for all users)
            const gameInterval = setInterval(async () => {
                try {
                    const response = await fetch(`${API_BASE}/api/game_state`, {
                        credentials: 'include'
                    });
                    const game = await response.json();
                    
                    multiplierSpan.textContent = game.multiplier.toFixed(2) + 'x';
                    
                    if (!game.game_active) {
                        gameStatusSpan.innerHTML = '💥 GAME CRASHED! New round starting...';
                        gameStatusSpan.style.color = '#ff6b6b';
                        cashoutBtn.disabled = true;
                        cashedOut = false;
                        
                        if (lastMultiplier > 0 && !cashedOut) {
                            gameMessage.innerHTML = '<div class="message error">💥 You lost! The flight crashed before you cashed out!</div>';
                        }
                        lastMultiplier = 0;
                        
                        // Re-enable cashout when new game starts
                        setTimeout(() => {
                            cashoutBtn.disabled = false;
                            gameStatusSpan.innerHTML = '🚀 New flight taking off!';
                            gameStatusSpan.style.color = '#9aaec7';
                            gameMessage.innerHTML = '';
                        }, 3000);
                    } else {
                        gameStatusSpan.innerHTML = `📈 Multiplier climbing | Cash out before ${game.crash_point.toFixed(2)}x!`;
                        gameStatusSpan.style.color = '#9aaec7';
                        lastMultiplier = game.multiplier;
                    }
                } catch (error) {
                    console.error('Game state error', error);
                }
            }, 200);
            
            cashoutBtn.onclick = async () => {
                if (cashedOut) {
                    showGameMessage('Already cashed out this round!', 'error', gameMessage);
                    return;
                }
                
                try {
                    const response = await fetch(`${API_BASE}/api/cashout`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'include',
                        body: JSON.stringify({ multiplier: lastMultiplier })
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        cashedOut = true;
                        cashoutBtn.disabled = true;
                        const winnings = Math.floor(lastMultiplier * currentBet);
                        lastCashoutSpan.textContent = `$${winnings}`;
                        lastMultiplierSpan.textContent = `${lastMultiplier.toFixed(2)}x`;
                        showGameMessage(`✅ Cashed out at ${lastMultiplier.toFixed(2)}x! Won $${winnings}!`, 'success', gameMessage);
                        
                        // Update balance display
                        document.querySelector('.stat-value').textContent = `$${data.new_balance}`;
                    } else {
                        showGameMessage(data.message, 'error', gameMessage);
                    }
                } catch (error) {
                    showGameMessage('Cashout failed', 'error', gameMessage);
                }
            };
            
            // Cleanup on logout
            window.cleanupGame = () => clearInterval(gameInterval);
        }
        
        function showGameMessage(msg, type, element) {
            element.innerHTML = `<div class="message ${type}">${msg}</div>`;
            setTimeout(() => {
                if (element.innerHTML.includes(msg)) {
                    element.innerHTML = '';
                }
            }, 3000);
        }
        
        async function logout() {
            if (window.cleanupGame) window.cleanupGame();
            await fetch(`${API_BASE}/api/logout`, { method: 'POST', credentials: 'include' });
            checkLoginState();
        }
        
        function escapeHtml(str) {
            const div = document.createElement('div');
            div.textContent = str;
            return div.innerHTML;
        }
        
        // Initialize
        checkLoginState();
    </script>
</body>
</html>
'''

# ============================================
# FLASK ROUTES
# ============================================
@app.route('/')
def index():
    """Serve the main game page"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/register', methods=['POST'])
def register():
    """Register a new user"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        
        if not username or not email or not password:
            return jsonify({"success": False, "message": "All fields are required"}), 400
        
        if len(password) < 4:
            return jsonify({"success": False, "message": "Password must be at least 4 characters"}), 400
        
        # Check if user already exists
        existing_user = users_collection.find_one({'username': username})
        if existing_user:
            return jsonify({"success": False, "message": "Username already exists"}), 409
        
        # Create new user
        user = {
            'username': username,
            'email': email,
            'password': hash_password(password),
            'balance': 1000,
            'games_played': 0,
            'total_won': 0,
            'created_at': datetime.now()
        }
        
        users_collection.insert_one(user)
        
        return jsonify({
            "success": True,
            "message": "Registration successful! Please login."
        }), 201
        
    except Exception as e:
        return jsonify({"success": False, "message": f"Registration failed: {str(e)}"}), 500

@app.route('/api/login', methods=['POST'])
def login():
    """Login user"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        user = users_collection.find_one({'username': username})
        
        if not user or user['password'] != hash_password(password):
            return jsonify({"success": False, "message": "Invalid username or password"}), 401
        
        session['user_id'] = str(user['_id'])
        session['username'] = user['username']
        
        return jsonify({
            "success": True,
            "message": f"Welcome back, {username}!",
            "user": {
                "username": user['username'],
                "balance": user.get('balance', 1000),
                "games_played": user.get('games_played', 0)
            }
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "message": "Login failed"}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    """Logout user"""
    session.clear()
    return jsonify({"success": True, "message": "Logged out"}), 200

@app.route('/api/check_session', methods=['GET'])
def check_session():
    """Check if user is logged in"""
    if 'user_id' in session:
        user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
        if user:
            return jsonify({
                "logged_in": True,
                "user": {
                    "username": user['username'],
                    "balance": user.get('balance', 1000),
                    "games_played": user.get('games_played', 0)
                }
            }), 200
    return jsonify({"logged_in": False}), 200

@app.route('/api/game_state', methods=['GET'])
def get_game_state():
    """Get current game state (UNIFORM for all users)"""
    state = game_engine.get_game_state()
    return jsonify(state), 200

@app.route('/api/cashout', methods=['POST'])
@login_required
def cashout():
    """Handle cashout for logged-in user"""
    try:
        data = request.get_json()
        multiplier = data.get('multiplier', 1.0)
        
        # Get current game state to verify if cashout is valid
        game = game_engine.get_game_state()
        
        if not game['game_active']:
            return jsonify({"success": False, "message": "Game has crashed! You lost."}), 400
        
        # Calculate winnings (bet is fixed at $10 for demo)
        bet_amount = 10
        winnings = int(multiplier * bet_amount)
        
        # Update user balance
        user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
        new_balance = user.get('balance', 1000) + winnings
        
        users_collection.update_one(
            {'_id': ObjectId(session['user_id'])},
            {'$set': {'balance': new_balance},
             '$inc': {'games_played': 1, 'total_won': winnings}}
        )
        
        return jsonify({
            "success": True,
            "message": f"Cashed out at {multiplier:.2f}x! Won ${winnings}!",
            "new_balance": new_balance,
            "winnings": winnings
        }), 200
        
    except Exception as e:
        return jsonify({"success": False, "message": "Cashout failed"}), 500

if __name__ == '__main__':
    print("=" * 60)
    print("✈️  AVIATOR GAME - MULTIPLAYER EDITION")
    print("=" * 60)
    print("🎮 UNIFORM GAME LOGIC: All players see the SAME multiplier!")
    print("🌐 Server running at: http://localhost:5000")
    print("\n📝 Features:")
    print("   • User Registration & Login")
    print("   • MongoDB Integration")
    print("   • Uniform multiplier for all connected users")
    print("   • Real-time game updates")
    print("   • Balance tracking")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=True)