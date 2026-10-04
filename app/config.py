from pathlib import Path
from decimal import Decimal

from pydantic import field_validator
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
	telegram_bot_token: str = ''
	telegram_chat_id: str = ''

	@field_validator('*', mode='before')
	@classmethod
	def strip_string_values(cls, value):
		if isinstance(value, str):
			return value.strip()
		return value

	model_config = SettingsConfigDict(
		env_file=(PROJECT_ROOT / '.env', BACKEND_ROOT / '.env'),
		env_file_encoding='utf-8',
		extra='ignore',
	)


settings = Settings()
