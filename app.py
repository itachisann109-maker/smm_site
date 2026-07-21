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
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Загружаем переменные окружения
load_dotenv()

# ========================================================
# НАСТРОЙКИ
# ========================================================

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# ===== БАЗОВЫЙ URL ДЛЯ OAuth =====
BASE_URL = os.environ.get('BASE_URL', 'https://sochyper.ru')

# ===== OAuth НАСТРОЙКИ (из переменных окружения) =====

# Яндекс OAuth
YANDEX_CLIENT_ID = os.environ.get('YANDEX_CLIENT_ID')
YANDEX_CLIENT_SECRET = os.environ.get('YANDEX_CLIENT_SECRET')

# Google OAuth
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')

# ===== НАСТРОЙКИ УВЕДОМЛЕНИЙ =====
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@sochyper.ru')
SMTP_HOST = os.environ.get('SMTP_HOST', 'smtp.yandex.ru')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_ADMIN_CHAT_ID = os.environ.get('TELEGRAM_ADMIN_CHAT_ID', '')

# ===== БАЗА ДАННЫХ =====
basedir = os.path.abspath(os.path.dirname(__file__))
DATABASE_URL = os.environ.get('DATABASE_URL', f'sqlite:///' + os.path.join(basedir, 'smm.db'))
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ===== ИМПОРТ SMM-API =====
from smm_api import create_order_api, check_order_status_api, USE_REAL_API, get_balance, get_services


# ========================================================
# ФУНКЦИИ УВЕДОМЛЕНИЙ
# ========================================================

def send_telegram_message(message):
    """Отправляет уведомление в Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_CHAT_ID:
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_ADMIN_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, data=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Ошибка отправки в Telegram: {e}")
        return False


def send_email_notification(subject, body):
    """Отправляет уведомление на email"""
    if not SMTP_USER or not SMTP_PASSWORD:
        return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = ADMIN_EMAIL
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки email: {e}")
        return False


def notify_admin(order_id, user_username, service_name, quantity, total_price, user_balance=None, action='new_order'):
    """Отправляет уведомление администратору"""
    if action == 'new_order':
        subject = f"🔔 Новый заказ #{order_id}"
        message = f"""
📦 <b>Новый заказ #{order_id}</b>

👤 Пользователь: {user_username}
📱 Услуга: {service_name}
📊 Количество: {quantity}
💰 Сумма: {total_price} ₽

🔗 Ссылка: https://sochyper.ru/admin
"""
    elif action == 'deposit':
        subject = f"💰 Пополнение баланса"
        message = f"""
💰 <b>Пополнение баланса</b>

👤 Пользователь: {user_username}
💵 Сумма: {total_price} ₽
🆕 Новый баланс: {user_balance} ₽

🔗 Ссылка: https://sochyper.ru/admin
"""
    else:
        return
    
    # Отправляем в Telegram
    send_telegram_message(message)
    
    # Отправляем на Email (без HTML-тегов)
    plain_message = message.replace('<b>', '').replace('</b>', '')
    send_email_notification(subject, plain_message)


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

# Яндекс
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

# Google
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    google = oauth.register(
        name='google',
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        access_token_url='https://oauth2.googleapis.com/token',
        authorize_url='https://accounts.google.com/o/oauth2/auth',
        api_base_url='https://www.googleapis.com/oauth2/v2/',
        userinfo_endpoint='https://www.googleapis.com/oauth2/v2/userinfo',
        client_kwargs={'scope': 'openid email profile'},
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration'
    )


# ========================================================
# СОЗДАНИЕ ТАБЛИЦ
# ========================================================
with app.app_context():
    db.create_all()
    
    if Service.query.count() == 0:
        services = [
            # ===== TELEGRAM =====
            Service(name='Telegram подписчики (Ultra Cheap, Instant)', description='Быстрые подписчики для канала/группы. Без возврата.', price=1.26, category='telegram'),
            Service(name='Telegram подписчики (90 Days NonDrop)', description='Качественные подписчики с гарантией 90 дней', price=54.00, category='telegram'),
            Service(name='Telegram подписчики (Lifetime Non-Drop)', description='Подписчики навсегда. Гарантия качества.', price=85.05, category='telegram'),
            Service(name='Telegram просмотры постов (50k/hour)', description='Быстрые просмотры постов. До 50к в час.', price=0.225, category='telegram'),
            Service(name='Telegram просмотры постов (Last 5)', description='Просмотры последних 5 постов', price=1.17, category='telegram'),
            Service(name='Telegram реакции (Mixed Positive)', description='Смешанные позитивные реакции 👍🤩🎉🔥❤️', price=1.17, category='telegram'),
            Service(name='Telegram реакции ❤️', description='Реакция ❤️ к посту + бесплатные просмотры', price=1.17, category='telegram'),
            Service(name='Telegram реакции 🔥', description='Реакция 🔥 к посту + бесплатные просмотры', price=1.17, category='telegram'),
            Service(name='Telegram Premium подписчики (7 дней)', description='Премиум-подписчики на 7 дней', price=223.21, category='telegram'),
            Service(name='Telegram Premium подписчики (30 дней)', description='Премиум-подписчики на 30 дней', price=486.38, category='telegram'),
            Service(name='Telegram Premium подписчики (90 дней)', description='Премиум-подписчики на 90 дней', price=1461.08, category='telegram'),
            Service(name='Telegram Boost канала (30+ дней)', description='Буст канала на 30+ дней', price=23940.00, category='telegram'),
            
            # ===== VK =====
            Service(name='VK подписчики (Fast)', description='Быстрая накрутка подписчиков в группу', price=63.00, category='vk'),
            Service(name='VK подписчики (Low Drop)', description='Подписчики с минимальным отписом', price=40.50, category='vk'),
            Service(name='VK лайки (Fast)', description='Быстрые лайки для постов', price=38.54, category='vk'),
            Service(name='VK просмотры постов', description='Просмотры записей на стене', price=0.126, category='vk'),
            Service(name='VK просмотры видео', description='Просмотры видео в VK', price=0.90, category='vk'),
            Service(name='VK просмотры клипов', description='Просмотры коротких видео (клипов)', price=0.90, category='vk'),
            Service(name='VK просмотры стены', description='Просмотры записей на стене (Wall Views)', price=0.90, category='vk'),
            
            # ===== YOUTUBE =====
            Service(name='YouTube подписчики (Max 30K/Day)', description='Подписчики до 30 000 в день', price=132.21, category='youtube'),
            Service(name='YouTube подписчики (Max 50K/Day)', description='Подписчики до 50 000 в день', price=108.81, category='youtube'),
            Service(name='YouTube подписчики (Max 100K/Day)', description='Подписчики до 100 000 в день', price=145.08, category='youtube'),
            Service(name='YouTube лайки (Max 50K)', description='Лайки для видео до 50 000', price=200.49, category='youtube'),
            Service(name='YouTube лайки (Max 100K)', description='Лайки для видео до 100 000', price=255.28, category='youtube'),
            Service(name='YouTube просмотры (Social Ads, Min 10K)', description='Просмотры с соцсетей. Минимум 10 000', price=98.53, category='youtube'),
            Service(name='YouTube просмотры (Social Ads, Min 3K)', description='Просмотры с соцсетей. Минимум 3 000', price=122.59, category='youtube'),
            Service(name='YouTube Shorts просмотры (Max 100M)', description='Просмотры коротких видео (Shorts)', price=111.20, category='youtube'),
            Service(name='YouTube Shorts лайки (Max 50K)', description='Лайки для коротких видео (Shorts)', price=362.70, category='youtube'),
            
            # ===== TIKTOK =====
            Service(name='TikTok подписчики (Max 25K, Quality)', description='Качественные подписчики до 25 000', price=157.10, category='tiktok'),
            Service(name='TikTok подписчики (Max 50K)', description='Подписчики до 50 000', price=691.20, category='tiktok'),
            Service(name='TikTok подписчики (Max 100K, HQ)', description='Высококачественные подписчики до 100 000', price=162.00, category='tiktok'),
            Service(name='TikTok лайки (Max 500K, HQ)', description='Лайки до 500 000', price=9.89, category='tiktok'),
            Service(name='TikTok лайки (Max 500K, Speed 50K/Day)', description='Быстрые лайки до 500 000', price=4.91, category='tiktok'),
            Service(name='TikTok просмотры видео (Non-Drop)', description='Просмотры видео без возврата', price=6.30, category='tiktok'),
            Service(name='TikTok репосты/шары (Max 100M)', description='Репосты видео до 100 000 000', price=6.55, category='tiktok'),
            Service(name='TikTok сохранения (Max 100K)', description='Сохранения видео в избранное', price=20.16, category='tiktok'),
            Service(name='TikTok Live Stream просмотры (15 мин)', description='Просмотры прямого эфира (15 минут)', price=567.00, category='tiktok'),
        ]
        db.session.add_all(services)
        db.session.commit()
        print(f'✅ Добавлено {len(services)} услуг')
        
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
# ОБРАБОТЧИКИ ОШИБОК
# ========================================================

@app.errorhandler(404)
def page_not_found(e):
    """Кастомная страница 404"""
    grouped_services = get_grouped_services()
    user = get_current_user()
    return render_template('404.html', user=user, grouped_services=grouped_services), 404


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
    print(f"🔍 Яндекс Redirect URI: {redirect_uri}")
    return yandex.authorize_redirect(redirect_uri)


@app.route('/yandex/callback')
def yandex_callback():
    """Callback после входа через Яндекс"""
    print("🔴 Яндекс: НАЧАЛ callback")
    try:
        token = yandex.authorize_access_token()
        print(f"🔴 Яндекс: токен получен: {token}")
        resp = yandex.get('info?format=json')
        print(f"🔴 Яндекс: статус ответа: {resp.status_code}")
        print(f"🔴 Яндекс: текст ответа: {resp.text}")
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
        print(f"❌ Яндекс: ошибка: {e}")
        flash(f'❌ Ошибка входа через Яндекс: {e}', 'danger')
        return redirect(url_for('login'))


@app.route('/google/login')
def google_login():
    """Вход через Google"""
    if 'google' not in globals():
        flash('❌ Google OAuth не настроен', 'danger')
        return redirect(url_for('login'))
    redirect_uri = f"{BASE_URL}/google/callback"
    print(f"🔍 Google Redirect URI: {redirect_uri}")
    return google.authorize_redirect(redirect_uri)


@app.route('/google/callback')
def google_callback():
    """Callback после входа через Google"""
    try:
        token = google.authorize_access_token()
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
# ЯНДЕКС ВЕБМАСТЕР - ПОДТВЕРЖДЕНИЕ ПРАВ
# ========================================================

@app.route('/yandex_30cf70d06142ad9d.html')
def yandex_verify():
    """Страница для подтверждения прав в Яндекс Вебмастере"""
    return '''<html>
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
</head>
<body>Verification: 30cf70d06142ad9d</body>
</html>'''


# ========================================================
# ПРАВОВЫЕ СТРАНИЦЫ
# ========================================================

@app.route('/privacy')
def privacy():
    """Страница политики конфиденциальности"""
    grouped_services = get_grouped_services()
    user = get_current_user()
    return render_template('privacy.html', user=user, grouped_services=grouped_services)


@app.route('/offer')
def offer():
    """Страница публичной оферты"""
    grouped_services = get_grouped_services()
    user = get_current_user()
    return render_template('offer.html', user=user, grouped_services=grouped_services)


# ========================================================
# ОСНОВНЫЕ МАРШРУТЫ
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
        
        # === ОТПРАВКА УВЕДОМЛЕНИЯ АДМИНИСТРАТОРУ ===
        try:
            notify_admin(
                order_id=order.id,
                user_username=user.username,
                service_name=service.name,
                quantity=quantity,
                total_price=total,
                action='new_order'
            )
        except Exception as e:
            print(f"⚠️ Ошибка уведомления: {e}")
        # ==========================================
        
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
        
        # === ОТПРАВКА УВЕДОМЛЕНИЯ АДМИНИСТРАТОРУ ===
        try:
            notify_admin(
                order_id=0,
                user_username=user.username,
                service_name='Пополнение баланса',
                quantity=1,
                total_price=amount,
                user_balance=user.balance,
                action='deposit'
            )
        except Exception as e:
            print(f"⚠️ Ошибка уведомления: {e}")
        # ==========================================
        
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