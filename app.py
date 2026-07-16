from flask import Flask, render_template, request, redirect, url_for, flash, session, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
import time
import threading
import csv
import secrets
import re
import requests
from io import StringIO
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
load_dotenv()
print("GOOGLE_CLIENT_ID:", os.environ.get('GOOGLE_CLIENT_ID'))
print("YANDEX_CLIENT_ID:", os.environ.get('YANDEX_CLIENT_ID'))

# ========================================================
# НАСТРОЙКИ
# ========================================================

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# ===== БАЗОВЫЙ URL ДЛЯ OAuth =====
# Для локального тестирования
BASE_URL = os.environ.get('BASE_URL', 'http://127.0.0.1:5000')

# ===== OAuth НАСТРОЙКИ (из переменных окружения) =====

# Яндекс OAuth
YANDEX_CLIENT_ID = os.environ.get('YANDEX_CLIENT_ID')
YANDEX_CLIENT_SECRET = os.environ.get('YANDEX_CLIENT_SECRET')

# Google OAuth
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')

# ===== БАЗА ДАННЫХ =====
basedir = os.path.abspath(os.path.dirname(__file__))
DATABASE_URL = os.environ.get('DATABASE_URL', f'sqlite:///' + os.path.join(basedir, 'smm.db'))
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ===== ИМПОРТ SMM-API =====
from smm_api import create_order_api, check_order_status_api, USE_REAL_API, get_balance, get_services


# ========================================================
# МОДЕЛИ ДАННЫХ
# ========================================================

class User(db.Model):
    """Модель пользователя"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(200), nullable=True)
    balance = db.Column(db.Float, default=0.0)
    is_admin = db.Column(db.Boolean, default=False)
    is_verified = db.Column(db.Boolean, default=True)
    avatar = db.Column(db.String(200), nullable=True)
    provider = db.Column(db.String(50), default='local')
    provider_id = db.Column(db.String(100), nullable=True)
    orders = db.relationship('Order', backref='user', lazy=True)

    def __repr__(self):
        return f'<User {self.username}>'


class Service(db.Model):
    """Модель услуги (накрутка)"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(300))
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50))

    def __repr__(self):
        return f'<Service {self.name}>'


class Order(db.Model):
    """Модель заказа"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'), nullable=False)
    link = db.Column(db.String(500), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    external_order_id = db.Column(db.String(50), nullable=True)
    service = db.relationship('Service', backref='orders')

    def __repr__(self):
        return f'<Order {self.id} - {self.status}>'


# ========================================================
# ИНИЦИАЛИЗАЦИЯ OAuth
# ========================================================

oauth = OAuth(app)

# Яндекс - упрощённая версия
if YANDEX_CLIENT_ID and YANDEX_CLIENT_SECRET:
    yandex = oauth.register(
        name='yandex',
        client_id=YANDEX_CLIENT_ID,
        client_secret=YANDEX_CLIENT_SECRET,
        access_token_url='https://oauth.yandex.ru/token',
        authorize_url='https://oauth.yandex.ru/authorize',
        api_base_url='https://login.yandex.ru/info',
        userinfo_endpoint='https://login.yandex.ru/info?format=json',
        client_kwargs={'scope': 'login:info login:email'}
    )

# Google - упрощённая версия
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    google = oauth.register(
        name='google',
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        access_token_url='https://oauth2.googleapis.com/token',
        authorize_url='https://accounts.google.com/o/oauth2/auth',
        api_base_url='https://www.googleapis.com/oauth2/v2/',
        userinfo_endpoint='https://www.googleapis.com/oauth2/v2/userinfo',
        client_kwargs={'scope': 'email profile'}
    )
# ========================================================
# СОЗДАНИЕ ТАБЛИЦ
# ========================================================

with app.app_context():
    db.create_all()
    
    if Service.query.count() == 0:
        services = [
            Service(name='Telegram подписчики (живые)', description='Качественные подписчики для вашего Telegram-канала', price=50, category='telegram'),
            Service(name='Telegram просмотры', description='Просмотры постов в Telegram', price=20, category='telegram'),
            Service(name='VK подписчики', description='Подписчики в группу ВКонтакте', price=30, category='vk'),
            Service(name='Instagram подписчики', description='Подписчики для аккаунта Instagram', price=60, category='instagram'),
            Service(name='YouTube подписчики', description='Подписчики для YouTube-канала', price=80, category='youtube'),
            Service(name='TikTok подписчики', description='Подписчики для TikTok-аккаунта', price=70, category='tiktok'),
        ]
        db.session.add_all(services)
        db.session.commit()
        
        if not User.query.filter_by(username='junkkk_cherkessk890890').first():
            admin = User(
                username='junkkk_cherkessk890890',
                email='admin@sochyper.ru',
                password_hash=generate_password_hash('Lobodina74!'),
                is_admin=True,
                is_verified=True,
                balance=9999,
                provider='local'
            )
            db.session.add(admin)
            db.session.commit()
            print('✅ Администратор создан: junkkk_cherkessk890890 / Lobodina74!')


# ========================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ========================================================

def get_current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None


def get_grouped_services():
    all_services = Service.query.all()
    grouped = {}
    for service in all_services:
        category = service.category if service.category else 'Другое'
        if category not in grouped:
            grouped[category] = []
        grouped[category].append(service)
    return grouped


def get_or_create_user_by_oauth(provider, provider_id, name, email, avatar=None):
    """Находит или создаёт пользователя через OAuth"""
    user = User.query.filter_by(provider=provider, provider_id=provider_id).first()
    
    if not user:
        if email:
            user = User.query.filter_by(email=email).first()
            if user:
                user.provider = provider
                user.provider_id = provider_id
                if avatar:
                    user.avatar = avatar
                db.session.commit()
                return user
        
        username = name.replace(' ', '_').lower()
        base_username = username
        counter = 1
        while User.query.filter_by(username=username).first():
            username = f"{base_username}_{counter}"
            counter += 1
        
        user = User(
            username=username,
            email=email,
            is_verified=True,
            is_admin=False,
            balance=0,
            provider=provider,
            provider_id=provider_id,
            avatar=avatar
        )
        db.session.add(user)
        db.session.commit()
    
    return user


def update_order_statuses():
    with app.app_context():
        while True:
            try:
                processing_orders = Order.query.filter_by(status='processing').all()
                
                for order in processing_orders:
                    if order.external_order_id and 'SIM' not in order.external_order_id:
                        result = check_order_status_api(order.external_order_id)
                        if result.get('status') == 'done':
                            order.status = 'done'
                            db.session.commit()
                            print(f"✅ Заказ #{order.id} выполнен!")
                        elif result.get('status') == 'cancelled':
                            order.status = 'cancelled'
                            db.session.commit()
                            print(f"❌ Заказ #{order.id} отменён")
                    else:
                        if order.created_at and (datetime.utcnow() - order.created_at).total_seconds() > 30:
                            order.status = 'done'
                            db.session.commit()
                            print(f"✅ Симуляция: заказ #{order.id} выполнен!")
                
                time.sleep(30)
                
            except Exception as e:
                print(f"Ошибка в фоновом процессе: {e}")
                time.sleep(60)


# ========================================================
# МАРШРУТЫ
# ========================================================

@app.route('/')
def index():
    user = get_current_user()
    services = Service.query.limit(4).all()
    grouped_services = get_grouped_services()
    return render_template('index.html', user=user, services=services, grouped_services=grouped_services)


@app.route('/register', methods=['GET', 'POST'])
def register():
    grouped_services = get_grouped_services()
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            flash('❌ Введите корректный email', 'danger')
            return render_template('register.html', grouped_services=grouped_services)
        
        if User.query.filter_by(username=username).first():
            flash('❌ Пользователь с таким именем уже существует', 'danger')
            return render_template('register.html', grouped_services=grouped_services)
        
        if User.query.filter_by(email=email).first():
            flash('❌ Этот email уже зарегистрирован', 'danger')
            return render_template('register.html', grouped_services=grouped_services)
        
        hashed = generate_password_hash(password)
        
        user = User(
            username=username,
            email=email,
            password_hash=hashed,
            is_verified=True,
            provider='local'
        )
        db.session.add(user)
        db.session.commit()
        
        flash('✅ Регистрация успешна! Теперь вы можете войти.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html', grouped_services=grouped_services)


@app.route('/login', methods=['GET', 'POST'])
def login():
    grouped_services = get_grouped_services()
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.password_hash and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            flash('Добро пожаловать!', 'success')
            
            if user.is_admin:
                return redirect(url_for('admin'))
            return redirect(url_for('index'))
        
        flash('Неверный логин или пароль', 'danger')
    
    return render_template('login.html', grouped_services=grouped_services)


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))


# ========================================================
# OAuth МАРШРУТЫ
# ========================================================

@app.route('/yandex/login')
def yandex_login():
    """Вход через Яндекс"""
    if 'yandex' not in globals():
        flash('❌ Яндекс OAuth не настроен', 'danger')
        return redirect(url_for('login'))
    redirect_uri = f"{BASE_URL}/yandex/callback"
    return yandex.authorize_redirect(redirect_uri)


@app.route('/yandex/callback')
def yandex_callback():
    """Callback после входа через Яндекс"""
    try:
        # Получаем токен
        token = yandex.authorize_access_token()
        
        # Получаем информацию о пользователе через API
        resp = yandex.get('info?format=json')
        user_info = resp.json()
        
        user = get_or_create_user_by_oauth(
            provider='yandex',
            provider_id=user_info.get('id'),
            name=user_info.get('login'),
            email=user_info.get('default_email'),
            avatar=None
        )
        
        session['user_id'] = user.id
        flash('✅ Вход через Яндекс выполнен!', 'success')
        return redirect(url_for('index'))
        
    except Exception as e:
        flash(f'❌ Ошибка входа через Яндекс: {e}', 'danger')
        return redirect(url_for('login'))


@app.route('/google/login')
def google_login():
    """Вход через Google"""
    if 'google' not in globals():
        flash('❌ Google OAuth не настроен', 'danger')
        return redirect(url_for('login'))
    redirect_uri = f"{BASE_URL}/google/callback"
    return google.authorize_redirect(redirect_uri)


@app.route('/google/callback')
def google_callback():
    """Callback после входа через Google"""
    try:
        # Получаем токен
        token = google.authorize_access_token()
        
        # Получаем информацию о пользователе через API
        resp = google.get('userinfo')
        user_info = resp.json()
        
        user = get_or_create_user_by_oauth(
            provider='google',
            provider_id=user_info.get('id', user_info.get('sub')),
            name=user_info.get('name'),
            email=user_info.get('email'),
            avatar=user_info.get('picture')
        )
        
        session['user_id'] = user.id
        flash('✅ Вход через Google выполнен!', 'success')
        return redirect(url_for('index'))
        
    except Exception as e:
        flash(f'❌ Ошибка входа через Google: {e}', 'danger')
        return redirect(url_for('login'))


# ========================================================
# ОСТАЛЬНЫЕ МАРШРУТЫ
# ========================================================

@app.route('/services')
def services():
    user = get_current_user()
    all_services = Service.query.all()
    grouped_services = get_grouped_services()
    return render_template('services.html', user=user, services=all_services, grouped_services=grouped_services)


@app.route('/my_orders')
def my_orders():
    user = get_current_user()
    grouped_services = get_grouped_services()
    
    if not user:
        flash('Пожалуйста, войдите в систему', 'warning')
        return redirect(url_for('login'))
    
    orders = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).all()
    
    return render_template('my_orders.html', user=user, orders=orders, grouped_services=grouped_services)


@app.route('/order/<int:service_id>', methods=['GET', 'POST'])
def order(service_id):
    user = get_current_user()
    grouped_services = get_grouped_services()
    
    if not user:
        flash('Пожалуйста, войдите в систему', 'warning')
        return redirect(url_for('login'))
    
    service = Service.query.get_or_404(service_id)
    
    if request.method == 'POST':
        link = request.form.get('link')
        quantity = int(request.form.get('quantity'))
        total = round(service.price * quantity / 1000, 2)
        
        if user.balance < total:
            flash('Недостаточно средств. Пополните баланс.', 'danger')
            return redirect(url_for('order', service_id=service_id))
        
        api_result = create_order_api(service_id, link, quantity)
        
        if api_result.get('error'):
            flash(f'❌ Ошибка при отправке заказа: {api_result["error"]}', 'danger')
            return redirect(url_for('order', service_id=service_id))
        
        order = Order(
            user_id=user.id,
            service_id=service.id,
            link=link,
            quantity=quantity,
            total_price=total,
            status='processing' if api_result.get('order_id') else 'pending'
        )
        
        if api_result.get('order_id'):
            order.external_order_id = api_result.get('order_id')
            order.status = 'processing'
        else:
            order.status = 'pending'
        
        user.balance -= total
        
        db.session.add(order)
        db.session.commit()
        
        flash(f'✅ Заказ оформлен! ID: {order.id}. {api_result.get("message", "Ожидайте выполнения.")}', 'success')
        return redirect(url_for('index'))
    
    return render_template('order.html', user=user, service=service, grouped_services=grouped_services)


@app.route('/admin')
def admin():
    user = get_current_user()
    grouped_services = get_grouped_services()
    
    if not user or not user.is_admin:
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('index'))
    
    orders = Order.query.order_by(Order.created_at.desc()).all()
    users = User.query.all()
    
    return render_template('admin.html', user=user, orders=orders, users=users, grouped_services=grouped_services)


@app.route('/admin/export/csv')
def export_orders_csv():
    user = get_current_user()
    
    if not user or not user.is_admin:
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('index'))
    
    orders = Order.query.order_by(Order.created_at.desc()).all()
    
    output = StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['ID', 'Пользователь', 'Email', 'Услуга', 'Кол-во', 'Сумма', 'Статус', 'Ссылка', 'Внешний ID', 'Дата'])
    
    for order in orders:
        writer.writerow([
            order.id,
            order.user.username,
            order.user.email,
            order.service.name,
            order.quantity,
            order.total_price,
            order.status,
            order.link,
            order.external_order_id or '—',
            order.created_at.strftime('%Y-%m-%d %H:%M')
        ])
    
    output.seek(0)
    return Response(
        output,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=orders_export.csv'}
    )


@app.route('/deposit', methods=['GET', 'POST'])
def deposit():
    user = get_current_user()
    grouped_services = get_grouped_services()
    
    if not user:
        flash('Пожалуйста, войдите в систему', 'warning')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        amount = float(request.form.get('amount'))
        user.balance += amount
        db.session.commit()
        
        flash(f'Баланс пополнен на {amount} руб.', 'success')
        return redirect(url_for('index'))
    
    return render_template('deposit.html', user=user, grouped_services=grouped_services)


@app.route('/payment', methods=['GET', 'POST'])
def payment_page():
    grouped_services = get_grouped_services()
    
    if request.method == 'POST':
        amount = float(request.form.get('amount', 0))
        method = request.form.get('method', 'sbp')
        user = get_current_user()
        
        if not user:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login'))
        
        if amount > 0:
            user.balance += amount
            db.session.commit()
            flash(f'✅ Баланс пополнен на {amount} ₽!', 'success')
        else:
            flash('❌ Ошибка: сумма не указана', 'danger')
        
        return redirect(url_for('index'))
    
    amount = request.args.get('amount', '0')
    method = request.args.get('method', 'sbp')
    
    return render_template('payment.html', amount=amount, method=method, grouped_services=grouped_services)


# ========================================================
# ЗАПУСК СЕРВЕРА
# ========================================================

if __name__ == '__main__':
    thread = threading.Thread(target=update_order_statuses, daemon=True)
    thread.start()
    print("🔄 Фоновый процесс обновления статусов запущен")
    
    if USE_REAL_API:
        print("🔗 Используется реальное API ConfirmSMM")
        try:
            balance = get_balance()
            if balance.get('balance'):
                print(f"💰 Баланс ConfirmSMM: {balance.get('balance')} {balance.get('currency', 'USD')}")
        except Exception as e:
            print(f"⚠️ Ошибка проверки баланса: {e}")
    else:
        print("🎭 Используется режим имитации (демо)")
    
    app.run(debug=True, host='0.0.0.0', port=8000)