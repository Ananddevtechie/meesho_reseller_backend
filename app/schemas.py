from decimal import Decimal
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class AddressExtractionRequest(BaseModel):
	text: str = Field(min_length=1, max_length=10_000)


class ExtractedAddress(BaseModel):
	name: str = ''
	address: str = ''
	district: str = ''
	pin: str = ''
	mobile: str = ''


class CustomerSaveRequest(BaseModel):
	full_name: str = Field(min_length=2, max_length=120)
	mobile: str = Field(pattern=r'^[6-9][0-9]{9}$')
	alternate_mobile: Optional[str] = Field(default=None, pattern=r'^[6-9][0-9]{9}$')
	address_line1: str = Field(min_length=2, max_length=255)
	address_line2: str = Field(min_length=2, max_length=255)
	pincode: str = Field(pattern=r'^[0-9]{6}$')
	city: str = Field(min_length=2, max_length=100)
	state: str = Field(min_length=2, max_length=100)
	landmark: Optional[str] = Field(default=None, max_length=255)

	@field_validator('full_name', 'address_line1', 'address_line2', 'city', 'state')
	@classmethod
	def normalize_required_text(cls, value: str) -> str:
		normalized = value.strip()
		if not normalized:
			raise ValueError('This field cannot be blank.')
		return normalized

	@field_validator('landmark', mode='before')
	@classmethod
	def normalize_landmark(cls, value: Optional[str]) -> Optional[str]:
		if isinstance(value, str):
			return value.strip() or None
		return value


class CustomerSaveResponse(BaseModel):
	customer_id: str


class CodOrderRequest(BaseModel):
	product_id: str = Field(min_length=1, max_length=100)
	quantity: int = Field(ge=1, le=10)
	customer_id: Optional[str] = Field(default=None, min_length=36, max_length=36)
	full_name: str = Field(min_length=2, max_length=120)
	mobile: str = Field(pattern=r'^[6-9][0-9]{9}$')
	alternate_mobile: Optional[str] = Field(default=None, pattern=r'^[6-9][0-9]{9}$')
	address_line1: str = Field(min_length=2, max_length=255)
	address_line2: str = Field(min_length=2, max_length=255)
	pin: str = Field(pattern=r'^[0-9]{6}$')
	city: str = Field(min_length=2, max_length=100)
	state: str = Field(min_length=2, max_length=100)
	landmark: Optional[str] = Field(default=None, max_length=255)
	customer_email: Optional[str] = Field(default=None, max_length=255)

	@field_validator('full_name', 'address_line1', 'address_line2', 'city', 'state')
	@classmethod
	def normalize_required_text(cls, value: str) -> str:
		normalized = value.strip()
		if not normalized:
			raise ValueError('This field cannot be blank.')
		return normalized

	@field_validator('landmark', mode='before')
	@classmethod
	def normalize_landmark(cls, value: Optional[str]) -> Optional[str]:
		if isinstance(value, str):
			return value.strip() or None
		return value



class CodOrderResponse(BaseModel):
	order_id: str
	order_status: Literal['PLACED']
	payment_method: Literal['COD']
	payment_status: Literal['COD_PENDING']
	product_title: str
	product_sku: str
	quantity: int
	unit_price: Decimal
	mrp: Decimal
	subtotal: Decimal
	discount: Decimal
	shipping: Decimal
	tax: Decimal
	cod_fee: Decimal
	total: Decimal
	currency: Literal['INR']
	order_date: datetime
	expected_delivery_range: str
	email_status: Literal['PENDING', 'SENDING', 'SENT', 'FAILED']
	email_notification_message: str
	notification_recipient: str


class RazorpayOrderResponse(BaseModel):
	order_id: str
	key_id: str
	provider_order_id: str
	checkout_config_id: str
	amount: int
	currency: Literal['INR']
	product_title: str
	customer_name: str
	customer_mobile: str
	customer_email: Optional[str]


class RazorpayVerificationRequest(BaseModel):
	order_id: str = Field(min_length=1, max_length=40)
	provider_order_id: str = Field(min_length=1, max_length=100)
	payment_id: str = Field(min_length=1, max_length=100)
	signature: str = Field(min_length=64, max_length=128)


class PaidOrderResponse(BaseModel):
	order_id: str
	order_status: Literal['PLACED']
	payment_method: Literal['UPI']
	payment_status: Literal['PAID']
	product_title: str
	product_sku: str
	quantity: int
	total: Decimal
	currency: Literal['INR']
	order_date: datetime
	expected_delivery_range: str
	email_status: Literal['PENDING', 'SENDING', 'SENT', 'FAILED']
	email_notification_message: str
	notification_recipient: str



class PaymentStatusResponse(BaseModel):
	order_id: str
	order_status: Literal['PAYMENT_PENDING', 'PAYMENT_FAILED', 'PLACED']
	payment_method: Literal['UPI']
	payment_status: Literal['PAYMENT_PENDING', 'PAYMENT_FAILED', 'PAID']
	product_title: str
	product_sku: str
	quantity: int
	total: Decimal
	currency: Literal['INR']
	order_date: datetime
	expected_delivery_range: str
	email_status: Literal['PENDING', 'SENDING', 'SENT', 'FAILED']
	email_notification_message: str
	notification_recipient: str
