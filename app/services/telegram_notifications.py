import logging
import time
from typing import Any

import httpx

from app.config import settings


logger = logging.getLogger(__name__)


class TelegramNotificationError(RuntimeError):
    """Raised when Telegram cannot deliver an order notification."""


def _money(amount: Any) -> str:
    return f'INR {amount:,.2f}'


def _address(order: dict[str, Any]) -> str:
    return ', '.join(
        part.strip()
        for part in (
            order['address_line1'],
            order['address_line2'],
            f"Landmark: {order['landmark']}" if order.get('landmark') else '',
            f"{order['city']}, {order['state']} {order['pin']}",
        )
        if part and part.strip()
    )


def _message(order: dict[str, Any]) -> str:
    fee_lines = [f"COD fee: {_money(order['cod_fee'])}"] if order['payment_method'] == 'COD' else []
    return '\n'.join(
        (
            'NEW THECART ORDER',
            f"Order: {order['order_id']}",
            '',
            'CUSTOMER',
            f"Name: {order['full_name']}",
            f"Phone: +91 {order['mobile']}",
            f"Alternate phone: {order.get('alternate_mobile') or 'Not provided'}",
            f"Email: {order.get('customer_email') or 'Not provided'}",
            f"Address: {_address(order)}",
            '',
            'PRODUCT',
            f"{order['product_title']} (SKU: {order['product_sku']})",
            f"Quantity: {order['quantity']}",
            '',
            'PAYMENT',
            f"Method: {order['payment_method']} ({order['payment_status']})",
            f"MRP: {_money(order['mrp'])}",
            f"Discount: -{_money(order['discount'])}",
            f"Shipping: {_money(order['shipping'])}",
            f"Tax: {_money(order['tax'])}",
            *fee_lines,
            f"Total: {_money(order['total'])}",
            f"Payment reference: {order.get('payment_reference') or 'Not applicable'}",
            '',
            f"Order date: {order['order_date']}",
            f"Expected delivery: {order['expected_delivery_range']}",
        )
    )


def send_order_notification(order: dict[str, Any]) -> None:
    missing_settings = [
        name
        for name, value in (
            ('TELEGRAM_BOT_TOKEN', settings.telegram_bot_token),
            ('TELEGRAM_CHAT_ID', settings.telegram_chat_id),
        )
        if not value
    ]
    if missing_settings:
        missing = ', '.join(missing_settings)
        raise TelegramNotificationError(
            f'Order notifications are not configured. Set {missing} in backend/.env, then restart the backend.'
        )

    url = f'https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage'
    payload = {'chat_id': settings.telegram_chat_id, 'text': _message(order)}
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