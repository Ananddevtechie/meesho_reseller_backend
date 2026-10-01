# Backend database

The FastAPI backend uses SQLAlchemy with PostgreSQL. `app/models.py` defines the
application's current database structure; Alembic migrations create and evolve
that structure. `schema.sql` is the equivalent SQL for manual inspection or
setup.

## Configure

Copy `.env.example` to `.env`. Set `DATABASE_URL` to the Supabase PostgreSQL
Session Pooler connection string shown in the Supabase **Connect** panel. Keep
the password out of source control and URL-encode reserved password characters.

Install dependencies and apply migrations from this directory:

```sh
python -m pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

The migrations preserve existing order rows by renaming `customer_orders` to
`orders`, then add `users`, `products`, `customers`, `order_items`, `payments`,
`shipments`, `expenses`, `profit_loss`, and `notifications`. New supporting
tables start empty.

The Razorpay payment flow writes payment orders to `orders`. The supporting
tables are schema foundations; the API does not yet write separate customer,
product, payment, shipment, expense, profit/loss, or notification records. The
COD email flow sends order details by email but does not persist them.