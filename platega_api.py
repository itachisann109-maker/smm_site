import requests
import os
import json
import logging

# ========================================================
# НАСТРОЙКИ PLATEGA
# ========================================================

PLATEGA_MERCHANT_ID = os.environ.get('PLATEGA_MERCHANT_ID', '')
PLATEGA_SECRET_KEY = os.environ.get('PLATEGA_SECRET_KEY', '')
PLATEGA_API_URL = os.environ.get('PLATEGA_API_URL', 'https://app.platega.io')

logging.basicConfig(level=logging.INFO)


def create_payment(amount, description, order_id, user_email, user_username):
    """
    Создаёт платёж через Platega
    Метод: Создание платежной ссылки без заданного метода
    """
    if not PLATEGA_MERCHANT_ID or not PLATEGA_SECRET_KEY:
        return {'error': 'Platega не настроен (нет Merchant ID или Secret Key)', 'status': 'error'}
    
    try:
        url = f"{PLATEGA_API_URL}/payments/create"
        
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
        
        headers = {
            'Content-Type': 'application/json',
            'X-MerchantId': PLATEGA_MERCHANT_ID,
            'X-Secret': PLATEGA_SECRET_KEY
        }
        
        logging.info(f"📤 Отправка запроса в Platega: {url}")
        logging.info(f"📤 Данные: {payload}")
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        logging.info(f"📥 Ответ Platega: {response.status_code} - {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success' or data.get('payment_url'):
                return {
                    'payment_url': data.get('payment_url'),
                    'payment_id': data.get('payment_id', data.get('id')),
                    'status': 'success'
                }
            else:
                return {'error': data.get('message', 'Неизвестная ошибка'), 'status': 'error'}
        else:
            return {
                'error': f'Ошибка API: {response.status_code}',
                'status': 'error',
                'response': response.text
            }
            
    except Exception as e:
        logging.error(f"❌ Ошибка создания платежа: {e}")
        return {'error': str(e), 'status': 'error'}


def check_payment_status(payment_id):
    """Проверяет статус платежа"""
    if not PLATEGA_MERCHANT_ID or not PLATEGA_SECRET_KEY:
        return {'error': 'Platega не настроен', 'status': 'error'}
    
    try:
        url = f"{PLATEGA_API_URL}/payments/status"
        
        payload = {
            'merchant_id': PLATEGA_MERCHANT_ID,
            'payment_id': payment_id
        }
        
        headers = {
            'Content-Type': 'application/json',
            'X-MerchantId': PLATEGA_MERCHANT_ID,
            'X-Secret': PLATEGA_SECRET_KEY
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
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