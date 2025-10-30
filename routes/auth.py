from flask import Blueprint, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

from models import db, User, Patient
from functools import wraps

# Create Blueprint
auth_bp = Blueprint('auth', __name__)


# ============================================================================
# DECORATORS FOR ROLE-BASED ACCESS CONTROL
# ============================================================================

def admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function


def doctor_required(f):
    """Decorator to require doctor role"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_doctor:
            return jsonify({'error': 'Doctor access required'}), 403
        return f(*args, **kwargs)
    return decorated_function


def patient_required(f):
    """Decorator to require patient role"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_patient:
            return jsonify({'error': 'Patient access required'}), 403
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# AUTHENTICATION ROUTES
# ============================================================================

@auth_bp.route('/register', methods=['POST'])
def register():
    """
    Register a new patient
    Only patients can self-register. Doctors are added by admin.
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['username', 'email', 'password', 'full_name', 'phone']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400
        
        # Check if username already exists
        if User.query.filter_by(username=data['username']).first():
            return jsonify({'error': 'Username already exists'}), 400
        
        # Check if email already exists
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'error': 'Email already exists'}), 400
        
        # Create new user with patient role
        new_user = User(
            username=data['username'],
            email=data['email'],
            password=generate_password_hash(data['password']),
            role='patient',
            full_name=data['full_name'],
            phone=data['phone'],
            address=data.get('address', ''),
            registration_timestamp=datetime.utcnow(),
            is_active=True
        )
        
        db.session.add(new_user)
        db.session.flush()  # Get the user ID without committing
        
        # Create patient profile
        new_patient = Patient(
            user_id=new_user.id,
            date_of_birth=datetime.strptime(data['date_of_birth'], '%Y-%m-%d').date() if data.get('date_of_birth') else None,
            blood_group=data.get('blood_group', ''),
            emergency_contact=data.get('emergency_contact', ''),
            medical_history=data.get('medical_history', ''),
            allergies=data.get('allergies', ''),
            created_at=datetime.utcnow()
        )
        
        db.session.add(new_patient)
        db.session.commit()
        
        return jsonify({
            'message': 'Registration successful',
            'user': {
                'id': new_user.id,
                'username': new_user.username,
                'email': new_user.email,
                'full_name': new_user.full_name,
                'role': new_user.role
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Login for all users (admin, doctor, patient)
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('username') or not data.get('password'):
            return jsonify({'error': 'Username and password are required'}), 400
        
        # Find user by username
        user = User.query.filter_by(username=data['username']).first()
        
        # Check if user exists and password is correct
        if not user or not check_password_hash(user.password, data['password']):
            return jsonify({'error': 'Invalid username or password'}), 401
        
        # Check if user is active (not blacklisted)
        if not user.is_active:
            return jsonify({'error': 'Your account has been deactivated. Please contact admin.'}), 403
        
        # Login user
        login_user(user, remember=data.get('remember', False))
        
        # Get role-specific profile data
        profile_data = {}
        if user.is_doctor and hasattr(user, 'doctor_profile'):
            profile_data = {
                'department': user.doctor_profile.department.name,
                'qualification': user.doctor_profile.qualification,
                'experience_years': user.doctor_profile.experience_years
            }
        elif user.is_patient and hasattr(user, 'patient_profile'):
            profile_data = {
                'blood_group': user.patient_profile.blood_group,
                'age': user.patient_profile.age
            }
        
        return jsonify({
            'message': 'Login successful',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'full_name': user.full_name,
                'role': user.role,
                'phone': user.phone,
                'profile': profile_data
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """
    Logout current user
    """
    try:
        logout_user()
        return jsonify({'message': 'Logout successful'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/me', methods=['GET'])
@login_required
def get_current_user():
    """
    Get current logged-in user's information
    """
    try:
        # Get role-specific profile data
        profile_data = {}
        if current_user.is_doctor and hasattr(current_user, 'doctor_profile'):
            profile_data = {
                'department_id': current_user.doctor_profile.department_id,
                'department': current_user.doctor_profile.department.name,
                'qualification': current_user.doctor_profile.qualification,
                'experience_years': current_user.doctor_profile.experience_years,
                'consultation_fee': current_user.doctor_profile.consultation_fee,
                'bio': current_user.doctor_profile.bio
            }
        elif current_user.is_patient and hasattr(current_user, 'patient_profile'):
            profile_data = {
                'date_of_birth': current_user.patient_profile.date_of_birth.isoformat() if current_user.patient_profile.date_of_birth else None,
                'age': current_user.patient_profile.age,
                'blood_group': current_user.patient_profile.blood_group,
                'emergency_contact': current_user.patient_profile.emergency_contact,
                'medical_history': current_user.patient_profile.medical_history,
                'allergies': current_user.patient_profile.allergies
            }
        
        return jsonify({
            'user': {
                'id': current_user.id,
                'username': current_user.username,
                'email': current_user.email,
                'full_name': current_user.full_name,
                'role': current_user.role,
                'phone': current_user.phone,
                'address': current_user.address,
                'is_active': current_user.is_active,
                'registration_timestamp': current_user.registration_timestamp.isoformat(),
                'profile': profile_data
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    """
    Change password for current user
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('old_password') or not data.get('new_password'):
            return jsonify({'error': 'Old password and new password are required'}), 400
        
        # Verify old password
        if not check_password_hash(current_user.password, data['old_password']):
            return jsonify({'error': 'Incorrect old password'}), 401
        
        # Validate new password
        if len(data['new_password']) < 6:
            return jsonify({'error': 'New password must be at least 6 characters long'}), 400
        
        # Update password
        current_user.password = generate_password_hash(data['new_password'])
        db.session.commit()
        
        return jsonify({'message': 'Password changed successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/update-profile', methods=['PUT'])
@login_required
def update_profile():
    """
    Update current user's profile information
    """
    try:
        data = request.get_json()
        
        # Update basic user fields
        if data.get('full_name'):
            current_user.full_name = data['full_name']
        if data.get('phone'):
            current_user.phone = data['phone']
        if data.get('address'):
            current_user.address = data['address']
        if data.get('email'):
            # Check if email is already taken by another user
            existing_user = User.query.filter_by(email=data['email']).first()
            if existing_user and existing_user.id != current_user.id:
                return jsonify({'error': 'Email already in use'}), 400
            current_user.email = data['email']
        
        # Update role-specific profile
        if current_user.is_patient and hasattr(current_user, 'patient_profile'):
            patient = current_user.patient_profile
            
            if data.get('date_of_birth'):
                patient.date_of_birth = datetime.strptime(data['date_of_birth'], '%Y-%m-%d').date()
            if data.get('blood_group'):
                patient.blood_group = data['blood_group']
            if data.get('emergency_contact'):
                patient.emergency_contact = data['emergency_contact']
            if 'medical_history' in data:
                patient.medical_history = data['medical_history']
            if 'allergies' in data:
                patient.allergies = data['allergies']
        
        db.session.commit()
        
        return jsonify({'message': 'Profile updated successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500