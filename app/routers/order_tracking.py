from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.models import Order, OrderTrackingEvent, Product
from app.routers.products import _require_admin
from app.schemas import (
	AdminOrderTrackingResponse,
	AdminOrderTrackingUpdate,
	OrderTrackingEventResponse,
	OrderTrackingResponse,
)


router = APIRouter(tags=['order tracking'])
_TRACKABLE_PAYMENT_STATUSES = {'PAID', 'COD_PENDING'}


def _tracking_events(session, order_id: str) -> list[OrderTrackingEventResponse]:
	events = session.scalars(
		select(OrderTrackingEvent)
		.where(OrderTrackingEvent.order_id == order_id)
		.order_by(OrderTrackingEvent.created_at.asc())
	)
	return [
		OrderTrackingEventResponse(
			status=event.status,
			estimated_delivery_date=event.estimated_delivery_date,
			created_at=event.created_at,
		)
		for event in events
	]


def _tracking_response(
	session,
	order: Order,
	*,
	admin: bool,
	meesho_url: Optional[str] = None,
) -> OrderTrackingResponse:
	response_fields = {
		'order_id': order.id,
		'product_title': order.product_title,
		'product_sku': order.product_sku,
		'quantity': order.quantity,
		'total': order.total,
		'currency': 'INR',
		'payment_method': order.payment_method,
		'payment_status': order.payment_status,
		'delivery_status': order.delivery_status,
		'estimated_delivery_date': order.estimated_delivery_date,
		'order_date': order.created_at,
		'tracking_events': _tracking_events(session, order.id),
	}
	if admin:
		return AdminOrderTrackingResponse(
			**response_fields,
			customer_name=order.customer_name,
			customer_mobile=order.customer_mobile,
			alternate_mobile=order.alternate_mobile,
			customer_email=order.customer_email,
			address_line1=order.address_line1,
			address_line2=order.address_line2,
			landmark=order.landmark,
			city=order.city,
			state=order.state,
			pincode=order.pincode,
			mrp=order.mrp,
			discount=order.discount,
			shipping=order.shipping,
			tax=order.tax,
			cod_fee=order.cod_fee,
			payment_reference=order.payment_reference,
			meesho_url=meesho_url,
		)
	return OrderTrackingResponse(**response_fields)


@router.get('/api/admin/orders', response_model=list[AdminOrderTrackingResponse])
def list_admin_orders(authorization: Optional[str] = Header(default=None)) -> list[AdminOrderTrackingResponse]:
	_require_admin(authorization)
	try:
		with SessionLocal() as session:
			orders = list(session.scalars(select(Order).order_by(Order.created_at.desc())))
			product_ids = {order.product_id for order in orders}
			products = list(session.scalars(select(Product).where(Product.id.in_(product_ids)))) if product_ids else []
			meesho_urls = {product.id: product.meesho_url for product in products}
			return [
				_tracking_response(session, order, admin=True, meesho_url=meesho_urls.get(order.product_id))
				for order in orders
			]
	except SQLAlchemyError as error:
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail='Could not load orders.',
		) from error


@router.put('/api/admin/orders/{order_id}/tracking', response_model=AdminOrderTrackingResponse)
def update_admin_order_tracking(
	order_id: str,
	request: AdminOrderTrackingUpdate,
	authorization: Optional[str] = Header(default=None),
) -> AdminOrderTrackingResponse:
	_require_admin(authorization)
	try:
		with SessionLocal() as session:
			order = session.get(Order, order_id)
			if order is None:
				raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Order not found.')
			if order.order_status != 'PLACED' or order.payment_status not in _TRACKABLE_PAYMENT_STATUSES:
				raise HTTPException(
					status_code=status.HTTP_409_CONFLICT,
					detail='Delivery tracking can only be updated for confirmed orders.',
				)
			url_was_provided = 'meesho_url' in request.model_fields_set
			product = session.get(Product, order.product_id)
			if url_was_provided and product is None and request.meesho_url is not None:
				raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='The product linked to this order was not found.')
			status_changed = order.delivery_status != request.delivery_status
			date_changed = order.estimated_delivery_date != request.estimated_delivery_date
			url_changed = url_was_provided and product is not None and product.meesho_url != request.meesho_url
			if status_changed or date_changed:
				order.delivery_status = request.delivery_status
				order.estimated_delivery_date = request.estimated_delivery_date
				session.add(OrderTrackingEvent(
					id=uuid4().hex,
					order_id=order.id,
					status=order.delivery_status,
					estimated_delivery_date=order.estimated_delivery_date,
					created_at=datetime.now(timezone.utc),
				))
			if url_changed and product is not None:
				product.meesho_url = request.meesho_url
			if status_changed or date_changed or url_changed:
				session.commit()
			session.refresh(order)
			return _tracking_response(session, order, admin=True, meesho_url=product.meesho_url if product else None)
	except SQLAlchemyError as error:
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail='Could not update order tracking.',
		) from error


@router.get('/api/orders/{order_id}/tracking', response_model=OrderTrackingResponse)
def get_customer_order_tracking(order_id: str) -> OrderTrackingResponse:
	try:
		with SessionLocal() as session:
			order = session.get(Order, order_id)
			if order is None:
				raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Order not found.')
			if order.order_status != 'PLACED' or order.payment_status not in _TRACKABLE_PAYMENT_STATUSES:
				raise HTTPException(
					status_code=status.HTTP_409_CONFLICT,
					detail='Tracking is available after your order is confirmed.',
				)
			return _tracking_response(session, order, admin=False)
	except SQLAlchemyError as error:
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail='Could not load order tracking.',
		) from error
