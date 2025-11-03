from flask import Blueprint, request, jsonify
from flask_login import current_user
from datetime import datetime, timedelta, time
from sqlalchemy import and_, or_

from models import db, Department, Doctor, DoctorAvailability, Appointment, Treatment, Patient, User
from routes.auth import patient_required

# Create Blueprint
patient_bp = Blueprint('patient', __name__)


@patient_bp.route('/dashboard', methods=['GET'])
@patient_required
def dashboard():
    """Get patient dashboard data"""
    try:
        patient = current_user.patient_profile
        
        # Get upcoming appointments
        today = datetime.utcnow().date()
        upcoming = Appointment.query.filter(
            Appointment.patient_id == patient.id,
            Appointment.appointment_date >= today,
            Appointment.status == 'Booked'
        ).order_by(Appointment.appointment_date, Appointment.appointment_time).all()
        
        # Get recent appointment history
        history = Appointment.query.filter(
            Appointment.patient_id == patient.id,
            or_(
                Appointment.appointment_date < today,
                Appointment.status.in_(['Completed', 'Cancelled'])
            )
        ).order_by(Appointment.appointment_date.desc()).limit(5).all()
        
        # Get all departments
        departments = Department.query.all()
        
        return jsonify({
            'patient_info': {
                'name': current_user.full_name,
                'blood_group': patient.blood_group,
                'age': patient.age
            },
            'upcoming_appointments': [{
                'id': apt.id,
                'doctor_name': apt.doctor.user.full_name,
                'department': apt.doctor.department.name,
                'date': apt.appointment_date.isoformat(),
                'time': apt.appointment_time.strftime('%H:%M'),
                'status': apt.status
            } for apt in upcoming],
            'recent_history': [{
                'id': apt.id,
                'doctor_name': apt.doctor.user.full_name,
                'department': apt.doctor.department.name,
                'date': apt.appointment_date.isoformat(),
                'status': apt.status
            } for apt in history],
            'departments': [{
                'id': dept.id,
                'name': dept.name,
                'description': dept.description,
                'doctors_count': dept.doctors_count
            } for dept in departments]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@patient_bp.route('/doctors', methods=['GET'])
@patient_required
def search_doctors():
    """Search doctors by department/specialization"""
    try:
        department_id = request.args.get('department_id', type=int)
        search_name = request.args.get('name', '')
        
        query = Doctor.query.join(Doctor.user).filter(Doctor.user.has(is_active=True))
        
        if department_id:
            query = query.filter(Doctor.department_id == department_id)
        
        if search_name:
            query = query.filter(Doctor.user.has(User.full_name.ilike(f'%{search_name}%')))
        
        doctors = query.all()
        
        return jsonify({
            'doctors': [{
                'id': doc.id,
                'name': doc.user.full_name,
                'department': doc.department.name,
                'qualification': doc.qualification,
                'experience_years': doc.experience_years,
                'consultation_fee': doc.consultation_fee,
                'bio': doc.bio
            } for doc in doctors]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@patient_bp.route('/doctors/<int:doctor_id>/availability', methods=['GET'])
@patient_required
def get_doctor_availability(doctor_id):
    """Get doctor's availability for next 7 days with slot occupancy details"""
    try:
        doctor = Doctor.query.get_or_404(doctor_id)
        
        today = datetime.utcnow().date()
        next_7_days = today + timedelta(days=7)
        
        availability = DoctorAvailability.query.filter(
            DoctorAvailability.doctor_id == doctor_id,
            DoctorAvailability.date >= today,
            DoctorAvailability.date <= next_7_days,
            DoctorAvailability.is_available == True
        ).order_by(DoctorAvailability.date, DoctorAvailability.start_time).all()
        
        # For each availability slot, get occupied time slots
        availability_with_occupied = []
        for slot in availability:
            # Get all booked appointments for this slot
            booked_times = db.session.query(Appointment.appointment_time).filter(
                Appointment.doctor_id == doctor_id,
                Appointment.appointment_date == slot.date,
                Appointment.appointment_time >= slot.start_time,
                Appointment.appointment_time < slot.end_time,
                Appointment.status == 'Booked'
            ).all()
            
            occupied_times = [t[0].strftime('%H:%M') for t in booked_times]
            
            availability_with_occupied.append({
                'id': slot.id,
                'date': slot.date.isoformat(),
                'start_time': slot.start_time.strftime('%H:%M'),
                'end_time': slot.end_time.strftime('%H:%M'),
                'slots_available': slot.slots_available,
                'booked_count': slot.booked_appointments_count,
                'occupied_times': occupied_times
            })
        
        return jsonify({
            'doctor': {
                'id': doctor.id,
                'name': doctor.user.full_name,
                'department': doctor.department.name
            },
            'availability': availability_with_occupied
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@patient_bp.route('/appointments/book', methods=['POST'])
@patient_required
def book_appointment():
    """Book a new appointment"""
    try:
        data = request.get_json()
        patient = current_user.patient_profile
        
        # Validate required fields
        if not all([data.get('doctor_id'), data.get('appointment_date'), data.get('appointment_time')]):
            return jsonify({'error': 'Doctor, date, and time are required'}), 400
        
        doctor_id = data['doctor_id']
        apt_date = datetime.strptime(data['appointment_date'], '%Y-%m-%d').date()
        apt_time_str = data['appointment_time']
        
        # Parse time - handle both "HH:MM" and "HH:MM:SS" formats
        try:
            apt_time = datetime.strptime(apt_time_str, '%H:%M').time()
        except ValueError:
            apt_time = datetime.strptime(apt_time_str, '%H:%M:%S').time()
        
        # Check if date is in the future
        now = datetime.utcnow()
        apt_datetime = datetime.combine(apt_date, apt_time)
        if apt_datetime < now:
            return jsonify({'error': 'Cannot book appointments in the past'}), 400
        
        # Check if doctor exists and is active
        doctor = Doctor.query.get(doctor_id)
        if not doctor or not doctor.user.is_active:
            return jsonify({'error': 'Doctor not found or inactive'}), 404
        
        # Check if doctor is available on this date/time
        availability = DoctorAvailability.query.filter(
            DoctorAvailability.doctor_id == doctor_id,
            DoctorAvailability.date == apt_date,
            DoctorAvailability.is_available == True,
            DoctorAvailability.start_time <= apt_time,
            DoctorAvailability.end_time > apt_time
        ).first()
        
        if not availability:
            return jsonify({'error': 'Doctor is not available at this time'}), 400
        
        # Check slot availability (count appointments in this half-hour slot)
        existing_appointments = Appointment.query.filter(
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date == apt_date,
            Appointment.appointment_time == apt_time,
            Appointment.status == 'Booked'
        ).count()
        
        if existing_appointments >= 1:  # Only 1 appointment per half-hour slot
            return jsonify({'error': 'This time slot is already booked'}), 400
        
        # Check for duplicate appointment for this patient
        existing = Appointment.query.filter(
            Appointment.patient_id == patient.id,
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date == apt_date,
            Appointment.appointment_time == apt_time,
            Appointment.status == 'Booked'
        ).first()
        
        if existing:
            return jsonify({'error': 'You already have an appointment at this time'}), 400
        
        # Create appointment
        appointment = Appointment(
            patient_id=patient.id,
            doctor_id=doctor_id,
            appointment_date=apt_date,
            appointment_time=apt_time,
            status='Booked',
            reason_for_visit=data.get('reason_for_visit', ''),
            created_at=datetime.utcnow()
        )
        
        db.session.add(appointment)
        db.session.commit()
        
        return jsonify({
            'message': 'Appointment booked successfully',
            'appointment': {
                'id': appointment.id,
                'doctor_name': doctor.user.full_name,
                'department': doctor.department.name,
                'date': appointment.appointment_date.isoformat(),
                'time': appointment.appointment_time.strftime('%H:%M'),
                'status': appointment.status
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@patient_bp.route('/appointments', methods=['GET'])
@patient_required
def get_appointments():
    """Get all appointments for current patient"""
    try:
        patient = current_user.patient_profile
        status_filter = request.args.get('status')  # 'upcoming', 'past', 'all'
        
        query = Appointment.query.filter(Appointment.patient_id == patient.id)
        
        today = datetime.utcnow().date()
        
        if status_filter == 'upcoming':
            query = query.filter(
                Appointment.appointment_date >= today,
                Appointment.status == 'Booked'
            )
        elif status_filter == 'past':
            query = query.filter(
                or_(
                    Appointment.appointment_date < today,
                    Appointment.status.in_(['Completed', 'Cancelled'])
                )
            )
        
        appointments = query.order_by(
            Appointment.appointment_date.desc(),
            Appointment.appointment_time.desc()
        ).all()
        
        return jsonify({
            'appointments': [{
                'id': apt.id,
                'doctor_name': apt.doctor.user.full_name,
                'department': apt.doctor.department.name,
                'date': apt.appointment_date.isoformat(),
                'time': apt.appointment_time.strftime('%H:%M'),
                'status': apt.status,
                'reason': apt.reason_for_visit,
                'can_cancel': apt.can_be_cancelled
            } for apt in appointments]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@patient_bp.route('/appointments/<int:appointment_id>', methods=['GET'])
@patient_required
def get_appointment_details(appointment_id):
    """Get detailed appointment information"""
    try:
        patient = current_user.patient_profile
        appointment = Appointment.query.filter_by(
            id=appointment_id,
            patient_id=patient.id
        ).first_or_404()
        
        response = {
            'appointment': {
                'id': appointment.id,
                'doctor': {
                    'name': appointment.doctor.user.full_name,
                    'department': appointment.doctor.department.name,
                    'qualification': appointment.doctor.qualification
                },
                'date': appointment.appointment_date.isoformat(),
                'time': appointment.appointment_time.strftime('%H:%M'),
                'status': appointment.status,
                'reason': appointment.reason_for_visit,
                'created_at': appointment.created_at.isoformat(),
                'can_cancel': appointment.can_be_cancelled
            }
        }
        
        # Add treatment details if completed
        if appointment.treatment:
            treatment = appointment.treatment
            response['treatment'] = {
                'diagnosis': treatment.diagnosis,
                'prescription': treatment.prescription,
                'notes': treatment.notes,
                'follow_up_required': treatment.follow_up_required,
                'follow_up_date': treatment.follow_up_date.isoformat() if treatment.follow_up_date else None
            }
        
        return jsonify(response), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@patient_bp.route('/appointments/<int:appointment_id>/cancel', methods=['POST'])
@patient_required
def cancel_appointment(appointment_id):
    """Cancel an appointment"""
    try:
        patient = current_user.patient_profile
        appointment = Appointment.query.filter_by(
            id=appointment_id,
            patient_id=patient.id
        ).first_or_404()
        
        if not appointment.can_be_cancelled:
            return jsonify({'error': 'This appointment cannot be cancelled'}), 400
        
        appointment.status = 'Cancelled'
        appointment.cancelled_at = datetime.utcnow()
        appointment.cancelled_by = 'patient'
        appointment.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({'message': 'Appointment cancelled successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@patient_bp.route('/treatment-history', methods=['GET'])
@patient_required
def get_treatment_history():
    """Get complete treatment history"""
    try:
        patient = current_user.patient_profile
        
        treatments = Treatment.query.join(Appointment).filter(
            Appointment.patient_id == patient.id,
            Appointment.status == 'Completed'
        ).order_by(Appointment.appointment_date.desc()).all()
        
        return jsonify({
            'treatments': [{
                'id': t.id,
                'appointment_id': t.appointment_id,
                'doctor_name': t.appointment.doctor.user.full_name,
                'department': t.appointment.doctor.department.name,
                'date': t.appointment.appointment_date.isoformat(),
                'diagnosis': t.diagnosis,
                'prescription': t.prescription,
                'notes': t.notes,
                'follow_up_required': t.follow_up_required,
                'follow_up_date': t.follow_up_date.isoformat() if t.follow_up_date else None
            } for t in treatments]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@patient_bp.route('/departments', methods=['GET'])
@patient_required
def get_departments():
    """Get all departments with doctor counts"""
    try:
        departments = Department.query.all()
        
        return jsonify({
            'departments': [{
                'id': dept.id,
                'name': dept.name,
                'description': dept.description,
                'doctors_count': dept.doctors_count,
                'available_doctors': dept.available_doctors_count
            } for dept in departments]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500