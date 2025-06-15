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


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат.

    Args:
        bot: Объект бота TeleBot
        message: Текст сообщения для отправки
    """
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.debug(f'Бот отправил сообщение: {message}')
    except Exception as error:
        logging.error(f'Ошибка при отправке сообщения в Telegram: {error}')


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
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except requests.RequestException as error:
        raise ConnectionError(f'Ошибка при запросе к API: {error}')

    if response.status_code != HTTPStatus.OK:
        raise ValueError(
            f'Эндпоинт {ENDPOINT} недоступен. '
            f'Код ответа API: {response.status_code}'
        )
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
        raise TypeError('Ответ API не является словарём')
    if 'homeworks' not in response:
        raise KeyError('Ключ "homeworks" отсутствует в ответе API')
    if not isinstance(response['homeworks'], list):
        raise TypeError('"homeworks" должен быть списком')
    return response['homeworks']


def parse_status(homework):
    """Извлекает статус домашней работы.

    Args:
        homework: Данные домашней работы

    Returns:
        str: Сообщение о статусе работы

    Raises:
        KeyError: Отсутствует обязательный ключ
        ValueError: Неизвестный статус работы
    """
    if 'homework_name' not in homework:
        raise KeyError('Ключ "homework_name" отсутствует в ответе API')

    homework_name = homework['homework_name']
    status = homework.get('status')
    verdict = HOMEWORK_VERDICTS.get(status)

    if verdict is None:
        raise ValueError(f'Неизвестный статус: {status}')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверяет наличие всех необходимых переменных окружения.

    Returns:
        bool: True если все переменные доступны, иначе False
    """
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logging.critical(
            'Отсутствует обязательная переменная окружения. '
            'Программа принудительно остановлена.'
        )
        sys.exit(1)

    bot = telebot.TeleBot(TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    last_error = ''
    last_message = ''

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)

            if homeworks:
                message = parse_status(homeworks[0])
                if message != last_message:
                    send_message(bot, message)
                    last_message = message
            else:
                logging.debug('Нет новых статусов домашних работ')

            current_timestamp = response.get('current_date', current_timestamp)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message)
            if message != last_error:
                send_message(bot, message)
                last_error = message

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    main()
