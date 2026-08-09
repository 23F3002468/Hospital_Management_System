import os
from datetime import timedelta

from dotenv import load_dotenv

# Load environment variables from .env (if present)
load_dotenv()


class Config:
    """Base configuration class"""
    
    # Basic Flask config
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database configuration
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(BASE_DIR, 'hospital.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Redis configuration
    REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    
    # Celery configuration
    broker_url = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    result_backend = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    accept_content = ['json']
    task_serializer = 'json'
    result_serializer = 'json'
    timezone = 'Asia/Kolkata'
    enable_utc = True
    
    # Cache configuration
    CACHE_TYPE = 'RedisCache'
    CACHE_REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    CACHE_DEFAULT_TIMEOUT = 300  # 5 minutes default cache timeout
    
    # Flask-Login configuration
    REMEMBER_COOKIE_DURATION = timedelta(days=7)
    
    # Pagination
    ITEMS_PER_PAGE = 10
    
    # File upload (for future use if needed)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Email configuration (Mailtrap sandbox in development)
    # Credentials come from .env - see .env.example
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'sandbox.smtp.mailtrap.io'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 2525)
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or 'HMS <noreply@hospital.com>'
    
    # Google Chat Webhook (for daily reminders)
    GOOGLE_CHAT_WEBHOOK_URL = os.environ.get('GOOGLE_CHAT_WEBHOOK_URL')
    
    # Admin default credentials (will be created on first run)
    ADMIN_USERNAME = 'admin'
    ADMIN_EMAIL = 'admin@hospital.com'
    ADMIN_PASSWORD = 'admin123'  # Change this in production!
    ADMIN_FULL_NAME = 'System Administrator'


class DevelopmentConfig(Config):
    """Development environment configuration"""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Production environment configuration"""
    DEBUG = False
    TESTING = False


class TestingConfig(Config):
    """Testing environment configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'  # In-memory database for tests
    WTF_CSRF_ENABLED = False
    CACHE_TYPE = 'SimpleCache'  # In-process cache so tests don't need a Redis server


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}