import hmac
from base64 import b64decode
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.database import SessionLocal
from app.models import Admin, Product
from app.schemas import AdminLoginRequest, AdminLoginResponse, ProductAdmin, ProductCreateRequest, ProductPublic
from app.services.admin_auth import verify_password


router = APIRouter(tags=['products'])
_DUMMY_PASSWORD_HASH = 'pbkdf2_sha256$600000$00000000000000000000000000000000$0000000000000000000000000000000000000000000000000000000000000000'


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