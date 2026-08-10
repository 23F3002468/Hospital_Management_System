"""Fire the two scheduled email tasks by hand.

A manual script, not part of the pytest suite - it runs the real tasks against
the real database and actually sends mail (to the Mailtrap sandbox inbox
configured in .env). Named ``send_test_email`` rather than ``test_email`` so
pytest does not collect it.

    python send_test_email.py
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

print("Tests completed. Check the Mailtrap inbox.")
print("Go to: https://mailtrap.io/inboxes")