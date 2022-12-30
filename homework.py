import logging
import os
import time
from http import HTTPStatus
from logging.handlers import RotatingFileHandler
from json.decoder import JSONDecodeError

import requests
import telegram
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    filename='program.log',
    filemode='w',
    format='%(asctime)s, %(levelname)s, %(message)s, %(name)s'
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = RotatingFileHandler(
    'my_logger.log', maxBytes=50000000, backupCount=5
)
logger.addHandler(handler)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверка доступности переменных окружения."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.critical('Ошибка импорта токенов Telegram.')
        return False
    elif not PRACTICUM_TOKEN:
        raise SystemError('Ошибка импорта токенов Домашки.')
    else:
        return True


def send_message(bot, message):
    """Бот отправляет сообщение в Telegram чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug('Бот успешно запущен.')
        logger.info(f'Отправлено сообщение: "{message}"')
    except telegram.TelegramError as error:
        logger.error(f'Cбой отправки сообщения. Ошибка: {error}')


def get_api_answer(timestamp):
    """Запрос к API Практикум.Домашка."""
    timestamp = timestamp or int(time.time())
    params = {'from_date': timestamp}
    try:
        homework_statuses = requests.get(ENDPOINT,
                                         headers=HEADERS,
                                         params=params
                                         )
    except requests.exceptions.RequestException as error:
        logger.error(f'Ошибка при запросе к API: {error}')
        raise Exception(f'Ошибка при запросе к API: {error}')
    if homework_statuses.status_code != HTTPStatus.OK:
        status_code = homework_statuses.status_code
        logger.error(f'Ошибка {status_code}')
        raise Exception(f'Ошибка {status_code}')
    try:
        return homework_statuses.json()
    except JSONDecodeError as value_error:
        logger.error(f'Код ответа: {value_error}')
        raise JSONDecodeError(f'Код ответа: {value_error}')


def check_response(response):
    """Проверка ответа от сервера."""
    if type(response) is not dict:
        raise TypeError('Ответ сервера не является словарем')
    if not all(['current_date' in response, 'homeworks' in response]):
        raise KeyError('В ответе сервера нет нужных ключей')
    homeworks = response['homeworks']
    if type(homeworks) is not list:
        raise TypeError(
            'Под ключом homeworks домашки приходят не в виде списка'
        )
    return response.get('homeworks')


def parse_status(homework):
    """Проверка статуса конкретной домашней работы."""
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    if homework_name is not None and homework_status is not None:
        if homework_status in HOMEWORK_VERDICTS:
            verdict = HOMEWORK_VERDICTS.get(homework_status)
            return ('Изменился статус проверки '
                    + f'работы "{homework_name}". {verdict}')
        else:
            raise SystemError('Неизвестный статус')
    else:
        raise KeyError('Ключи отсуствуют')


def check_message(last_message, message):
    """Проверка сообщений."""
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    last_message = ''
    if last_message != message:
        send_message(bot, message)
        last_message = message


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        exit()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    send_message(bot, 'Я начал свою работу')
    timestamp = int(time.time())
    last_message = ''
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                message = parse_status(homeworks[0])
                check_message(last_message, message)
            else:
                logger.debug(f'Новых статусов нет. Перепроверка через '
                             f'{RETRY_PERIOD} сек.')
            timestamp = int(time.time())
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            check_message(last_message, message)
        else:
            logger.debug('Отправка повторного запроса')
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
