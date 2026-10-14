import logging
import time
from contextlib import asynccontextmanager

from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.database import check_database_connection
from app.schemas import AddressExtractionRequest, ExtractedAddress
from app.routers.cod_orders import router as cod_orders_router
from app.routers.customers import router as customers_router
from app.routers.meesho_reviews import router as meesho_reviews_router
from app.routers.order_tracking import router as order_tracking_router
from app.routers.payments import router as payments_router
from app.routers.products import router as products_router
from app.services.ai_parser import GeminiExtractionError, extract_address


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
	check_database_connection()
	yield


app = FastAPI(title='Meesho Reseller API', lifespan=lifespan)


@app.middleware('http')
async def log_product_api_timing(request: Request, call_next):
	path = request.url.path
	is_product_api = request.method == 'GET' and (
		path == '/api/products' or (path.startswith('/api/products/') and path.count('/') == 3)
	)
	if not is_product_api:
		return await call_next(request)

	started_at = time.perf_counter()
	response = await call_next(request)
	logger.info(
		'product_api_request method=%s path=%s status=%s duration_ms=%.2f cache=%s',
		request.method,
		path,
		response.status_code,
		(time.perf_counter() - started_at) * 1000,
		response.headers.get('X-Catalog-Cache', 'not-applicable'),
	)
	return response


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(request: Request, error: RequestValidationError) -> Response:
	if request.method == 'POST' and request.url.path == '/api/payments/razorpay/verify':
		return JSONResponse(
			status_code=400,
			content={'detail': 'Payment verification fields are missing or invalid.'},
		)
	return await request_validation_exception_handler(request, error)


app.add_middleware(
	CORSMiddleware,
	allow_origins=['http://localhost:4200', 'http://127.0.0.1:4200'],
	allow_methods=['*'],
	allow_headers=['*'],
)
app.include_router(cod_orders_router)
app.include_router(customers_router)
app.include_router(meesho_reviews_router)
app.include_router(order_tracking_router)
app.include_router(payments_router)
app.include_router(products_router)


@app.get('/')
async def root() -> dict[str, str]:
	return {'status': 'ok', 'health': '/health', 'docs': '/docs'}


@app.get('/health')
async def health() -> dict[str, str]:
	return {'status': 'ok'}


@app.post('/api/extract', response_model=ExtractedAddress)
async def extract(request: AddressExtractionRequest) -> ExtractedAddress:
	try:
		return await extract_address(request.text)
	except GeminiExtractionError as error:
		raise HTTPException(status_code=503, detail=str(error)) from error
