"""Модуль для проверки статуса домашней работы через API Яндекс.Практикума."""

import logging
import os
import sys
import time
from http import HTTPStatus

import requests
import telebot
from dotenv import load_dotenv

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


class MissingTokensError(Exception):
    """Исключение при отсутствии обязательных переменных окружения."""

    pass


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат.

    Args:
        bot: Объект бота TeleBot
        message: Текст сообщения для отправки

    Returns:
        bool: True если сообщение отправлено успешно, False при ошибке
    """
    try:
        logging.debug(f'Попытка отправить сообщение: {message}')
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.debug('Сообщение успешно отправлено')
        return True
    except (
        telebot.apihelper.ApiException,
        requests.exceptions.RequestException
    ) as error:
        logging.error(f'Ошибка при отправке сообщения: {error}')
        return False


def get_api_answer(timestamp):
    """Делает запрос к API Практикум.Домашка.

    Args:
        timestamp: Временная метка для запроса

    Returns:
        dict: Ответ API в формате JSON

    Raises:
        ConnectionError: Ошибка соединения с API
        ValueError: Некорректный статус ответа
    """
    request_params = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp},
    }

    logging.debug(
        'Отправка запроса к API:\n'
        'URL: {url}\n'
        'Headers: {headers}\n'
        'Params: {params}'.format(**request_params)
    )

    try:
        response = requests.get(**request_params)
    except requests.RequestException as error:
        raise ConnectionError(
            'Ошибка при запросе к API {url} с параметрами {params}. '
            'Ошибка: {error}'.format(
                url=ENDPOINT,
                params={'from_date': timestamp},
                error=error
            )
        )

    if response.status_code != HTTPStatus.OK:
        raise ValueError(
            'Эндпоинт {url} недоступен. '
            'Код ответа API: {status_code}\n'
            'Параметры запроса: {params}\n'
            'Заголовки запроса: {headers}'.format(
                url=ENDPOINT,
                status_code=response.status_code,
                params={'from_date': timestamp},
                headers=HEADERS
            )
        )

    logging.debug('Успешный ответ от API')
    return response.json()


def check_response(response):
    """Проверяет корректность ответа API.

    Args:
        response: Ответ API для проверки

    Returns:
        list: Список домашних работ

    Raises:
        TypeError: Некорректный тип данных
        KeyError: Отсутствует обязательный ключ
    """
    if not isinstance(response, dict):
        raise TypeError(
            f'Ответ API должен быть словарём, '
            f'получен {type(response).__name__}'
        )

    if 'homeworks' not in response:
        raise KeyError('Ключ "homeworks" отсутствует в ответе API')

    homeworks = response['homeworks']

    if not isinstance(homeworks, list):
        raise TypeError(
            f'homeworks должен быть списком, '
            f'получен {type(homeworks).__name__}'
        )

    return homeworks


def parse_status(homework):
    """Извлекает статус домашней работы.

    Args:
        homework: Данные домашней работы

    Returns:
        str: Сообщение о статусе работы

    Raises:
        KeyError: Отсутствует обязательный ключ ('homework_name' или 'status')
        ValueError: Неизвестный статус работы
    """
    if 'homework_name' not in homework:
        raise KeyError('Ключ "homework_name" отсутствует в ответе API')
    if 'status' not in homework:
        raise KeyError('Ключ "status" отсутствует в ответе API')

    homework_name = homework['homework_name']
    status = homework['status']

    verdict = HOMEWORK_VERDICTS.get(status)
    if verdict is None:
        raise ValueError(f'Неизвестный статус работы: {status}')

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверяет наличие всех необходимых переменных окружения.

    Returns:
        bool: True если все переменные доступны

    Raises:
        MissingTokensError: Если отсутствуют обязательные переменные
    """
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
    }

    missing_tokens = [name for name, value in tokens.items() if not value]

    if missing_tokens:
        raise MissingTokensError(
            f'Отсутствуют обязательные переменные окружения: '
            f'{", ".join(missing_tokens)}'
        )
    return True


def main():
    """Основная логика работы бота."""
    try:
        check_tokens()
    except MissingTokensError as error:
        logging.critical(str(error))
        sys.exit(1)

    bot = telebot.TeleBot(TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    last_error = None

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)

            if homeworks:
                message = parse_status(homeworks[0])
                if send_message(bot, message):
                    current_timestamp = response.get(
                        'current_date',
                        current_timestamp
                    )
                    last_error = None

        except Exception as error:
            error_message = f'Сбой в работе программы: {error}'
            if error_message != last_error:
                logging.error(error_message)
                send_message(bot, error_message)
                last_error = error_message

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    main()
