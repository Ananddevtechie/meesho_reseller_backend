import logging
import time
from typing import Any

import httpx

from app.config import Settings


logger = logging.getLogger(__name__)


class TelegramNotificationError(RuntimeError):
    """Raised when Telegram cannot deliver an order notification."""


def _money(amount: Any) -> str:
    return f'INR {amount:,.2f}'


def _address_lines(order: dict[str, Any]) -> list[str]:
    fields = (
        ('House / Street', order.get('address_line1')),
        ('Address line 2', order.get('address_line2')),
        ('Landmark', order.get('landmark')),
        ('City', order.get('city')),
        ('State', order.get('state')),
        ('PIN / ZIP', order.get('pin')),
    )
    return [f'{label}: {value.strip()}' for label, value in fields if value and value.strip()]


def _message(order: dict[str, Any]) -> str:
    payment_method = 'COD' if order['payment_method'] == 'COD' else 'Online payment'
    payment_status = {
        'COD_PENDING': 'COD Pending',
        'PAID': 'Paid',
        'PAYMENT_PENDING': 'Payment Pending',
        'PAYMENT_FAILED': 'Payment Failed',
    }.get(order['payment_status'], order['payment_status'].replace('_', ' ').title())
    return '\n'.join(
        (
            'NEW THECART ORDER 🛍️',
            f"Order: {order['order_id']}",
            '------------------------------',
            '',
            'CUSTOMER',
            f"Name: {order['full_name']}",
            f"Phone: +91 {order['mobile']}",
            f"Alternate phone: {order.get('alternate_mobile') or 'Not provided'}",
            f"Email: {order.get('customer_email') or 'Not provided'}",
            '',
            'DELIVERY ADDRESS',
            *_address_lines(order),
            '',
            'PRODUCT',
            f"{order['product_title']} (SKU: {order['product_sku']})",
            f"Quantity: {order['quantity']}",
            *([f"Product link: {order['meesho_url']}"] if order.get('meesho_url') else []),
            '',
            'PAYMENT',
            f'Method: {payment_method}',
            f'State: {payment_status}',
            f"Total: {_money(order['total'])}",
            '------------------------------',
            '',
            f"Order date: {order['order_date']}",
            f"Expected delivery: {order['expected_delivery_range']}",
        )
    )


def send_order_notification(order: dict[str, Any]) -> None:
    telegram_settings = Settings()
    missing_settings = [
        name
        for name, value in (
            ('TELEGRAM_BOT_TOKEN', telegram_settings.telegram_bot_token),
            ('TELEGRAM_CHAT_ID', telegram_settings.telegram_chat_id),
        )
        if not value
    ]
    if missing_settings:
        missing = ', '.join(missing_settings)
        raise TelegramNotificationError(
            f'Order notifications are not configured. Set {missing} in the backend runtime environment '
            '(backend/.env for local development; Render service environment for production).'
        )

    url = f'https://api.telegram.org/bot{telegram_settings.telegram_bot_token}/sendMessage'
    payload = {'chat_id': telegram_settings.telegram_chat_id, 'text': _message(order)}
    for attempt in range(3):
        try:
            response = httpx.post(url, json=payload, timeout=15)
            response.raise_for_status()
            try:
                result = response.json()
            except ValueError as error:
                raise TelegramNotificationError('Telegram returned an invalid response.') from error
            if result.get('ok') is not True:
                raise TelegramNotificationError('Telegram rejected the order notification.')
            return
        except httpx.HTTPError as error:
            status_code = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
            retryable = status_code is None or status_code == 429 or status_code >= 500
            logger.warning(
                'Telegram notification attempt %s/3 failed for order %s (%s, HTTP %s).',
                attempt + 1,
                order['order_id'],
                type(error).__name__,
                status_code or 'unavailable',
            )
            if not retryable or attempt == 2:
                raise TelegramNotificationError('Telegram notification delivery failed.') from error
            time.sleep(0.5 * (2 ** attempt))