// ==================== LOGIN PAGE JAVASCRIPT ====================
// This file handles user login

document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Login page loaded');
    
    // Check if already logged in
    checkIfAlreadyLoggedIn();
    
    const loginForm = document.getElementById('login-form');
    const usernameInput = document.getElementById('username');
    const passwordInput = document.getElementById('password');
    const loginButton = document.getElementById('login-btn');
    const errorMessage = document.getElementById('error-message');
    
    // Check if user is already logged in
    async function checkIfAlreadyLoggedIn() {
        try {
            const response = await fetch('/api/check-auth', {
                credentials: 'include'
            });
            const data = await response.json();
            
            if (data.authenticated) {
                console.log('✅ Already logged in, redirecting...');
                window.location.href = '/';
            }
        } catch (error) {
            console.log('Not logged in');
        }
    }
    
    // Handle form submission
    loginForm.addEventListener('submit', async function(event) {
        event.preventDefault();
        
        const username = usernameInput.value.trim();
        const password = passwordInput.value.trim();
        
        // Validate inputs
        if (!username || !password) {
            showError('Please enter username and password');
            return;
        }
        
        // Disable button while processing
        loginButton.disabled = true;
        loginButton.textContent = 'Logging in...';
        hideError();
        
        try {
            console.log('📤 Sending login request...');
            
            // Send login request to backend
            const response = await fetch('/api/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                credentials: 'include', // IMPORTANT: Send cookies
                body: JSON.stringify({
                    username: username,
                    password: password
                })
            });
            
            console.log('📥 Login response status:', response.status);
            
            const data = await response.json();
            
            if (response.ok && data.success) {
                // Login successful!
                console.log('✅ Login successful:', data.username);
                
                // Small delay to ensure session cookie is set
                await new Promise(resolve => setTimeout(resolve, 100));
                
                // Verify session before redirecting
                const authCheck = await fetch('/api/check-auth', {
                    credentials: 'include'
                });
                const authData = await authCheck.json();
                
                if (authData.authenticated) {
                    console.log('✅ Session verified, redirecting to dashboard...');
                    window.location.href = '/';
                } else {
                    console.error('⚠️ Session not set properly');
                    showError('Login succeeded but session failed. Please try again.');
                    loginButton.disabled = false;
                    loginButton.textContent = 'Login';
                }
                
            } else {
                // Login failed
                console.error('❌ Login failed:', data.error);
                showError(data.error || 'Login failed');
                loginButton.disabled = false;
                loginButton.textContent = 'Login';
            }
            
        } catch (error) {
            console.error('❌ Network error:', error);
            showError('Network error. Please check your connection.');
            loginButton.disabled = false;
            loginButton.textContent = 'Login';
        }
    });
    
    // Helper function to show error message
    function showError(message) {
        errorMessage.textContent = message;
        errorMessage.style.display = 'block';
    }
    
    // Helper function to hide error message
    function hideError() {
        errorMessage.style.display = 'none';
    }
});