from flask import Flask, jsonify, render_template, redirect, url_for
from flask_login import LoginManager, current_user, login_required
from flask_cors import CORS
from flask_caching import Cache
from celery import Celery
import os

from models import db, User
from config import config

# Initialize extensions
login_manager = LoginManager()
cache = Cache()
celery = Celery(__name__)


def create_app(config_name=None):
    """
    Application factory pattern for creating Flask app
    """
    if config_name is None:
        # Default to development if no environment is set
        config_name = os.environ.get('FLASK_ENV', 'default')
    
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    cache.init_app(app)
    CORS(app)  # Enable CORS for Vue.js frontend
    
    # Configure Celery
    celery.conf.update(app.config)
    
    # Configure Flask-Login
    login_manager.login_view = 'index'
    login_manager.login_message = 'Please log in to access this page.'
    
    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID for Flask-Login"""
        return User.query.get(int(user_id))
    
    # Register blueprints
    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.doctor import doctor_bp
    from routes.patient import patient_bp
    
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(doctor_bp, url_prefix='/api/doctor')
    app.register_blueprint(patient_bp, url_prefix='/api/patient')
    
    # Health check endpoint
    @app.route('/api/health')
    def health_check():
        """Simple health check endpoint"""
        return jsonify({
            'status': 'healthy',
            'message': 'Hospital Management System API is running'
        }), 200
    
    # API info endpoint
    @app.route('/api')
    def api_info():
        """API information endpoint"""
        return jsonify({
            'message': 'Welcome to Hospital Management System API',
            'version': '1.0',
            'endpoints': {
                'health': '/api/health',
                'auth': '/api/auth',
                'admin': '/api/admin',
                'doctor': '/api/doctor',
                'patient': '/api/patient'
            }
        }), 200
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Not found'}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500
    
    @app.errorhandler(403)
    def forbidden(error):
        return jsonify({'error': 'Forbidden - Insufficient permissions'}), 403
    
    @app.errorhandler(401)
    def unauthorized(error):
        return jsonify({'error': 'Unauthorized - Please login'}), 401
    
    return app


def make_celery(app):
    """
    Create Celery instance with Flask app context
    """
    celery = Celery(
        app.import_name,
        backend=app.config['CELERY_RESULT_BACKEND'],
        broker=app.config['CELERY_BROKER_URL']
    )
    celery.conf.update(app.config)
    
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    
    celery.Task = ContextTask
    return celery


# Create app instance
app = create_app()

# Create Celery instance
celery = make_celery(app)


# ============================================================================
# HTML ROUTES (Serve Vue.js pages)
# ============================================================================

@app.route('/')
def index():
    """Landing page / Login"""
    if current_user.is_authenticated:
        # Redirect to appropriate dashboard
        if current_user.is_admin:
            return redirect('/admin/dashboard')
        elif current_user.is_doctor:
            return redirect('/doctor/dashboard')
        elif current_user.is_patient:
            return redirect('/patient/dashboard')
    return render_template('index.html')


@app.route('/register')
def register_page():
    """Registration page"""
    return render_template('register.html')


@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    """Admin dashboard page"""
    if not current_user.is_admin:
        return redirect('/')
    return render_template('admin_dashboard.html')


@app.route('/doctor/dashboard')
@login_required
def doctor_dashboard():
    """Doctor dashboard page"""
    if not current_user.is_doctor:
        return redirect('/')
    return render_template('doctor_dashboard.html')


@app.route('/patient/dashboard')
@login_required
def patient_dashboard():
    """Patient dashboard page"""
    if not current_user.is_patient:
        return redirect('/')
    return render_template('patient_dashboard.html')

@app.route('/patient/history')
@login_required
def patient_history():
    """Patient treatment history page"""
    if not current_user.is_patient:
        return redirect('/')
    return render_template('patient_history.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)