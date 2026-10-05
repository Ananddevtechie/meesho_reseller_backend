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
from app.routers.order_tracking import router as order_tracking_router
from app.routers.payments import router as payments_router
from app.routers.products import router as products_router
from app.services.ai_parser import GeminiExtractionError, extract_address


@asynccontextmanager
async def lifespan(_: FastAPI):
	check_database_connection()
	yield


app = FastAPI(title='Meesho Reseller API', lifespan=lifespan)


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
