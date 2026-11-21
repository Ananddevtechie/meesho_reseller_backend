import asyncio
import hashlib
import html
import logging
import re
import secrets
import smtplib
import ssl
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import quote

import httpx
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database import SessionLocal
from app.models import EbookDownloadToken, EbookEmailJob, EbookEntitlement, Order, Product


logger = logging.getLogger(__name__)
_MAX_EMAIL_ATTEMPTS = 5
_STALE_JOB_LOCK = timedelta(minutes=10)
_MAX_EBOOK_BYTES = 50 * 1024 * 1024


class EbookDeliveryError(RuntimeError):
	pass


class EbookStorageError(EbookDeliveryError):
	pass


class EbookEmailError(EbookDeliveryError):
	pass


def is_book_category(category: str | None) -> bool:
	return isinstance(category, str) and category.strip().lower() == 'book'


def storage_is_configured() -> bool:
	return bool(settings.supabase_url and settings.supabase_service_role_key)


def email_is_configured() -> bool:
	return bool(
		settings.smtp_host
		and settings.email_from
		and settings.smtp_port > 0
		and settings.public_api_url
		and (
			settings.smtp_use_tls
			or settings.smtp_host.lower() in {'localhost', '127.0.0.1', '::1'}
		)
		and (bool(settings.smtp_username) == bool(settings.smtp_password))
	)


def ensure_ebook_entitlement(session, order: Order, product: Product) -> EbookEntitlement | None:
	if not is_book_category(product.category):
		return None
	if not product.ebook_storage_path:
		raise EbookDeliveryError('The Book product does not have a private PDF storage path.')
	if not order.customer_email:
		raise EbookDeliveryError('The Book order does not have a customer email address.')

	entitlement = session.scalar(
		select(EbookEntitlement).where(EbookEntitlement.order_id == order.id)
	)
	if entitlement is not None:
		return entitlement

	now = datetime.now(timezone.utc)
	entitlement = EbookEntitlement(
		id=uuid.uuid4().hex,
		order_id=order.id,
		product_id=product.id,
		storage_path=product.ebook_storage_path,
		download_count=0,
		download_limit=settings.ebook_download_limit,
		created_at=now,
		expires_at=now + timedelta(days=settings.ebook_entitlement_ttl_days),
	)
	session.add(entitlement)
	session.flush()
	session.add(EbookEmailJob(
		id=uuid.uuid4().hex,
		entitlement_id=entitlement.id,
		status='PENDING',
		attempts=0,
		next_attempt_at=now,
		created_at=now,
		updated_at=now,
	))
	return entitlement


def _new_download_token(session, entitlement: EbookEntitlement, now: datetime) -> tuple[str, datetime]:
	if entitlement.revoked_at or entitlement.expires_at <= now:
		raise EbookDeliveryError('This eBook entitlement has expired or been revoked.')
	token = secrets.token_urlsafe(32)
	expires_at = min(
		entitlement.expires_at,
		now + timedelta(hours=settings.ebook_download_token_ttl_hours),
	)
	session.add(EbookDownloadToken(
		id=uuid.uuid4().hex,
		entitlement_id=entitlement.id,
		token_hash=hashlib.sha256(token.encode('utf-8')).hexdigest(),
		created_at=now,
		expires_at=expires_at,
	))
	return token, expires_at


def create_download_link(session, entitlement: EbookEntitlement) -> tuple[str, datetime]:
	token, expires_at = _new_download_token(session, entitlement, datetime.now(timezone.utc))
	session.flush()
	return f"{settings.public_api_url.rstrip('/')}/api/ebooks/download/{token}", expires_at


def _send_email(
	recipient: str,
	customer_name: str,
	product_title: str,
	download_url: str,
	expires_at: datetime,
	pdf_data: bytes,
) -> None:
	if not email_is_configured():
		raise EbookEmailError('SMTP, EMAIL_FROM, and PUBLIC_API_URL must be securely configured for Book delivery.')

	message = EmailMessage()
	message['Subject'] = f'Your eBook is ready: {" ".join(product_title.split())[:180]}'
	message['From'] = settings.email_from
	message['To'] = recipient
	filename = re.sub(r'[^A-Za-z0-9._-]+', '-', product_title).strip('-.')[:120] or 'ebook'
	expiry_text = expires_at.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
	message.set_content(
		f'Hello {customer_name},\n\n'
		f'Your purchased book PDF, "{product_title}", is attached to this email.\n\n'
		f'You can also download it securely here:\n{download_url}\n\n'
		f'This secure link expires at {expiry_text}. Please keep it private.\n'
	)
	message.add_alternative(
		'<html><body>'
		f'<p>Hello {html.escape(customer_name)},</p>'
		f'<p>Your purchased book PDF, <strong>{html.escape(product_title)}</strong>, is attached.</p>'
		f'<p><a href="{html.escape(download_url, quote=True)}">Download your eBook</a></p>'
		f'<p>This secure link expires at {html.escape(expiry_text)}. Please keep it private.</p>'
		'</body></html>',
		subtype='html',
	)
	message.add_attachment(
		pdf_data,
		maintype='application',
		subtype='pdf',
		filename=f'{filename}.pdf',
	)

	try:
		if settings.smtp_use_tls and settings.smtp_port == 465:
			with smtplib.SMTP_SSL(
				settings.smtp_host,
				settings.smtp_port,
				timeout=20,
				context=ssl.create_default_context(),
			) as client:
				if settings.smtp_username:
					client.login(settings.smtp_username, settings.smtp_password)
				client.send_message(message)
		else:
			with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as client:
				if settings.smtp_use_tls:
					client.starttls(context=ssl.create_default_context())
				if settings.smtp_username:
					client.login(settings.smtp_username, settings.smtp_password)
				client.send_message(message)
	except (OSError, smtplib.SMTPException, ValueError) as error:
		raise EbookEmailError('SMTP could not deliver the eBook email.') from error


def process_next_email_job() -> bool:
	now = datetime.now(timezone.utc)
	with SessionLocal() as session:
		job = session.scalar(
			select(EbookEmailJob)
			.where(
				EbookEmailJob.attempts < _MAX_EMAIL_ATTEMPTS,
				or_(
					(EbookEmailJob.status.in_(('PENDING', 'RETRY')) & (EbookEmailJob.next_attempt_at <= now)),
					(EbookEmailJob.status == 'PROCESSING') & (EbookEmailJob.locked_at < now - _STALE_JOB_LOCK),
				),
			)
			.order_by(EbookEmailJob.created_at)
			.with_for_update(skip_locked=True)
			.limit(1)
		)
		if job is None:
			return False
		job.status = 'PROCESSING'
		job.locked_at = now
		job.attempts += 1
		job.last_error = None
		entitlement = session.get(EbookEntitlement, job.entitlement_id)
		if entitlement is None:
			job.status = 'FAILED'
			job.last_error = 'The eBook entitlement no longer exists.'
			job.locked_at = None
			session.commit()
			return True
		order = session.get(Order, entitlement.order_id)
		if order is None or order.payment_status != 'PAID' or not order.customer_email:
			job.status = 'FAILED'
			job.last_error = 'The paid order or customer email is unavailable.'
			job.locked_at = None
			session.commit()
			return True
		try:
			token, expires_at = _new_download_token(session, entitlement, now)
		except EbookDeliveryError as error:
			job.status = 'FAILED'
			job.last_error = str(error)
			job.locked_at = None
			session.commit()
			return True
		download_url = f"{settings.public_api_url.rstrip('/')}/api/ebooks/download/{token}"
		recipient = order.customer_email
		customer_name = order.customer_name
		product_title = order.product_title
		storage_path = entitlement.storage_path
		job_id = job.id
		session.commit()

	try:
		pdf_data = asyncio.run(fetch_private_pdf(storage_path))
		_send_email(recipient, customer_name, product_title, download_url, expires_at, pdf_data)
	except EbookDeliveryError as error:
		with SessionLocal() as session:
			job = session.get(EbookEmailJob, job_id)
			if job is not None and job.status == 'PROCESSING':
				job.status = 'FAILED' if job.attempts >= _MAX_EMAIL_ATTEMPTS else 'RETRY'
				job.next_attempt_at = datetime.now(timezone.utc) + timedelta(
					seconds=min(30 * (2 ** max(job.attempts - 1, 0)), 3600)
				)
				job.last_error = str(error)
				job.locked_at = None
				session.commit()
		logger.error('eBook email delivery failed for job %s (%s).', job_id, type(error).__name__)
	else:
		with SessionLocal() as session:
			job = session.get(EbookEmailJob, job_id)
			if job is not None and job.status == 'PROCESSING':
				job.status = 'SENT'
				job.locked_at = None
				job.last_error = None
				job.updated_at = datetime.now(timezone.utc)
				session.commit()
	return True


async def run_email_worker() -> None:
	while True:
		try:
			processed = await asyncio.to_thread(process_next_email_job)
		except SQLAlchemyError:
			logger.exception('Could not process the eBook email outbox.')
			processed = False
		if not processed:
			await asyncio.sleep(max(settings.ebook_email_poll_seconds, 1))


async def fetch_private_pdf(storage_path: str) -> bytes:
	if not storage_is_configured():
		raise EbookStorageError('Private Supabase Storage is not configured.')
	url = (
		f"{settings.supabase_url.rstrip('/')}/storage/v1/object/ebooks/"
		f"{quote(storage_path, safe='/')}"
	)
	headers = {
		'apikey': settings.supabase_service_role_key,
		'Authorization': f'Bearer {settings.supabase_service_role_key}',
	}
	data = bytearray()
	try:
		async with httpx.AsyncClient(timeout=30) as client:
			async with client.stream('GET', url, headers=headers) as response:
				if response.status_code == 404:
					raise EbookStorageError('The private eBook file could not be found.')
				response.raise_for_status()
				content_length = response.headers.get('content-length')
				if content_length and int(content_length) > _MAX_EBOOK_BYTES:
					raise EbookStorageError('The eBook PDF exceeds the configured 50 MB limit.')
				async for chunk in response.aiter_bytes():
					data.extend(chunk)
					if len(data) > _MAX_EBOOK_BYTES:
						raise EbookStorageError('The eBook PDF exceeds the configured 50 MB limit.')
	except EbookStorageError:
		raise
	except (httpx.HTTPError, ValueError) as error:
		raise EbookStorageError('Supabase Storage could not retrieve the eBook PDF.') from error
	if not data.startswith(b'%PDF-'):
		raise EbookStorageError('The stored eBook file is not a valid PDF.')
	return bytes(data)


async def upload_private_pdf(storage_path: str, data: bytes) -> None:
	if not storage_is_configured():
		raise EbookStorageError('Private Supabase Storage is not configured.')
	url = (
		f"{settings.supabase_url.rstrip('/')}/storage/v1/object/ebooks/"
		f"{quote(storage_path, safe='/')}"
	)
	headers = {
		'apikey': settings.supabase_service_role_key,
		'Authorization': f'Bearer {settings.supabase_service_role_key}',
		'Content-Type': 'application/pdf',
		'x-upsert': 'true',
	}
	try:
		async with httpx.AsyncClient(timeout=60) as client:
			response = await client.post(url, headers=headers, content=data)
			response.raise_for_status()
	except httpx.HTTPStatusError as error:
		logger.error('Private eBook upload failed with Supabase status %s.', error.response.status_code)
		raise EbookStorageError('Supabase Storage rejected the eBook upload.') from error
	except httpx.HTTPError as error:
		logger.error('Private eBook upload failed (%s).', type(error).__name__)
		raise EbookStorageError('Supabase Storage could not save the eBook PDF.') from error
