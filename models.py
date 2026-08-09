from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timedelta

from timeutils import hospital_now, hospital_today

# Initialize our database
db = SQLAlchemy()

class User(db.Model, UserMixin):
    """
    Represents a user in our hospital management system.
    Can be Admin, Doctor, or Patient.
    """
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)  # This will be hashed
    role = db.Column(db.String(20), nullable=False)  # 'admin', 'doctor', or 'patient'
    full_name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(15), nullable=True)
    address = db.Column(db.Text, nullable=True)
    registration_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)  # For blacklisting users
    
    def __repr__(self):
        return f'<User {self.username} - {self.role}>'
    
    @property
    def is_admin(self):
        return self.role == 'admin'
    
    @property
    def is_doctor(self):
        return self.role == 'doctor'
    
    @property
    def is_patient(self):
        return self.role == 'patient'


class Department(db.Model):
    """
    Represents medical departments/specializations in the hospital.
    Examples: Cardiology, Neurology, Orthopedics, etc.
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship - department has many doctors
    doctors = db.relationship('Doctor', backref='department', lazy=True)
    
    def __repr__(self):
        return f'<Department {self.name}>'
    
    @property
    def doctors_count(self):
        """Count active doctors in this department.

        One COUNT query - does not load the doctor or user rows.
        """
        return db.session.query(db.func.count(Doctor.id)).join(
            User, Doctor.user_id == User.id
        ).filter(
            Doctor.department_id == self.id,
            User.is_active.is_(True)
        ).scalar()

    @property
    def available_doctors_count(self):
        """Count active doctors with an availability slot today.

        One COUNT query. DISTINCT because a doctor may have several slots.
        """
        today = hospital_today()
        return db.session.query(db.func.count(db.distinct(Doctor.id))).join(
            User, Doctor.user_id == User.id
        ).join(
            DoctorAvailability, DoctorAvailability.doctor_id == Doctor.id
        ).filter(
            Doctor.department_id == self.id,
            User.is_active.is_(True),
            DoctorAvailability.date == today,
            DoctorAvailability.is_available.is_(True)
        ).scalar()


class Doctor(db.Model):
    """
    Represents a doctor's profile with specialization and availability.
    Links to User model for authentication.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)
    qualification = db.Column(db.String(200), nullable=True)
    experience_years = db.Column(db.Integer, nullable=True)
    consultation_fee = db.Column(db.Float, nullable=True)
    bio = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('doctor_profile', uselist=False))
    availability_slots = db.relationship('DoctorAvailability', backref='doctor', lazy=True, cascade='all, delete-orphan')
    appointments = db.relationship('Appointment', backref='doctor', lazy=True)
    
    def __repr__(self):
        return f'<Doctor {self.user.full_name} - {self.department.name}>'
    
    def is_available_on_date(self, date):
        """Check if doctor has availability on a specific date"""
        return DoctorAvailability.query.filter_by(
            doctor_id=self.id,
            date=date,
            is_available=True
        ).first() is not None
    
    @property
    def upcoming_appointments_count(self):
        """Count upcoming appointments for this doctor.

        One COUNT query rather than loading every appointment row into memory.
        """
        today = hospital_today()
        return db.session.query(db.func.count(Appointment.id)).filter(
            Appointment.doctor_id == self.id,
            Appointment.appointment_date >= today,
            Appointment.status == 'Booked'
        ).scalar()

    @property
    def completed_appointments_count(self):
        """Count completed appointments. One COUNT query."""
        return db.session.query(db.func.count(Appointment.id)).filter(
            Appointment.doctor_id == self.id,
            Appointment.status == 'Completed'
        ).scalar()


class Patient(db.Model):
    """
    Represents a patient's profile with medical information.
    Links to User model for authentication.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    date_of_birth = db.Column(db.Date, nullable=True)
    blood_group = db.Column(db.String(5), nullable=True)
    emergency_contact = db.Column(db.String(15), nullable=True)
    medical_history = db.Column(db.Text, nullable=True)
    allergies = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('patient_profile', uselist=False))
    appointments = db.relationship('Appointment', backref='patient', lazy=True)
    
    def __repr__(self):
        return f'<Patient {self.user.full_name}>'
    
    @property
    def age(self):
        """Calculate patient's age from date of birth"""
        if self.date_of_birth:
            today = hospital_today()
            return today.year - self.date_of_birth.year - (
                (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
            )
        return None
    
    @property
    def upcoming_appointments(self):
        """Upcoming appointments, filtered and ordered by the database."""
        today = hospital_today()
        return Appointment.query.filter(
            Appointment.patient_id == self.id,
            Appointment.appointment_date >= today,
            Appointment.status == 'Booked'
        ).order_by(Appointment.appointment_date, Appointment.appointment_time).all()

    @property
    def appointment_history(self):
        """Past appointments, filtered and ordered by the database."""
        today = hospital_today()
        return Appointment.query.filter(
            Appointment.patient_id == self.id,
            db.or_(
                Appointment.appointment_date < today,
                Appointment.status.in_(['Completed', 'Cancelled'])
            )
        ).order_by(Appointment.appointment_date.desc()).all()


class DoctorAvailability(db.Model):
    """
    Represents doctor's availability for specific dates and time slots.
    Doctors can set their availability for the next 7 days.
    """
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    is_available = db.Column(db.Boolean, default=True)
    max_appointments = db.Column(db.Integer, default=10)  # Max appointments per slot
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Availability Doctor:{self.doctor_id} Date:{self.date}>'
    
    @property
    def booked_appointments_count(self):
        """Count how many appointments are booked for this slot"""
        return Appointment.query.filter_by(
            doctor_id=self.doctor_id,
            appointment_date=self.date,
            status='Booked'
        ).filter(
            Appointment.appointment_time >= self.start_time,
            Appointment.appointment_time < self.end_time
        ).count()
    
    @property
    def slots_available(self):
        """Check if there are still slots available"""
        return self.booked_appointments_count < self.max_appointments


class Appointment(db.Model):
    """
    Represents an appointment between a patient and doctor.
    Tracks status from booking through completion or cancellation.
    """
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False)
    appointment_date = db.Column(db.Date, nullable=False)
    appointment_time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(20), default='Booked')  # 'Booked', 'Completed', 'Cancelled'
    reason_for_visit = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    cancelled_by = db.Column(db.String(20), nullable=True)  # 'patient', 'doctor', or 'admin'

    __table_args__ = (
        # One live booking per doctor per slot, enforced by the database so that
        # two concurrent requests cannot both pass the application-level check.
        # Partial index: cancelled and completed rows are excluded, so a slot
        # becomes bookable again once it is cancelled.
        db.Index(
            'uq_appointment_doctor_slot',
            'doctor_id', 'appointment_date', 'appointment_time',
            unique=True,
            sqlite_where=db.text("status = 'Booked'"),
            postgresql_where=db.text("status = 'Booked'"),
        ),
    )

    # Relationship - appointment can have one treatment record
    treatment = db.relationship('Treatment', backref='appointment', uselist=False, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Appointment {self.id} - {self.status}>'
    
    @property
    def appointment_datetime(self):
        """Combine date and time into a single datetime object"""
        return datetime.combine(self.appointment_date, self.appointment_time)
    
    @property
    def is_upcoming(self):
        """Check if appointment is in the future"""
        return self.appointment_datetime > hospital_now() and self.status == 'Booked'
    
    @property
    def can_be_cancelled(self):
        """Check if appointment can still be cancelled"""
        # Can only cancel if it's booked and in the future
        return self.status == 'Booked' and self.is_upcoming
    
    @property
    def can_be_rescheduled(self):
        """Check if appointment can be rescheduled"""
        return self.status == 'Booked' and self.is_upcoming


class Treatment(db.Model):
    """
    Represents treatment details recorded after an appointment.
    Contains diagnosis, prescriptions, and doctor's notes.
    """
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointment.id'), nullable=False, unique=True)
    diagnosis = db.Column(db.Text, nullable=False)
    prescription = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    follow_up_required = db.Column(db.Boolean, default=False)
    follow_up_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Treatment for Appointment:{self.appointment_id}>'
    
    @property
    def patient_name(self):
        """Get patient's name from the appointment"""
        return self.appointment.patient.user.full_name
    
    @property
    def doctor_name(self):
        """Get doctor's name from the appointment"""
        return self.appointment.doctor.user.full_name
    
    @property
    def treatment_date(self):
        """Get the date when treatment was given"""
        return self.appointment.appointment_date


class ActivityLog(db.Model):
    """
    Tracks important activities in the system for audit purposes.
    Useful for admin to monitor system usage and doctor monthly reports.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    action_type = db.Column(db.String(50), nullable=False)  # 'login', 'appointment_booked', 'appointment_completed', etc.
    description = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(50), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    user = db.relationship('User', backref=db.backref('activity_logs', lazy=True))
    
    def __repr__(self):
        return f'<ActivityLog {self.action_type} at {self.timestamp}>'