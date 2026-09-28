from pathlib import Path
import sqlite3

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import Base


database_url = settings.database_url
if database_url.startswith('sqlite:///'):
	db_path = Path(database_url.removeprefix('sqlite:///')).resolve()
	db_path.parent.mkdir(parents=True, exist_ok=True)
else:
	db_path = None

engine = create_engine(
	database_url,
	connect_args={'check_same_thread': False} if database_url.startswith('sqlite:') else {},
	pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def initialize_database() -> None:
	if db_path and db_path.exists():
		try:
			with sqlite3.connect(str(db_path)) as conn:
				tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='customer_orders'").fetchone()
				if tables:
					columns = {row[1] for row in conn.execute('PRAGMA table_info(customer_orders)').fetchall()}
					required = {'idempotency_key', 'mrp', 'email_status'}
					if not required.issubset(columns):
						conn.close()
						db_path.unlink(missing_ok=True)
						Base.metadata.create_all(bind=engine)
						return
					if 'whatsapp_opt_in' not in columns:
						conn.execute('ALTER TABLE customer_orders ADD COLUMN whatsapp_opt_in BOOLEAN NOT NULL DEFAULT 0')
					if 'whatsapp_status' not in columns:
						conn.execute("ALTER TABLE customer_orders ADD COLUMN whatsapp_status VARCHAR(30) NOT NULL DEFAULT 'NOT_OPTED_IN'")
		except sqlite3.DatabaseError:
			if db_path.exists():
				db_path.unlink(missing_ok=True)
	Base.metadata.create_all(bind=engine)
