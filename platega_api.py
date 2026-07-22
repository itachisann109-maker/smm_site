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
    # Проверка настроек
    if not PLATEGA_MERCHANT_ID:
        return {'error': 'Platega не настроен: отсутствует Merchant ID', 'status': 'error'}
    if not PLATEGA_SECRET_KEY:
        return {'error': 'Platega не настроен: отсутствует Secret Key', 'status': 'error'}
    
    # ⚠️ ЖЁСТКАЯ ЗАГЛУШКА
    description = "Пополнение баланса SOCHYPER"
    
    # ⚠️ ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА (на случай, если description всё равно None)
    if description is None or description.strip() == '':
        description = "Пополнение баланса SOCHYPER"
    
    try:
        url = f"{PLATEGA_API_URL}/v2/transaction/process"
        
        # Сумма в КОПЕЙКАХ
        amount_in_cents = int(amount * 100)
        
        # Отладка
        print("=" * 50)
        print("🔍 ПАРАМЕТРЫ create_payment:")
        print(f"amount: {amount} ({amount_in_cents} копеек)")
        print(f"description: '{description}' (len: {len(description)})")
        print(f"order_id: {order_id}")
        print(f"Merchant ID: {PLATEGA_MERCHANT_ID}")
        print(f"API URL: {PLATEGA_API_URL}")
        print("=" * 50)
        
        payload = {
            "paymentDetails": {
                "amount": amount_in_cents,
                "currency": "RUB",
                "description": description,
                "return": "https://sochyper.ru/payment/success",
                "failedUrl": "https://sochyper.ru/payment/fail",
                "payload": str(order_id)
            },
            "metadata": {
                "userid": str(order_id),
                "userName": user_username or "User"
            }
        }
        
        headers = {
            'Content-Type': 'application/json',
            'X-MerchantId': PLATEGA_MERCHANT_ID,
            'X-Secret': PLATEGA_SECRET_KEY
        }
        
        print("=" * 50)
        print("📤 ЗАПРОС К PLATEGA")
        print(f"URL: {url}")
        print(f"PAYLOAD: {json.dumps(payload, indent=2, ensure_ascii=False)}")
        print("=" * 50)
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        print("=" * 50)
        print("📥 ОТВЕТ ОТ PLATEGA")
        print(f"STATUS: {response.status_code}")
        print(f"TEXT: {response.text}")
        print("=" * 50)
        
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
                'error': f'Ошибка API: {response.status_code} - {response.text}',
                'status': 'error',
                'response': response.text
            }
            
    except Exception as e:
        print(f"❌ ИСКЛЮЧЕНИЕ: {e}")
        return {'error': str(e), 'status': 'error'}


def check_payment_status(payment_id):
    """Проверяет статус платежа"""
    if not PLATEGA_MERCHANT_ID or not PLATEGA_SECRET_KEY:
        return {'error': 'Platega не настроен', 'status': 'error'}
    
    try:
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
            return {
                'error': f'Ошибка API: {response.status_code} - {response.text}',
                'status': 'error'
            }
            
    except Exception as e:
        return {'error': str(e), 'status': 'error'}


def cancel_payment(order_id):
    """Отменяет платёж"""
    if not PLATEGA_MERCHANT_ID or not PLATEGA_SECRET_KEY:
        return {'error': 'Platega не настроен', 'status': 'error'}
    
    try:
        url = f"{PLATEGA_API_URL}/v2/transaction/cancel"
        
        payload = {
            'order_id': str(order_id)
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
                'status': 'success',
                'message': data.get('message', 'Платёж отменён')
            }
        else:
            return {
                'error': f'Ошибка API: {response.status_code}',
                'status': 'error'
            }
            
    except Exception as e:
        return {'error': str(e), 'status': 'error'}