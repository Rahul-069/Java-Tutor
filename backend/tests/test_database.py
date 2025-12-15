import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import Database

def test_database_initialization():
    """Test database initializes correctly"""
    db = Database(db_file='test.db')
    assert db is not None
    
    # Clean up
    if os.path.exists('test.db'):
        os.remove('test.db')

def test_user_creation():
    """Test user creation"""
    db = Database(db_file='test.db')
    
    # Create user
    success = db.create_user('testuser', 'testpass123')
    assert success == True
    
    # Check user exists
    exists = db.user_exists('testuser')
    assert exists == True
    
    # Clean up
    if os.path.exists('test.db'):
        os.remove('test.db')

def test_user_verification():
    """Test user login verification"""
    db = Database(db_file='test.db')
    
    # Create user
    db.create_user('testuser', 'testpass123')
    
    # Verify correct password
    valid = db.verify_user('testuser', 'testpass123')
    assert valid == True
    
    # Verify wrong password
    invalid = db.verify_user('testuser', 'wrongpass')
    assert invalid == False
    
    # Clean up
    if os.path.exists('test.db'):
        os.remove('test.db')