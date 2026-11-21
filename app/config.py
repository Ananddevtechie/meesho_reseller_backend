from pathlib import Path
from decimal import Decimal
from email.utils import parseaddr
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
	gemini_api_key: str = ''
	gemini_model: str = 'gemini-2.0-flash'
	database_url: str
	admin_username: str = ''
	admin_password: str = ''
	cod_shipping_fee: Decimal = Decimal('0.00')
	cod_tax_amount: Decimal = Decimal('0.00')
	cod_fee: Decimal = Decimal('0.00')
	cod_expected_delivery_range: str = 'To be confirmed'
	razorpay_key_id: str = ''
	razorpay_key_secret: str = ''
	razorpay_checkout_config_id: str = ''
	razorpay_webhook_secret: str = ''
	supabase_url: str = ''
	supabase_service_role_key: str = ''
	public_api_url: str = ''
	smtp_host: str = ''
	smtp_port: int = Field(default=587, ge=1, le=65535)
	smtp_username: str = ''
	smtp_password: str = ''
	smtp_use_tls: bool = True
	email_from: str = ''
	ebook_entitlement_ttl_days: int = Field(default=30, gt=0)
	ebook_download_token_ttl_hours: int = Field(default=168, gt=0)
	ebook_download_limit: int = Field(default=5, gt=0)
	ebook_email_poll_seconds: int = Field(default=5, ge=1, le=300)
	apify_api_token: str = ''
	telegram_bot_token: str = ''
	telegram_chat_id: str = ''

	@field_validator('*', mode='before')
	@classmethod
	def strip_string_values(cls, value):
		if isinstance(value, str):
			return value.strip()
		return value

	@field_validator('public_api_url')
	@classmethod
	def validate_public_api_url(cls, value: str) -> str:
		if not value:
			return value
		parsed = urlparse(value)
		is_local = parsed.hostname in {'localhost', '127.0.0.1', '::1'}
		if (
			parsed.scheme not in {'http', 'https'}
			or not parsed.hostname
			or parsed.username
			or parsed.password
			or (parsed.scheme != 'https' and not is_local)
		):
			raise ValueError('PUBLIC_API_URL must use HTTPS except for a local development host.')
		if parsed.path not in {'', '/'} or parsed.query or parsed.fragment:
			raise ValueError('PUBLIC_API_URL cannot include a path, query string, or fragment.')
		return value.rstrip('/')

	@field_validator('supabase_url')
	@classmethod
	def validate_supabase_url(cls, value: str) -> str:
		if not value:
			return value
		parsed = urlparse(value)
		is_local = parsed.hostname in {'localhost', '127.0.0.1', '::1'}
		if (
			parsed.scheme not in {'http', 'https'}
			or not parsed.hostname
			or parsed.username
			or parsed.password
			or (parsed.scheme != 'https' and not is_local)
		):
			raise ValueError('SUPABASE_URL must use HTTPS except for a local development host.')
		if parsed.path not in {'', '/'} or parsed.query or parsed.fragment:
			raise ValueError('SUPABASE_URL cannot include a path, query string, or fragment.')
		return value.rstrip('/')

	@field_validator('email_from')
	@classmethod
	def validate_email_from(cls, value: str) -> str:
		if not value:
			return value
		if '\r' in value or '\n' in value or '@' not in parseaddr(value)[1]:
			raise ValueError('EMAIL_FROM must be a valid email address or display-name address.')
		return value

	model_config = SettingsConfigDict(
		env_file=(PROJECT_ROOT / '.env', BACKEND_ROOT / '.env'),
		env_file_encoding='utf-8',
		extra='ignore',
	)


settings = Settings()
