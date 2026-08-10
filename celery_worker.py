"""
Celery worker - loads app and tasks
"""
import sys
import os

# Add project directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import Celery app
from celery_app import celery

# Import Flask app first to avoid circular imports
from app import create_app
flask_app = create_app()

# Now import models
from models import db, Appointment, Doctor, Treatment, Patient, User

# Import task decorators and functions
from celery.schedules import crontab
from celery.utils.log import get_task_logger
from datetime import datetime, timedelta
import csv
import io

from timeutils import hospital_today

# Worker output goes through Celery's task logger, not print(). It carries the
# task name and id, honours --loglevel, and is routed wherever the worker's
# logging is configured. print() also writes through the console's encoding -
# on a stock Windows terminal that is cp1252, and a single emoji in the output
# raised UnicodeEncodeError and killed the task.
logger = get_task_logger(__name__)

# ============================================================================
# DEFINE TASKS HERE
# ============================================================================

@celery.task(name='tasks.send_daily_appointment_reminders')
def send_daily_appointment_reminders():
    """Send reminders to patients with appointments today"""
    with flask_app.app_context():
        today = hospital_today()
        
        appointments = Appointment.query.filter(
            Appointment.appointment_date == today,
            Appointment.status == 'Booked'
        ).all()
        
        logger.info("Found %d appointments for today", len(appointments))
        
        for appointment in appointments:
            patient = appointment.patient.user
            doctor = appointment.doctor.user
            
            message = f"""
🏥 Appointment Reminder

Dear {patient.full_name},

This is a reminder that you have an appointment today:

Doctor: Dr. {doctor.full_name}
Department: {appointment.doctor.department.name}
Time: {appointment.appointment_time.strftime('%I:%M %p')}

Please arrive 10 minutes early.

Hospital Management System
            """
            
            logger.info("Sending reminder to %s (%s)", patient.full_name, patient.email)
            
            # Send email

            email_sent = send_email(
                to_email=patient.email,
                subject="🏥 Appointment Reminder - Hospital Management System",
                body=message
            )
            
            if not email_sent:
                logger.warning("Reminder email to %s failed", patient.email)
        
        return f"Sent {len(appointments)} reminders"


@celery.task(name='tasks.send_monthly_doctor_reports')
def send_monthly_doctor_reports():
    """Generate and send monthly reports to doctors"""
    with flask_app.app_context():
        today = hospital_today()
        first_day_current_month = today.replace(day=1)
        last_day_previous_month = first_day_current_month - timedelta(days=1)
        first_day_previous_month = last_day_previous_month.replace(day=1)
        
        doctors = Doctor.query.join(User).filter(User.is_active == True).all()
        
        logger.info("Generating reports for %d doctors", len(doctors))
        
        for doctor in doctors:
            appointments = Appointment.query.filter(
                Appointment.doctor_id == doctor.id,
                Appointment.appointment_date >= first_day_previous_month,
                Appointment.appointment_date <= last_day_previous_month
            ).all()
            
            total_appointments = len(appointments)
            completed = len([a for a in appointments if a.status == 'Completed'])
            cancelled = len([a for a in appointments if a.status == 'Cancelled'])
            
            logger.info(
                "Report for Dr. %s (%s): %d total, %d completed, %d cancelled",
                doctor.user.full_name, doctor.user.email,
                total_appointments, completed, cancelled,
            )
        
        return f"Sent reports to {len(doctors)} doctors"


@celery.task(name='tasks.export_patient_treatment_history_csv')
def export_patient_treatment_history_csv(patient_id):
    """Export patient treatment history as CSV"""
    with flask_app.app_context():
        patient = Patient.query.get(patient_id)
        if not patient:
            return {'error': 'Patient not found'}
        
        treatments = Treatment.query.join(Appointment).filter(
            Appointment.patient_id == patient_id,
            Appointment.status == 'Completed'
        ).order_by(Appointment.appointment_date.desc()).all()
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        writer.writerow([
            'Patient ID', 'Patient Name', 'Appointment Date', 'Doctor Name',
            'Department', 'Diagnosis', 'Prescription', 'Treatment Notes',
            'Follow-up Required', 'Follow-up Date'
        ])
        
        for treatment in treatments:
            appointment = treatment.appointment
            writer.writerow([
                patient.id,
                patient.user.full_name,
                appointment.appointment_date.strftime('%Y-%m-%d'),
                appointment.doctor.user.full_name,
                appointment.doctor.department.name,
                treatment.diagnosis,
                treatment.prescription or '',
                treatment.notes or '',
                'Yes' if treatment.follow_up_required else 'No',
                treatment.follow_up_date.strftime('%Y-%m-%d') if treatment.follow_up_date else ''
            ])
        
        csv_content = output.getvalue()
        output.close()
        
        filename = f"patient_{patient_id}_treatment_history_{datetime.utcnow().strftime('%Y%m%d')}.csv"
        
        os.makedirs('exports', exist_ok=True)
        filepath = f"exports/{filename}"
        
        with open(filepath, 'w', newline='') as f:
            f.write(csv_content)
        
        logger.info("CSV exported: %s (%d records)", filepath, len(treatments))
        
        return {
            'success': True,
            'filename': filename,
            'filepath': filepath,
            'records': len(treatments)
        }

# ============================================================================
# Helper Functions
# ============================================================================

def send_email(to_email, subject, body, html=False):
    """
    Send email using Flask-Mail via Mailtrap
    """
    try:
        from flask_mail import Mail, Message
        
        mail = Mail(flask_app)
        
        msg = Message(
            subject=subject,
            recipients=[to_email],
            sender=flask_app.config['MAIL_DEFAULT_SENDER']
        )
        
        if html:
            msg.html = body
        else:
            msg.body = body
        
        with flask_app.app_context():
            mail.send(msg)
        
        logger.info("Email sent to %s", to_email)
        return True
    except Exception:
        # exception() logs the traceback through the same handler as everything
        # else, instead of print_exc() writing straight to stderr.
        logger.exception("Failed to send email to %s", to_email)
        return False

logger.info("Celery worker loaded with tasks")