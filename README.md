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

The Razorpay flow writes payment orders to `orders`, and catalog listings are
stored in `products`. Customer details are stored separately in `customers`.
The COD email flow sends order details by email but does not persist order rows;
payment, shipment, expense, profit/loss, and notification tables remain unused.

## Product catalog

Set a long random `ADMIN_API_KEY` in the backend environment, then apply the
migrations. Open `/admin/products` in the storefront and enter that key to add
products. Public product pages read active listings from `/api/products`; admin
catalog requests require the configured key. Keep the key out of source control.