document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Login page loaded');
    console.log('🍪 Current cookies:', document.cookie);
    
    // Check session immediately
    checkSessionDebug();
    
    const loginForm = document.getElementById('login-form');
    const usernameInput = document.getElementById('username');
    const passwordInput = document.getElementById('password');
    const loginButton = document.getElementById('login-btn');
    const errorMessage = document.getElementById('error-message');
    
    // Debug function to check session
    async function checkSessionDebug() {
        try {
            console.log('🔍 Checking session status...');
            const response = await fetch('/api/debug/session', {
                credentials: 'include'
            });
            const data = await response.json();
            console.log('📊 Session debug data:', data);
        } catch (error) {
            console.error('❌ Debug check failed:', error);
        }
    }
    
    // Handle form submission
    loginForm.addEventListener('submit', async function(event) {
        event.preventDefault();
        
        const username = usernameInput.value.trim();
        const password = passwordInput.value.trim();
        
        if (!username || !password) {
            showError('Please enter username and password');
            return;
        }
        
        loginButton.disabled = true;
        loginButton.textContent = 'Logging in...';
        hideError();
        
        try {
            console.log('📤 Sending login request for user:', username);
            console.log('🍪 Cookies before login:', document.cookie);
            
            const response = await fetch('/api/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                credentials: 'include',
                body: JSON.stringify({
                    username: username,
                    password: password
                })
            });
            
            console.log('📥 Response status:', response.status);
            console.log('📥 Response headers:', [...response.headers.entries()]);
            console.log('🍪 Cookies after login:', document.cookie);
            
            const data = await response.json();
            console.log('📥 Response data:', data);
            
            if (response.ok && data.success) {
                console.log('✅ Login API returned success');
                
                // Wait a bit for cookie to be set
                await new Promise(resolve => setTimeout(resolve, 200));
                
                console.log('🍪 Cookies after delay:', document.cookie);
                
                // Check session
                console.log('🔍 Verifying session...');
                const debugResponse = await fetch('/api/debug/session', {
                    credentials: 'include'
                });
                const debugData = await debugResponse.json();
                console.log('📊 Session after login:', debugData);
                
                // Check auth
                const authResponse = await fetch('/api/check-auth', {
                    credentials: 'include'
                });
                const authData = await authResponse.json();
                console.log('📊 Auth check:', authData);
                
                if (authData.authenticated) {
                    console.log('✅ Session verified! Redirecting...');
                    window.location.href = '/';
                } else {
                    console.error('❌ Session NOT verified after login!');
                    console.error('❌ This means cookies are not being saved');
                    showError('Session failed. Check browser console for details.');
                    loginButton.disabled = false;
                    loginButton.textContent = 'Login';
                }
                
            } else {
                console.error('❌ Login failed:', data.error);
                showError(data.error || 'Login failed');
                loginButton.disabled = false;
                loginButton.textContent = 'Login';
            }
            
        } catch (error) {
            console.error('❌ Network error:', error);
            showError('Network error: ' + error.message);
            loginButton.disabled = false;
            loginButton.textContent = 'Login';
        }
    });
    
    function showError(message) {
        errorMessage.textContent = message;
        errorMessage.style.display = 'block';
    }
    
    function hideError() {
        errorMessage.style.display = 'none';
    }
});