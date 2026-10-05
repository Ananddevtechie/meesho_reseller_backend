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
`shipments`, `expenses`, `profit_loss`, and `notifications`. Revision 0007
renames the sample `backup` table to `admins` and seeds the configured admin
account with a salted password hash.

The Razorpay and COD flows write orders to `orders`, and catalog listings are
stored in `products`. Customer details are stored separately in `customers`.
COD orders are committed before Telegram notification delivery, and the client supplies an
`Idempotency-Key` so retries cannot create duplicate orders. Notification status,
attempt count, and the last delivery error are stored on the order. Telegram retries
transient failures up to three times. A failed order notification can be retried by an
admin with Basic authentication using `POST
/api/admin/orders/{order_id}/retry-notification`. For local development, set
`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `backend/.env`. For the deployed
storefront, set them in the backend host's environment (Render), not in Vercel's
frontend settings or only in the local `.env`. Send `/start` to the bot from the
target chat. Apply the migrations to rename the existing notification status fields.
Payment, shipment, expense, and
profit/loss tables remain unused.

## Razorpay checkout

Set `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` in `backend/.env` (or the
backend host's environment). The backend creates INR orders from the current
catalog price, rejects payments below ₹1.00, and verifies the payment signature
before marking an order paid. The Angular checkout loads Razorpay Standard
Checkout and sends the returned payment details to the backend. Never expose the
secret key to the frontend. Use Razorpay Test Mode keys and test cards/UPI
handles before switching to Live Mode.

The checkout API is available at `POST /api/payments/razorpay/orders` and
`POST /api/payments/razorpay/verify`. Run the backend as described above and the
Angular app from `frontend/` with `npm start`, then complete checkout from a
product page. In the Razorpay Dashboard, configure `order.paid` and
`payment.failed` webhooks to `/api/payments/razorpay/webhook` and set the
matching `RAZORPAY_WEBHOOK_SECRET` in the backend environment so payment status
updates are confirmed server-side. The verification callback marks captured
payments as paid, and status checks reconcile pending orders against Razorpay
so delayed or missing webhooks do not leave successful payments pending.

## Product catalog

Set `ADMIN_USERNAME` and `ADMIN_PASSWORD` in the backend environment, then apply
the migrations. Open `/admin/products` in the storefront and enter those
credentials to add products. Login is verified against the `admins` table by
`POST /api/admin/login`, which returns HTTP 200 on success; the raw password is
not stored in the database. Public product pages read active listings from
`/api/products`, while admin catalog requests verify the same credentials.
Keep the credentials out of source control and use a strong, unique password.