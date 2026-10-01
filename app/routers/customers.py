from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.models import Customer
from app.schemas import CustomerSaveRequest, CustomerSaveResponse


router = APIRouter(prefix='/api/customers', tags=['customers'])


@router.post('/upsert', response_model=CustomerSaveResponse)
def save_customer(request: CustomerSaveRequest) -> CustomerSaveResponse:
	values = request.model_dump()
	values['id'] = f'{request.full_name}:{request.mobile}'
	statement = insert(Customer).values(**values)
	statement = statement.on_conflict_do_update(
		constraint='uq_customers_name_mobile',
		set_={
			'full_name': statement.excluded.full_name,
			'alternate_mobile': statement.excluded.alternate_mobile,
			'address_line1': statement.excluded.address_line1,
			'address_line2': statement.excluded.address_line2,
			'landmark': statement.excluded.landmark,
			'city': statement.excluded.city,
			'state': statement.excluded.state,
			'pincode': statement.excluded.pincode,
			'updated_at': func.now(),
		},
	).returning(Customer.id)

	try:
		with SessionLocal() as session:
			customer_id = session.scalar(statement)
			session.commit()
	except SQLAlchemyError as error:
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail='Could not save customer details.',
		) from error

	if customer_id is None:
		raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Could not save customer details.')
	return CustomerSaveResponse(customer_id=customer_id)