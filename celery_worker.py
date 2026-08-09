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
from datetime import datetime, timedelta
import csv
import io

from timeutils import hospital_today

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
        
        print(f"Found {len(appointments)} appointments for today")
        
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
            
            print(f"Sending reminder to {patient.full_name} ({patient.email})")
            
            # Send email

            email_sent = send_email(
                to_email=patient.email,
                subject="🏥 Appointment Reminder - Hospital Management System",
                body=message
            )
            
            if email_sent:
                print(f"✅ Email sent successfully")
            else:
                print(f"❌ Email failed")
        
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
        
        print(f"Generating reports for {len(doctors)} doctors")
        
        for doctor in doctors:
            appointments = Appointment.query.filter(
                Appointment.doctor_id == doctor.id,
                Appointment.appointment_date >= first_day_previous_month,
                Appointment.appointment_date <= last_day_previous_month
            ).all()
            
            total_appointments = len(appointments)
            completed = len([a for a in appointments if a.status == 'Completed'])
            cancelled = len([a for a in appointments if a.status == 'Cancelled'])
            
            print(f"Sending report to Dr. {doctor.user.full_name} ({doctor.user.email})")
            print(f"Stats: {total_appointments} total, {completed} completed, {cancelled} cancelled")
        
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
        
        print(f"CSV exported: {filepath}")
        
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
        
        print(f"✅ Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"❌ Failed to send email to {to_email}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

print("✅ Celery worker loaded with tasks")