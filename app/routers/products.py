import hmac
import uuid
from base64 import b64decode
from typing import Optional

from fastapi import APIRouter, File, Form, Header, HTTPException, Response, UploadFile, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.database import SessionLocal
from app.models import Admin, Order, OrderItem, Product, ProductReview, ProductReviewImage
from app.schemas import (
	AdminLoginRequest,
	AdminLoginResponse,
	ProductAdmin,
	ProductCreateRequest,
	ProductPublic,
	ProductReviewItem,
	ProductReviewSummary,
)
from app.services.admin_auth import verify_password
from app.services.order_notification_delivery import deliver_order_notification, is_stale_notification


router = APIRouter(tags=['products'])
_DUMMY_PASSWORD_HASH = 'pbkdf2_sha256$600000$00000000000000000000000000000000$0000000000000000000000000000000000000000000000000000000000000000'
_MAX_REVIEW_IMAGES = 5
_MAX_REVIEW_IMAGE_BYTES = 5 * 1024 * 1024
_REVIEW_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp'}


def _review_summary(session, slug: str) -> ProductReviewSummary:
	reviews = list(session.scalars(
		select(ProductReview).where(ProductReview.product_id == slug).order_by(ProductReview.created_at.desc())
	))
	images_by_review: dict[str, list[str]] = {review.id: [] for review in reviews}
	if reviews:
		images = session.scalars(
			select(ProductReviewImage).where(ProductReviewImage.review_id.in_([review.id for review in reviews]))
		)
		for image in images:
			images_by_review[image.review_id].append(
				f'/api/products/{slug}/reviews/{image.review_id}/images/{image.id}'
			)
	items = [
		ProductReviewItem(
			id=review.id,
			reviewer_name=review.reviewer_name,
			rating=review.rating,
			comment=review.comment,
			created_at=review.created_at,
			image_urls=images_by_review[review.id],
		)
		for review in reviews
	]
	average_rating = round(sum(review.rating for review in reviews) / len(reviews), 1) if reviews else 0.0
	return ProductReviewSummary(average_rating=average_rating, review_count=len(reviews), reviews=items)


def _valid_review_image(content_type: str, data: bytes) -> bool:
	if content_type == 'image/jpeg':
		return data.startswith(b'\xff\xd8\xff')
	if content_type == 'image/png':
		return data.startswith(b'\x89PNG\r\n\x1a\n')
	return content_type == 'image/webp' and data.startswith(b'RIFF') and data[8:12] == b'WEBP'


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
def list_products() -> list[Product]:
	try:
		with SessionLocal() as session:
			return list(session.scalars(select(Product).where(Product.is_active.is_(True)).order_by(Product.created_at.desc())))
	except SQLAlchemyError as error:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not load products.') from error


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


@router.get('/api/products/{slug}/reviews', response_model=ProductReviewSummary)
def get_product_reviews(slug: str) -> ProductReviewSummary:
	try:
		with SessionLocal() as session:
			product = session.scalar(select(Product).where(Product.id == slug, Product.is_active.is_(True)))
			if product is None:
				raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Product not found.')
			return _review_summary(session, slug)
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
			if session.get(Product, slug) is None:
				raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Product not found.')
			return _review_summary(session, slug)
	except SQLAlchemyError as error:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not load product reviews.') from error


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
		if not _valid_review_image(content_type, data):
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
			return _review_summary(session, slug).reviews[0]
	except SQLAlchemyError as error:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not save the product review.') from error


@router.get('/api/admin/products', response_model=list[ProductAdmin])
def list_admin_products(authorization: Optional[str] = Header(default=None)) -> list[Product]:
	_require_admin(authorization)
	try:
		with SessionLocal() as session:
			return list(session.scalars(select(Product).order_by(Product.created_at.desc())))
	except SQLAlchemyError as error:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not load admin products.') from error


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
	if order.order_status != 'PLACED':
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Only placed orders can have their notification retried.')
	deliver_order_notification(order_id)
	with SessionLocal() as session:
		order = session.get(Order, order_id)
	if order is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Order not found.')
	message = 'Order notification sent.' if order.notification_status == 'SENT' else 'Order notification could not be sent; check backend logs.'
	return {'notification_status': order.notification_status, 'message': message}