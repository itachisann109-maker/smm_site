import requests
import random
import time
import logging
import os

# ========================================================
# НАСТРОЙКИ API (из переменных окружения)
# ========================================================

SMM_API_KEY = os.environ.get('SMM_API_KEY', '')
SMM_API_URL = 'https://confirmsmm.com/api/v2'
USE_REAL_API = os.environ.get('USE_REAL_API', 'False').lower() == 'true'

# Настройка логирования
logging.basicConfig(level=logging.INFO)


def get_services():
    """Получает список всех услуг из ConfirmSMM"""
    if not USE_REAL_API or not SMM_API_KEY:
        return {'error': 'API отключено или ключ не задан', 'status': 'error'}
    
    try:
        payload = {
            'key': SMM_API_KEY,
            'action': 'services'
        }
        response = requests.post(SMM_API_URL, data=payload, timeout=30)
        
        if response.status_code == 200:
            return response.json()
        else:
            return {'error': f'Ошибка API: {response.status_code}'}
            
    except Exception as e:
        return {'error': str(e), 'status': 'error'}


def get_balance():
    """Проверяет баланс аккаунта в ConfirmSMM"""
    if not USE_REAL_API or not SMM_API_KEY:
        return {'balance': '0.00', 'currency': 'USD'}
    
    try:
        payload = {
            'key': SMM_API_KEY,
            'action': 'balance'
        }
        response = requests.post(SMM_API_URL, data=payload, timeout=30)
        
        if response.status_code == 200:
            return response.json()
        else:
            return {'error': f'Ошибка API: {response.status_code}'}
            
    except Exception as e:
        return {'error': str(e), 'status': 'error'}


def create_order_api(service_id, link, quantity):
    """
    Создаёт заказ на накрутку через API ConfirmSMM
    """
    # =========================================================
    # МАППИНГ УСЛУГ (внутренний ID → внешний ID из API)
    # =========================================================
    service_mapping = {
        # ===== TELEGRAM =====
        1: 2317,   # Telegram подписчики (быстрые)
        2: 2548,   # Telegram подписчики (качественные, 90 дней)
        3: 2457,   # Telegram подписчики (навсегда)
        4: 2406,   # Telegram просмотры постов
        5: 2466,   # Telegram реакции (любые)
        6: 2432,   # Telegram Premium подписчики (7 дней)
        7: 2437,   # Telegram Premium подписчики (30 дней)
        8: 2408,   # Telegram рефералы в бот
        
        # ===== VK =====
        9: 1956,   # VK подписчики (быстрые)
        10: 1305,  # VK подписчики (качественные)
        11: 1306,  # VK лайки
        12: 2544,  # VK просмотры постов
        13: 2545,  # VK просмотры видео
        14: 1310,  # VK заявки в друзья
        
        # ===== YOUTUBE =====
        15: 2042,  # YouTube подписчики (быстрые)
        16: 2043,  # YouTube подписчики (качественные)
        17: 2054,  # YouTube лайки
        18: 2074,  # YouTube просмотры (органические)
        19: 2081,  # YouTube Shorts просмотры
        
        # ===== TIKTOK =====
        20: 1899,  # TikTok подписчики (быстрые)
        21: 1902,  # TikTok подписчики (качественные)
        22: 1910,  # TikTok лайки
        23: 408,   # TikTok просмотры
        24: 639,   # TikTok репосты
        25: 645,   # TikTok сохранения
    }
    
    external_service_id = service_mapping.get(service_id)
    if not external_service_id:
        return {
            'error': f'Услуга с ID {service_id} не настроена или не найдена в API.',
            'status': 'error'
        }
    
    if not USE_REAL_API or not SMM_API_KEY:
        # Имитация для демонстрации
        import random
        delay = random.randint(5, 30)
        success_rate = 0.95
        if random.random() < success_rate:
            return {
                'order_id': f"SIM{random.randint(10000, 99999)}",
                'status': 'processing',
                'message': f'Заказ принят в работу (Симуляция).',
                'simulated': True
            }
        else:
            return {
                'error': 'Ошибка выполнения заказа (Симуляция)',
                'status': 'error',
                'simulated': True
            }
    
    # ===== РЕАЛЬНЫЙ ЗАПРОС =====
    try:
        payload = {
            'key': SMM_API_KEY,
            'action': 'add',
            'service': external_service_id,
            'link': link,
            'quantity': quantity
        }
        
        logging.info(f"📤 Отправка заказа: service={external_service_id}, quantity={quantity}")
        response = requests.post(SMM_API_URL, data=payload, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            logging.info(f"📥 Ответ API: {data}")
            
            if 'error' in data:
                return {
                    'error': data.get('error', 'Неизвестная ошибка'),
                    'status': 'error'
                }
            
            if data.get('order'):
                return {
                    'order_id': data.get('order'),
                    'status': 'processing',
                    'message': 'Заказ отправлен на выполнение в ConfirmSMM'
                }
            else:
                return {
                    'error': 'Не удалось создать заказ',
                    'status': 'error'
                }
        else:
            return {
                'error': f'Ошибка API: {response.status_code}',
                'status': 'error'
            }
            
    except requests.exceptions.Timeout:
        return {'error': 'Таймаут при соединении с API', 'status': 'error'}
    except requests.exceptions.ConnectionError:
        return {'error': 'Не удалось подключиться к API', 'status': 'error'}
    except Exception as e:
        logging.error(f"❌ Ошибка: {e}")
        return {'error': str(e), 'status': 'error'}


def check_order_status_api(order_id):
    """Проверяет статус заказа в ConfirmSMM"""
    if not USE_REAL_API or not SMM_API_KEY:
        return {'status': 'done', 'count': 1000, 'message': 'Выполнено (Симуляция)'}
    
    try:
        payload = {
            'key': SMM_API_KEY,
            'action': 'status',
            'order': order_id
        }
        response = requests.post(SMM_API_URL, data=payload, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            
            status_map = {
                'In progress': 'processing',
                'Partial': 'processing',
                'Completed': 'done',
                'Cancelled': 'cancelled',
                'Error': 'error'
            }
            
            smm_status = data.get('status', 'unknown')
            our_status = status_map.get(smm_status, 'pending')
            
            return {
                'status': our_status,
                'count': data.get('start_count', 0),
                'message': data.get('status', '')
            }
        else:
            return {'error': f'Ошибка API: {response.status_code}'}
            
    except Exception as e:
        return {'error': str(e)}


def cancel_order_api(order_id):
    """Отменяет заказ в ConfirmSMM"""
    if not USE_REAL_API or not SMM_API_KEY:
        return {'status': 'cancelled', 'message': 'Заказ отменён (симуляция)'}
    
    try:
        payload = {
            'key': SMM_API_KEY,
            'action': 'cancel',
            'orders': order_id
        }
        response = requests.post(SMM_API_URL, data=payload, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                result = data[0]
                if result.get('cancel') == 1:
                    return {'status': 'cancelled', 'message': 'Заказ отменён'}
                else:
                    return {'error': result.get('cancel', {}).get('error', 'Ошибка отмены')}
            return {'status': 'cancelled', 'message': 'Заказ отменён'}
        else:
            return {'error': f'Ошибка API: {response.status_code}'}
            
    except Exception as e:
        return {'error': str(e)}