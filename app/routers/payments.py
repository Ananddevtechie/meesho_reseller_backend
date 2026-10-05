import hashlib
import json
import uuid
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database import SessionLocal
from app.models import Customer, Order, Product
from app.schemas import (
	CodOrderRequest,
	PaidOrderResponse,
	PaymentStatusResponse,
	RazorpayOrderResponse,
	RazorpayVerificationRequest,
)
from app.services.order_notification_delivery import deliver_order_notification, is_stale_notification
from app.services.razorpay import (
	RazorpayAuthenticationError,
	RazorpayError,
	create_order as create_razorpay_order,
	fetch_order_payments,
	fetch_payment,
	is_configured as razorpay_is_configured,
	verify_payment_signature,
	verify_webhook_signature,
)


router = APIRouter(prefix='/api/payments/razorpay', tags=['payments'])


def _priced_total(request: CodOrderRequest, product: Product) -> tuple[Decimal, Decimal, Decimal]:
	if not product.is_active:
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='This product is no longer available.')
	if (
		product.selling_price <= 0
		or product.mrp < product.selling_price
		or min(settings.cod_shipping_fee, settings.cod_tax_amount, settings.cod_fee) < 0
	):
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail='Store pricing is not configured correctly.',
		)
	subtotal = product.selling_price * request.quantity
	discount = (product.mrp - product.selling_price) * request.quantity
	total = subtotal + settings.cod_shipping_fee + settings.cod_tax_amount
	return subtotal, discount, total


def _paid_response(order: Order) -> PaidOrderResponse:
	message = (
		'The store has been notified of your order.'
		if order.notification_status == 'SENT'
		else 'Payment confirmed. The store will follow up with your order details.'
	)
	return PaidOrderResponse(
		order_id=order.id,
		order_status='PLACED',
		payment_method='UPI',
		payment_status='PAID',
		product_title=order.product_title,
		product_sku=order.product_sku,
		quantity=order.quantity,
		total=order.total,
		currency='INR',
		order_date=order.created_at,
		expected_delivery_range=order.expected_delivery_range,
		notification_status=order.notification_status,
		notification_message=message,
	)


def _payment_status_response(order: Order) -> PaymentStatusResponse:
	message = (
		'The store has been notified of your order.'
		if order.notification_status == 'SENT'
		else 'Payment confirmed. The store will follow up with your order details.'
		if order.payment_status == 'PAID'
		else 'Waiting for payment provider confirmation.'
	)
	return PaymentStatusResponse(
		order_id=order.id,
		order_status=order.order_status,
		payment_method='UPI',
		payment_status=order.payment_status,
		product_title=order.product_title,
		product_sku=order.product_sku,
		quantity=order.quantity,
		total=order.total,
		currency='INR',
		order_date=order.created_at,
		expected_delivery_range=order.expected_delivery_range,
		notification_status=order.notification_status,
		notification_message=message,
	)


@router.post('/orders', response_model=RazorpayOrderResponse, status_code=status.HTTP_201_CREATED)
def create_payment_order(request: CodOrderRequest) -> RazorpayOrderResponse:
	if not razorpay_is_configured():
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail='Razorpay is not configured. Set the Razorpay test API keys in backend/.env.',
		)
	with SessionLocal() as session:
		product = session.get(Product, request.product_id)
		if not product or not product.is_active:
			raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='This product is no longer available.')
		customer = session.get(Customer, request.customer_id) if request.customer_id else None
		if not customer:
			raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Save customer details before starting payment.')
		customer_details = {
			'id': customer.id,
			'full_name': customer.full_name,
			'email': customer.email,
			'mobile': customer.mobile,
			'alternate_mobile': customer.alternate_mobile,
			'address_line1': customer.address_line1,
			'address_line2': customer.address_line2,
			'landmark': customer.landmark,
			'city': customer.city,
			'state': customer.state,
			'pincode': customer.pincode,
		}
	subtotal, discount, total = _priced_total(request, product)
	amount = int((total * 100).to_integral_exact())
	if amount < 100:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail='The minimum payment amount is ₹1.00.',
		)
	order_id = f"ORD-{uuid.uuid4().hex[:16].upper()}"
	try:
		provider_order_id = create_razorpay_order(amount, order_id, settings.razorpay_checkout_config_id or None)
	except RazorpayAuthenticationError as error:
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error
	except RazorpayError as error:
		raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)) from error

	order = Order(
		id=order_id,
		idempotency_key=f'UPI-{provider_order_id}',
		request_fingerprint=hashlib.sha256(request.model_dump_json().encode()).hexdigest(),
		product_id=product.id,
		customer_id=customer_details['id'],
		product_sku=product.sku,
		product_title=product.title,
		quantity=request.quantity,
		unit_price=product.selling_price,
		mrp=product.mrp,
		subtotal=subtotal,
		discount=discount,
		shipping=settings.cod_shipping_fee,
		tax=settings.cod_tax_amount,
		cod_fee=Decimal('0.00'),
		total=total,
		currency='INR',
		payment_method='UPI',
		payment_status='PAYMENT_PENDING',
		order_status='PAYMENT_PENDING',
		payment_reference=provider_order_id,
		customer_name=customer_details['full_name'],
		customer_email=customer_details['email'],
		customer_mobile=customer_details['mobile'],
		alternate_mobile=customer_details['alternate_mobile'],
		address_line1=customer_details['address_line1'],
		address_line2=customer_details['address_line2'],
		landmark=customer_details['landmark'],
		city=customer_details['city'],
		state=customer_details['state'],
		pincode=customer_details['pincode'],
		expected_delivery_range=settings.cod_expected_delivery_range,
		notification_status='PENDING',
		notification_attempts=0,
	)
	try:
		with SessionLocal() as session:
			session.add(order)
			session.commit()
	except SQLAlchemyError as error:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not save the pending order.') from error

	return RazorpayOrderResponse(
		order_id=order_id,
		key_id=settings.razorpay_key_id,
		provider_order_id=provider_order_id,
		checkout_config_id=settings.razorpay_checkout_config_id or '',
		amount=amount,
		currency='INR',
		product_title=product.title,
		customer_name=customer_details['full_name'],
		customer_mobile=customer_details['mobile'],
		customer_email=customer_details['email'],
	)


def _validate_captured_payment(provider_order_id: str, payment_id: str, signature: str) -> dict[str, Any]:
	if not verify_payment_signature(provider_order_id, payment_id, signature):
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Payment signature is invalid.')
	try:
		payment = fetch_payment(payment_id)
	except RazorpayAuthenticationError as error:
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error
	except RazorpayError as error:
		raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)) from error
	if (
		payment.get('order_id') != provider_order_id
		or payment.get('status') != 'captured'
		or payment.get('method') != 'upi'
	):
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='UPI payment is not captured yet.')
	return payment


def _confirm_order(order_id: str, provider_order_id: str, payment_id: str, payment: dict[str, Any]) -> PaidOrderResponse:
	with SessionLocal() as session:
		order = session.get(Order, order_id)
		if not order or order.payment_method != 'UPI':
			raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Payment order was not found.')
		if order.payment_status == 'PAID':
			if order.idempotency_key == f'UPI-{provider_order_id}' and order.payment_reference == payment_id:
				return _paid_response(order)
			raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='This order has already been paid.')
		if order.payment_reference != provider_order_id:
			raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Payment order was not found.')
		expected_amount = int((order.total * 100).to_integral_exact())
		if payment.get('amount') != expected_amount or payment.get('currency') != order.currency:
			raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Payment amount does not match the order.')
		order.order_status = 'PLACED'
		order.payment_status = 'PAID'
		order.payment_reference = payment_id
		session.commit()
		order_id = order.id

	with SessionLocal() as session:
		order = session.get(Order, order_id)
		if not order:
			raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Order was not found.')
		should_notify = order.notification_status in {'PENDING', 'FAILED'} or is_stale_notification(order)
	if should_notify:
		deliver_order_notification(order.id)
	with SessionLocal() as session:
		order = session.get(Order, order_id)
		if not order:
			raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Order was not found.')
		return _paid_response(order)


@router.get('/orders/{order_id}/status', response_model=PaymentStatusResponse)
def get_payment_status(order_id: str) -> PaymentStatusResponse:
	with SessionLocal() as session:
		order = session.get(Order, order_id)
		if not order or order.payment_method != 'UPI':
			raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Payment order was not found.')
		response = _payment_status_response(order)
		provider_order_id = order.payment_reference if order.payment_status == 'PAYMENT_PENDING' else None
	if provider_order_id and razorpay_is_configured():
		try:
			payments = fetch_order_payments(provider_order_id)
		except RazorpayAuthenticationError as error:
			raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error
		except RazorpayError as error:
			raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)) from error
		captured_payment = next(
			(
				payment for payment in payments
				if payment.get('order_id') == provider_order_id
				and payment.get('status') == 'captured'
				and payment.get('method') == 'upi'
				and isinstance(payment.get('id'), str)
				and payment['id']
			),
			None,
		)
		if captured_payment:
			confirmed = _confirm_order(
				order_id,
				provider_order_id,
				captured_payment.get('id', ''),
				captured_payment,
			)
			return PaymentStatusResponse.model_validate(confirmed.model_dump())
	return response


@router.post('/verify', response_model=PaymentStatusResponse)
def verify_payment(request: RazorpayVerificationRequest) -> PaymentStatusResponse:
	with SessionLocal() as session:
		order = session.get(Order, request.order_id)
		if not order or order.payment_method != 'UPI' or not order.idempotency_key.startswith('UPI-'):
			raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Payment order was not found.')
		provider_order_id = order.idempotency_key.removeprefix('UPI-')
		if request.provider_order_id != provider_order_id:
			raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Payment order was not found.')
		if order.payment_status == 'PAID' and order.payment_reference != request.payment_id:
			raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='This order has already been paid.')
	payment = _validate_captured_payment(provider_order_id, request.payment_id, request.signature)
	confirmed = _confirm_order(request.order_id, provider_order_id, request.payment_id, payment)
	return PaymentStatusResponse.model_validate(confirmed.model_dump())


@router.post('/webhook')
async def razorpay_webhook(
	request: Request,
	x_razorpay_signature: Optional[str] = Header(default=None),
) -> dict[str, str]:
	body = await request.body()
	if not x_razorpay_signature or not verify_webhook_signature(body, x_razorpay_signature):
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Webhook signature is invalid.')
	try:
		event = json.loads(body)
	except (json.JSONDecodeError, UnicodeDecodeError) as error:
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Webhook payload is invalid.') from error
	event_name = event.get('event')
	if event_name not in {'order.paid', 'payment.failed'}:
		return {'status': 'ignored'}
	entities = event.get('payload', {})
	payment = entities.get('payment', {}).get('entity', {})
	if event_name == 'payment.failed' and (payment.get('status') != 'failed' or payment.get('method') != 'upi'):
		return {'status': 'ignored'}
	provider_order_id = payment.get('order_id')
	payment_id = payment.get('id')
	if not isinstance(provider_order_id, str) or not isinstance(payment_id, str):
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Webhook payment details are missing.')
	with SessionLocal() as session:
		order = session.scalar(select(Order).where(Order.payment_reference == provider_order_id))
		if not order:
			return {'status': 'ignored'}
		if event_name == 'payment.failed':
			if order.payment_status == 'PAYMENT_PENDING':
				order.payment_status = 'PAYMENT_FAILED'
				order.order_status = 'PAYMENT_FAILED'
				session.commit()
			return {'status': 'processed'}
		order_id = order.id
	if payment.get('status') != 'captured' or payment.get('method') != 'upi':
		return {'status': 'ignored'}
	_confirm_order(order_id, provider_order_id, payment_id, payment)
	return {'status': 'processed'}