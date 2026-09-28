import hashlib
import hmac
from typing import Any, Optional, Union

import httpx

from app.config import settings


RAZORPAY_API_URL = 'https://api.razorpay.com/v1'


class RazorpayError(RuntimeError):
	"""Raised when Razorpay cannot create or verify a payment."""


def is_configured() -> bool:
	return bool(settings.razorpay_key_id and settings.razorpay_key_secret)


def _request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
	try:
		response = httpx.request(
			method,
			f'{RAZORPAY_API_URL}{path}',
			auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
			timeout=15,
			**kwargs,
		)
		response.raise_for_status()
		payload = response.json()
		if not isinstance(payload, dict):
			raise RazorpayError('Razorpay returned an invalid response.')
		return payload
	except (httpx.HTTPError, ValueError) as error:
		raise RazorpayError('Razorpay could not process the payment request.') from error


def create_order(amount: int, receipt: str, checkout_config_id: Optional[str] = None) -> str:
	payload_data: dict[str, Union[str, int]] = {
		'amount': amount,
		'currency': 'INR',
		'receipt': receipt[:40],
	}
	if checkout_config_id:
		payload_data['checkout_config_id'] = checkout_config_id
	payload = _request(
		'POST',
		'/orders',
		json=payload_data,
	)
	provider_order_id = payload.get('id')
	if not isinstance(provider_order_id, str) or not provider_order_id:
		raise RazorpayError('Razorpay returned an invalid order.')
	return provider_order_id


def fetch_payment(payment_id: str) -> dict[str, Any]:
	return _request('GET', f'/payments/{payment_id}')


def verify_payment_signature(provider_order_id: str, payment_id: str, signature: str) -> bool:
	message = f'{provider_order_id}|{payment_id}'.encode()
	expected = hmac.new(
		settings.razorpay_key_secret.encode(),
		message,
		hashlib.sha256,
	).hexdigest()
	return hmac.compare_digest(expected, signature)


def verify_webhook_signature(body: bytes, signature: str) -> bool:
	if not settings.razorpay_webhook_secret:
		return False
	expected = hmac.new(
		settings.razorpay_webhook_secret.encode(),
		body,
		hashlib.sha256,
	).hexdigest()
	return hmac.compare_digest(expected, signature)