from flask import Blueprint, request, jsonify
from flask_login import current_user
from werkzeug.security import generate_password_hash
from datetime import datetime
from sqlalchemy import or_

from models import db, User, Doctor, Patient, Department, Appointment, DoctorAvailability
from routes.auth import admin_required

# Create Blueprint
admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/dashboard', methods=['GET'])
@admin_required
def dashboard():
    """Get admin dashboard statistics"""
    try:
        total_doctors = Doctor.query.join(User).filter(User.is_active == True).count()
        total_patients = Patient.query.join(User).filter(User.is_active == True).count()
        total_appointments = Appointment.query.count()
        
        # Upcoming appointments
        today = datetime.utcnow().date()
        upcoming_appointments = Appointment.query.filter(
            Appointment.appointment_date >= today,
            Appointment.status == 'Booked'
        ).count()
        
        # Completed appointments
        completed_appointments = Appointment.query.filter(
            Appointment.status == 'Completed'
        ).count()
        
        # Recent appointments (last 10)
        recent_appointments = Appointment.query.order_by(
            Appointment.created_at.desc()
        ).limit(10).all()
        
        return jsonify({
            'statistics': {
                'total_doctors': total_doctors,
                'total_patients': total_patients,
                'total_appointments': total_appointments,
                'upcoming_appointments': upcoming_appointments,
                'completed_appointments': completed_appointments
            },
            'recent_appointments': [{
                'id': apt.id,
                'patient_name': apt.patient.user.full_name,
                'doctor_name': apt.doctor.user.full_name,
                'department': apt.doctor.department.name,
                'date': apt.appointment_date.isoformat(),
                'time': apt.appointment_time.strftime('%H:%M'),
                'status': apt.status
            } for apt in recent_appointments]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# DOCTOR MANAGEMENT
# ============================================================================

@admin_bp.route('/doctors', methods=['GET'])
@admin_required
def get_doctors():
    """Get all doctors with filters"""
    try:
        department_id = request.args.get('department_id', type=int)
        search = request.args.get('search', '')
        status = request.args.get('status', 'active')  # 'active', 'inactive', 'all'
        
        query = Doctor.query.join(User)
        
        if department_id:
            query = query.filter(Doctor.department_id == department_id)
        
        if search:
            query = query.filter(User.full_name.ilike(f'%{search}%'))
        
        if status == 'active':
            query = query.filter(User.is_active == True)
        elif status == 'inactive':
            query = query.filter(User.is_active == False)
        
        doctors = query.all()
        
        return jsonify({
            'doctors': [{
                'id': doc.id,
                'user_id': doc.user_id,
                'name': doc.user.full_name,
                'email': doc.user.email,
                'phone': doc.user.phone,
                'department': doc.department.name,
                'department_id': doc.department_id,
                'qualification': doc.qualification,
                'experience_years': doc.experience_years,
                'consultation_fee': doc.consultation_fee,
                'is_active': doc.user.is_active,
                'upcoming_appointments': doc.upcoming_appointments_count,
                'completed_appointments': doc.completed_appointments_count
            } for doc in doctors]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/doctors/<int:doctor_id>', methods=['GET'])
@admin_required
def get_doctor_details(doctor_id):
    """Get detailed doctor information"""
    try:
        doctor = Doctor.query.get_or_404(doctor_id)
        
        return jsonify({
            'doctor': {
                'id': doctor.id,
                'user_id': doctor.user_id,
                'name': doctor.user.full_name,
                'email': doctor.user.email,
                'phone': doctor.user.phone,
                'address': doctor.user.address,
                'department': doctor.department.name,
                'department_id': doctor.department_id,
                'qualification': doctor.qualification,
                'experience_years': doctor.experience_years,
                'consultation_fee': doctor.consultation_fee,
                'bio': doctor.bio,
                'is_active': doctor.user.is_active,
                'registration_date': doctor.created_at.isoformat()
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/doctors/add', methods=['POST'])
@admin_required
def add_doctor():
    """Add a new doctor"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required = ['username', 'email', 'password', 'full_name', 'phone', 'department_id']
        if not all(data.get(field) for field in required):
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Check if username exists
        if User.query.filter_by(username=data['username']).first():
            return jsonify({'error': 'Username already exists'}), 400
        
        # Check if email exists
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'error': 'Email already exists'}), 400
        
        # Check if department exists
        department = Department.query.get(data['department_id'])
        if not department:
            return jsonify({'error': 'Department not found'}), 404
        
        # Create user account
        new_user = User(
            username=data['username'],
            email=data['email'],
            password=generate_password_hash(data['password']),
            role='doctor',
            full_name=data['full_name'],
            phone=data['phone'],
            address=data.get('address', ''),
            registration_timestamp=datetime.utcnow(),
            is_active=True
        )
        
        db.session.add(new_user)
        db.session.flush()
        
        # Create doctor profile
        new_doctor = Doctor(
            user_id=new_user.id,
            department_id=data['department_id'],
            qualification=data.get('qualification', ''),
            experience_years=data.get('experience_years', 0),
            consultation_fee=data.get('consultation_fee', 0.0),
            bio=data.get('bio', ''),
            created_at=datetime.utcnow()
        )
        
        db.session.add(new_doctor)
        db.session.commit()
        
        return jsonify({
            'message': 'Doctor added successfully',
            'doctor': {
                'id': new_doctor.id,
                'name': new_user.full_name,
                'department': department.name
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/doctors/<int:doctor_id>', methods=['PUT'])
@admin_required
def update_doctor(doctor_id):
    """Update doctor information"""
    try:
        doctor = Doctor.query.get_or_404(doctor_id)
        data = request.get_json()
        
        # Update user fields
        if data.get('full_name'):
            doctor.user.full_name = data['full_name']
        if data.get('email'):
            # Check if email is taken by another user
            existing = User.query.filter_by(email=data['email']).first()
            if existing and existing.id != doctor.user_id:
                return jsonify({'error': 'Email already in use'}), 400
            doctor.user.email = data['email']
        if data.get('phone'):
            doctor.user.phone = data['phone']
        if 'address' in data:
            doctor.user.address = data['address']
        
        # Update doctor fields
        if data.get('department_id'):
            department = Department.query.get(data['department_id'])
            if not department:
                return jsonify({'error': 'Department not found'}), 404
            doctor.department_id = data['department_id']
        
        if 'qualification' in data:
            doctor.qualification = data['qualification']
        if 'experience_years' in data:
            doctor.experience_years = data['experience_years']
        if 'consultation_fee' in data:
            doctor.consultation_fee = data['consultation_fee']
        if 'bio' in data:
            doctor.bio = data['bio']
        
        db.session.commit()
        
        return jsonify({'message': 'Doctor updated successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/doctors/<int:doctor_id>/toggle-status', methods=['POST'])
@admin_required
def toggle_doctor_status(doctor_id):
    """Activate/Deactivate doctor (blacklist)"""
    try:
        doctor = Doctor.query.get_or_404(doctor_id)
        
        doctor.user.is_active = not doctor.user.is_active
        db.session.commit()
        
        status = 'activated' if doctor.user.is_active else 'deactivated'
        return jsonify({'message': f'Doctor {status} successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/doctors/<int:doctor_id>', methods=['DELETE'])
@admin_required
def delete_doctor(doctor_id):
    """Delete doctor (use toggle-status for blacklisting instead)"""
    try:
        doctor = Doctor.query.get_or_404(doctor_id)
        user = doctor.user
        
        db.session.delete(doctor)
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({'message': 'Doctor deleted successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# PATIENT MANAGEMENT
# ============================================================================

@admin_bp.route('/patients', methods=['GET'])
@admin_required
def get_patients():
    """Get all patients with search"""
    try:
        search = request.args.get('search', '')
        status = request.args.get('status', 'active')
        
        query = Patient.query.join(User)
        
        if search:
            query = query.filter(
                or_(
                    User.full_name.ilike(f'%{search}%'),
                    User.email.ilike(f'%{search}%'),
                    User.phone.ilike(f'%{search}%')
                )
            )
        
        if status == 'active':
            query = query.filter(User.is_active == True)
        elif status == 'inactive':
            query = query.filter(User.is_active == False)
        
        patients = query.all()
        
        return jsonify({
            'patients': [{
                'id': pat.id,
                'user_id': pat.user_id,
                'name': pat.user.full_name,
                'email': pat.user.email,
                'phone': pat.user.phone,
                'age': pat.age,
                'blood_group': pat.blood_group,
                'is_active': pat.user.is_active,
                'registration_date': pat.created_at.isoformat()
            } for pat in patients]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/patients/<int:patient_id>', methods=['GET'])
@admin_required
def get_patient_details(patient_id):
    """Get detailed patient information"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        
        # Get appointment history
        appointments = Appointment.query.filter_by(patient_id=patient_id).order_by(
            Appointment.appointment_date.desc()
        ).limit(10).all()
        
        return jsonify({
            'patient': {
                'id': patient.id,
                'name': patient.user.full_name,
                'email': patient.user.email,
                'phone': patient.user.phone,
                'address': patient.user.address,
                'date_of_birth': patient.date_of_birth.isoformat() if patient.date_of_birth else None,
                'age': patient.age,
                'blood_group': patient.blood_group,
                'emergency_contact': patient.emergency_contact,
                'medical_history': patient.medical_history,
                'allergies': patient.allergies,
                'is_active': patient.user.is_active,
                'registration_date': patient.created_at.isoformat()
            },
            'recent_appointments': [{
                'id': apt.id,
                'doctor_name': apt.doctor.user.full_name,
                'department': apt.doctor.department.name,
                'date': apt.appointment_date.isoformat(),
                'status': apt.status
            } for apt in appointments]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/patients/<int:patient_id>/toggle-status', methods=['POST'])
@admin_required
def toggle_patient_status(patient_id):
    """Activate/Deactivate patient (blacklist)"""
    try:
        patient = Patient.query.get_or_404(patient_id)
        
        patient.user.is_active = not patient.user.is_active
        db.session.commit()
        
        status = 'activated' if patient.user.is_active else 'deactivated'
        return jsonify({'message': f'Patient {status} successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# APPOINTMENT MANAGEMENT
# ============================================================================

@admin_bp.route('/appointments', methods=['GET'])
@admin_required
def get_all_appointments():
    """Get all appointments with filters"""
    try:
        status = request.args.get('status')  # 'Booked', 'Completed', 'Cancelled'
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        doctor_id = request.args.get('doctor_id', type=int)
        patient_id = request.args.get('patient_id', type=int)
        
        query = Appointment.query
        
        if status:
            query = query.filter(Appointment.status == status)
        
        if date_from:
            query = query.filter(Appointment.appointment_date >= datetime.strptime(date_from, '%Y-%m-%d').date())
        
        if date_to:
            query = query.filter(Appointment.appointment_date <= datetime.strptime(date_to, '%Y-%m-%d').date())
        
        if doctor_id:
            query = query.filter(Appointment.doctor_id == doctor_id)
        
        if patient_id:
            query = query.filter(Appointment.patient_id == patient_id)
        
        appointments = query.order_by(
            Appointment.appointment_date.desc(),
            Appointment.appointment_time.desc()
        ).all()
        
        return jsonify({
            'appointments': [{
                'id': apt.id,
                'patient_name': apt.patient.user.full_name,
                'patient_id': apt.patient_id,
                'doctor_name': apt.doctor.user.full_name,
                'doctor_id': apt.doctor_id,
                'department': apt.doctor.department.name,
                'date': apt.appointment_date.isoformat(),
                'time': apt.appointment_time.strftime('%H:%M'),
                'status': apt.status,
                'reason': apt.reason_for_visit
            } for apt in appointments]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/departments', methods=['GET'])
@admin_required
def get_departments():
    """Get all departments"""
    try:
        departments = Department.query.all()
        
        return jsonify({
            'departments': [{
                'id': dept.id,
                'name': dept.name,
                'description': dept.description,
                'doctors_count': dept.doctors_count
            } for dept in departments]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# SEARCH FUNCTIONALITY
# ============================================================================

@admin_bp.route('/search', methods=['GET'])
@admin_required
def search():
    """Universal search for doctors, patients, and appointments"""
    try:
        query_text = request.args.get('q', '')
        search_type = request.args.get('type', 'all')  # 'all', 'doctors', 'patients', 'appointments'
        
        if not query_text:
            return jsonify({'error': 'Search query is required'}), 400
        
        results = {}
        
        if search_type in ['all', 'doctors']:
            doctors = Doctor.query.join(User).filter(
                User.full_name.ilike(f'%{query_text}%')
            ).limit(10).all()
            results['doctors'] = [{
                'id': doc.id,
                'name': doc.user.full_name,
                'department': doc.department.name,
                'is_active': doc.user.is_active
            } for doc in doctors]
        
        if search_type in ['all', 'patients']:
            patients = Patient.query.join(User).filter(
                or_(
                    User.full_name.ilike(f'%{query_text}%'),
                    User.email.ilike(f'%{query_text}%'),
                    User.phone.ilike(f'%{query_text}%')
                )
            ).limit(10).all()
            results['patients'] = [{
                'id': pat.id,
                'name': pat.user.full_name,
                'email': pat.user.email,
                'phone': pat.user.phone
            } for pat in patients]
        
        return jsonify(results), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500