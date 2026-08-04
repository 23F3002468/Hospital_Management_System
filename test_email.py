"""
Test email functionality
"""
from celery_worker import (
    send_daily_appointment_reminders,
    send_monthly_doctor_reports
)

print("=" * 60)
print("Testing Daily Appointment Reminders")
print("=" * 60)
result1 = send_daily_appointment_reminders()
print(f"\nResult: {result1}\n")

print("=" * 60)
print("Testing Monthly Doctor Reports")
print("=" * 60)
result2 = send_monthly_doctor_reports()
print(f"\nResult: {result2}\n")

print("✅ Tests completed! Check Mailtrap inbox.")
print("📧 Go to: https://mailtrap.io/inboxes")