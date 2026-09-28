CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    address_line1 VARCHAR(255) NOT NULL,
    address_line2 VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(100),
    pincode VARCHAR(10) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE pricing_rules (
    id SERIAL PRIMARY KEY,
    category VARCHAR(100) DEFAULT 'default',
    margin_type VARCHAR(10) CHECK (margin_type IN ('flat','percent')),
    value NUMERIC(10,2) NOT NULL,
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    raw_input TEXT,
    customer_id INTEGER REFERENCES customers(id),
    product_link TEXT NOT NULL,
    product_title VARCHAR(255),
    product_image_url TEXT,
    variant JSONB,
    quantity INTEGER DEFAULT 1,
    base_price NUMERIC(10,2),
    margin_applied NUMERIC(10,2),
    final_price NUMERIC(10,2),
    payment_mode VARCHAR(10) DEFAULT 'COD',
    status VARCHAR(30) DEFAULT 'draft',
    meesho_order_id VARCHAR(100),
    awb_number VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE order_status_log (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
    status VARCHAR(30) NOT NULL,
    note TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);