"""
Database initialization script
Creates all tables and adds default admin user
Run this once to set up the database
"""

from app import app
from models import db, User, Department
from werkzeug.security import generate_password_hash
from datetime import datetime


def init_database():
    """
    Initialize database with tables and default data
    """
    with app.app_context():
        print("🏥 Initializing Hospital Management System Database...")
        
        # Drop all existing tables (WARNING: This deletes all data!)
        # Comment out the next line if you want to keep existing data
        print("⚠️  Dropping existing tables...")
        db.drop_all()
        
        # Create all tables
        print("📋 Creating database tables...")
        db.create_all()
        print("✅ Database tables created successfully!")
        
        # Create default admin user
        print("\n👤 Creating default admin user...")
        create_admin_user()
        
        # Create default departments
        print("\n🏢 Creating default departments...")
        create_default_departments()
        
        print("\n✨ Database initialization complete!")
        print("\n" + "="*50)
        print("DEFAULT ADMIN CREDENTIALS:")
        print("="*50)
        print(f"Username: {app.config['ADMIN_USERNAME']}")
        print(f"Email: {app.config['ADMIN_EMAIL']}")
        print(f"Password: {app.config['ADMIN_PASSWORD']}")
        print("="*50)
        print("⚠️  IMPORTANT: Change the admin password after first login!")
        print("="*50 + "\n")


def create_admin_user():
    """
    Create the default admin user if it doesn't exist
    """
    # Check if admin already exists
    existing_admin = User.query.filter_by(username=app.config['ADMIN_USERNAME']).first()
    
    if existing_admin:
        print(f"⚠️  Admin user '{app.config['ADMIN_USERNAME']}' already exists. Skipping...")
        return
    
    # Create admin user
    admin = User(
        username=app.config['ADMIN_USERNAME'],
        email=app.config['ADMIN_EMAIL'],
        password=generate_password_hash(app.config['ADMIN_PASSWORD']),
        role='admin',
        full_name=app.config['ADMIN_FULL_NAME'],
        phone='1234567890',
        address='Hospital Administration Office',
        registration_timestamp=datetime.utcnow(),
        is_active=True
    )
    
    db.session.add(admin)
    db.session.commit()
    
    print(f"✅ Admin user '{app.config['ADMIN_USERNAME']}' created successfully!")


def create_default_departments():
    """
    Create default medical departments/specializations
    """
    departments = [
        {
            'name': 'Cardiology',
            'description': 'Diagnosis and treatment of heart and cardiovascular system disorders'
        },
        {
            'name': 'Neurology',
            'description': 'Diagnosis and treatment of nervous system disorders'
        },
        {
            'name': 'Orthopedics',
            'description': 'Treatment of musculoskeletal system disorders, bones, joints, and muscles'
        },
        {
            'name': 'Pediatrics',
            'description': 'Medical care for infants, children, and adolescents'
        },
        {
            'name': 'Dermatology',
            'description': 'Diagnosis and treatment of skin, hair, and nail conditions'
        },
        {
            'name': 'General Medicine',
            'description': 'Primary healthcare and treatment of common medical conditions'
        },
        {
            'name': 'Gynecology',
            'description': 'Healthcare for women, focusing on reproductive system'
        },
        {
            'name': 'ENT (Otolaryngology)',
            'description': 'Treatment of ear, nose, and throat disorders'
        },
        {
            'name': 'Ophthalmology',
            'description': 'Diagnosis and treatment of eye and vision problems'
        },
        {
            'name': 'Psychiatry',
            'description': 'Diagnosis, treatment, and prevention of mental health disorders'
        }
    ]
    
    for dept_data in departments:
        # Check if department already exists
        existing_dept = Department.query.filter_by(name=dept_data['name']).first()
        if existing_dept:
            print(f"  ⚠️  Department '{dept_data['name']}' already exists. Skipping...")
            continue
        
        department = Department(
            name=dept_data['name'],
            description=dept_data['description'],
            created_at=datetime.utcnow()
        )
        db.session.add(department)
        print(f"  ✅ Created department: {dept_data['name']}")
    
    db.session.commit()
    print("✅ All default departments created successfully!")


def reset_database():
    """
    Reset database - drops all tables and recreates them
    WARNING: This will delete ALL data!
    """
    response = input("⚠️  WARNING: This will DELETE ALL DATA. Are you sure? (yes/no): ")
    if response.lower() != 'yes':
        print("❌ Database reset cancelled.")
        return
    
    with app.app_context():
        print("🗑️  Dropping all tables...")
        db.drop_all()
        print("✅ All tables dropped.")
        
        print("📋 Creating fresh tables...")
        db.create_all()
        print("✅ Fresh tables created.")
        
        create_admin_user()
        create_default_departments()
        
        print("✅ Database reset complete!")


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'reset':
        reset_database()
    else:
        init_database()