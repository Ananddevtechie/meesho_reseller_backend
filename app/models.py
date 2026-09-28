from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
	pass


class Order(Base):
	__tablename__ = 'customer_orders'
	__table_args__ = (UniqueConstraint('idempotency_key', name='uq_customer_orders_idempotency_key'),)

	id: Mapped[str] = mapped_column(String(40), primary_key=True)
	idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
	request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
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
	email_status: Mapped[str] = mapped_column(String(20), nullable=False, default='PENDING')
	email_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
	email_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
