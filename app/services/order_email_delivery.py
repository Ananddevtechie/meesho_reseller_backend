import logging
from typing import Any

from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.models import Order
from app.services.order_notifications import OrderNotificationError, send_order_notification


logger = logging.getLogger(__name__)


def _notification_payload(order: Order) -> dict[str, Any]:
    return {
        'order_id': order.id,
        'product_sku': order.product_sku,
        'product_title': order.product_title,
        'quantity': order.quantity,
        'mrp': order.mrp,
        'discount': order.discount,
        'shipping': order.shipping,
        'tax': order.tax,
        'cod_fee': order.cod_fee,
        'total': order.total,
        'payment_method': order.payment_method,
        'payment_status': order.payment_status,
        'payment_reference': order.payment_reference,
        'full_name': order.customer_name,
        'customer_email': order.customer_email,
        'mobile': order.customer_mobile,
        'alternate_mobile': order.alternate_mobile,
        'address_line1': order.address_line1,
        'address_line2': order.address_line2,
        'landmark': order.landmark,
        'pin': order.pincode,
        'city': order.city,
        'state': order.state,
        'order_date': order.created_at.strftime('%Y-%m-%d %H:%M UTC'),
        'expected_delivery_range': order.expected_delivery_range,
    }


def deliver_order_email(order_id: str) -> None:
    try:
        with SessionLocal() as session:
            claim = session.execute(
                update(Order)
                .where(Order.id == order_id, Order.email_status.in_(('PENDING', 'FAILED')))
                .values(
                    email_status='SENDING',
                    email_attempts=Order.email_attempts + 1,
                    email_error=None,
                )
            )
            session.commit()
            if claim.rowcount != 1:
                return
            order = session.get(Order, order_id)
            if order is None:
                return
            payload = _notification_payload(order)
    except SQLAlchemyError:
        logger.exception('Could not claim order email delivery for order %s.', order_id)
        return

    email_error: str | None = None
    try:
        send_order_notification(payload)
    except OrderNotificationError as error:
        email_error = str(error)
        cause = error.__cause__
        logger.error(
            'Order email delivery failed for order %s (cause: %s).',
            order_id,
            type(cause).__name__ if cause else type(error).__name__,
        )

    try:
        with SessionLocal() as session:
            order = session.get(Order, order_id)
            if order is None or order.email_status != 'SENDING':
                return
            order.email_status = 'FAILED' if email_error else 'SENT'
            order.email_error = email_error
            session.commit()
    except SQLAlchemyError:
        logger.exception('Could not save order email delivery result for order %s.', order_id)