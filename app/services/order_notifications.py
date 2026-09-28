import smtplib
import ssl
from html import escape
from email.message import EmailMessage
from typing import Any

from app.config import settings


class OrderNotificationError(RuntimeError):
    """Raised when the configured order notification could not be sent."""


def _money(amount: Any) -> str:
    return f'₹{amount:,.2f}'


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


def _html_email(order: dict[str, Any]) -> str:
    address = _address(order)
    rows = [
        ('Product', f"{order['product_title']} (SKU: {order['product_sku']})"),
        ('Quantity', order['quantity']),
        ('MRP', _money(order['mrp'])),
        ('Discount', f"−{_money(order['discount'])}"),
        ('Shipping', _money(order['shipping'])),
        ('Tax', _money(order['tax'])),
        ('Total amount', _money(order['total'])),
        ('Payment method', order['payment_method']),
        ('Payment status', order['payment_status']),
        ('Payment reference', order.get('payment_reference') or 'Not applicable'),
        ('Order date', order['order_date']),
        ('Expected delivery', order['expected_delivery_range']),
    ]
    if order['payment_method'] == 'COD':
        rows.insert(6, ('COD fee', _money(order['cod_fee'])))
    pricing_rows = ''.join(
        '<tr><td style="padding:9px 12px;border-bottom:1px solid #edf0f5;color:#64748b">'
        f'{escape(str(label))}</td><td style="padding:9px 12px;border-bottom:1px solid #edf0f5;'
        f'color:#0f172a;text-align:right;font-weight:600">{escape(str(value))}</td></tr>'
        for label, value in rows
    )
    payment_note = (
        'Cash on Delivery order placed. Confirm stock and serviceability before dispatch.'
        if order['payment_method'] == 'COD'
        else 'UPI payment verified. Confirm stock and serviceability before dispatch.'
    )
    return f'''<!doctype html>
<html lang="en"><body style="margin:0;padding:24px;background:#f4f6fa;font-family:Arial,sans-serif;color:#0f172a">
<table role="presentation" style="width:100%;max-width:640px;margin:auto;background:#fff;border:1px solid #e2e8f0;border-radius:14px;border-spacing:0;overflow:hidden">
<tr><td style="padding:24px 28px;background:#172b22;color:#f8fafc"><div style="font-size:12px;letter-spacing:2px;color:#f0b95d">THECART · ORDER NOTIFICATION</div><h1 style="margin:12px 0 0;font-size:24px">New order received</h1><p style="margin:8px 0 0;color:#d5dfd7">Order #{escape(str(order['order_id']))}</p></td></tr>
<tr><td style="padding:24px 28px"><h2 style="margin:0 0 12px;font-size:16px">Customer details</h2><p style="margin:6px 0">Name: <strong>{escape(str(order['full_name']))}</strong></p><p style="margin:6px 0">Phone: <strong>+91 {escape(str(order['mobile']))}</strong></p><p style="margin:6px 0">Email: <strong>{escape(str(order.get('customer_email') or 'Not provided'))}</strong></p>
<h2 style="margin:22px 0 12px;font-size:16px">Delivery address</h2><p style="margin:0;line-height:1.6">{escape(address)}</p>
<h2 style="margin:22px 0 12px;font-size:16px">Order and pricing</h2><table role="presentation" style="width:100%;border:1px solid #edf0f5;border-radius:8px;border-spacing:0">{pricing_rows}</table>
<p style="margin:20px 0 0;padding:12px 14px;border-radius:8px;background:#fff8e8;color:#7c5715">{escape(payment_note)}</p></td></tr>
<tr><td style="padding:16px 28px;border-top:1px solid #edf0f5;color:#64748b;font-size:12px">This is an automated transactional order notification.</td></tr>
</table></body></html>'''


def send_order_notification(order: dict[str, Any]) -> None:
    missing_settings = [
        name
        for name, value in (
            ('SMTP_HOST', settings.smtp_host),
            ('SMTP_USERNAME', settings.smtp_username),
            ('SMTP_PASSWORD', settings.smtp_password),
        )
        if not value
    ]
    if missing_settings:
        missing = ', '.join(missing_settings)
        raise OrderNotificationError(
            f'Order email is not configured. Set {missing} in backend/.env, then restart the backend.'
        )

    message = EmailMessage()
    message['Subject'] = f"New Order Received — Order #{order['order_id']}"
    message['From'] = settings.smtp_from_email or settings.smtp_username
    message['To'] = settings.order_notification_email
    fee_lines = (f"COD fee: {_money(order['cod_fee'])}",) if order['payment_method'] == 'COD' else ()
    message.set_content(
        '\n'.join(
            (
                'NEW ORDER RECEIVED',
                f"Order #{order['order_id']}",
                '',
                'CUSTOMER DETAILS',
                f"Name: {order['full_name']}",
                f"Phone: +91 {order['mobile']}",
                f"Email: {order.get('customer_email') or 'Not provided'}",
                '',
                'DELIVERY ADDRESS',
                _address(order),
                '',
                'ORDER DETAILS',
                f"Product: {order['product_title']}",
                f"SKU: {order['product_sku']}",
                f"Quantity: {order['quantity']}",
                '',
                'PRICING',
                f"MRP: {_money(order['mrp'])}",
                f"Discount: -{_money(order['discount'])}",
                f"Shipping: {_money(order['shipping'])}",
                f"Tax: {_money(order['tax'])}",
                *fee_lines,
                f"Total amount: {_money(order['total'])}",
                '',
                'PAYMENT DETAILS',
                f"Payment method: {order['payment_method']}",
                f"Payment status: {order['payment_status']}",
                f"Payment reference: {order.get('payment_reference') or 'Not applicable'}",
                '',
                f"Order date: {order['order_date']}",
                f"Expected delivery: {order['expected_delivery_range']}",
            )
        )
    )
    message.add_alternative(_html_email(order), subtype='html')

    try:
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=15,
                context=ssl.create_default_context(),
            ) as server:
                server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(message)
            return

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            if settings.smtp_starttls:
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        raise OrderNotificationError('The order email could not be sent.') from error


def send_cod_order_notification(order: dict[str, Any]) -> None:
    send_order_notification(order)
