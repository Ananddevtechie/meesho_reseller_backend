import hashlib
import hmac
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.models import EbookDownloadToken, EbookEntitlement, EbookOrderAccess, Order
from app.schemas import EbookDownloadLinkResponse
from app.services.ebook_delivery import EbookDeliveryError, create_download_link, fetch_private_pdf


router = APIRouter(tags=['ebook delivery'])


def _authorization_token(authorization: Optional[str]) -> str:
	if not authorization or not authorization.startswith('Bearer '):
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='A valid eBook access token is required.')
	return authorization.removeprefix('Bearer ').strip()


@router.post(
	'/api/payments/razorpay/orders/{order_id}/download-link',
	response_model=EbookDownloadLinkResponse,
)
def create_ebook_download_link(
	order_id: str,
	authorization: Optional[str] = Header(default=None),
) -> EbookDownloadLinkResponse:
	access_token = _authorization_token(authorization)
	if not access_token:
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='A valid eBook access token is required.')
	token_hash = hashlib.sha256(access_token.encode('utf-8')).hexdigest()

	try:
		with SessionLocal() as session:
			access = session.get(EbookOrderAccess, order_id)
			if (
				access is None
				or access.expires_at <= datetime.now(timezone.utc)
				or not hmac.compare_digest(access.token_hash, token_hash)
			):
				raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='eBook order was not found.')
			order = session.get(Order, order_id)
			entitlement = session.scalar(
				select(EbookEntitlement)
				.where(EbookEntitlement.order_id == order_id)
				.with_for_update()
			)
			if order is None or order.payment_status != 'PAID' or entitlement is None:
				raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='The eBook is available after payment is confirmed.')
			if entitlement.revoked_at or entitlement.expires_at <= datetime.now(timezone.utc):
				raise HTTPException(status_code=status.HTTP_410_GONE, detail='The eBook entitlement has expired or been revoked.')
			if entitlement.download_count >= entitlement.download_limit:
				raise HTTPException(status_code=status.HTTP_410_GONE, detail='The eBook download limit has been reached.')
			try:
				download_url, expires_at = create_download_link(session, entitlement)
			except EbookDeliveryError as error:
				raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(error)) from error
			session.commit()
	except SQLAlchemyError as error:
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail='Could not create a secure eBook download link.',
		) from error
	return EbookDownloadLinkResponse(download_url=download_url, expires_at=expires_at)


@router.get('/api/ebooks/download/{token}')
async def download_ebook(token: str) -> Response:
	token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
	now = datetime.now(timezone.utc)
	try:
		with SessionLocal() as session:
			row = session.execute(
				select(EbookDownloadToken, EbookEntitlement, Order)
				.join(EbookEntitlement, EbookDownloadToken.entitlement_id == EbookEntitlement.id)
				.join(Order, EbookEntitlement.order_id == Order.id)
				.where(EbookDownloadToken.token_hash == token_hash)
			).one_or_none()
			if row is None:
				raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Download link is invalid.')
			download_token, entitlement, order = row
			if download_token.revoked_at or download_token.expires_at <= now:
				raise HTTPException(status_code=status.HTTP_410_GONE, detail='This download link has expired or been revoked.')
			if entitlement.revoked_at or entitlement.expires_at <= now:
				raise HTTPException(status_code=status.HTTP_410_GONE, detail='This eBook entitlement has expired or been revoked.')
			if order.payment_status != 'PAID':
				raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Payment has not been confirmed.')
			if entitlement.download_count >= entitlement.download_limit:
				raise HTTPException(status_code=status.HTTP_410_GONE, detail='The eBook download limit has been reached.')
			entitlement_id = entitlement.id
			storage_path = entitlement.storage_path
			product_title = order.product_title
	except SQLAlchemyError as error:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not validate this download link.') from error

	try:
		pdf_data = await fetch_private_pdf(storage_path)
	except EbookDeliveryError as error:
		raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail='The eBook file could not be delivered.') from error

	try:
		with SessionLocal() as session:
			entitlement = session.scalar(
				select(EbookEntitlement)
				.where(EbookEntitlement.id == entitlement_id)
				.with_for_update()
			)
			download_token = session.scalar(
				select(EbookDownloadToken)
				.where(EbookDownloadToken.token_hash == token_hash)
				.with_for_update()
			)
			order = session.get(Order, entitlement.order_id) if entitlement else None
			now = datetime.now(timezone.utc)
			if (
				entitlement is None
				or download_token is None
				or order is None
				or order.payment_status != 'PAID'
				or entitlement.revoked_at
				or download_token.revoked_at
				or entitlement.expires_at <= now
				or download_token.expires_at <= now
				or entitlement.download_count >= entitlement.download_limit
			):
				raise HTTPException(status_code=status.HTTP_410_GONE, detail='This download is no longer available.')
			entitlement.download_count += 1
			session.commit()
	except SQLAlchemyError as error:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not record this download.') from error

	filename = re.sub(r'[^A-Za-z0-9._-]+', '-', product_title).strip('-.') or 'ebook'
	return Response(
		content=pdf_data,
		media_type='application/pdf',
		headers={
			'Content-Disposition': f'attachment; filename="{filename}.pdf"',
			'Cache-Control': 'private, no-store, max-age=0',
			'Pragma': 'no-cache',
			'X-Content-Type-Options': 'nosniff',
			'Referrer-Policy': 'no-referrer',
		},
	)
