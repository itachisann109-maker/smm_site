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
    POST /v2/transaction/process
    """
    if not PLATEGA_MERCHANT_ID or not PLATEGA_SECRET_KEY:
        return {'error': 'Platega не настроен (нет Merchant ID или Secret Key)', 'status': 'error'}
    
    try:
        url = f"{PLATEGA_API_URL}/v2/transaction/process"
        
        payload = {
            "paymentDetails": {
                "amount": amount,
                "currency": "RUB",
                "description": description,
                "return": "https://sochyper.ru/payment/success",
                "failedUrl": "https://sochyper.ru/payment/fail",
                "payload": str(order_id)
            },
            "metadata": {
                "userid": str(order_id),
                "userName": user_username
            }
        }
        
        headers = {
            'Content-Type': 'application/json',
            'X-MerchantId': PLATEGA_MERCHANT_ID,
            'X-Secret': PLATEGA_SECRET_KEY
        }
        
        logging.info(f"📤 Запрос в Platega: {url}")
        logging.info(f"📤 Данные: {json.dumps(payload, indent=2)}")
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        logging.info(f"📥 Ответ: {response.status_code}")
        logging.info(f"📥 Тело: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('url'):
                return {
                    'payment_url': data.get('url'),
                    'payment_id': data.get('transactionId'),
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
        logging.error(f"❌ Ошибка: {e}")
        return {'error': str(e), 'status': 'error'}


def check_payment_status(payment_id):
    """Проверяет статус платежа"""
    if not PLATEGA_MERCHANT_ID or not PLATEGA_SECRET_KEY:
        return {'error': 'Platega не настроен', 'status': 'error'}
    
    try:
        # Проверьте в документации правильный путь для статуса
        url = f"{PLATEGA_API_URL}/v2/transaction/status"
        
        payload = {
            'transactionId': payment_id
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