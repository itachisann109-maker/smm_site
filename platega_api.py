import requests
import os
import json
import hashlib
import hmac
import time

# ========================================================
# НАСТРОЙКИ PLATEGA
# ========================================================

PLATEGA_MERCHANT_ID = os.environ.get('PLATEGA_MERCHANT_ID', '')
PLATEGA_SECRET_KEY = os.environ.get('PLATEGA_SECRET_KEY', '')
PLATEGA_PUBLIC_KEY = os.environ.get('PLATEGA_PUBLIC_KEY', '')
PLATEGA_API_URL = os.environ.get('PLATEGA_API_URL', 'https://api.platega.io/v1')


def create_payment(amount, description, order_id, user_email, user_username):
    """
    Создаёт платёж через Platega
    """
    if not PLATEGA_MERCHANT_ID or not PLATEGA_SECRET_KEY:
        return {'error': 'Platega не настроен', 'status': 'error'}
    
    try:
        payload = {
            'merchant_id': PLATEGA_MERCHANT_ID,
            'amount': amount,
            'currency': 'RUB',
            'description': description,
            'order_id': str(order_id),
            'customer_email': user_email,
            'customer_username': user_username,
            'success_url': 'https://sochyper.ru/payment/success',
            'fail_url': 'https://sochyper.ru/payment/fail',
            'webhook_url': 'https://sochyper.ru/webhook/platega'
        }
        
        # Подпись запроса
        signature = generate_signature(payload)
        headers = {
            'Content-Type': 'application/json',
            'X-Signature': signature
        }
        
        response = requests.post(
            f"{PLATEGA_API_URL}/payments/create",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                return {
                    'payment_url': data.get('payment_url'),
                    'payment_id': data.get('payment_id'),
                    'status': 'success'
                }
            else:
                return {'error': data.get('message', 'Неизвестная ошибка'), 'status': 'error'}
        else:
            return {'error': f'Ошибка API: {response.status_code}', 'status': 'error'}
            
    except Exception as e:
        return {'error': str(e), 'status': 'error'}


def generate_signature(payload):
    """Генерирует подпись для запроса"""
    # Сортируем ключи
    sorted_payload = {k: v for k, v in sorted(payload.items())}
    # Преобразуем в строку
    payload_str = json.dumps(sorted_payload, separators=(',', ':'))
    # Создаём подпись
    signature = hmac.new(
        PLATEGA_SECRET_KEY.encode('utf-8'),
        payload_str.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature


def check_payment_status(payment_id):
    """Проверяет статус платежа"""
    if not PLATEGA_MERCHANT_ID or not PLATEGA_SECRET_KEY:
        return {'error': 'Platega не настроен', 'status': 'error'}
    
    try:
        payload = {
            'merchant_id': PLATEGA_MERCHANT_ID,
            'payment_id': payment_id
        }
        
        signature = generate_signature(payload)
        headers = {
            'Content-Type': 'application/json',
            'X-Signature': signature
        }
        
        response = requests.post(
            f"{PLATEGA_API_URL}/payments/status",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            return {
                'status': data.get('status'),
                'amount': data.get('amount'),
                'message': data.get('message', '')
            }
        else:
            return {'error': f'Ошибка API: {response.status_code}', 'status': 'error'}
            
    except Exception as e:
        return {'error': str(e), 'status': 'error'}