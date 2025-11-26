from celery.schedules import crontab
from datetime import datetime, timedelta
from flask import render_template_string
import csv
import io
import os
import sys

# Add project directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import Celery instance FIRST
from celery_app import celery

# Import Flask app and models
from app import create_app
from models import db, Appointment, Doctor, Treatment, Patient, User

# Create Flask app instance for tasks
flask_app = create_app()
# ============================================================================
# TASK 1: Daily Appointment Reminders
# ============================================================================

@celery.task(name='tasks.send_daily_appointment_reminders')
def send_daily_appointment_reminders():
    """
    Send reminders to patients who have appointments today
    Runs every day at 8:00 AM
    """
    with flask_app.app_context():
        today = datetime.utcnow().date()
        
        # Get all appointments for today with status 'Booked'
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
            
            # Send reminder (choose one method below)
            
            # Method 1: Print to console (for testing)
            print(f"Reminder sent to {patient.full_name}: {message}")
            
            # Method 2: Send Email (uncomment if email is configured)
            # send_email(patient.email, "Appointment Reminder", message)
            
            # Method 3: Send to Google Chat (uncomment if webhook is configured)
            # send_google_chat_message(message)
        
        return f"Sent {len(appointments)} reminders"


# ============================================================================
# TASK 2: Monthly Doctor Reports
# ============================================================================

@celery.task(name='tasks.send_monthly_doctor_reports')
def send_monthly_doctor_reports():
    """
    Generate and send monthly activity reports to all doctors
    Runs on 1st day of every month at 9:00 AM
    """
    with flask_app.app_context():
        # Get previous month date range
        today = datetime.utcnow().date()
        first_day_current_month = today.replace(day=1)
        last_day_previous_month = first_day_current_month - timedelta(days=1)
        first_day_previous_month = last_day_previous_month.replace(day=1)
        
        # Get all active doctors
        doctors = Doctor.query.join(User).filter(User.is_active == True).all()
        
        print(f"Generating reports for {len(doctors)} doctors")
        
        for doctor in doctors:
            # Get appointments for this doctor in previous month
            appointments = Appointment.query.filter(
                Appointment.doctor_id == doctor.id,
                Appointment.appointment_date >= first_day_previous_month,
                Appointment.appointment_date <= last_day_previous_month
            ).all()
            
            # Calculate statistics
            total_appointments = len(appointments)
            completed = len([a for a in appointments if a.status == 'Completed'])
            cancelled = len([a for a in appointments if a.status == 'Cancelled'])
            
            # Generate HTML report
            report_html = generate_monthly_report_html(
                doctor, 
                appointments, 
                first_day_previous_month, 
                last_day_previous_month,
                total_appointments,
                completed,
                cancelled
            )
            
            # Send report
            # Method 1: Print to console (for testing)
            print(f"\nMonthly Report for Dr. {doctor.user.full_name}:")
            print(f"Total Appointments: {total_appointments}")
            print(f"Completed: {completed}")
            print(f"Cancelled: {cancelled}")
            
            # Method 2: Send Email (uncomment if email is configured)
            # send_email(
            #     doctor.user.email,
            #     f"Monthly Activity Report - {first_day_previous_month.strftime('%B %Y')}",
            #     report_html,
            #     html=True
            # )
        
        return f"Sent reports to {len(doctors)} doctors"


def generate_monthly_report_html(doctor, appointments, start_date, end_date, total, completed, cancelled):
    """Generate HTML report for doctor's monthly activity"""
    
    template = """
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            h1 { color: #198754; }
            table { border-collapse: collapse; width: 100%; margin-top: 20px; }
            th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
            th { background-color: #198754; color: white; }
            .stats { background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0; }
            .stat-item { display: inline-block; margin-right: 30px; }
        </style>
    </head>
    <body>
        <h1>Monthly Activity Report</h1>
        <h2>Dr. {{ doctor_name }}</h2>
        <p><strong>Department:</strong> {{ department }}</p>
        <p><strong>Period:</strong> {{ start_date }} to {{ end_date }}</p>
        
        <div class="stats">
            <div class="stat-item">
                <strong>Total Appointments:</strong> {{ total }}
            </div>
            <div class="stat-item">
                <strong>Completed:</strong> {{ completed }}
            </div>
            <div class="stat-item">
                <strong>Cancelled:</strong> {{ cancelled }}
            </div>
        </div>
        
        <h3>Appointment Details</h3>
        <table>
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Patient Name</th>
                    <th>Status</th>
                    <th>Diagnosis</th>
                </tr>
            </thead>
            <tbody>
                {% for apt in appointments %}
                <tr>
                    <td>{{ apt.date }}</td>
                    <td>{{ apt.patient }}</td>
                    <td>{{ apt.status }}</td>
                    <td>{{ apt.diagnosis }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        
        <p style="margin-top: 30px; color: #666;">
            Generated by Hospital Management System on {{ generated_date }}
        </p>
    </body>
    </html>
    """
    
    from jinja2 import Template
    tmpl = Template(template)
    
    appointments_data = [{
        'date': apt.appointment_date.strftime('%Y-%m-%d'),
        'patient': apt.patient.user.full_name,
        'status': apt.status,
        'diagnosis': apt.treatment.diagnosis if apt.treatment else 'N/A'
    } for apt in appointments]
    
    return tmpl.render(
        doctor_name=doctor.user.full_name,
        department=doctor.department.name,
        start_date=start_date.strftime('%B %d, %Y'),
        end_date=end_date.strftime('%B %d, %Y'),
        total=total,
        completed=completed,
        cancelled=cancelled,
        appointments=appointments_data,
        generated_date=datetime.utcnow().strftime('%B %d, %Y')
    )


# ============================================================================
# TASK 3: CSV Export (User-triggered async job)
# ============================================================================

@celery.task(name='tasks.export_patient_treatment_history_csv')
def export_patient_treatment_history_csv(patient_id):
    """
    Export patient's treatment history as CSV
    This is a user-triggered async job
    """
    with flask_app.app_context():
        patient = Patient.query.get(patient_id)
        if not patient:
            return {'error': 'Patient not found'}
        
        # Get all treatments for this patient
        treatments = Treatment.query.join(Appointment).filter(
            Appointment.patient_id == patient_id,
            Appointment.status == 'Completed'
        ).order_by(Appointment.appointment_date.desc()).all()
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Patient ID',
            'Patient Name',
            'Appointment Date',
            'Doctor Name',
            'Department',
            'Diagnosis',
            'Prescription',
            'Treatment Notes',
            'Follow-up Required',
            'Follow-up Date'
        ])
        
        # Write data
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
        
        # Save to file or return
        filename = f"patient_{patient_id}_treatment_history_{datetime.utcnow().strftime('%Y%m%d')}.csv"
        filepath = f"exports/{filename}"
        
        # Create exports directory if not exists
        import os
        os.makedirs('exports', exist_ok=True)
        
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
# Helper Functions (Email/Google Chat)
# ============================================================================

def send_email(to_email, subject, body, html=False):
    """
    Send email using Flask-Mail
    Uncomment and configure MAIL settings in config.py
    """
    try:
        from flask_mail import Mail, Message
        mail = Mail(flask_app())
        
        msg = Message(
            subject=subject,
            recipients=[to_email],
            body=body if not html else None,
            html=body if html else None
        )
        mail.send(msg)
        print(f"Email sent to {to_email}")
    except Exception as e:
        print(f"Failed to send email: {str(e)}")


def send_google_chat_message(message):
    """
    Send message to Google Chat using webhook
    Configure GOOGLE_CHAT_WEBHOOK_URL in config.py
    """
    try:
        import requests
        webhook_url = flask_app().config.get('GOOGLE_CHAT_WEBHOOK_URL')
        
        if not webhook_url:
            print("Google Chat webhook URL not configured")
            return
        
        response = requests.post(
            webhook_url,
            json={'text': message}
        )
        
        if response.status_code == 200:
            print("Google Chat message sent")
        else:
            print(f"Failed to send Google Chat message: {response.status_code}")
    except Exception as e:
        print(f"Failed to send Google Chat message: {str(e)}")