-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- products: catalog of SKUs carried by the store
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sku TEXT UNIQUE NOT NULL,
    name_vi TEXT NOT NULL,
    active_ingredient TEXT NOT NULL,
    strength TEXT NOT NULL,
    dosage_form TEXT NOT NULL,
    pack_size TEXT,
    rx_only BOOLEAN NOT NULL DEFAULT FALSE,
    manufacturer TEXT,
    price_vnd INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_products_inn_strength_form
    ON products (active_ingredient, strength, dosage_form);
CREATE INDEX IF NOT EXISTS idx_products_rx_only ON products (rx_only);

-- inventory
CREATE TABLE IF NOT EXISTS inventory (
    product_id UUID PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE,
    qty_on_hand INTEGER NOT NULL DEFAULT 0,
    reorder_point INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- otc_formulas: vector-searchable OTC combos
CREATE TABLE IF NOT EXISTS otc_formulas (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code TEXT UNIQUE NOT NULL,
    name_vi TEXT NOT NULL,
    symptom_tags TEXT[] NOT NULL,
    symptom_text_vi TEXT NOT NULL,
    embedding vector(1536),
    min_age_years NUMERIC NOT NULL DEFAULT 0,
    max_age_years NUMERIC,
    pregnancy_safe BOOLEAN NOT NULL DEFAULT FALSE,
    notes_vi TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_otc_formulas_embedding
    ON otc_formulas USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_otc_formulas_tags
    ON otc_formulas USING gin (symptom_tags);

-- formula_items: ingredients of each formula
CREATE TABLE IF NOT EXISTS formula_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    formula_id UUID NOT NULL REFERENCES otc_formulas(id) ON DELETE CASCADE,
    active_ingredient TEXT NOT NULL,
    strength_hint TEXT,
    dose_per_take_vi TEXT NOT NULL,
    frequency_per_day SMALLINT NOT NULL,
    duration_days SMALLINT NOT NULL,
    age_rule_vi TEXT,
    role TEXT NOT NULL CHECK (role IN ('primary', 'adjuvant'))
);

CREATE INDEX IF NOT EXISTS idx_formula_items_formula ON formula_items (formula_id);

-- agent_audit_log
CREATE TABLE IF NOT EXISTS agent_audit_log (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    flow TEXT NOT NULL CHECK (flow IN ('prescription', 'symptom')),
    patient_hash TEXT,
    request_json JSONB NOT NULL,
    response_json JSONB NOT NULL,
    llm_model TEXT,
    latency_ms INTEGER,
    red_flags TEXT[]
);

CREATE INDEX IF NOT EXISTS idx_audit_created_at ON agent_audit_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_flow_created ON agent_audit_log (flow, created_at DESC);
