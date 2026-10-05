import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.config import settings
from app.database import SessionLocal
from app.models import Order, OrderTrackingEvent, Product
from app.schemas import CodOrderRequest, CodOrderResponse
from app.services.order_notification_delivery import deliver_order_notification, is_stale_notification


router = APIRouter(prefix='/api/orders', tags=['orders'])


def _cod_order_response(order: Order) -> CodOrderResponse:
    if order.notification_status == 'SENT':
        notification_message = 'The store has been notified of your order.'
    elif order.notification_status == 'FAILED':
        notification_message = 'Your order is confirmed. The store notification is pending.'
    else:
        notification_message = 'Your order is confirmed. The store is being notified.'
    return CodOrderResponse(
        order_id=order.id,
        order_status='PLACED',
        payment_method='COD',
        payment_status='COD_PENDING',
        product_title=order.product_title,
        product_sku=order.product_sku,
        quantity=order.quantity,
        unit_price=order.unit_price,
        mrp=order.mrp,
        subtotal=order.subtotal,
        discount=order.discount,
        shipping=order.shipping,
        tax=order.tax,
        cod_fee=order.cod_fee,
        total=order.total,
        currency='INR',
        order_date=order.created_at,
        expected_delivery_range=order.expected_delivery_range,
        notification_status=order.notification_status,
        notification_message=notification_message,
    )


@router.post('/cod', response_model=CodOrderResponse, status_code=status.HTTP_201_CREATED)
def create_cod_order(
    request: CodOrderRequest,
    idempotency_key: Optional[str] = Header(default=None, alias='Idempotency-Key'),
) -> CodOrderResponse:
    key = (idempotency_key or uuid.uuid4().hex).strip()
    if not key or len(key) > 128:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Idempotency-Key must be 1 to 128 characters.')
    fingerprint = hashlib.sha256(request.model_dump_json().encode('utf-8')).hexdigest()
    try:
        with SessionLocal() as session:
            order = session.scalar(select(Order).where(Order.idempotency_key == key))
            if order is not None:
                if order.request_fingerprint != fingerprint:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Idempotency-Key was already used for different order details.')
            else:
                product = session.get(Product, request.product_id)
                if not product or not product.is_active:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='This product is no longer available.')
                if (
                    product.selling_price <= 0
                    or product.mrp < product.selling_price
                    or min(settings.cod_shipping_fee, settings.cod_tax_amount, settings.cod_fee) < 0
                ):
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Store pricing is not configured correctly.')

                subtotal = product.selling_price * request.quantity
                discount = (product.mrp - product.selling_price) * request.quantity
                total = subtotal + settings.cod_shipping_fee + settings.cod_tax_amount + settings.cod_fee
                now = datetime.now(timezone.utc)
                order = Order(
                    id=f"ORD-{uuid.uuid4().hex[:16].upper()}",
                    idempotency_key=key,
                    request_fingerprint=fingerprint,
                    product_id=product.id,
                    customer_id=request.customer_id,
                    product_sku=product.sku,
                    product_title=product.title,
                    quantity=request.quantity,
                    unit_price=product.selling_price,
                    mrp=product.mrp,
                    subtotal=subtotal,
                    discount=discount,
                    shipping=settings.cod_shipping_fee,
                    tax=settings.cod_tax_amount,
                    cod_fee=settings.cod_fee,
                    total=total,
                    currency='INR',
                    payment_method='COD',
                    payment_status='COD_PENDING',
                    order_status='PLACED',
                    delivery_status='ORDER_CONFIRMED',
                    payment_reference=None,
                    customer_name=request.full_name,
                    customer_email=request.customer_email,
                    customer_mobile=request.mobile,
                    alternate_mobile=request.alternate_mobile,
                    address_line1=request.address_line1,
                    address_line2=request.address_line2,
                    landmark=request.landmark,
                    city=request.city,
                    state=request.state,
                    pincode=request.pin,
                    expected_delivery_range=settings.cod_expected_delivery_range,
                    notification_status='PENDING',
                    notification_attempts=0,
                    notification_error=None,
                    whatsapp_opt_in=False,
                    whatsapp_status='NOT_OPTED_IN',
                    created_at=now,
                )
                session.add(order)
                session.add(OrderTrackingEvent(
                    id=uuid.uuid4().hex,
                    order_id=order.id,
                    status=order.delivery_status,
                    estimated_delivery_date=None,
                    created_at=now,
                ))
                session.commit()
    except IntegrityError as error:
        with SessionLocal() as session:
            order = session.scalar(select(Order).where(Order.idempotency_key == key))
        if order is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not save the COD order.') from error
        if order.request_fingerprint != fingerprint:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Idempotency-Key was already used for different order details.') from error
    except SQLAlchemyError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not save the COD order.') from error

    if order.notification_status in {'PENDING', 'FAILED'} or is_stale_notification(order):
        deliver_order_notification(order.id)
        try:
            with SessionLocal() as session:
                order = session.get(Order, order.id)
        except SQLAlchemyError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Order was saved, but its notification status could not be loaded.') from error
        if order is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Order was saved, but could not be loaded.')
    return _cod_order_response(order)