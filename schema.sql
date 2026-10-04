CREATE TABLE users (
    id VARCHAR(36) PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(30) NOT NULL,
    is_active BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_users_email UNIQUE (email)
);

CREATE TABLE products (
    id VARCHAR(100) PRIMARY KEY,
    sku VARCHAR(100) NOT NULL,
    title VARCHAR(255) NOT NULL,
    category VARCHAR(80) NOT NULL DEFAULT 'Other',
    description TEXT,
    eyebrow VARCHAR(120) NOT NULL DEFAULT '',
    image_url TEXT,
    meesho_url TEXT,
    currency VARCHAR(3) NOT NULL DEFAULT 'INR',
    cost_price NUMERIC(12, 2) NOT NULL,
    selling_price NUMERIC(12, 2) NOT NULL,
    mrp NUMERIC(12, 2) NOT NULL,
    stock_quantity INTEGER NOT NULL,
    stock_label VARCHAR(120) NOT NULL DEFAULT 'Available now',
    gallery JSON NOT NULL DEFAULT '[]',
    benefits JSON NOT NULL DEFAULT '[]',
    features JSON NOT NULL DEFAULT '[]',
    specifications JSON NOT NULL DEFAULT '[]',
    package_contents JSON NOT NULL DEFAULT '[]',
    faqs JSON NOT NULL DEFAULT '[]',
    is_active BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_products_sku UNIQUE (sku)
);

CREATE TABLE admins (
    id VARCHAR(36) PRIMARY KEY,
    username VARCHAR(120) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_admins_username UNIQUE (username)
);

CREATE TABLE customers (
    id VARCHAR(141) PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    email VARCHAR(255),
    mobile VARCHAR(20) NOT NULL,
    alternate_mobile VARCHAR(20),
    address_line1 VARCHAR(255) NOT NULL,
    address_line2 VARCHAR(255) NOT NULL,
    landmark VARCHAR(255),
    city VARCHAR(100) NOT NULL,
    state VARCHAR(100) NOT NULL,
    pincode VARCHAR(6) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_customers_name_mobile UNIQUE (full_name, mobile)
);

CREATE TABLE orders (
    id VARCHAR(40) PRIMARY KEY,
    idempotency_key VARCHAR(128) NOT NULL,
    request_fingerprint VARCHAR(64) NOT NULL,
    product_id VARCHAR(100) NOT NULL,
    product_sku VARCHAR(100) NOT NULL,
    product_title VARCHAR(255) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,
    mrp NUMERIC(12, 2) NOT NULL,
    subtotal NUMERIC(12, 2) NOT NULL,
    discount NUMERIC(12, 2) NOT NULL,
    shipping NUMERIC(12, 2) NOT NULL,
    tax NUMERIC(12, 2) NOT NULL,
    cod_fee NUMERIC(12, 2) NOT NULL,
    total NUMERIC(12, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    payment_method VARCHAR(20) NOT NULL,
    payment_status VARCHAR(30) NOT NULL,
    order_status VARCHAR(30) NOT NULL,
    payment_reference VARCHAR(255),
    customer_name VARCHAR(120) NOT NULL,
    customer_email VARCHAR(255),
    customer_mobile VARCHAR(20) NOT NULL,
    alternate_mobile VARCHAR(20),
    address_line1 VARCHAR(255) NOT NULL,
    address_line2 VARCHAR(255) NOT NULL,
    landmark VARCHAR(255),
    city VARCHAR(100) NOT NULL,
    state VARCHAR(100) NOT NULL,
    pincode VARCHAR(6) NOT NULL,
    expected_delivery_range VARCHAR(120) NOT NULL,
    notification_status VARCHAR(20) NOT NULL,
    notification_attempts INTEGER NOT NULL,
    notification_error TEXT,
    whatsapp_opt_in BOOLEAN NOT NULL,
    whatsapp_status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    user_id VARCHAR(36) REFERENCES users(id),
    customer_id VARCHAR(141) REFERENCES customers(id),
    CONSTRAINT uq_orders_idempotency_key UNIQUE (idempotency_key)
);

CREATE TABLE order_items (
    id VARCHAR(36) PRIMARY KEY,
    order_id VARCHAR(40) NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id VARCHAR(100) REFERENCES products(id),
    product_sku VARCHAR(100) NOT NULL,
    product_title VARCHAR(255) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,
    discount NUMERIC(12, 2) NOT NULL,
    line_total NUMERIC(12, 2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE payments (
    id VARCHAR(36) PRIMARY KEY,
    order_id VARCHAR(40) NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    provider VARCHAR(40) NOT NULL,
    provider_order_id VARCHAR(120),
    provider_payment_id VARCHAR(120),
    method VARCHAR(30) NOT NULL,
    status VARCHAR(30) NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE shipments (
    id VARCHAR(36) PRIMARY KEY,
    order_id VARCHAR(40) NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    carrier VARCHAR(100),
    tracking_number VARCHAR(120),
    status VARCHAR(30) NOT NULL,
    shipped_at TIMESTAMP WITH TIME ZONE,
    delivered_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE expenses (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) REFERENCES users(id),
    category VARCHAR(80) NOT NULL,
    description TEXT,
    amount NUMERIC(12, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    expense_date DATE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE profit_loss (
    id VARCHAR(36) PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    revenue NUMERIC(12, 2) NOT NULL,
    cost_of_goods NUMERIC(12, 2) NOT NULL,
    expenses NUMERIC(12, 2) NOT NULL,
    net_profit NUMERIC(12, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE notifications (
    id VARCHAR(36) PRIMARY KEY,
    order_id VARCHAR(40) REFERENCES orders(id) ON DELETE SET NULL,
    customer_id VARCHAR(36) REFERENCES customers(id) ON DELETE SET NULL,
    channel VARCHAR(30) NOT NULL,
    recipient VARCHAR(255) NOT NULL,
    subject VARCHAR(255),
    status VARCHAR(30) NOT NULL,
    provider_message_id VARCHAR(255),
    error TEXT,
    sent_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);