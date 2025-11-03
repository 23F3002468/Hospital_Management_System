from flask import Blueprint, request, jsonify
from flask_login import current_user
from datetime import datetime, timedelta, time
from sqlalchemy import and_

from models import db, Appointment, Treatment, DoctorAvailability, Patient, User
from routes.auth import doctor_required

# Create Blueprint
doctor_bp = Blueprint('doctor', __name__)


@doctor_bp.route('/dashboard', methods=['GET'])
@doctor_required
def dashboard():
    """Get doctor dashboard with today's appointments and statistics"""
    try:
        doctor = current_user.doctor_profile
        today = datetime.utcnow().date()
        
        # Today's appointments
        today_appointments = Appointment.query.filter(
            Appointment.doctor_id == doctor.id,
            Appointment.appointment_date == today,
            Appointment.status == 'Booked'
        ).order_by(Appointment.appointment_time).all()
        
        # This week's appointments
        week_end = today + timedelta(days=7)
        week_appointments = Appointment.query.filter(
            Appointment.doctor_id == doctor.id,
            Appointment.appointment_date >= today,
            Appointment.appointment_date <= week_end,
            Appointment.status == 'Booked'
        ).count()
        
        # Total patients treated
        total_patients = db.session.query(Appointment.patient_id).filter(
            Appointment.doctor_id == doctor.id,
            Appointment.status == 'Completed'
        ).distinct().count()
        
        # Completed appointments count
        completed_count = Appointment.query.filter(
            Appointment.doctor_id == doctor.id,
            Appointment.status == 'Completed'
        ).count()
        
        return jsonify({
            'doctor_info': {
                'name': current_user.full_name,
                'department': doctor.department.name,
                'qualification': doctor.qualification,
                'experience_years': doctor.experience_years
            },
            'statistics': {
                'today_appointments': len(today_appointments),
                'week_appointments': week_appointments,
                'total_patients_treated': total_patients,
                'completed_appointments': completed_count
            },
            'today_schedule': [{
                'id': apt.id,
                'patient_name': apt.patient.user.full_name,
                'patient_age': apt.patient.age,
                'patient_blood_group': apt.patient.blood_group,
                'time': apt.appointment_time.strftime('%H:%M'),
                'reason': apt.reason_for_visit,
                'status': apt.status
            } for apt in today_appointments]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@doctor_bp.route('/appointments', methods=['GET'])
@doctor_required
def get_appointments():
    """Get all appointments for the doctor with filters"""
    try:
        doctor = current_user.doctor_profile
        status = request.args.get('status')  # 'Booked', 'Completed', 'Cancelled'
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        query = Appointment.query.filter(Appointment.doctor_id == doctor.id)
        
        if status:
            query = query.filter(Appointment.status == status)
        
        if date_from:
            query = query.filter(
                Appointment.appointment_date >= datetime.strptime(date_from, '%Y-%m-%d').date()
            )
        
        if date_to:
            query = query.filter(
                Appointment.appointment_date <= datetime.strptime(date_to, '%Y-%m-%d').date()
            )
        
        appointments = query.order_by(
            Appointment.appointment_date.desc(),
            Appointment.appointment_time.desc()
        ).all()
        
        return jsonify({
            'appointments': [{
                'id': apt.id,
                'patient_name': apt.patient.user.full_name,
                'patient_id': apt.patient_id,
                'date': apt.appointment_date.isoformat(),
                'time': apt.appointment_time.strftime('%H:%M'),
                'status': apt.status,
                'reason': apt.reason_for_visit,
                'has_treatment': apt.treatment is not None
            } for apt in appointments]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@doctor_bp.route('/appointments/<int:appointment_id>', methods=['GET'])
@doctor_required
def get_appointment_details(appointment_id):
    """Get detailed appointment information including patient history"""
    try:
        doctor = current_user.doctor_profile
        appointment = Appointment.query.filter_by(
            id=appointment_id,
            doctor_id=doctor.id
        ).first_or_404()
        
        patient = appointment.patient
        
        # Get patient's previous appointments with this doctor
        previous_visits = Appointment.query.filter(
            Appointment.patient_id == patient.id,
            Appointment.doctor_id == doctor.id,
            Appointment.status == 'Completed',
            Appointment.id != appointment_id
        ).order_by(Appointment.appointment_date.desc()).limit(5).all()
        
        response = {
            'appointment': {
                'id': appointment.id,
                'date': appointment.appointment_date.isoformat(),
                'time': appointment.appointment_time.strftime('%H:%M'),
                'status': appointment.status,
                'reason': appointment.reason_for_visit
            },
            'patient': {
                'id': patient.id,
                'name': patient.user.full_name,
                'age': patient.age,
                'blood_group': patient.blood_group,
                'phone': patient.user.phone,
                'email': patient.user.email,
                'emergency_contact': patient.emergency_contact,
                'medical_history': patient.medical_history,
                'allergies': patient.allergies
            },
            'previous_visits': [{
                'date': visit.appointment_date.isoformat(),
                'diagnosis': visit.treatment.diagnosis if visit.treatment else None,
                'prescription': visit.treatment.prescription if visit.treatment else None
            } for visit in previous_visits]
        }
        
        # Add treatment if exists
        if appointment.treatment:
            response['treatment'] = {
                'diagnosis': appointment.treatment.diagnosis,
                'prescription': appointment.treatment.prescription,
                'notes': appointment.treatment.notes,
                'follow_up_required': appointment.treatment.follow_up_required,
                'follow_up_date': appointment.treatment.follow_up_date.isoformat() if appointment.treatment.follow_up_date else None
            }
        
        return jsonify(response), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@doctor_bp.route('/appointments/<int:appointment_id>/complete', methods=['POST'])
@doctor_required
def complete_appointment(appointment_id):
    """Mark appointment as completed and add treatment details"""
    try:
        doctor = current_user.doctor_profile
        appointment = Appointment.query.filter_by(
            id=appointment_id,
            doctor_id=doctor.id
        ).first_or_404()
        
        if appointment.status == 'Completed':
            return jsonify({'error': 'Appointment already completed'}), 400
        
        if appointment.status == 'Cancelled':
            return jsonify({'error': 'Cannot complete a cancelled appointment'}), 400
        
        data = request.get_json()
        
        # Validate required fields
        if not data.get('diagnosis'):
            return jsonify({'error': 'Diagnosis is required'}), 400
        
        # Mark appointment as completed
        appointment.status = 'Completed'
        appointment.updated_at = datetime.utcnow()
        
        # Create or update treatment record
        if appointment.treatment:
            treatment = appointment.treatment
            treatment.diagnosis = data['diagnosis']
            treatment.prescription = data.get('prescription', '')
            treatment.notes = data.get('notes', '')
            treatment.follow_up_required = data.get('follow_up_required', False)
            treatment.follow_up_date = datetime.strptime(data['follow_up_date'], '%Y-%m-%d').date() if data.get('follow_up_date') else None
            treatment.updated_at = datetime.utcnow()
        else:
            treatment = Treatment(
                appointment_id=appointment_id,
                diagnosis=data['diagnosis'],
                prescription=data.get('prescription', ''),
                notes=data.get('notes', ''),
                follow_up_required=data.get('follow_up_required', False),
                follow_up_date=datetime.strptime(data['follow_up_date'], '%Y-%m-%d').date() if data.get('follow_up_date') else None,
                created_at=datetime.utcnow()
            )
            db.session.add(treatment)
        
        db.session.commit()
        
        return jsonify({
            'message': 'Appointment completed and treatment recorded successfully',
            'appointment_id': appointment_id
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@doctor_bp.route('/appointments/<int:appointment_id>/cancel', methods=['POST'])
@doctor_required
def cancel_appointment(appointment_id):
    """Cancel an appointment"""
    try:
        doctor = current_user.doctor_profile
        appointment = Appointment.query.filter_by(
            id=appointment_id,
            doctor_id=doctor.id
        ).first_or_404()
        
        if appointment.status != 'Booked':
            return jsonify({'error': 'Only booked appointments can be cancelled'}), 400
        
        appointment.status = 'Cancelled'
        appointment.cancelled_at = datetime.utcnow()
        appointment.cancelled_by = 'doctor'
        appointment.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({'message': 'Appointment cancelled successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@doctor_bp.route('/availability', methods=['GET'])
@doctor_required
def get_availability():
    """Get doctor's availability schedule"""
    try:
        doctor = current_user.doctor_profile
        
        today = datetime.utcnow().date()
        next_7_days = today + timedelta(days=7)
        
        availability = DoctorAvailability.query.filter(
            DoctorAvailability.doctor_id == doctor.id,
            DoctorAvailability.date >= today,
            DoctorAvailability.date <= next_7_days
        ).order_by(DoctorAvailability.date, DoctorAvailability.start_time).all()
        
        return jsonify({
            'availability': [{
                'id': slot.id,
                'date': slot.date.isoformat(),
                'start_time': slot.start_time.strftime('%H:%M'),
                'end_time': slot.end_time.strftime('%H:%M'),
                'is_available': slot.is_available,
                'max_appointments': slot.max_appointments,
                'booked_count': slot.booked_appointments_count
            } for slot in availability]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@doctor_bp.route('/availability/set', methods=['POST'])
@doctor_required
def set_availability():
    """Set availability for specific dates and times"""
    try:
        doctor = current_user.doctor_profile
        data = request.get_json()
        
        # Validate required fields
        if not all([data.get('date'), data.get('start_time'), data.get('end_time')]):
            return jsonify({'error': 'Date, start_time, and end_time are required'}), 400
        
        slot_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
        start_time = datetime.strptime(data['start_time'], '%H:%M').time()
        end_time = datetime.strptime(data['end_time'], '%H:%M').time()
        
        # Validate date is not in the past
        if slot_date < datetime.utcnow().date():
            return jsonify({'error': 'Cannot set availability for past dates'}), 400
        
        # Validate date is within 7 days
        if slot_date > datetime.utcnow().date() + timedelta(days=7):
            return jsonify({'error': 'Can only set availability for next 7 days'}), 400
        
        # Validate time
        if start_time >= end_time:
            return jsonify({'error': 'End time must be after start time'}), 400
        
        # Check if slot already exists
        existing = DoctorAvailability.query.filter_by(
            doctor_id=doctor.id,
            date=slot_date,
            start_time=start_time
        ).first()
        
        if existing:
            # Update existing slot
            existing.end_time = end_time
            existing.is_available = data.get('is_available', True)
            existing.max_appointments = data.get('max_appointments', 10)
        else:
            # Create new slot
            new_slot = DoctorAvailability(
                doctor_id=doctor.id,
                date=slot_date,
                start_time=start_time,
                end_time=end_time,
                is_available=data.get('is_available', True),
                max_appointments=data.get('max_appointments', 10),
                created_at=datetime.utcnow()
            )
            db.session.add(new_slot)
        
        db.session.commit()
        
        return jsonify({'message': 'Availability set successfully'}), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@doctor_bp.route('/availability/<int:slot_id>', methods=['PUT'])
@doctor_required
def update_availability(slot_id):
    """Update existing availability slot"""
    try:
        doctor = current_user.doctor_profile
        slot = DoctorAvailability.query.filter_by(
            id=slot_id,
            doctor_id=doctor.id
        ).first_or_404()
        
        data = request.get_json()
        
        if 'start_time' in data:
            slot.start_time = datetime.strptime(data['start_time'], '%H:%M').time()
        
        if 'end_time' in data:
            slot.end_time = datetime.strptime(data['end_time'], '%H:%M').time()
        
        if 'is_available' in data:
            slot.is_available = data['is_available']
        
        if 'max_appointments' in data:
            slot.max_appointments = data['max_appointments']
        
        db.session.commit()
        
        return jsonify({'message': 'Availability updated successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@doctor_bp.route('/availability/<int:slot_id>', methods=['DELETE'])
@doctor_required
def delete_availability(slot_id):
    """Delete availability slot"""
    try:
        doctor = current_user.doctor_profile
        slot = DoctorAvailability.query.filter_by(
            id=slot_id,
            doctor_id=doctor.id
        ).first_or_404()
        
        # Check if there are booked appointments for this slot
        if slot.booked_appointments_count > 0:
            return jsonify({'error': 'Cannot delete slot with booked appointments'}), 400
        
        db.session.delete(slot)
        db.session.commit()
        
        return jsonify({'message': 'Availability slot deleted successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@doctor_bp.route('/patients', methods=['GET'])
@doctor_required
def get_patients():
    """Get list of all patients assigned to this doctor"""
    try:
        doctor = current_user.doctor_profile
        
        # Get unique patients who have appointments with this doctor
        patients_query = db.session.query(Patient).join(Appointment).filter(
            Appointment.doctor_id == doctor.id
        ).distinct()
        
        search = request.args.get('search', '')
        if search:
            patients_query = patients_query.join(Patient.user).filter(
                Patient.user.has(User.full_name.ilike(f'%{search}%'))
            )
        
        patients = patients_query.all()
        
        return jsonify({
            'patients': [{
                'id': pat.id,
                'name': pat.user.full_name,
                'age': pat.age,
                'blood_group': pat.blood_group,
                'phone': pat.user.phone,
                'last_visit': Appointment.query.filter_by(
                    patient_id=pat.id,
                    doctor_id=doctor.id,
                    status='Completed'
                ).order_by(Appointment.appointment_date.desc()).first().appointment_date.isoformat() if Appointment.query.filter_by(
                    patient_id=pat.id,
                    doctor_id=doctor.id,
                    status='Completed'
                ).first() else None
            } for pat in patients]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@doctor_bp.route('/patients/<int:patient_id>/history', methods=['GET'])
@doctor_required
def get_patient_history(patient_id):
    """Get complete treatment history for a specific patient"""
    try:
        doctor = current_user.doctor_profile
        patient = Patient.query.get_or_404(patient_id)
        
        # Get all appointments with this doctor
        appointments = Appointment.query.filter_by(
            patient_id=patient_id,
            doctor_id=doctor.id
        ).order_by(Appointment.appointment_date.desc()).all()
        
        return jsonify({
            'patient': {
                'id': patient.id,
                'name': patient.user.full_name,
                'age': patient.age,
                'blood_group': patient.blood_group,
                'medical_history': patient.medical_history,
                'allergies': patient.allergies
            },
            'appointment_history': [{
                'id': apt.id,
                'date': apt.appointment_date.isoformat(),
                'status': apt.status,
                'reason': apt.reason_for_visit,
                'treatment': {
                    'diagnosis': apt.treatment.diagnosis,
                    'prescription': apt.treatment.prescription,
                    'notes': apt.treatment.notes,
                    'follow_up_required': apt.treatment.follow_up_required
                } if apt.treatment else None
            } for apt in appointments]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500