"""Demo doctors and their availability.

The point of this module is that a fresh clone is immediately explorable: log in
as a patient and there are doctors in every department, each with bookable slots
for the next week. Without it the patient dashboard is empty until someone logs
in as admin and creates a doctor by hand, which is a poor first impression of
the project.

Naming convention: each doctor's first name echoes their specialisation -
Dr. Otho in Orthopedics, Dr. Cardia in Cardiology - so a reviewer clicking
through can tell at a glance which department they are looking at.

Names are stored **without** the "Dr." prefix. `templates/doctor_dashboard.html`
and `templates/patient_history.html` render `Dr. {{ name }}` themselves, so a
stored prefix would come out as "Dr. Dr. Otho Menon".

Run standalone to (re)seed without touching anything else:

    python demo_data.py

It is idempotent - existing doctors are left alone, and availability is topped
up for the rolling 7-day window, so an old demo database becomes bookable again
rather than showing "No available slots".
"""

from datetime import time, timedelta

from werkzeug.security import generate_password_hash

from models import Department, Doctor, DoctorAvailability, User, db
from timeutils import hospital_now, hospital_today

# Every demo doctor shares this password, in the same spirit as the seeded
# admin/admin123 login: this is a portfolio demo and a reviewer needs to get in
# without hunting for credentials.
DEMO_DOCTOR_PASSWORD = 'doctor123'

# Consulting hours, as two blocks per day. The booking UI expands each block
# into 30-minute slots, so this yields 8 morning and 6 afternoon slots.
MORNING = (time(9, 0), time(13, 0))
AFTERNOON = (time(14, 0), time(17, 0))

# Days of availability created ahead of today. The patient-facing availability
# endpoint looks at today .. today + 7, so 7 fills that window.
AVAILABILITY_DAYS = 7

DEMO_DOCTORS = [
    {
        'department': 'Cardiology',
        'username': 'dr.cardia',
        'full_name': 'Cardia Nair',
        'qualification': 'MBBS, MD (General Medicine), DM (Cardiology)',
        'experience_years': 14,
        'consultation_fee': 900.0,
        'bio': 'Interventional cardiologist with a focus on preventive heart care '
               'and post-operative follow-up.',
    },
    {
        'department': 'Cardiology',
        'username': 'dr.cardio',
        'full_name': 'Cardio Sethi',
        'qualification': 'MBBS, MD, DNB (Cardiology)',
        'experience_years': 8,
        'consultation_fee': 750.0,
        'bio': 'Treats arrhythmia and heart failure; runs the weekly hypertension clinic.',
    },
    {
        'department': 'Neurology',
        'username': 'dr.neura',
        'full_name': 'Neura Iyer',
        'qualification': 'MBBS, MD, DM (Neurology)',
        'experience_years': 11,
        'consultation_fee': 950.0,
        'bio': 'Specialises in epilepsy, migraine and movement disorders.',
    },
    {
        'department': 'Orthopedics',
        'username': 'dr.otho',
        'full_name': 'Otho Menon',
        'qualification': 'MBBS, MS (Orthopedics)',
        'experience_years': 16,
        'consultation_fee': 800.0,
        'bio': 'Joint replacement and sports injuries, with a special interest in '
               'knee reconstruction.',
    },
    {
        'department': 'Pediatrics',
        'username': 'dr.pedia',
        'full_name': 'Pedia Rao',
        'qualification': 'MBBS, MD (Pediatrics)',
        'experience_years': 9,
        'consultation_fee': 600.0,
        'bio': 'Newborn care, childhood immunisation and developmental checks.',
    },
    {
        'department': 'Dermatology',
        'username': 'dr.derma',
        'full_name': 'Derma Shah',
        'qualification': 'MBBS, MD (Dermatology)',
        'experience_years': 7,
        'consultation_fee': 700.0,
        'bio': 'Chronic skin conditions, acne and hair loss; runs a weekly patch-test clinic.',
    },
    {
        'department': 'General Medicine',
        'username': 'dr.genera',
        'full_name': 'Genera Bose',
        'qualification': 'MBBS, MD (General Medicine)',
        'experience_years': 12,
        'consultation_fee': 500.0,
        'bio': 'First point of contact for fever, infection and long-term conditions '
               'such as diabetes and thyroid disorders.',
    },
    {
        'department': 'General Medicine',
        'username': 'dr.medica',
        'full_name': 'Medica Joshi',
        'qualification': 'MBBS, DNB (Family Medicine)',
        'experience_years': 5,
        'consultation_fee': 450.0,
        'bio': 'General consultations and routine health check-ups.',
    },
    {
        'department': 'Gynecology',
        'username': 'dr.gyna',
        'full_name': 'Gyna Reddy',
        'qualification': 'MBBS, MS (Obstetrics & Gynecology)',
        'experience_years': 13,
        'consultation_fee': 850.0,
        'bio': 'Antenatal care, fertility counselling and minimally invasive surgery.',
    },
    {
        'department': 'ENT (Otolaryngology)',
        'username': 'dr.ento',
        'full_name': 'Ento Pillai',
        'qualification': 'MBBS, MS (ENT)',
        'experience_years': 10,
        'consultation_fee': 650.0,
        'bio': 'Sinus disease, hearing assessment and paediatric ENT.',
    },
    {
        'department': 'Ophthalmology',
        'username': 'dr.ophtha',
        'full_name': 'Ophtha Kapoor',
        'qualification': 'MBBS, MS (Ophthalmology)',
        'experience_years': 15,
        'consultation_fee': 700.0,
        'bio': 'Cataract surgery, glaucoma management and diabetic retinopathy screening.',
    },
    {
        'department': 'Psychiatry',
        'username': 'dr.psycha',
        'full_name': 'Psycha Verma',
        'qualification': 'MBBS, MD (Psychiatry)',
        'experience_years': 9,
        'consultation_fee': 1000.0,
        'bio': 'Anxiety, depression and sleep disorders; offers both medication review '
               'and talking therapy.',
    },
]


def _email_for(username):
    """dr.otho -> otho@hospital.com"""
    return f"{username.removeprefix('dr.')}@hospital.com"


def create_demo_doctors(availability_days=AVAILABILITY_DAYS, verbose=True):
    """Create the demo doctors and fill their calendars.

    Requires an application context. Returns ``(created, skipped, slots_added)``.

    Idempotent in both directions: a doctor whose username already exists is
    left untouched, and availability is only added for dates that do not have a
    matching row yet. Re-running after a week tops the calendar back up.
    """
    def log(message):
        if verbose:
            print(message)

    departments = {department.name: department for department in Department.query.all()}
    if not departments:
        raise RuntimeError(
            'No departments found. Run init_db.py first - the demo doctors are '
            'assigned to the default departments it creates.'
        )

    created = skipped = 0

    for spec in DEMO_DOCTORS:
        department = departments.get(spec['department'])
        if department is None:
            log(f"  skipped {spec['full_name']}: no '{spec['department']}' department")
            skipped += 1
            continue

        if User.query.filter_by(username=spec['username']).first():
            log(f"  {spec['username']} already exists, skipping")
            skipped += 1
            continue

        user = User(
            username=spec['username'],
            email=_email_for(spec['username']),
            password=generate_password_hash(DEMO_DOCTOR_PASSWORD),
            role='doctor',
            full_name=spec['full_name'],
            phone='9800000000',
            address='Hospital Campus',
            registration_timestamp=hospital_now(),
            is_active=True,
        )
        db.session.add(user)
        db.session.flush()

        db.session.add(Doctor(
            user_id=user.id,
            department_id=department.id,
            qualification=spec['qualification'],
            experience_years=spec['experience_years'],
            consultation_fee=spec['consultation_fee'],
            bio=spec['bio'],
        ))
        created += 1
        log(f"  created Dr. {spec['full_name']} ({spec['department']})")

    db.session.commit()

    slots_added = _fill_availability(availability_days, log)
    db.session.commit()

    if created or slots_added:
        _invalidate_department_cache(log)

    return created, skipped, slots_added


def _invalidate_department_cache(log):
    """Drop the cached department payload - it carries per-department counts.

    Tolerates a missing cache backend: seeding is a setup step that should not
    fail because Redis happens not to be running yet.
    """
    from cache import invalidate_departments

    try:
        invalidate_departments()
    except Exception as exc:  # noqa: BLE001 - any backend error is equally fine here
        log(f'  could not clear the department cache ({exc.__class__.__name__}); '
            f'it expires on its own within 5 minutes')


def _fill_availability(availability_days, log):
    """Give every demo doctor a morning and afternoon block for each day ahead.

    Only the demo doctors are touched - a real doctor's calendar is theirs to
    manage from the doctor dashboard.
    """
    usernames = [spec['username'] for spec in DEMO_DOCTORS]
    doctors = Doctor.query.join(User).filter(User.username.in_(usernames)).all()

    today = hospital_today()
    dates = [today + timedelta(days=offset) for offset in range(availability_days + 1)]

    existing = {
        (slot.doctor_id, slot.date, slot.start_time)
        for slot in DoctorAvailability.query.filter(
            DoctorAvailability.date >= today
        ).all()
    }

    added = 0
    for doctor in doctors:
        for day in dates:
            for start, end in (MORNING, AFTERNOON):
                if (doctor.id, day, start) in existing:
                    continue
                db.session.add(DoctorAvailability(
                    doctor_id=doctor.id,
                    date=day,
                    start_time=start,
                    end_time=end,
                    is_available=True,
                    max_appointments=8,
                ))
                added += 1

    log(f'  {added} availability blocks added across {len(doctors)} doctors')
    return added


if __name__ == '__main__':
    # Imported here rather than at module scope so that importing this module
    # (from init_db.py, or from a test) does not build a Flask app.
    from app import app

    with app.app_context():
        print('Seeding demo doctors...')
        created, skipped, slots = create_demo_doctors()
        print(f'\nDone: {created} created, {skipped} skipped, {slots} availability blocks.')
        if created:
            print(f'Doctor logins: username as listed above, password {DEMO_DOCTOR_PASSWORD}')
