import hmac
from base64 import b64decode
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.config import settings
from app.database import SessionLocal
from app.models import Product
from app.schemas import ProductAdmin, ProductCreateRequest, ProductPublic


router = APIRouter(tags=['products'])


def _require_admin(authorization: Optional[str]) -> None:
	if not settings.admin_username or not settings.admin_password:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Admin username and password are not configured.')
	scheme, separator, token = (authorization or '').partition(' ')
	if not separator or scheme.lower() != 'basic':
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Admin username or password is incorrect.')
	try:
		credentials = b64decode(token, validate=True).decode('utf-8')
		username, separator, password = credentials.partition(':')
	except (ValueError, UnicodeDecodeError) as error:
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Admin username or password is incorrect.') from error
	if (
		not separator
		or not hmac.compare_digest(username.encode('utf-8'), settings.admin_username.encode('utf-8'))
		or not hmac.compare_digest(password.encode('utf-8'), settings.admin_password.encode('utf-8'))
	):
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Admin username or password is incorrect.')


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