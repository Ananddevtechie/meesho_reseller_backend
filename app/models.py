from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, JSON, LargeBinary, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
	pass


class User(Base):
	__tablename__ = 'users'
	__table_args__ = (UniqueConstraint('email', name='uq_users_email'),)

	id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
	full_name: Mapped[str] = mapped_column(String(120), nullable=False)
	email: Mapped[str] = mapped_column(String(255), nullable=False)
	password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
	role: Mapped[str] = mapped_column(String(30), nullable=False, default='reseller')
	is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		default=lambda: datetime.now(timezone.utc),
		onupdate=lambda: datetime.now(timezone.utc),
		nullable=False,
	)


class Product(Base):
	__tablename__ = 'products'
	__table_args__ = (UniqueConstraint('sku', name='uq_products_sku'),)

	id: Mapped[str] = mapped_column(String(100), primary_key=True)
	sku: Mapped[str] = mapped_column(String(100), nullable=False)
	title: Mapped[str] = mapped_column(String(255), nullable=False)
	category: Mapped[str] = mapped_column(String(80), nullable=False, default='Other')
	description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
	eyebrow: Mapped[str] = mapped_column(String(120), nullable=False, default='')
	image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
	meesho_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
	currency: Mapped[str] = mapped_column(String(3), nullable=False, default='INR')
	cost_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal('0.00'))
	selling_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
	mrp: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
	stock_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
	stock_label: Mapped[str] = mapped_column(String(120), nullable=False, default='Available now')
	gallery: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False, default=list)
	benefits: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False, default=list)
	features: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
	specifications: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False, default=list)
	package_contents: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
	faqs: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False, default=list)
	is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		default=lambda: datetime.now(timezone.utc),
		onupdate=lambda: datetime.now(timezone.utc),
		nullable=False,
	)


class ProductReview(Base):
	__tablename__ = 'product_reviews'
	__table_args__ = (CheckConstraint('rating >= 1 AND rating <= 5', name='ck_product_reviews_rating_range'),)

	id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
	product_id: Mapped[str] = mapped_column(ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
	reviewer_name: Mapped[str] = mapped_column(String(120), nullable=False)
	rating: Mapped[int] = mapped_column(Integer, nullable=False)
	comment: Mapped[str] = mapped_column(Text, nullable=False)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
	)


class ProductReviewImage(Base):
	__tablename__ = 'product_review_images'

	id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
	review_id: Mapped[str] = mapped_column(ForeignKey('product_reviews.id', ondelete='CASCADE'), nullable=False)
	content_type: Mapped[str] = mapped_column(String(40), nullable=False)
	image_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class Admin(Base):
	__tablename__ = 'admins'
	__table_args__ = (UniqueConstraint('username', name='uq_admins_username'),)

	id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
	username: Mapped[str] = mapped_column(String(120), nullable=False)
	password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
	)


class Customer(Base):
	__tablename__ = 'customers'
	__table_args__ = (UniqueConstraint('full_name', 'mobile', name='uq_customers_name_mobile'),)

	id: Mapped[str] = mapped_column(String(141), primary_key=True)
	full_name: Mapped[str] = mapped_column(String(120), nullable=False)
	email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
	mobile: Mapped[str] = mapped_column(String(20), nullable=False)
	alternate_mobile: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
	address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
	address_line2: Mapped[str] = mapped_column(String(255), nullable=False)
	landmark: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
	city: Mapped[str] = mapped_column(String(100), nullable=False)
	state: Mapped[str] = mapped_column(String(100), nullable=False)
	pincode: Mapped[str] = mapped_column(String(6), nullable=False)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		default=lambda: datetime.now(timezone.utc),
		onupdate=lambda: datetime.now(timezone.utc),
		nullable=False,
	)


class Order(Base):
	__tablename__ = 'orders'
	__table_args__ = (UniqueConstraint('idempotency_key', name='uq_orders_idempotency_key'),)

	id: Mapped[str] = mapped_column(String(40), primary_key=True)
	idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
	request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
	user_id: Mapped[Optional[str]] = mapped_column(ForeignKey('users.id'), nullable=True)
	customer_id: Mapped[Optional[str]] = mapped_column(ForeignKey('customers.id'), nullable=True)
	product_id: Mapped[str] = mapped_column(String(100), nullable=False)
	product_sku: Mapped[str] = mapped_column(String(100), nullable=False)
	product_title: Mapped[str] = mapped_column(String(255), nullable=False)
	quantity: Mapped[int] = mapped_column(Integer, nullable=False)
	unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
	mrp: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
	subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
	discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
	shipping: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
	tax: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
	cod_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
	total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
	currency: Mapped[str] = mapped_column(String(3), nullable=False, default='INR')
	payment_method: Mapped[str] = mapped_column(String(20), nullable=False, default='COD')
	payment_status: Mapped[str] = mapped_column(String(30), nullable=False, default='COD_PENDING')
	order_status: Mapped[str] = mapped_column(String(30), nullable=False, default='PLACED')
	payment_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
	customer_name: Mapped[str] = mapped_column(String(120), nullable=False)
	customer_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
	customer_mobile: Mapped[str] = mapped_column(String(20), nullable=False)
	alternate_mobile: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
	address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
	address_line2: Mapped[str] = mapped_column(String(255), nullable=False)
	landmark: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
	city: Mapped[str] = mapped_column(String(100), nullable=False)
	state: Mapped[str] = mapped_column(String(100), nullable=False)
	pincode: Mapped[str] = mapped_column(String(6), nullable=False)
	expected_delivery_range: Mapped[str] = mapped_column(String(120), nullable=False)
	notification_status: Mapped[str] = mapped_column(String(20), nullable=False, default='PENDING')
	notification_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
	notification_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
	whatsapp_opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
	whatsapp_status: Mapped[str] = mapped_column(String(30), nullable=False, default='NOT_OPTED_IN')
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		default=lambda: datetime.now(timezone.utc),
		nullable=False,
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		default=lambda: datetime.now(timezone.utc),
		onupdate=lambda: datetime.now(timezone.utc),
		nullable=False,
	)


class OrderItem(Base):
	__tablename__ = 'order_items'

	id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
	order_id: Mapped[str] = mapped_column(ForeignKey('orders.id', ondelete='CASCADE'), nullable=False)
	product_id: Mapped[Optional[str]] = mapped_column(ForeignKey('products.id'), nullable=True)
	product_sku: Mapped[str] = mapped_column(String(100), nullable=False)
	product_title: Mapped[str] = mapped_column(String(255), nullable=False)
	quantity: Mapped[int] = mapped_column(Integer, nullable=False)
	unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
	discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal('0.00'))
	line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
	)


class Payment(Base):
	__tablename__ = 'payments'

	id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
	order_id: Mapped[str] = mapped_column(ForeignKey('orders.id', ondelete='CASCADE'), nullable=False)
	provider: Mapped[str] = mapped_column(String(40), nullable=False)
	provider_order_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
	provider_payment_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
	method: Mapped[str] = mapped_column(String(30), nullable=False)
	status: Mapped[str] = mapped_column(String(30), nullable=False)
	amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
	currency: Mapped[str] = mapped_column(String(3), nullable=False, default='INR')
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		default=lambda: datetime.now(timezone.utc),
		onupdate=lambda: datetime.now(timezone.utc),
		nullable=False,
	)


class Shipment(Base):
	__tablename__ = 'shipments'

	id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
	order_id: Mapped[str] = mapped_column(ForeignKey('orders.id', ondelete='CASCADE'), nullable=False)
	carrier: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
	tracking_number: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
	status: Mapped[str] = mapped_column(String(30), nullable=False, default='PENDING')
	shipped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
	delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		default=lambda: datetime.now(timezone.utc),
		onupdate=lambda: datetime.now(timezone.utc),
		nullable=False,
	)


class Expense(Base):
	__tablename__ = 'expenses'

	id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
	user_id: Mapped[Optional[str]] = mapped_column(ForeignKey('users.id'), nullable=True)
	category: Mapped[str] = mapped_column(String(80), nullable=False)
	description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
	amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
	currency: Mapped[str] = mapped_column(String(3), nullable=False, default='INR')
	expense_date: Mapped[date] = mapped_column(Date, nullable=False)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
	)


class ProfitLoss(Base):
	__tablename__ = 'profit_loss'

	id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
	period_start: Mapped[date] = mapped_column(Date, nullable=False)
	period_end: Mapped[date] = mapped_column(Date, nullable=False)
	revenue: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
	cost_of_goods: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
	expenses: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
	net_profit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
	currency: Mapped[str] = mapped_column(String(3), nullable=False, default='INR')
	generated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
	)


class Notification(Base):
	__tablename__ = 'notifications'

	id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
	order_id: Mapped[Optional[str]] = mapped_column(ForeignKey('orders.id', ondelete='SET NULL'), nullable=True)
	customer_id: Mapped[Optional[str]] = mapped_column(ForeignKey('customers.id', ondelete='SET NULL'), nullable=True)
	channel: Mapped[str] = mapped_column(String(30), nullable=False)
	recipient: Mapped[str] = mapped_column(String(255), nullable=False)
	subject: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
	status: Mapped[str] = mapped_column(String(30), nullable=False, default='PENDING')
	provider_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
	error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
	sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		default=lambda: datetime.now(timezone.utc),
		onupdate=lambda: datetime.now(timezone.utc),
		nullable=False,
	)
