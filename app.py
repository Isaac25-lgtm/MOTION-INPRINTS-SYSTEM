"""
Motion - Design, Print, Brand
Flask Backend Application with E-commerce

This module contains the main Flask application with:
- Database models (User, Order, Product, Category, CartItem, QuoteRequest)
- User authentication (register, login, logout)
- Product catalog and shopping cart
- Quote request system with file uploads
- Order management
- User dashboard with order tracking
- Admin dashboard with analytics and quote management
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from decimal import Decimal

from flask import Flask, render_template, redirect, url_for, flash, request, abort, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from config import config

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()

# Configure login manager
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

# File upload configuration
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'ai', 'psd', 'eps', 'svg', 'doc', 'docx', 'zip'}
UPLOAD_FOLDER = 'uploads'

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


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
    phone = db.Column(db.String(20))
    company = db.Column(db.String(100))
    address = db.Column(db.Text)
    is_admin = db.Column(db.Boolean, default=False)
    customer_tier = db.Column(db.String(20), default='New')  # New, Bronze, Silver, Gold, VIP
    total_orders = db.Column(db.Integer, default=0)
    total_spent = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    orders = db.relationship('Order', backref='user', lazy='dynamic')
    cart_items = db.relationship('CartItem', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    quote_requests = db.relationship('QuoteRequest', backref='user', lazy='dynamic')
    
    def set_password(self, password):
        """Hash and set the user's password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verify the password against the hash"""
        return check_password_hash(self.password_hash, password)
    
    def update_tier(self):
        """Update customer tier based on order count"""
        if self.total_orders >= 50:
            self.customer_tier = 'VIP'
        elif self.total_orders >= 30:
            self.customer_tier = 'Gold'
        elif self.total_orders >= 15:
            self.customer_tier = 'Silver'
        elif self.total_orders >= 5:
            self.customer_tier = 'Bronze'
        else:
            self.customer_tier = 'New'
    
    @property
    def discount_percent(self):
        """Get discount percentage based on tier"""
        discounts = {'New': 0, 'Bronze': 5, 'Silver': 10, 'Gold': 15, 'VIP': 20}
        return discounts.get(self.customer_tier, 0)
    
    def __repr__(self):
        return f'<User {self.email}>'


class Category(db.Model):
    """Product category model"""
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(50))  # Font Awesome icon class
    image = db.Column(db.String(255))
    display_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    products = db.relationship('Product', backref='category', lazy='dynamic')
    
    def __repr__(self):
        return f'<Category {self.name}>'


class Product(db.Model):
    """Product model for shop items"""
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    image = db.Column(db.String(255))
    base_price = db.Column(db.Float, default=0.0)  # Starting price for quotes
    min_quantity = db.Column(db.Integer, default=1)
    is_active = db.Column(db.Boolean, default=True)
    requires_design = db.Column(db.Boolean, default=True)  # If customer needs to upload design
    
    # Product options stored as JSON-like string
    # Format: size options, material options, etc.
    size_options = db.Column(db.Text)  # e.g., "A4,A5,A6,Custom"
    material_options = db.Column(db.Text)  # e.g., "Glossy,Matte,Silk"
    color_options = db.Column(db.Text)  # e.g., "Full Color,Black & White"
    finishing_options = db.Column(db.Text)  # e.g., "Laminated,UV Coated,None"
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    def get_options(self, option_type):
        """Get options as list"""
        option_str = getattr(self, f'{option_type}_options', '')
        if option_str:
            return [opt.strip() for opt in option_str.split(',') if opt.strip()]
        return []
    
    def __repr__(self):
        return f'<Product {self.name}>'


class CartItem(db.Model):
    """Shopping cart item model"""
    __tablename__ = 'cart_items'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    
    # Selected options
    size = db.Column(db.String(50))
    material = db.Column(db.String(50))
    color = db.Column(db.String(50))
    finishing = db.Column(db.String(50))
    custom_size = db.Column(db.String(100))  # For custom dimensions
    
    # Design file
    design_file = db.Column(db.String(255))  # Uploaded file path
    design_notes = db.Column(db.Text)  # Special instructions
    
    added_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationship to product
    product = db.relationship('Product', backref='cart_items')
    
    def __repr__(self):
        return f'<CartItem {self.product.name} x{self.quantity}>'


class QuoteRequest(db.Model):
    """Quote request model for pricing requests"""
    __tablename__ = 'quote_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Quote details stored as JSON-like text
    items_json = db.Column(db.Text, nullable=False)  # Serialized cart items
    
    # Status: Pending, Quoted, Accepted, Rejected, Expired, Converted
    status = db.Column(db.String(20), default='Pending')
    
    # Quote response from admin
    quoted_price = db.Column(db.Float)
    discount_applied = db.Column(db.Float, default=0.0)
    delivery_fee = db.Column(db.Float, default=0.0)
    total_price = db.Column(db.Float)
    admin_notes = db.Column(db.Text)
    valid_until = db.Column(db.DateTime)
    
    # Customer response
    customer_notes = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    quoted_at = db.Column(db.DateTime)
    responded_at = db.Column(db.DateTime)
    
    # Link to order if converted
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'))
    
    def __repr__(self):
        return f'<QuoteRequest {self.id} - {self.status}>'


class Order(db.Model):
    """Order model for tracking client requests"""
    __tablename__ = 'orders'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    quote_request_id = db.Column(db.Integer, db.ForeignKey('quote_requests.id'))
    
    # Contact info (for guest orders or additional contact)
    guest_name = db.Column(db.String(100))
    guest_email = db.Column(db.String(120))
    guest_phone = db.Column(db.String(20))
    
    # Order details
    service_type = db.Column(db.String(50), nullable=False)
    details = db.Column(db.Text, nullable=False)
    items_json = db.Column(db.Text)  # For e-commerce orders
    
    # Pricing
    subtotal = db.Column(db.Float, default=0.0)
    discount = db.Column(db.Float, default=0.0)
    delivery_fee = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)
    
    # Status tracking
    status = db.Column(db.String(20), default='New')
    
    # Timestamps
    date_created = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    date_updated = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    estimated_completion = db.Column(db.DateTime)
    
    # Admin notes (internal use)
    admin_notes = db.Column(db.Text)
    
    # Design files
    design_files = db.Column(db.Text)  # Comma-separated file paths
    
    # Relationship to quote
    quote_request = db.relationship('QuoteRequest', backref='order', foreign_keys=[quote_request_id])
    
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
    
    @property
    def customer_phone(self):
        """Return customer phone"""
        if self.user and self.user.phone:
            return self.user.phone
        return self.guest_phone or 'N/A'


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
    import json
    
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')
    
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Add custom Jinja filters
    @app.template_filter('from_json')
    def from_json_filter(value):
        try:
            return json.loads(value) if value else []
        except:
            return []
    
    # Configure uploads
    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, UPLOAD_FOLDER)
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size
    
    # Create upload directory if it doesn't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    
    # Create database tables
    with app.app_context():
        db.create_all()
        create_default_admin()
        create_default_categories()
        create_sample_products()
    
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
            is_admin=True,
            phone='0787984135'
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print('Default admin created: admin@motion.co.ug / admin123')


def create_default_categories():
    """Create default product categories"""
    if Category.query.count() == 0:
        categories = [
            {'name': 'Business Cards', 'slug': 'business-cards', 'icon': 'fas fa-id-card', 'description': 'Professional business cards in various styles and finishes', 'display_order': 1, 'image': 'digital printing.jpg'},
            {'name': 'Flyers & Brochures', 'slug': 'flyers-brochures', 'icon': 'fas fa-file-alt', 'description': 'Marketing flyers and brochures for your business', 'display_order': 2, 'image': 'digital printing.jpg'},
            {'name': 'Banners & Posters', 'slug': 'banners-posters', 'icon': 'fas fa-scroll', 'description': 'Large format printing for events and advertising', 'display_order': 3, 'image': 'offsetprinting.webp'},
            {'name': 'T-Shirts & Apparel', 'slug': 't-shirts-apparel', 'icon': 'fas fa-tshirt', 'description': 'Custom printed clothing and merchandise', 'display_order': 4, 'image': 'sublimationprinting.jpg'},
            {'name': 'Signage', 'slug': 'signage', 'icon': 'fas fa-sign', 'description': '3D signs, billboards, and indoor/outdoor signage', 'display_order': 5, 'image': '3Dsigns.avif'},
            {'name': 'Promotional Items', 'slug': 'promotional-items', 'icon': 'fas fa-gift', 'description': 'Branded mugs, pens, bags, and corporate gifts', 'display_order': 6, 'image': 'promotionalitems.png'},
            {'name': 'Stationery', 'slug': 'stationery', 'icon': 'fas fa-envelope', 'description': 'Letterheads, envelopes, and office stationery', 'display_order': 7, 'image': 'digital printing.jpg'},
            {'name': 'Custom Projects', 'slug': 'custom-projects', 'icon': 'fas fa-magic', 'description': 'Special requests and custom design projects', 'display_order': 8, 'image': 'graphicdesign.webp'},
        ]
        for cat_data in categories:
            category = Category(**cat_data)
            db.session.add(category)
        db.session.commit()
        print('Default categories created')


def create_sample_products():
    """Create sample products for the shop"""
    if Product.query.count() == 0:
        # Get categories
        cards = Category.query.filter_by(slug='business-cards').first()
        flyers = Category.query.filter_by(slug='flyers-brochures').first()
        banners = Category.query.filter_by(slug='banners-posters').first()
        tshirts = Category.query.filter_by(slug='t-shirts-apparel').first()
        signage = Category.query.filter_by(slug='signage').first()
        promo = Category.query.filter_by(slug='promotional-items').first()
        
        products = [
            # Business Cards
            {'category_id': cards.id, 'name': 'Standard Business Cards', 'slug': 'standard-business-cards', 
             'description': 'Professional business cards on premium cardstock', 'base_price': 50000,
             'min_quantity': 100, 'size_options': '90x50mm,85x55mm,Custom', 
             'material_options': '300gsm,350gsm,400gsm', 'finishing_options': 'Matte,Glossy,Spot UV,None'},
            {'category_id': cards.id, 'name': 'Premium Business Cards', 'slug': 'premium-business-cards',
             'description': 'Luxury business cards with special finishes', 'base_price': 100000,
             'min_quantity': 50, 'size_options': '90x50mm,85x55mm,Custom',
             'material_options': 'Textured,Metallic,Transparent', 'finishing_options': 'Foil Stamping,Embossed,Die-Cut'},
            
            # Flyers
            {'category_id': flyers.id, 'name': 'A5 Flyers', 'slug': 'a5-flyers',
             'description': 'Full color flyers for marketing and events', 'base_price': 100000,
             'min_quantity': 100, 'size_options': 'A5,A6,DL',
             'material_options': '130gsm,170gsm,250gsm', 'finishing_options': 'Matte,Glossy,None'},
            {'category_id': flyers.id, 'name': 'Brochures', 'slug': 'brochures',
             'description': 'Folded brochures for detailed information', 'base_price': 200000,
             'min_quantity': 50, 'size_options': 'A4 Bi-fold,A4 Tri-fold,A3 Bi-fold',
             'material_options': '130gsm,170gsm,250gsm', 'finishing_options': 'Matte,Glossy,None'},
            
            # Banners
            {'category_id': banners.id, 'name': 'Roll-Up Banner', 'slug': 'roll-up-banner',
             'description': 'Portable roll-up banners with stand', 'base_price': 150000,
             'min_quantity': 1, 'size_options': '85x200cm,100x200cm,120x200cm',
             'material_options': 'Standard,Premium', 'finishing_options': 'With Stand,Banner Only'},
            {'category_id': banners.id, 'name': 'Vinyl Banner', 'slug': 'vinyl-banner',
             'description': 'Outdoor vinyl banners with grommets', 'base_price': 80000,
             'min_quantity': 1, 'size_options': '1x2m,2x3m,3x4m,Custom',
             'material_options': 'Standard Vinyl,Heavy Duty', 'finishing_options': 'Grommets,Pole Pockets,None'},
            
            # T-Shirts
            {'category_id': tshirts.id, 'name': 'Printed T-Shirts', 'slug': 'printed-t-shirts',
             'description': 'Custom printed t-shirts for teams and events', 'base_price': 25000,
             'min_quantity': 10, 'size_options': 'S,M,L,XL,XXL',
             'material_options': 'Cotton,Polyester,Blend', 'color_options': 'White,Black,Navy,Red,Custom'},
            {'category_id': tshirts.id, 'name': 'Polo Shirts', 'slug': 'polo-shirts',
             'description': 'Embroidered or printed polo shirts', 'base_price': 45000,
             'min_quantity': 5, 'size_options': 'S,M,L,XL,XXL',
             'material_options': 'Cotton Pique,Performance', 'color_options': 'White,Black,Navy,Custom'},
            
            # Signage
            {'category_id': signage.id, 'name': '3D Letter Signs', 'slug': '3d-letter-signs',
             'description': 'Custom 3D letters for storefronts', 'base_price': 500000,
             'min_quantity': 1, 'size_options': 'Small (30cm),Medium (50cm),Large (100cm),Custom',
             'material_options': 'Acrylic,Metal,PVC', 'finishing_options': 'LED Lit,Non-Lit,Backlit'},
            {'category_id': signage.id, 'name': 'Vehicle Branding', 'slug': 'vehicle-branding',
             'description': 'Full or partial vehicle wraps and graphics', 'base_price': 800000,
             'min_quantity': 1, 'size_options': 'Partial Wrap,Full Wrap,Decals Only',
             'material_options': 'Cast Vinyl,Calendered Vinyl', 'finishing_options': 'Matte,Glossy,Chrome'},
            
            # Promotional
            {'category_id': promo.id, 'name': 'Branded Mugs', 'slug': 'branded-mugs',
             'description': 'Custom printed ceramic mugs', 'base_price': 15000,
             'min_quantity': 20, 'size_options': '11oz Standard,15oz Large',
             'material_options': 'Ceramic,Magic (Color Changing)', 'color_options': 'White,Black,Custom'},
            {'category_id': promo.id, 'name': 'Branded Pens', 'slug': 'branded-pens',
             'description': 'Custom printed pens with your logo', 'base_price': 2000,
             'min_quantity': 100, 'size_options': 'Standard,Executive',
             'material_options': 'Plastic,Metal', 'color_options': 'Blue,Black,Red,Custom'},
        ]
        
        for prod_data in products:
            product = Product(**prod_data)
            db.session.add(product)
        db.session.commit()
        print('Sample products created')


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
            phone = request.form.get('phone', '').strip()
            company = request.form.get('company', '').strip()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            
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
            
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                errors.append('Email is already registered.')
            
            if errors:
                for error in errors:
                    flash(error, 'danger')
                return render_template('register.html', name=name, email=email, phone=phone, company=company)
            
            user = User(name=name, email=email, phone=phone, company=company)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            
            login_user(user)
            flash('Registration successful! Welcome to Motion.', 'success')
            return redirect(url_for('dashboard'))
        
        return render_template('register.html')
    
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """User login"""
        if current_user.is_authenticated:
            if current_user.is_admin:
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('dashboard'))
        
        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            remember = request.form.get('remember') == 'on'
            
            user = User.query.filter_by(email=email).first()
            
            if user and user.check_password(password):
                login_user(user, remember=remember)
                flash('Login successful!', 'success')
                
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
    # SHOP / CATALOG ROUTES
    # -------------------------------------------------------------------------
    
    @app.route('/shop')
    def shop():
        """Product catalog page"""
        categories = Category.query.filter_by(is_active=True).order_by(Category.display_order).all()
        return render_template('shop/catalog.html', categories=categories)
    
    @app.route('/shop/category/<slug>')
    def shop_category(slug):
        """Products in a category"""
        category = Category.query.filter_by(slug=slug, is_active=True).first_or_404()
        products = Product.query.filter_by(category_id=category.id, is_active=True).all()
        return render_template('shop/category.html', category=category, products=products)
    
    @app.route('/shop/product/<slug>')
    def shop_product(slug):
        """Product detail page"""
        product = Product.query.filter_by(slug=slug, is_active=True).first_or_404()
        return render_template('shop/product.html', product=product)
    
    # -------------------------------------------------------------------------
    # CART ROUTES
    # -------------------------------------------------------------------------
    
    @app.route('/cart')
    @login_required
    def cart():
        """View shopping cart"""
        cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
        return render_template('shop/cart.html', cart_items=cart_items)
    
    @app.route('/cart/add/<int:product_id>', methods=['POST'])
    @login_required
    def add_to_cart(product_id):
        """Add item to cart"""
        product = Product.query.get_or_404(product_id)
        
        quantity = int(request.form.get('quantity', product.min_quantity))
        if quantity < product.min_quantity:
            flash(f'Minimum quantity is {product.min_quantity}', 'warning')
            quantity = product.min_quantity
        
        # Get selected options
        size = request.form.get('size', '')
        material = request.form.get('material', '')
        color = request.form.get('color', '')
        finishing = request.form.get('finishing', '')
        custom_size = request.form.get('custom_size', '')
        design_notes = request.form.get('design_notes', '')
        
        # Handle file upload
        design_file = None
        if 'design_file' in request.files:
            file = request.files['design_file']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4().hex}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                design_file = unique_filename
        
        # Create cart item
        cart_item = CartItem(
            user_id=current_user.id,
            product_id=product_id,
            quantity=quantity,
            size=size,
            material=material,
            color=color,
            finishing=finishing,
            custom_size=custom_size,
            design_file=design_file,
            design_notes=design_notes
        )
        db.session.add(cart_item)
        db.session.commit()
        
        flash(f'{product.name} added to cart!', 'success')
        return redirect(url_for('cart'))
    
    @app.route('/cart/update/<int:item_id>', methods=['POST'])
    @login_required
    def update_cart_item(item_id):
        """Update cart item quantity"""
        cart_item = CartItem.query.get_or_404(item_id)
        
        if cart_item.user_id != current_user.id:
            abort(403)
        
        quantity = int(request.form.get('quantity', 1))
        if quantity < cart_item.product.min_quantity:
            flash(f'Minimum quantity is {cart_item.product.min_quantity}', 'warning')
            quantity = cart_item.product.min_quantity
        
        cart_item.quantity = quantity
        db.session.commit()
        
        flash('Cart updated!', 'success')
        return redirect(url_for('cart'))
    
    @app.route('/cart/remove/<int:item_id>', methods=['POST'])
    @login_required
    def remove_from_cart(item_id):
        """Remove item from cart"""
        cart_item = CartItem.query.get_or_404(item_id)
        
        if cart_item.user_id != current_user.id:
            abort(403)
        
        # Delete uploaded file if exists
        if cart_item.design_file:
            try:
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], cart_item.design_file))
            except:
                pass
        
        db.session.delete(cart_item)
        db.session.commit()
        
        flash('Item removed from cart.', 'info')
        return redirect(url_for('cart'))
    
    # -------------------------------------------------------------------------
    # QUOTE REQUEST ROUTES
    # -------------------------------------------------------------------------
    
    @app.route('/cart/request-quote', methods=['POST'])
    @login_required
    def request_quote():
        """Submit cart for quote"""
        cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
        
        if not cart_items:
            flash('Your cart is empty.', 'warning')
            return redirect(url_for('shop'))
        
        # Serialize cart items
        import json
        items_data = []
        for item in cart_items:
            items_data.append({
                'product_id': item.product_id,
                'product_name': item.product.name,
                'quantity': item.quantity,
                'size': item.size,
                'material': item.material,
                'color': item.color,
                'finishing': item.finishing,
                'custom_size': item.custom_size,
                'design_file': item.design_file,
                'design_notes': item.design_notes,
                'base_price': item.product.base_price
            })
        
        customer_notes = request.form.get('notes', '')
        
        quote_request = QuoteRequest(
            user_id=current_user.id,
            items_json=json.dumps(items_data),
            customer_notes=customer_notes
        )
        db.session.add(quote_request)
        
        # Clear the cart
        for item in cart_items:
            db.session.delete(item)
        
        db.session.commit()
        
        flash('Quote request submitted! We will get back to you shortly.', 'success')
        return redirect(url_for('my_quotes'))
    
    @app.route('/my-quotes')
    @login_required
    def my_quotes():
        """View user's quote requests"""
        quotes = QuoteRequest.query.filter_by(user_id=current_user.id)\
            .order_by(QuoteRequest.created_at.desc()).all()
        return render_template('shop/my_quotes.html', quotes=quotes)
    
    @app.route('/quote/<int:quote_id>')
    @login_required
    def view_quote(quote_id):
        """View quote details"""
        quote = QuoteRequest.query.get_or_404(quote_id)
        
        if quote.user_id != current_user.id and not current_user.is_admin:
            abort(403)
        
        import json
        items = json.loads(quote.items_json)
        return render_template('shop/quote_detail.html', quote=quote, items=items)
    
    @app.route('/quote/<int:quote_id>/accept', methods=['POST'])
    @login_required
    def accept_quote(quote_id):
        """Accept a quote and convert to order"""
        quote = QuoteRequest.query.get_or_404(quote_id)
        
        if quote.user_id != current_user.id:
            abort(403)
        
        if quote.status != 'Quoted':
            flash('This quote cannot be accepted.', 'danger')
            return redirect(url_for('view_quote', quote_id=quote_id))
        
        # Check if quote is still valid
        if quote.valid_until and quote.valid_until < datetime.now(timezone.utc):
            quote.status = 'Expired'
            db.session.commit()
            flash('This quote has expired. Please request a new quote.', 'danger')
            return redirect(url_for('view_quote', quote_id=quote_id))
        
        # Create order from quote
        import json
        items = json.loads(quote.items_json)
        
        order = Order(
            user_id=current_user.id,
            quote_request_id=quote.id,
            service_type='Shop Order',
            details=f"Order from Quote #{quote.id}",
            items_json=quote.items_json,
            subtotal=quote.quoted_price,
            discount=quote.discount_applied,
            delivery_fee=quote.delivery_fee,
            total=quote.total_price,
            status='Confirmed'
        )
        
        # Collect design files
        design_files = [item.get('design_file') for item in items if item.get('design_file')]
        if design_files:
            order.design_files = ','.join(design_files)
        
        db.session.add(order)
        
        # Update quote status
        quote.status = 'Converted'
        quote.order_id = order.id
        quote.responded_at = datetime.now(timezone.utc)
        
        # Update user stats
        current_user.total_orders += 1
        current_user.total_spent += quote.total_price
        current_user.update_tier()
        
        db.session.commit()
        
        flash('Order confirmed! Thank you for your business.', 'success')
        return redirect(url_for('view_order', order_id=order.id))
    
    @app.route('/quote/<int:quote_id>/reject', methods=['POST'])
    @login_required
    def reject_quote(quote_id):
        """Reject a quote"""
        quote = QuoteRequest.query.get_or_404(quote_id)
        
        if quote.user_id != current_user.id:
            abort(403)
        
        if quote.status != 'Quoted':
            flash('This quote cannot be rejected.', 'danger')
            return redirect(url_for('view_quote', quote_id=quote_id))
        
        quote.status = 'Rejected'
        quote.responded_at = datetime.now(timezone.utc)
        quote.customer_notes = request.form.get('reason', '')
        db.session.commit()
        
        flash('Quote rejected.', 'info')
        return redirect(url_for('my_quotes'))
    
    # -------------------------------------------------------------------------
    # LEGACY ORDER ROUTES (Contact Form)
    # -------------------------------------------------------------------------
    
    @app.route('/order', methods=['POST'])
    def submit_order():
        """Handle order/contact form submission"""
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        service_type = request.form.get('service', 'general')
        details = request.form.get('message', '').strip()
        
        if not name or not email or not details:
            flash('Please fill in all required fields.', 'danger')
            return redirect(url_for('home') + '#contact')
        
        order = Order(
            service_type=service_type,
            details=details,
            guest_phone=phone
        )
        
        if current_user.is_authenticated:
            order.user_id = current_user.id
        else:
            order.guest_name = name
            order.guest_email = email
        
        db.session.add(order)
        db.session.commit()
        
        try:
            send_order_notification(order, name, email, phone)
        except Exception as e:
            app.logger.error(f'Failed to send order notification: {e}')
        
        flash('Thank you! Your request has been received. We will contact you shortly.', 'success')
        
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        return redirect(url_for('home') + '#contact')
    
    # -------------------------------------------------------------------------
    # USER DASHBOARD ROUTES
    # -------------------------------------------------------------------------
    
    @app.route('/dashboard')
    @login_required
    def dashboard():
        """User dashboard showing their orders and quotes"""
        orders = Order.query.filter_by(user_id=current_user.id)\
            .order_by(Order.date_created.desc()).limit(5).all()
        quotes = QuoteRequest.query.filter_by(user_id=current_user.id)\
            .order_by(QuoteRequest.created_at.desc()).limit(5).all()
        cart_count = CartItem.query.filter_by(user_id=current_user.id).count()
        return render_template('dashboard.html', orders=orders, quotes=quotes, cart_count=cart_count)
    
    @app.route('/dashboard/order/<int:order_id>')
    @login_required
    def view_order(order_id):
        """View a specific order (user view)"""
        order = Order.query.get_or_404(order_id)
        
        if order.user_id != current_user.id and not current_user.is_admin:
            abort(403)
        
        import json
        items = []
        if order.items_json:
            items = json.loads(order.items_json)
        
        return render_template('order_detail.html', order=order, items=items)
    
    @app.route('/dashboard/profile', methods=['GET', 'POST'])
    @login_required
    def profile():
        """User profile page"""
        if request.method == 'POST':
            current_user.name = request.form.get('name', '').strip()
            current_user.phone = request.form.get('phone', '').strip()
            current_user.company = request.form.get('company', '').strip()
            current_user.address = request.form.get('address', '').strip()
            db.session.commit()
            flash('Profile updated!', 'success')
            return redirect(url_for('profile'))
        
        return render_template('profile.html')
    
    # -------------------------------------------------------------------------
    # ADMIN ROUTES
    # -------------------------------------------------------------------------
    
    @app.route('/admin')
    @admin_required
    def admin_dashboard():
        """Admin analytics dashboard"""
        total_orders = Order.query.count()
        total_users = User.query.filter_by(is_admin=False).count()
        pending_quotes = QuoteRequest.query.filter_by(status='Pending').count()
        
        new_orders = Order.query.filter_by(status='New').count()
        in_progress_orders = Order.query.filter_by(status='In Progress').count()
        completed_orders = Order.query.filter_by(status='Completed').count()
        
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        orders_this_week = Order.query.filter(Order.date_created >= week_ago).count()
        
        recent_orders = Order.query.order_by(Order.date_created.desc()).limit(5).all()
        recent_quotes = QuoteRequest.query.filter_by(status='Pending')\
            .order_by(QuoteRequest.created_at.desc()).limit(5).all()
        
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
                'date': day.strftime('%a'),
                'count': count
            })
        
        return render_template('admin/dashboard.html',
            total_orders=total_orders,
            total_users=total_users,
            pending_quotes=pending_quotes,
            new_orders=new_orders,
            in_progress_orders=in_progress_orders,
            completed_orders=completed_orders,
            orders_this_week=orders_this_week,
            recent_orders=recent_orders,
            recent_quotes=recent_quotes,
            daily_orders=daily_orders
        )
    
    @app.route('/admin/orders')
    @admin_required
    def admin_orders():
        """Admin view of all orders"""
        status_filter = request.args.get('status', '')
        
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
            new_status = request.form.get('status')
            admin_notes = request.form.get('admin_notes', '')
            estimated_completion = request.form.get('estimated_completion')
            
            if new_status in ['New', 'Confirmed', 'In Progress', 'Completed', 'Cancelled']:
                order.status = new_status
                order.admin_notes = admin_notes
                if estimated_completion:
                    order.estimated_completion = datetime.strptime(estimated_completion, '%Y-%m-%d')
                db.session.commit()
                flash(f'Order #{order.id} updated successfully.', 'success')
            else:
                flash('Invalid status.', 'danger')
            
            return redirect(url_for('admin_order_detail', order_id=order_id))
        
        import json
        items = []
        if order.items_json:
            items = json.loads(order.items_json)
        
        return render_template('admin/order_detail.html', order=order, items=items)
    
    @app.route('/admin/quotes')
    @admin_required
    def admin_quotes():
        """Admin view of all quote requests"""
        status_filter = request.args.get('status', '')
        
        query = QuoteRequest.query.order_by(QuoteRequest.created_at.desc())
        if status_filter:
            query = query.filter_by(status=status_filter)
        
        quotes = query.all()
        return render_template('admin/quotes.html', quotes=quotes, current_status=status_filter)
    
    @app.route('/admin/quotes/<int:quote_id>', methods=['GET', 'POST'])
    @admin_required
    def admin_quote_detail(quote_id):
        """Admin view/respond to a quote request"""
        quote = QuoteRequest.query.get_or_404(quote_id)
        
        import json
        items = json.loads(quote.items_json)
        
        if request.method == 'POST':
            action = request.form.get('action')
            
            if action == 'send_quote':
                quoted_price = float(request.form.get('quoted_price', 0))
                discount_applied = float(request.form.get('discount_applied', 0))
                delivery_fee = float(request.form.get('delivery_fee', 0))
                admin_notes = request.form.get('admin_notes', '')
                valid_days = int(request.form.get('valid_days', 7))
                
                quote.quoted_price = quoted_price
                quote.discount_applied = discount_applied
                quote.delivery_fee = delivery_fee
                quote.total_price = quoted_price - discount_applied + delivery_fee
                quote.admin_notes = admin_notes
                quote.valid_until = datetime.now(timezone.utc) + timedelta(days=valid_days)
                quote.quoted_at = datetime.now(timezone.utc)
                quote.status = 'Quoted'
                
                db.session.commit()
                flash(f'Quote sent to {quote.user.name}!', 'success')
            
            return redirect(url_for('admin_quote_detail', quote_id=quote_id))
        
        # Calculate suggested price
        suggested_total = sum(item.get('base_price', 0) * item.get('quantity', 1) for item in items)
        user_discount = quote.user.discount_percent
        
        return render_template('admin/quote_detail.html', 
            quote=quote, 
            items=items,
            suggested_total=suggested_total,
            user_discount=user_discount
        )
    
    @app.route('/admin/users')
    @admin_required
    def admin_users():
        """Admin view of all users"""
        users = User.query.order_by(User.created_at.desc()).all()
        return render_template('admin/users.html', users=users)
    
    @app.route('/admin/products')
    @admin_required
    def admin_products():
        """Admin view of all products"""
        products = Product.query.order_by(Product.category_id, Product.name).all()
        categories = Category.query.order_by(Category.display_order).all()
        return render_template('admin/products.html', products=products, categories=categories)
    
    @app.route('/admin/products/add', methods=['GET', 'POST'])
    @admin_required
    def admin_add_product():
        """Add a new product"""
        categories = Category.query.order_by(Category.display_order).all()
        
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            slug = request.form.get('slug', '').strip().lower().replace(' ', '-')
            category_id = int(request.form.get('category_id'))
            description = request.form.get('description', '').strip()
            base_price = float(request.form.get('base_price', 0))
            min_quantity = int(request.form.get('min_quantity', 1))
            
            size_options = request.form.get('size_options', '').strip()
            material_options = request.form.get('material_options', '').strip()
            color_options = request.form.get('color_options', '').strip()
            finishing_options = request.form.get('finishing_options', '').strip()
            
            product = Product(
                name=name,
                slug=slug,
                category_id=category_id,
                description=description,
                base_price=base_price,
                min_quantity=min_quantity,
                size_options=size_options,
                material_options=material_options,
                color_options=color_options,
                finishing_options=finishing_options
            )
            db.session.add(product)
            db.session.commit()
            
            flash(f'Product "{name}" added!', 'success')
            return redirect(url_for('admin_products'))
        
        return render_template('admin/product_form.html', categories=categories, product=None)
    
    # -------------------------------------------------------------------------
    # FILE SERVING
    # -------------------------------------------------------------------------
    
    @app.route('/uploads/<filename>')
    @login_required
    def uploaded_file(filename):
        """Serve uploaded files (protected)"""
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def send_order_notification(order, customer_name, customer_email, customer_phone=None):
    """Send email notification for new order"""
    from flask import current_app
    
    if not current_app.config.get('MAIL_USERNAME'):
        current_app.logger.info('Mail not configured, skipping notification')
        return
    
    admin_msg = Message(
        subject=f'New Order #{order.id} from {customer_name}',
        recipients=[current_app.config['ADMIN_EMAIL']],
        body=f"""
New order received on Motion website.

Order ID: {order.id}
Customer: {customer_name}
Email: {customer_email}
Phone: {customer_phone or 'N/A'}
Service: {order.service_type}

Details:
{order.details}

View in admin panel: {url_for('admin_order_detail', order_id=order.id, _external=True)}
        """
    )
    mail.send(admin_msg)
    
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

If you have any questions, feel free to contact us at 0787984135 or reply to this email.

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

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
