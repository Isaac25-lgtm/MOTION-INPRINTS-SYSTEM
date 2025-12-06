"""
Motion - Design, Print, Brand
Flask Backend Application

This module contains the main Flask application with:
- Database models (User, Order)
- User authentication (register, login, logout)
- Order management
- User dashboard
- Admin dashboard with analytics
"""

import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, render_template, redirect, url_for, flash, request, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash

from config import config

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()

# Configure login manager
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'


# =============================================================================
# DATABASE MODELS
# =============================================================================

class User(UserMixin, db.Model):
    """User model for authentication and order tracking"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationship to orders
    orders = db.relationship('Order', backref='user', lazy='dynamic')
    
    def set_password(self, password):
        """Hash and set the user's password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verify the password against the hash"""
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.email}>'


class Order(db.Model):
    """Order model for tracking client requests"""
    __tablename__ = 'orders'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Nullable for guest orders
    
    # Contact info (for guest orders or additional contact)
    guest_name = db.Column(db.String(100))
    guest_email = db.Column(db.String(120))
    
    # Order details
    service_type = db.Column(db.String(50), nullable=False)  # e.g., 'design', 'printing', 'branding', 'signage', 'general'
    details = db.Column(db.Text, nullable=False)
    
    # Status tracking
    status = db.Column(db.String(20), default='New')  # New, In Progress, Completed, Cancelled
    
    # Timestamps
    date_created = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    date_updated = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Admin notes (internal use)
    admin_notes = db.Column(db.Text)
    
    def __repr__(self):
        return f'<Order {self.id} - {self.service_type}>'
    
    @property
    def customer_name(self):
        """Return customer name (from user or guest info)"""
        if self.user:
            return self.user.name
        return self.guest_name or 'Guest'
    
    @property
    def customer_email(self):
        """Return customer email (from user or guest info)"""
        if self.user:
            return self.user.email
        return self.guest_email or 'N/A'


# Flask-Login user loader
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# =============================================================================
# DECORATORS
# =============================================================================

def admin_required(f):
    """Decorator to require admin access for a route"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


# =============================================================================
# APPLICATION FACTORY
# =============================================================================

def create_app(config_name=None):
    """Application factory for creating the Flask app"""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')
    
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    
    # Create database tables
    with app.app_context():
        db.create_all()
        # Create default admin user if none exists
        create_default_admin()
    
    # Register routes
    register_routes(app)
    register_error_handlers(app)
    
    return app


def create_default_admin():
    """Create a default admin user if no admin exists"""
    admin = User.query.filter_by(is_admin=True).first()
    if not admin:
        admin = User(
            name='Admin',
            email='admin@motion.co.ug',
            is_admin=True
        )
        admin.set_password('admin123')  # Change this in production!
        db.session.add(admin)
        db.session.commit()
        print('Default admin created: admin@motion.co.ug / admin123')


# =============================================================================
# ROUTES
# =============================================================================

def register_routes(app):
    """Register all application routes"""
    
    # -------------------------------------------------------------------------
    # PUBLIC ROUTES
    # -------------------------------------------------------------------------
    
    @app.route('/')
    def home():
        """Homepage with all sections"""
        return render_template('index.html')
    
    # -------------------------------------------------------------------------
    # AUTHENTICATION ROUTES
    # -------------------------------------------------------------------------
    
    @app.route('/register', methods=['GET', 'POST'])
    def register():
        """User registration"""
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            # Validation
            errors = []
            if not name:
                errors.append('Name is required.')
            if not email:
                errors.append('Email is required.')
            if not password:
                errors.append('Password is required.')
            if len(password) < 6:
                errors.append('Password must be at least 6 characters.')
            if password != confirm_password:
                errors.append('Passwords do not match.')
            
            # Check if email already exists
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                errors.append('Email is already registered.')
            
            if errors:
                for error in errors:
                    flash(error, 'danger')
                return render_template('register.html', name=name, email=email)
            
            # Create new user
            user = User(name=name, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            
            # Log in the new user
            login_user(user)
            flash('Registration successful! Welcome to Motion.', 'success')
            return redirect(url_for('dashboard'))
        
        return render_template('register.html')
    
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """User login"""
        if current_user.is_authenticated:
            # Redirect to appropriate dashboard based on user type
            if current_user.is_admin:
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('dashboard'))
        
        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            remember = request.form.get('remember') == 'on'  # Checkbox returns 'on' when checked
            
            user = User.query.filter_by(email=email).first()
            
            if user and user.check_password(password):
                login_user(user, remember=remember)
                flash('Login successful!', 'success')
                
                # Redirect to next page or appropriate dashboard
                next_page = request.args.get('next')
                if next_page:
                    return redirect(next_page)
                if user.is_admin:
                    return redirect(url_for('admin_dashboard'))
                return redirect(url_for('dashboard'))
            
            flash('Invalid email or password.', 'danger')
        
        return render_template('login.html')
    
    @app.route('/logout')
    @login_required
    def logout():
        """User logout"""
        logout_user()
        flash('You have been logged out.', 'info')
        return redirect(url_for('home'))
    
    # -------------------------------------------------------------------------
    # ORDER ROUTES
    # -------------------------------------------------------------------------
    
    @app.route('/order', methods=['POST'])
    def submit_order():
        """Handle order/contact form submission"""
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        service_type = request.form.get('service', 'general')
        details = request.form.get('message', '').strip()
        
        # Validation
        if not name or not email or not details:
            flash('Please fill in all required fields.', 'danger')
            return redirect(url_for('home') + '#contact')
        
        # Create order
        order = Order(
            service_type=service_type,
            details=details
        )
        
        # Link to user if logged in, otherwise store guest info
        if current_user.is_authenticated:
            order.user_id = current_user.id
        else:
            order.guest_name = name
            order.guest_email = email
        
        db.session.add(order)
        db.session.commit()
        
        # Send email notification (non-blocking, with error handling)
        try:
            send_order_notification(order, name, email)
        except Exception as e:
            app.logger.error(f'Failed to send order notification: {e}')
        
        flash('Thank you! Your request has been received. We will contact you shortly.', 'success')
        
        # Redirect based on login status
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        return redirect(url_for('home') + '#contact')
    
    # -------------------------------------------------------------------------
    # USER DASHBOARD ROUTES
    # -------------------------------------------------------------------------
    
    @app.route('/dashboard')
    @login_required
    def dashboard():
        """User dashboard showing their orders"""
        orders = Order.query.filter_by(user_id=current_user.id)\
            .order_by(Order.date_created.desc()).all()
        return render_template('dashboard.html', orders=orders)
    
    @app.route('/dashboard/order/<int:order_id>')
    @login_required
    def view_order(order_id):
        """View a specific order (user view)"""
        order = Order.query.get_or_404(order_id)
        
        # Ensure user owns this order
        if order.user_id != current_user.id:
            abort(403)
        
        return render_template('order_detail.html', order=order)
    
    # -------------------------------------------------------------------------
    # ADMIN ROUTES
    # -------------------------------------------------------------------------
    
    @app.route('/admin')
    @admin_required
    def admin_dashboard():
        """Admin analytics dashboard"""
        # Get statistics
        total_orders = Order.query.count()
        total_users = User.query.filter_by(is_admin=False).count()
        
        # Orders by status
        new_orders = Order.query.filter_by(status='New').count()
        in_progress_orders = Order.query.filter_by(status='In Progress').count()
        completed_orders = Order.query.filter_by(status='Completed').count()
        
        # Orders in last 7 days
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        orders_this_week = Order.query.filter(Order.date_created >= week_ago).count()
        
        # Recent orders (last 5)
        recent_orders = Order.query.order_by(Order.date_created.desc()).limit(5).all()
        
        # Daily orders for chart (last 7 days)
        daily_orders = []
        for i in range(6, -1, -1):
            day = datetime.now(timezone.utc).date() - timedelta(days=i)
            day_start = datetime.combine(day, datetime.min.time())
            day_end = datetime.combine(day, datetime.max.time())
            count = Order.query.filter(
                Order.date_created >= day_start,
                Order.date_created <= day_end
            ).count()
            daily_orders.append({
                'date': day.strftime('%a'),  # e.g., 'Mon', 'Tue'
                'count': count
            })
        
        return render_template('admin/dashboard.html',
            total_orders=total_orders,
            total_users=total_users,
            new_orders=new_orders,
            in_progress_orders=in_progress_orders,
            completed_orders=completed_orders,
            orders_this_week=orders_this_week,
            recent_orders=recent_orders,
            daily_orders=daily_orders
        )
    
    @app.route('/admin/orders')
    @admin_required
    def admin_orders():
        """Admin view of all orders"""
        # Get filter parameters
        status_filter = request.args.get('status', '')
        
        # Build query
        query = Order.query.order_by(Order.date_created.desc())
        if status_filter:
            query = query.filter_by(status=status_filter)
        
        orders = query.all()
        return render_template('admin/orders.html', orders=orders, current_status=status_filter)
    
    @app.route('/admin/orders/<int:order_id>', methods=['GET', 'POST'])
    @admin_required
    def admin_order_detail(order_id):
        """Admin view/edit a specific order"""
        order = Order.query.get_or_404(order_id)
        
        if request.method == 'POST':
            # Update order status
            new_status = request.form.get('status')
            admin_notes = request.form.get('admin_notes', '')
            
            if new_status in ['New', 'In Progress', 'Completed', 'Cancelled']:
                order.status = new_status
                order.admin_notes = admin_notes
                db.session.commit()
                flash(f'Order #{order.id} updated successfully.', 'success')
            else:
                flash('Invalid status.', 'danger')
            
            return redirect(url_for('admin_order_detail', order_id=order_id))
        
        return render_template('admin/order_detail.html', order=order)
    
    @app.route('/admin/users')
    @admin_required
    def admin_users():
        """Admin view of all users"""
        users = User.query.order_by(User.created_at.desc()).all()
        return render_template('admin/users.html', users=users)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def send_order_notification(order, customer_name, customer_email):
    """Send email notification for new order"""
    from flask import current_app
    
    # Only send if mail is configured
    if not current_app.config.get('MAIL_USERNAME'):
        current_app.logger.info('Mail not configured, skipping notification')
        return
    
    # Email to admin
    admin_msg = Message(
        subject=f'New Order #{order.id} from {customer_name}',
        recipients=[current_app.config['ADMIN_EMAIL']],
        body=f"""
New order received on Motion website.

Order ID: {order.id}
Customer: {customer_name}
Email: {customer_email}
Service: {order.service_type}

Details:
{order.details}

View in admin panel: {url_for('admin_order_detail', order_id=order.id, _external=True)}
        """
    )
    mail.send(admin_msg)
    
    # Confirmation email to customer
    customer_msg = Message(
        subject='Your Order Request - Motion',
        recipients=[customer_email],
        body=f"""
Dear {customer_name},

Thank you for your order request! We have received your inquiry and will get back to you shortly.

Order Reference: #{order.id}
Service: {order.service_type}

Your Details:
{order.details}

If you have any questions, feel free to contact us at 0782656721 or reply to this email.

Best regards,
Motion Team
        """
    )
    mail.send(customer_msg)


# =============================================================================
# ERROR HANDLERS
# =============================================================================

def register_error_handlers(app):
    """Register error handlers"""
    
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template('errors/403.html'), 403
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        app.logger.error(f'Server Error: {error}')
        return render_template('errors/500.html'), 500


# =============================================================================
# MAIN
# =============================================================================

# Create the application instance
app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
