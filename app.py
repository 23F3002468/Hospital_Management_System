from flask import Flask, jsonify, render_template, redirect, url_for
from flask_login import LoginManager, current_user, login_required
from flask_cors import CORS
import os

from models import db, User
from config import config
from cache import cache

# The single Celery instance lives in celery_app.py - see the note there.
# Nothing in the web process constructs one.

# Initialize extensions
login_manager = LoginManager()

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

    # Behind a reverse proxy (nginx, Caddy, a platform router), the app sees the
    # proxy's address and http:// unless it reads the X-Forwarded-* headers. It
    # needs the real scheme to build correct URLs and to know the connection was
    # TLS. Those headers are trivially spoofed by a direct client, so this is
    # opt-in: set TRUST_PROXY_HOPS to the number of proxies actually in front of
    # the app, and leave it unset when nothing is.
    proxy_hops = int(os.environ.get('TRUST_PROXY_HOPS', '0'))
    if proxy_hops > 0:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=proxy_hops, x_proto=proxy_hops, x_host=proxy_hops, x_prefix=proxy_hops,
        )

    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    cache.init_app(app, config={
        'CACHE_TYPE': app.config['CACHE_TYPE'],
        'CACHE_REDIS_URL': app.config['CACHE_REDIS_URL'],
        'CACHE_DEFAULT_TIMEOUT': app.config['CACHE_DEFAULT_TIMEOUT'],
    })
    CORS(app)  # Enable CORS for Vue.js frontend

    # Configure Flask-Login
    login_manager.login_view = 'index'
    login_manager.login_message = 'Please log in to access this page.'
    
    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID for Flask-Login.

        Returns None for deactivated users so that blacklisting takes effect
        immediately instead of waiting for the session cookie to expire.
        """
        user = db.session.get(User, int(user_id))
        if user is None or not user.is_active:
            return None
        return user
    
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

    # ------------------------------------------------------------------
    # HTML ROUTES (serve the Vue.js pages)
    #
    # These must be registered inside the factory. login_manager.login_view
    # points at 'index', so an app built without them cannot resolve the
    # login redirect and raises BuildError on the first anonymous request.
    # ------------------------------------------------------------------

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

    return app


# Module-level instance for `flask run` and `python app.py`.
app = create_app()


if __name__ == '__main__':
    # Development server only.
    #
    # Never deploy by running this file. `debug` used to be hardcoded to True
    # here, which serves the Werkzeug debugger - an interactive console that
    # executes Python on the server - and the old host of '0.0.0.0' offered it
    # to every machine on the network. Debug now follows the loaded config, so
    # ProductionConfig cannot switch it on, and the server binds to localhost
    # unless you deliberately widen it.
    config_name = os.environ.get('FLASK_ENV', 'default')
    if config_name == 'production':
        raise SystemExit(
            'Refusing to start the development server with FLASK_ENV=production.\n'
            'Serve the app through a WSGI server instead:\n'
            '    waitress-serve --host=0.0.0.0 --port=8000 app:app     (Windows)\n'
            '    gunicorn --bind 0.0.0.0:8000 app:app                  (Linux/macOS)'
        )

    # Set FLASK_RUN_HOST=0.0.0.0 to reach the dev server from another device.
    # Only do that on a network you trust - with debug on it is a remote shell.
    host = os.environ.get('FLASK_RUN_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_RUN_PORT', '5000'))

    app.run(debug=app.config['DEBUG'], host=host, port=port)