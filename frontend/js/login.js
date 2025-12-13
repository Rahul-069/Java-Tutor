// ==================== LOGIN PAGE JAVASCRIPT ====================
// This file handles user login

document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Login page loaded');
    
    const loginForm = document.getElementById('login-form');
    const usernameInput = document.getElementById('username');
    const passwordInput = document.getElementById('password');
    const loginButton = document.getElementById('login-btn');
    const errorMessage = document.getElementById('error-message');
    
    // Handle form submission
    loginForm.addEventListener('submit', async function(event) {
        event.preventDefault(); // Prevent default form submission
        
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
                
                // Redirect to main page
                window.location.href = '/';
                
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