import hmac
import json
import logging
import threading
import time
import uuid
from base64 import b64decode
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, File, Form, Header, HTTPException, Response, UploadFile, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from pydantic import ValidationError

from app.database import SessionLocal
from app.models import Admin, Order, OrderItem, Product, ProductImage, ProductReview, ProductReviewImage
from app.schemas import (
	AdminLoginRequest,
	AdminLoginResponse,
	ProductAdmin,
	ProductCreateRequest,
	ProductPublic,
	ProductReviewItem,
	ProductReviewImportRequest,
	ProductReviewImportResult,
	ProductReviewSummary,
	ProductReviewUpdate,
)
from app.services.admin_auth import verify_password
from app.services.order_notification_delivery import deliver_order_notification, is_stale_notification


router = APIRouter(tags=['products'])
logger = logging.getLogger(__name__)
_DUMMY_PASSWORD_HASH = 'pbkdf2_sha256$600000$00000000000000000000000000000000$0000000000000000000000000000000000000000000000000000000000000000'
_MAX_REVIEW_IMAGES = 5
_MAX_REVIEW_IMAGE_BYTES = 5 * 1024 * 1024
_REVIEW_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp'}
_MAX_MEESHO_REVIEWS_PER_IMPORT = 100
_MAX_IMPORTED_IMAGES_PER_REVIEW = 5
_MAX_IMPORTED_IMAGES_PER_IMPORT = 100
_MAX_IMPORTED_IMAGE_BYTES_PER_IMPORT = 50 * 1024 * 1024
_MAX_PRODUCT_IMAGES = 10
_MAX_PRODUCT_IMAGE_BYTES = 5 * 1024 * 1024
_PRODUCT_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp'}
_PRODUCT_LIST_CACHE_TTL_SECONDS = 30
_PRODUCT_REVIEW_CACHE_TTL_SECONDS = 30
_product_list_cache_lock = threading.Lock()
_product_list_cache_refresh_lock = threading.Lock()
_product_list_cache: tuple[float, list[Product]] | None = None
_product_list_cache_generation = 0
_product_review_cache_lock = threading.Lock()
_product_review_cache: dict[str, tuple[float, ProductReviewSummary]] = {}
_product_review_request_locks: dict[str, threading.Lock] = {}
_product_review_cache_generation = 0


def _invalidate_product_list_cache() -> None:
	global _product_list_cache, _product_list_cache_generation
	with _product_list_cache_lock:
		_product_list_cache = None
		_product_list_cache_generation += 1
	_invalidate_product_review_cache()


def _invalidate_product_review_cache(slug: str | None = None) -> None:
	global _product_review_cache_generation
	with _product_review_cache_lock:
		_product_review_cache_generation += 1
		if slug is None:
			_product_review_cache.clear()
		else:
			_product_review_cache.pop(slug, None)


def _review_summary(session, slug: str, active_only: bool = False) -> ProductReviewSummary:
	statement = (
		select(
			Product.id,
			ProductReview.id,
			ProductReview.reviewer_name,
			ProductReview.rating,
			ProductReview.comment,
			ProductReview.created_at,
			ProductReviewImage.id,
		)
		.select_from(Product)
		.outerjoin(ProductReview, ProductReview.product_id == Product.id)
		.outerjoin(ProductReviewImage, ProductReviewImage.review_id == ProductReview.id)
		.where(Product.id == slug)
		.order_by(ProductReview.created_at.desc())
	)
	if active_only:
		statement = statement.where(Product.is_active.is_(True))

	rows = session.execute(statement)
	reviews_by_id: dict[str, ProductReviewItem] = {}
	product_found = False
	for _, review_id, reviewer_name, rating, comment, created_at, image_id in rows:
		product_found = True
		if review_id is None:
			continue
		review = reviews_by_id.get(review_id)
		if review is None:
			review = ProductReviewItem(
				id=review_id,
				reviewer_name=reviewer_name,
				rating=rating,
				comment=comment,
				created_at=created_at,
				image_urls=[],
			)
			reviews_by_id[review_id] = review
		if image_id is not None:
			review.image_urls.append(f'/api/products/{slug}/reviews/{review_id}/images/{image_id}')

	if not product_found:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Product not found.')

	items = list(reviews_by_id.values())
	average_rating = round(sum(item.rating for item in items) / len(items), 1) if items else 0.0
	return ProductReviewSummary(average_rating=average_rating, review_count=len(items), reviews=items)


def _cached_product_review_summary(slug: str) -> ProductReviewSummary:
	with _product_review_cache_lock:
		request_lock = _product_review_request_locks.setdefault(slug, threading.Lock())
	with request_lock:
		now = time.monotonic()
		with _product_review_cache_lock:
			cached = _product_review_cache.get(slug)
			if cached is not None and cached[0] > now:
				return cached[1]
			cache_generation = _product_review_cache_generation
		with SessionLocal() as session:
			summary = _review_summary(session, slug, active_only=True)
		with _product_review_cache_lock:
			if cache_generation == _product_review_cache_generation:
				_product_review_cache[slug] = (time.monotonic() + _PRODUCT_REVIEW_CACHE_TTL_SECONDS, summary)
		return summary


def _valid_image_data(content_type: str, data: bytes) -> bool:
	if content_type == 'image/jpeg':
		return data.startswith(b'\xff\xd8\xff')
	if content_type == 'image/png':
		return data.startswith(b'\x89PNG\r\n\x1a\n')
	return content_type == 'image/webp' and data.startswith(b'RIFF') and data[8:12] == b'WEBP'


async def _download_meesho_review_image(client: httpx.AsyncClient, image_url: str) -> tuple[str, bytes]:
	parsed_url = urlparse(image_url)
	if parsed_url.scheme != 'https' or not parsed_url.hostname or not (
		parsed_url.hostname == 'meesho.com' or parsed_url.hostname.endswith('.meesho.com')
	):
		raise HTTPException(
			status_code=status.HTTP_502_BAD_GATEWAY,
			detail='The review scraper returned an unsupported image URL.',
		)
	try:
		async with client.stream('GET', image_url) as response:
			if not response.is_success:
				raise HTTPException(
					status_code=status.HTTP_502_BAD_GATEWAY,
					detail='Could not download a customer review image.',
				)
			content_type = response.headers.get('content-type', '').split(';', 1)[0].strip().lower()
			if content_type not in _REVIEW_IMAGE_TYPES:
				raise HTTPException(
					status_code=status.HTTP_502_BAD_GATEWAY,
					detail='The review scraper returned an unsupported image type.',
				)
			content_length = response.headers.get('content-length')
			if content_length:
				try:
					image_size = int(content_length)
				except ValueError as error:
					raise HTTPException(
						status_code=status.HTTP_502_BAD_GATEWAY,
						detail='The review scraper returned an invalid image size.',
					) from error
				if image_size > _MAX_REVIEW_IMAGE_BYTES:
					raise HTTPException(
						status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
						detail='A customer review image exceeded the 5 MB limit.',
					)
			data = bytearray()
			async for chunk in response.aiter_bytes():
				data.extend(chunk)
				if len(data) > _MAX_REVIEW_IMAGE_BYTES:
					raise HTTPException(
						status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
						detail='A customer review image exceeded the 5 MB limit.',
					)
	except httpx.HTTPError as error:
		raise HTTPException(
			status_code=status.HTTP_502_BAD_GATEWAY,
			detail='Could not download a customer review image.',
		) from error
	image_data = bytes(data)
	if not _valid_image_data(content_type, image_data):
		raise HTTPException(
			status_code=status.HTTP_502_BAD_GATEWAY,
			detail='The review scraper returned invalid image data.',
		)
	return content_type, image_data


async def _read_product_image(image: UploadFile) -> tuple[str, bytes]:
	try:
		content_type = (image.content_type or '').lower()
		if content_type not in _PRODUCT_IMAGE_TYPES:
			raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail='Product images must be JPEG, PNG, or WebP.')
		data = await image.read(_MAX_PRODUCT_IMAGE_BYTES + 1)
		if len(data) > _MAX_PRODUCT_IMAGE_BYTES:
			raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail='Each product image must be 5 MB or smaller.')
		if not _valid_image_data(content_type, data):
			raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail='The uploaded file is not a valid image.')
		return content_type, data
	finally:
		await image.close()


def _admin_credentials_match(username: str, password: str) -> bool:
	try:
		with SessionLocal() as session:
			admin = session.scalar(select(Admin).where(Admin.username == username))
	except SQLAlchemyError as error:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not verify admin credentials.') from error
	if admin is None:
		verify_password(password, _DUMMY_PASSWORD_HASH)
		return False
	return hmac.compare_digest(username.encode('utf-8'), admin.username.encode('utf-8')) and verify_password(password, admin.password_hash)


def _require_admin(authorization: Optional[str]) -> None:
	scheme, separator, token = (authorization or '').partition(' ')
	if not separator or scheme.lower() != 'basic':
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Admin username or password is incorrect.')
	try:
		credentials = b64decode(token, validate=True).decode('utf-8')
		username, separator, password = credentials.partition(':')
	except (ValueError, UnicodeDecodeError) as error:
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Admin username or password is incorrect.') from error
	if not separator or not _admin_credentials_match(username, password):
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Admin username or password is incorrect.')


@router.post('/api/admin/login', response_model=AdminLoginResponse)
def admin_login(request: AdminLoginRequest) -> AdminLoginResponse:
	if not _admin_credentials_match(request.username, request.password):
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Admin username or password is incorrect.')
	return AdminLoginResponse()


@router.get('/api/products', response_model=list[ProductPublic])
def list_products(response: Response) -> list[Product]:
	global _product_list_cache
	response.headers['Cache-Control'] = (
		'public, max-age=0, s-maxage=30, '
		'stale-while-revalidate=86400, stale-if-error=86400'
	)
	with _product_list_cache_lock:
		if _product_list_cache is not None and _product_list_cache[0] > time.monotonic():
			response.headers['X-Catalog-Cache'] = 'HIT'
			return list(_product_list_cache[1])

	with _product_list_cache_refresh_lock:
		with _product_list_cache_lock:
			if _product_list_cache is not None and _product_list_cache[0] > time.monotonic():
				response.headers['X-Catalog-Cache'] = 'COALESCED'
				return list(_product_list_cache[1])
			cache_generation = _product_list_cache_generation

		database_started_at = time.perf_counter()
		try:
			with SessionLocal() as session:
				products = list(session.scalars(
					select(Product).where(Product.is_active.is_(True)).order_by(Product.created_at.desc())
				))
		except SQLAlchemyError as error:
			logger.warning(
				'product_list_cache_fill_failed database_ms=%.2f',
				(time.perf_counter() - database_started_at) * 1000,
			)
			raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not load products.') from error

		database_duration_ms = (time.perf_counter() - database_started_at) * 1000
		with _product_list_cache_lock:
			if cache_generation == _product_list_cache_generation:
				_product_list_cache = (time.monotonic() + _PRODUCT_LIST_CACHE_TTL_SECONDS, products)
		logger.info('product_list_cache_fill products=%d database_ms=%.2f', len(products), database_duration_ms)
		response.headers['X-Catalog-Cache'] = 'MISS'
	return products


@router.get('/api/products/{slug}', response_model=ProductPublic)
def get_product(slug: str) -> Product:
	try:
		with SessionLocal() as session:
			product = session.scalar(select(Product).where(Product.id == slug, Product.is_active.is_(True)))
	except SQLAlchemyError as error:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not load this product.') from error
	if product is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Product not found.')
	return product


@router.get('/api/products/{slug}/images/{image_id}')
def get_product_image(slug: str, image_id: str) -> Response:
	try:
		with SessionLocal() as session:
			image = session.scalar(
				select(ProductImage)
				.join(Product, Product.id == ProductImage.product_id)
				.where(
					Product.id == slug,
					ProductImage.id == image_id,
				)
			)
	except SQLAlchemyError as error:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not load the product image.') from error
	if image is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Product image not found.')
	return Response(
		content=image.image_data,
		media_type=image.content_type,
		headers={'Cache-Control': 'public, max-age=31536000, immutable'},
	)


@router.get('/api/products/{slug}/reviews', response_model=ProductReviewSummary)
def get_product_reviews(slug: str) -> ProductReviewSummary:
	try:
		return _cached_product_review_summary(slug)
	except HTTPException:
		raise
	except SQLAlchemyError as error:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not load product reviews.') from error


@router.get('/api/products/{slug}/reviews/{review_id}/images/{image_id}')
def get_product_review_image(slug: str, review_id: str, image_id: str) -> Response:
	try:
		with SessionLocal() as session:
			image = session.scalar(
				select(ProductReviewImage)
				.join(ProductReview, ProductReview.id == ProductReviewImage.review_id)
				.join(Product, Product.id == ProductReview.product_id)
				.where(
					Product.id == slug,
					Product.is_active.is_(True),
					ProductReview.id == review_id,
					ProductReviewImage.id == image_id,
				)
			)
	except SQLAlchemyError as error:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not load review image.') from error
	if image is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Review image not found.')
	return Response(content=image.image_data, media_type=image.content_type, headers={'Cache-Control': 'public, max-age=86400'})


@router.get('/api/admin/products/{slug}/reviews', response_model=ProductReviewSummary)
def list_admin_product_reviews(
	slug: str,
	authorization: Optional[str] = Header(default=None),
) -> ProductReviewSummary:
	_require_admin(authorization)
	try:
		with SessionLocal() as session:
			return _review_summary(session, slug)
	except HTTPException:
		raise
	except SQLAlchemyError as error:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not load product reviews.') from error


@router.post(
	'/api/admin/products/{slug}/reviews/import',
	response_model=ProductReviewImportResult,
)
async def import_meesho_product_reviews(
	slug: str,
	request: ProductReviewImportRequest,
	authorization: Optional[str] = Header(default=None),
) -> ProductReviewImportResult:
	_require_admin(authorization)
	from app.routers.meesho_reviews import _product_id, _run_scraper

	_product_id(request.meesho_url)
	try:
		with SessionLocal() as session:
			if session.get(Product, slug) is None:
				raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Product not found.')
	except SQLAlchemyError as error:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not look up this product.') from error

	scraped = await _run_scraper(
		request.meesho_url,
		max_reviews_per_product=_MAX_MEESHO_REVIEWS_PER_IMPORT,
	)
	skipped_count = 0
	skipped_image_count = 0
	reviews_to_import = scraped.reviews[:_MAX_MEESHO_REVIEWS_PER_IMPORT]
	source_ids = [review.id for review in reviews_to_import]
	try:
		with SessionLocal() as session:
			existing_records = list(session.execute(
				select(ProductReview.source_review_id, ProductReview.id).where(
					ProductReview.product_id == slug,
					ProductReview.source_review_id.in_(source_ids),
				)
			)) if source_ids else []
			existing_by_source = {
				source_id: review_id
				for source_id, review_id in existing_records
				if source_id is not None
			}
			existing_image_review_ids = set(session.scalars(
				select(ProductReviewImage.review_id).where(
					ProductReviewImage.review_id.in_(set(existing_by_source.values()))
				)
			)) if existing_by_source else set()
	except SQLAlchemyError as error:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not check existing reviews.') from error

	new_reviews = []
	reviews_needing_image_backfill = []
	seen_ids = set(existing_by_source)
	processed_source_ids: set[str] = set()
	for review in reviews_to_import:
		if review.id in processed_source_ids:
			continue
		processed_source_ids.add(review.id)
		if review.id in seen_ids:
			skipped_count += 1
			if (
				existing_by_source[review.id] not in existing_image_review_ids
				and review.image_urls
			):
				reviews_needing_image_backfill.append(review)
		else:
			new_reviews.append(review)
			seen_ids.add(review.id)

	images_by_source: dict[str, list[tuple[str, bytes]]] = {}
	stored_image_count = 0
	stored_image_bytes = 0
	new_review_ids = {review.id: uuid.uuid4().hex for review in new_reviews}
	image_candidates = [
		(review.id, image_url)
		for review in [*new_reviews, *reviews_needing_image_backfill]
		for image_url in review.image_urls[:_MAX_IMPORTED_IMAGES_PER_REVIEW]
	]
	skipped_image_count += sum(
		max(0, len(review.image_urls) - _MAX_IMPORTED_IMAGES_PER_REVIEW)
		for review in [*new_reviews, *reviews_needing_image_backfill]
	)
	async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=10), follow_redirects=False) as client:
		for image_index, (source_id, image_url) in enumerate(image_candidates):
			if (
				stored_image_count >= _MAX_IMPORTED_IMAGES_PER_IMPORT
				or stored_image_bytes >= _MAX_IMPORTED_IMAGE_BYTES_PER_IMPORT
			):
				skipped_image_count += len(image_candidates) - image_index
				break
			content_type, image_data = await _download_meesho_review_image(client, image_url)
			if stored_image_bytes + len(image_data) > _MAX_IMPORTED_IMAGE_BYTES_PER_IMPORT:
				skipped_image_count += 1
				continue
			images_by_source.setdefault(source_id, []).append((content_type, image_data))
			stored_image_count += 1
			stored_image_bytes += len(image_data)

	imported_count = 0
	backfilled_review_count = 0
	review_id_by_source = {**existing_by_source, **new_review_ids}
	try:
		with SessionLocal() as session:
			for review in new_reviews:
				stored_review = ProductReview(
					id=new_review_ids[review.id],
					product_id=slug,
					source_review_id=review.id,
					reviewer_name=review.reviewer_name,
					rating=review.rating,
					comment=review.comment,
					created_at=review.created_at,
				)
				session.add(stored_review)
				session.flush()
				for content_type, image_data in images_by_source.get(review.id, []):
					session.add(ProductReviewImage(
						id=uuid.uuid4().hex,
						review_id=stored_review.id,
						content_type=content_type,
						image_data=image_data,
					))
				imported_count += 1
			for review in reviews_needing_image_backfill:
				review_images = images_by_source.get(review.id, [])
				for content_type, image_data in review_images:
					session.add(ProductReviewImage(
						id=uuid.uuid4().hex,
						review_id=review_id_by_source[review.id],
						content_type=content_type,
						image_data=image_data,
					))
				if review_images:
					backfilled_review_count += 1
			session.commit()
			_invalidate_product_review_cache(slug)
			summary = _review_summary(session, slug)
	except IntegrityError as error:
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Some reviews were imported concurrently. Refresh and retry.') from error
	except SQLAlchemyError as error:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not save imported reviews.') from error
	return ProductReviewImportResult(
		imported_count=imported_count,
		skipped_count=skipped_count,
		backfilled_review_count=backfilled_review_count,
		saved_image_count=stored_image_count,
		skipped_image_count=skipped_image_count,
		reviews=summary,
	)


@router.post('/api/admin/products/{slug}/reviews', response_model=ProductReviewItem, status_code=status.HTTP_201_CREATED)
async def create_product_review(
	slug: str,
	rating: int = Form(..., ge=1, le=5),
	comment: str = Form(..., min_length=1, max_length=2000),
	reviewer_name: str = Form(default='Verified customer', min_length=1, max_length=120),
	images: list[UploadFile] = File(default=[]),
	authorization: Optional[str] = Header(default=None),
) -> ProductReviewItem:
	_require_admin(authorization)
	if len(images) > _MAX_REVIEW_IMAGES:
		raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail='Upload no more than five review images.')
	comment = comment.strip()
	reviewer_name = reviewer_name.strip()
	if not comment or not reviewer_name:
		raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Reviewer name and comment cannot be blank.')
	image_data: list[tuple[str, bytes]] = []
	for image in images:
		content_type = (image.content_type or '').lower()
		if content_type not in _REVIEW_IMAGE_TYPES:
			raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail='Review images must be JPEG, PNG, or WebP.')
		data = await image.read(_MAX_REVIEW_IMAGE_BYTES + 1)
		await image.close()
		if len(data) > _MAX_REVIEW_IMAGE_BYTES:
			raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail='Each review image must be 5 MB or smaller.')
		if not _valid_image_data(content_type, data):
			raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail='The uploaded file is not a valid image.')
		image_data.append((content_type, data))
	try:
		with SessionLocal() as session:
			if session.get(Product, slug) is None:
				raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Product not found.')
			review = ProductReview(
				id=uuid.uuid4().hex,
				product_id=slug,
				reviewer_name=reviewer_name,
				rating=rating,
				comment=comment,
			)
			session.add(review)
			session.flush()
			for content_type, data in image_data:
				session.add(ProductReviewImage(
					id=uuid.uuid4().hex,
					review_id=review.id,
					content_type=content_type,
					image_data=data,
				))
			session.commit()
			session.refresh(review)
			_invalidate_product_review_cache(slug)
			return _review_summary(session, slug).reviews[0]
	except SQLAlchemyError as error:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not save the product review.') from error


@router.put('/api/admin/products/{slug}/reviews/{review_id}', response_model=ProductReviewItem)
def update_product_review(
	slug: str,
	review_id: str,
	request: ProductReviewUpdate,
	authorization: Optional[str] = Header(default=None),
) -> ProductReviewItem:
	_require_admin(authorization)
	try:
		with SessionLocal() as session:
			review = session.scalar(select(ProductReview).where(
				ProductReview.id == review_id,
				ProductReview.product_id == slug,
			))
			if review is None:
				raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Product review not found.')
			review.reviewer_name = request.reviewer_name
			review.rating = request.rating
			review.comment = request.comment
			session.commit()
			session.refresh(review)
			_invalidate_product_review_cache(slug)
			return ProductReviewItem(
				id=review.id,
				reviewer_name=review.reviewer_name,
				rating=review.rating,
				comment=review.comment,
				created_at=review.created_at,
				image_urls=[],
			)
	except SQLAlchemyError as error:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not update product review.') from error


@router.delete('/api/admin/products/{slug}/reviews/{review_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_product_review(
	slug: str,
	review_id: str,
	authorization: Optional[str] = Header(default=None),
) -> Response:
	_require_admin(authorization)
	try:
		with SessionLocal() as session:
			review = session.scalar(select(ProductReview).where(
				ProductReview.id == review_id,
				ProductReview.product_id == slug,
			))
			if review is None:
				raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Product review not found.')
			for image in session.scalars(select(ProductReviewImage).where(ProductReviewImage.review_id == review_id)):
				session.delete(image)
			session.delete(review)
			session.commit()
			_invalidate_product_review_cache(slug)
	except SQLAlchemyError as error:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not delete product review.') from error
	return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get('/api/admin/products', response_model=list[ProductAdmin])
def list_admin_products(authorization: Optional[str] = Header(default=None)) -> list[Product]:
	_require_admin(authorization)
	try:
		with SessionLocal() as session:
			return list(session.scalars(select(Product).order_by(Product.created_at.desc())))
	except SQLAlchemyError as error:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not load admin products.') from error


@router.post('/api/admin/products/save', response_model=ProductAdmin)
async def save_product_with_images(
	product_data: str = Form(...),
	main_image: Optional[UploadFile] = File(default=None),
	additional_images: list[UploadFile] = File(default=[]),
	authorization: Optional[str] = Header(default=None),
) -> Product:
	_require_admin(authorization)
	if len(additional_images) > _MAX_PRODUCT_IMAGES:
		raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail='Upload no more than ten additional product images.')

	try:
		values = json.loads(product_data)
	except json.JSONDecodeError as error:
		raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Product details are invalid.') from error
	if not isinstance(values, dict):
		raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Product details are invalid.')
	if main_image is not None and not values.get('image_url'):
		values['image_url'] = 'uploaded-image'
	try:
		request = ProductCreateRequest.model_validate(values)
	except ValidationError as error:
		raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Product details are invalid.') from error

	uploaded_images: list[tuple[str, bytes]] = []
	if main_image is not None:
		uploaded_images.append(await _read_product_image(main_image))
	for image in additional_images:
		uploaded_images.append(await _read_product_image(image))

	try:
		with SessionLocal() as session:
			product = session.get(Product, request.slug)
			is_new = product is None
			if is_new:
				product = Product(id=request.slug, **request.model_dump(exclude={'slug'}))
				session.add(product)
				old_main_image_url = None
			else:
				old_main_image_url = product.image_url
				for field, value in request.model_dump(exclude={'slug'}).items():
					setattr(product, field, value)
			session.flush()

			next_gallery = list(request.gallery)
			if main_image is not None:
				next_gallery = [
					image for image in next_gallery
					if image.get('src') not in {old_main_image_url, request.image_url}
				]
			for index, (content_type, data) in enumerate(uploaded_images):
				image_id = uuid.uuid4().hex
				session.add(ProductImage(
					id=image_id,
					product_id=request.slug,
					content_type=content_type,
					image_data=data,
				))
				image_url = f'/api/products/{request.slug}/images/{image_id}'
				if index == 0 and main_image is not None:
					product.image_url = image_url
					next_gallery.insert(0, {'src': image_url, 'alt': request.title, 'label': 'Product'})
				else:
					additional_index = index - (1 if main_image is not None else 0) + 1
					next_gallery.append({
						'src': image_url,
						'alt': f'{request.title} product view {additional_index}',
						'label': f'View {additional_index}',
					})
			if not any(image.get('src') == product.image_url for image in next_gallery):
				next_gallery.insert(0, {'src': product.image_url, 'alt': request.title, 'label': 'Product'})
			product.gallery = next_gallery
			session.flush()

			referenced_urls = {product.image_url, *(image.get('src', '') for image in product.gallery)}
			for stored_image in session.scalars(
				select(ProductImage).where(ProductImage.product_id == request.slug)
			):
				stored_url = f'/api/products/{request.slug}/images/{stored_image.id}'
				if stored_url not in referenced_urls:
					session.delete(stored_image)
			session.commit()
			session.refresh(product)
			_invalidate_product_list_cache()
			return product
	except IntegrityError as error:
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='A product with this slug or SKU already exists.') from error
	except SQLAlchemyError as error:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not save this product.') from error


@router.post('/api/admin/products', response_model=ProductAdmin, status_code=status.HTTP_201_CREATED)
def create_product(
	request: ProductCreateRequest,
	authorization: Optional[str] = Header(default=None),
) -> Product:
	_require_admin(authorization)
	product = Product(id=request.slug, **request.model_dump(exclude={'slug'}))
	try:
		with SessionLocal() as session:
			session.add(product)
			session.commit()
			session.refresh(product)
			_invalidate_product_list_cache()
	except IntegrityError as error:
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='A product with this slug or SKU already exists.') from error
	except SQLAlchemyError as error:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not save this product.') from error
	return product


@router.put('/api/admin/products/{slug}', response_model=ProductAdmin)
def update_product(
	slug: str,
	request: ProductCreateRequest,
	authorization: Optional[str] = Header(default=None),
) -> Product:
	_require_admin(authorization)
	if request.slug != slug:
		raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Product slug cannot be changed.')
	try:
		with SessionLocal() as session:
			product = session.scalar(select(Product).where(Product.id == slug))
			if product is None:
				raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Product not found.')
			for field, value in request.model_dump(exclude={'slug'}).items():
				setattr(product, field, value)
			session.commit()
			session.refresh(product)
			_invalidate_product_list_cache()
	except IntegrityError as error:
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='A product with this SKU already exists.') from error
	except SQLAlchemyError as error:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not update this product.') from error
	return product


@router.delete('/api/admin/products/{slug}', status_code=status.HTTP_204_NO_CONTENT)
def delete_product(slug: str, authorization: Optional[str] = Header(default=None)) -> Response:
	_require_admin(authorization)
	try:
		with SessionLocal() as session:
			product = session.get(Product, slug)
			if product is None:
				raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Product not found.')
			session.execute(update(OrderItem).where(OrderItem.product_id == slug).values(product_id=None))
			session.delete(product)
			session.commit()
			_invalidate_product_list_cache()
	except SQLAlchemyError as error:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not delete this product.') from error
	return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post('/api/admin/orders/{order_id}/retry-notification', status_code=status.HTTP_202_ACCEPTED)
def retry_order_notification(
	order_id: str,
	authorization: Optional[str] = Header(default=None),
) -> dict[str, str]:
	_require_admin(authorization)
	with SessionLocal() as session:
		order = session.get(Order, order_id)
	if order is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Order not found.')
	if order.notification_status == 'SENT':
		return {'notification_status': 'SENT', 'message': 'Order notification was already sent.'}
	if order.notification_status == 'SENDING' and not is_stale_notification(order):
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='This order notification is already being sent.')
	if order.order_status not in {'PLACED', 'CANCELLED'}:
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Only placed or cancelled orders can have their notification retried.')
	deliver_order_notification(order_id)
	with SessionLocal() as session:
		order = session.get(Order, order_id)
	if order is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Order not found.')
	message = 'Order notification sent.' if order.notification_status == 'SENT' else 'Order notification could not be sent; check backend logs.'
	return {'notification_status': order.notification_status, 'message': message}