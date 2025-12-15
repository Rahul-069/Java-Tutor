import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, db

@pytest.fixture
def client():
    """Create test client"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_health_endpoint(client):
    """Test health check endpoint"""
    response = client.get('/health')
    assert response.status_code == 200
    data = response.get_json()
    assert 'status' in data
    assert data['status'] == 'healthy'

def test_login_page(client):
    """Test login page loads"""
    response = client.get('/login')
    assert response.status_code == 200

def test_signup_page(client):
    """Test signup page loads"""
    response = client.get('/signup')
    assert response.status_code == 200

def test_login_without_credentials(client):
    """Test login fails without credentials"""
    response = client.post('/api/login', json={})
    assert response.status_code == 400

def test_signup_validation(client):
    """Test signup validation"""
    response = client.post('/api/signup', json={
        'username': 'ab',  # Too short
        'password': '123'   # Too short
    })
    assert response.status_code == 400

def test_check_auth_unauthenticated(client):
    """Test auth check when not logged in"""
    response = client.get('/api/check-auth')
    assert response.status_code == 200
    data = response.get_json()
    assert data['authenticated'] == False