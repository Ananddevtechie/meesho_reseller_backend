import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.schemas import CodOrderRequest, CodOrderResponse
from app.services.order_notifications import OrderNotificationError, send_cod_order_notification


router = APIRouter(prefix='/api/orders', tags=['orders'])


@router.post('/cod-email', response_model=CodOrderResponse, status_code=status.HTTP_201_CREATED)
@router.post('/cod', response_model=CodOrderResponse, status_code=status.HTTP_201_CREATED)
def create_cod_order(
    request: CodOrderRequest,
) -> CodOrderResponse:
    if request.product_id != settings.cod_product_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='This product is no longer available.',
        )
    if (
        settings.cod_product_price <= 0
        or settings.cod_product_mrp < settings.cod_product_price
        or min(settings.cod_shipping_fee, settings.cod_tax_amount, settings.cod_fee) < 0
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Store pricing is not configured correctly.',
        )

    subtotal = settings.cod_product_price * request.quantity
    discount = (settings.cod_product_mrp - settings.cod_product_price) * request.quantity
    total = subtotal + settings.cod_shipping_fee + settings.cod_tax_amount + settings.cod_fee
    now = datetime.now(timezone.utc)
    order_id = f"ORD-{uuid.uuid4().hex[:16].upper()}"
    order_payload = {
        'order_id': order_id,
        'product_id': settings.cod_product_id,
        'product_sku': settings.cod_product_id,
        'product_title': settings.cod_product_title,
        'quantity': request.quantity,
        'unit_price': settings.cod_product_price,
        'mrp': settings.cod_product_mrp,
        'subtotal': subtotal,
        'discount': discount,
        'shipping': settings.cod_shipping_fee,
        'tax': settings.cod_tax_amount,
        'cod_fee': settings.cod_fee,
        'total': total,
        'payment_method': 'COD',
        'payment_status': 'COD_PENDING',
        'payment_reference': None,
        'full_name': request.full_name,
        'customer_email': request.customer_email,
        'mobile': request.mobile,
        'alternate_mobile': request.alternate_mobile,
        'address_line1': request.address_line1,
        'address_line2': request.address_line2,
        'landmark': request.landmark,
        'pin': request.pin,
        'city': request.city,
        'state': request.state,
        'order_date': now.strftime('%Y-%m-%d %H:%M UTC'),
        'expected_delivery_range': settings.cod_expected_delivery_range,
    }
    try:
        send_cod_order_notification(order_payload)
    except OrderNotificationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error

    return CodOrderResponse(
        order_id=order_id,
        order_status='PLACED',
        payment_method='COD',
        payment_status='COD_PENDING',
        product_title=settings.cod_product_title,
        product_sku=settings.cod_product_id,
        quantity=request.quantity,
        unit_price=settings.cod_product_price,
        mrp=settings.cod_product_mrp,
        subtotal=subtotal,
        discount=discount,
        shipping=settings.cod_shipping_fee,
        tax=settings.cod_tax_amount,
        cod_fee=settings.cod_fee,
        total=total,
        currency='INR',
        order_date=now,
        expected_delivery_range=settings.cod_expected_delivery_range,
        email_status='SENT',
        email_notification_message=f'Order details emailed to {settings.order_notification_email}.',
        notification_recipient=settings.order_notification_email,
    )
