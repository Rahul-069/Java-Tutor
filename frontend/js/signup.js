// ==================== SIGNUP PAGE JAVASCRIPT ====================
// This file handles user registration

document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Signup page loaded');
    
    const signupForm = document.getElementById('signup-form');
    const usernameInput = document.getElementById('username');
    const passwordInput = document.getElementById('password');
    const confirmPasswordInput = document.getElementById('confirm-password');
    const signupButton = document.getElementById('signup-btn');
    const errorMessage = document.getElementById('error-message');
    const successMessage = document.getElementById('success-message');
    
    // Handle form submission
    signupForm.addEventListener('submit', async function(event) {
        event.preventDefault(); // Prevent default form submission
        
        const username = usernameInput.value.trim();
        const password = passwordInput.value.trim();
        const confirmPassword = confirmPasswordInput.value.trim();
        
        // Validate inputs
        if (!username || !password || !confirmPassword) {
            showError('Please fill in all fields');
            return;
        }
        
        if (username.length < 3) {
            showError('Username must be at least 3 characters');
            return;
        }
        
        if (password.length < 6) {
            showError('Password must be at least 6 characters');
            return;
        }
        
        if (password !== confirmPassword) {
            showError('Passwords do not match');
            return;
        }
        
        // Disable button while processing
        signupButton.disabled = true;
        signupButton.textContent = 'Creating account...';
        hideError();
        hideSuccess();
        
        try {
            console.log('📤 Sending signup request...');
            
            // Send signup request to backend
            const response = await fetch('/api/signup', {
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
            
            console.log('📥 Signup response status:', response.status);
            
            const data = await response.json();
            
            if (response.ok && data.success) {
                // Signup successful!
                console.log('✅ Signup successful:', data.username);
                
                showSuccess('Account created successfully! Redirecting to login...');
                
                // Redirect to login page after 2 seconds
                setTimeout(function() {
                    window.location.href = '/login';
                }, 2000);
                
            } else {
                // Signup failed
                console.error('❌ Signup failed:', data.error);
                showError(data.error || 'Signup failed');
                signupButton.disabled = false;
                signupButton.textContent = 'Create Account';
            }
            
        } catch (error) {
            console.error('❌ Network error:', error);
            showError('Network error. Please check your connection.');
            signupButton.disabled = false;
            signupButton.textContent = 'Create Account';
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
    
    // Helper function to show success message
    function showSuccess(message) {
        successMessage.textContent = message;
        successMessage.style.display = 'block';
    }
    
    // Helper function to hide success message
    function hideSuccess() {
        successMessage.style.display = 'none';
    }
});