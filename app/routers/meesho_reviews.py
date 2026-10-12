import asyncio
import logging
import re
import time
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.database import SessionLocal
from app.models import Product
from app.schemas import ProductReviewItem, ProductReviewSummary


router = APIRouter(tags=['meesho-reviews'])
_APIFY_ACTOR_URL = 'https://api.apify.com/v2/acts/scrapeai~meesho-reviews-scraper/run-sync-get-dataset-items'
_MEESHO_PRODUCT_URL = 'https://www.meesho.com/littel-krishna-printed-wooden-key-holder-for-home-office-kitchen-key-holders-key-hanger-for-wall-key-holder-gift-best-decorative-item-for-home-decor85-inches-x-115-inches/p/90v2q0'
_REVIEWS_PER_PRODUCT = 15
_CACHE_TTL_SECONDS = 6 * 60 * 60
_PRODUCT_ID_PATTERN = re.compile(r'/p/([a-zA-Z0-9]+)(?:/|$)')
_logger = logging.getLogger(__name__)
_cache: dict[str, tuple[float, ProductReviewSummary]] = {}
_in_flight: dict[str, asyncio.Task[ProductReviewSummary]] = {}
_cache_lock = asyncio.Lock()


def _product_id(product_url: str) -> str:
	parsed = urlparse(product_url)
	if parsed.scheme != 'https' or parsed.hostname not in {'meesho.com', 'www.meesho.com'}:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail='A valid https://www.meesho.com product URL is required.',
		)
	match = _PRODUCT_ID_PATTERN.search(parsed.path)
	if match is None:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail='The Meesho URL must include a product catalog ID.',
		)
	return match.group(1)


def _parse_results(items: object) -> ProductReviewSummary:
	if not isinstance(items, list):
		raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail='The review scraper returned an invalid response.')

	reviews: list[ProductReviewItem] = []
	average_rating = 0.0
	review_count = 0
	try:
		for item in items:
			if not isinstance(item, dict):
				raise ValueError('A review record was not an object.')
			if not reviews:
				average_rating = float(item.get('productAverageRating') or 0)
				review_count = int(item.get('productReviewCount') or 0)
			images = item.get('imageUrls') or []
			if not isinstance(images, list) or not all(isinstance(url, str) for url in images):
				raise ValueError('A review record contained invalid image URLs.')
			reviews.append(ProductReviewItem.model_validate({
				'id': str(item['reviewId']),
				'reviewer_name': item['reviewerName'],
				'rating': item['rating'],
				'comment': item.get('comment') or '',
				'created_at': item['createdAt'],
				'image_urls': images,
			}))
	except (KeyError, TypeError, ValueError, ValidationError) as error:
		raise HTTPException(
			status_code=status.HTTP_502_BAD_GATEWAY,
			detail='The review scraper returned review data in an unexpected format.',
		) from error

	if not items:
		return ProductReviewSummary(average_rating=0, review_count=0, reviews=[])
	return ProductReviewSummary(
		average_rating=average_rating,
		review_count=review_count or len(reviews),
		reviews=reviews,
	)


async def _run_scraper(product_url: str) -> ProductReviewSummary:
	if not settings.apify_api_token:
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail='Meesho reviews are not configured. Set APIFY_API_TOKEN on the backend.',
		)
	input_data = {
		'productUrls': [product_url],
		'maxReviewsPerProduct': _REVIEWS_PER_PRODUCT,
		'reviewType': 'all',
		'proxyConfiguration': {
			'useApifyProxy': True,
			'apifyProxyGroups': ['RESIDENTIAL'],
			'apifyProxyCountry': 'IN',
		},
	}
	try:
		async with httpx.AsyncClient(timeout=httpx.Timeout(320, connect=10)) as client:
			response = await client.post(
				_APIFY_ACTOR_URL,
				params={'waitForFinish': 300, 'timeout': 300},
				headers={'Authorization': f'Bearer {settings.apify_api_token}'},
				json=input_data,
			)
	except httpx.TimeoutException as error:
		_logger.exception('Timed out while scraping Meesho reviews.')
		raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail='The Meesho review scraper timed out.') from error
	except httpx.HTTPError as error:
		_logger.exception('Could not reach the Meesho review scraper.')
		raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail='Could not reach the Meesho review scraper.') from error

	if not response.is_success:
		_logger.error('Meesho scraper returned HTTP %s.', response.status_code)
		raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail='The Meesho review scraper failed.')
	try:
		items = response.json()
	except ValueError as error:
		raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail='The Meesho review scraper returned invalid JSON.') from error
	return _parse_results(items)


async def _scrape_and_cache(product_url: str, product_id: str) -> ProductReviewSummary:
	summary = await _run_scraper(product_url)
	async with _cache_lock:
		_cache[product_id] = (time.monotonic() + _CACHE_TTL_SECONDS, summary)
	return summary


async def get_meesho_reviews(product_url: str) -> ProductReviewSummary:
	product_id = _product_id(product_url)
	async with _cache_lock:
		cached = _cache.get(product_id)
		if cached is not None and cached[0] > time.monotonic():
			return cached[1]
		_cache.pop(product_id, None)
		task = _in_flight.get(product_id)
		if task is None:
			task = asyncio.create_task(_scrape_and_cache(product_url, product_id))
			_in_flight[product_id] = task
	try:
		return await task
	finally:
		async with _cache_lock:
			if _in_flight.get(product_id) is task:
				_in_flight.pop(product_id, None)


@router.get('/api/products/{slug}/meesho-reviews', response_model=ProductReviewSummary)
async def fetch_meesho_reviews(slug: str) -> ProductReviewSummary:
	product_url = await run_in_threadpool(_get_product_url, slug)
	return await get_meesho_reviews(product_url)


def _get_product_url(slug: str) -> str:
	try:
		with SessionLocal() as session:
			product = session.scalar(select(Product).where(Product.id == slug, Product.is_active.is_(True)))
	except SQLAlchemyError as error:
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail='Could not look up this product.',
		) from error
	if product is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Product not found.')
	return _MEESHO_PRODUCT_URL
