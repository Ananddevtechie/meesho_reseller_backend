from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.database import check_database_connection
from app.schemas import AddressExtractionRequest, ExtractedAddress
from app.routers.cod_email import router as cod_email_router
from app.routers.customers import router as customers_router
from app.routers.payments import router as payments_router
from app.services.ai_parser import GeminiExtractionError, extract_address


@asynccontextmanager
async def lifespan(_: FastAPI):
	check_database_connection()
	yield


app = FastAPI(title='Meesho Reseller API', lifespan=lifespan)
app.add_middleware(
	CORSMiddleware,
	allow_origins=['http://localhost:4200', 'http://127.0.0.1:4200'],
	allow_methods=['*'],
	allow_headers=['*'],
)
app.include_router(cod_email_router)
app.include_router(customers_router)
app.include_router(payments_router)


@app.get('/health')
async def health() -> dict[str, str]:
	return {'status': 'ok'}


@app.post('/api/extract', response_model=ExtractedAddress)
async def extract(request: AddressExtractionRequest) -> ExtractedAddress:
	try:
		return await extract_address(request.text)
	except GeminiExtractionError as error:
		raise HTTPException(status_code=503, detail=str(error)) from error
