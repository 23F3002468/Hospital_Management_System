"""
Test script for authentication endpoints
Run this after starting the Flask app to test login/register functionality
"""

import requests
import json

BASE_URL = "http://localhost:5000/api"

def print_response(response):
    """Helper function to print response nicely"""
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}\n")


def test_admin_login():
    """Test 1: Login as admin"""
    print("=" * 50)
    print("TEST 1: Admin Login")
    print("=" * 50)
    
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={
            "username": "admin",
            "password": "admin123"
        }
    )
    print_response(response)
    return response


def test_patient_registration():
    """Test 2: Register a new patient"""
    print("=" * 50)
    print("TEST 2: Patient Registration")
    print("=" * 50)
    
    response = requests.post(
        f"{BASE_URL}/auth/register",
        json={
            "username": "john_patient",
            "email": "john@example.com",
            "password": "password123",
            "full_name": "John Doe",
            "phone": "9876543210",
            "address": "123 Main Street, City",
            "date_of_birth": "1990-05-15",
            "blood_group": "O+",
            "emergency_contact": "9876543211",
            "medical_history": "No major illnesses",
            "allergies": "None"
        }
    )
    print_response(response)
    return response


def test_patient_login():
    """Test 3: Login as patient"""
    print("=" * 50)
    print("TEST 3: Patient Login")
    print("=" * 50)
    
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={
            "username": "john_patient",
            "password": "password123"
        }
    )
    print_response(response)
    return response


def test_get_current_user(session):
    """Test 4: Get current user info (requires login)"""
    print("=" * 50)
    print("TEST 4: Get Current User Info")
    print("=" * 50)
    
    response = session.get(f"{BASE_URL}/auth/me")
    print_response(response)
    return response


def test_change_password(session):
    """Test 5: Change password"""
    print("=" * 50)
    print("TEST 5: Change Password")
    print("=" * 50)
    
    response = session.post(
        f"{BASE_URL}/auth/change-password",
        json={
            "old_password": "password123",
            "new_password": "newpassword123"
        }
    )
    print_response(response)
    return response


def test_update_profile(session):
    """Test 6: Update profile"""
    print("=" * 50)
    print("TEST 6: Update Profile")
    print("=" * 50)
    
    response = session.put(
        f"{BASE_URL}/auth/update-profile",
        json={
            "full_name": "John Smith Doe",
            "phone": "9999999999",
            "address": "456 New Street, New City"
        }
    )
    print_response(response)
    return response


def test_logout(session):
    """Test 7: Logout"""
    print("=" * 50)
    print("TEST 7: Logout")
    print("=" * 50)
    
    response = session.post(f"{BASE_URL}/auth/logout")
    print_response(response)
    return response


def test_invalid_login():
    """Test 8: Invalid login (wrong password)"""
    print("=" * 50)
    print("TEST 8: Invalid Login (Wrong Password)")
    print("=" * 50)
    
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={
            "username": "admin",
            "password": "wrongpassword"
        }
    )
    print_response(response)
    return response


def test_duplicate_registration():
    """Test 9: Duplicate registration (should fail)"""
    print("=" * 50)
    print("TEST 9: Duplicate Registration (Should Fail)")
    print("=" * 50)
    
    response = requests.post(
        f"{BASE_URL}/auth/register",
        json={
            "username": "john_patient",  # Already exists
            "email": "another@example.com",
            "password": "password123",
            "full_name": "Another User",
            "phone": "1234567890"
        }
    )
    print_response(response)
    return response


def run_all_tests():
    """Run all authentication tests"""
    print("\n" + "=" * 50)
    print("STARTING AUTHENTICATION TESTS")
    print("=" * 50 + "\n")
    
    # Test 1: Admin login
    test_admin_login()
    
    # Test 2: Register new patient
    test_patient_registration()
    
    # Create a session to maintain cookies
    session = requests.Session()
    
    # Test 3: Patient login (with session)
    response = session.post(
        f"{BASE_URL}/auth/login",
        json={
            "username": "john_patient",
            "password": "password123"
        }
    )
    print("=" * 50)
    print("TEST 3: Patient Login (With Session)")
    print("=" * 50)
    print_response(response)
    
    # Test 4: Get current user (requires login)
    test_get_current_user(session)
    
    # Test 5: Update profile
    test_update_profile(session)
    
    # Test 6: Change password
    test_change_password(session)
    
    # Test 7: Logout
    test_logout(session)
    
    # Test 8: Invalid login
    test_invalid_login()
    
    # Test 9: Duplicate registration
    test_duplicate_registration()
    
    print("\n" + "=" * 50)
    print("ALL TESTS COMPLETED")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    print("\n🧪 Authentication Endpoint Testing Script")
    print("Make sure Flask app is running on http://localhost:5000\n")
    
    try:
        # Check if server is running
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            print("✅ Server is running!\n")
            run_all_tests()
        else:
            print("❌ Server is not responding correctly")
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Cannot connect to server")
        print("Please make sure the Flask app is running:")
        print("  python app.py")