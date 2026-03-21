-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- Enable pg_trgm for fuzzy search
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Trigger function for updating updated_at timestamp
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- TABLE 1: customers
CREATE TABLE IF NOT EXISTS customers (
    customer_id       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name              VARCHAR(255) NOT NULL,
    age               SMALLINT CHECK (age >= 18 AND age <= 80),
    gender            VARCHAR(20) CHECK (gender IN ('male', 'female', 'other', 'prefer_not_to_say')),
    marital_status    VARCHAR(20) CHECK (marital_status IN ('single', 'married', 'divorced', 'widowed')),
    dependents        SMALLINT DEFAULT 0,
    education_level   VARCHAR(50) CHECK (education_level IN ('below_10th', '10th', '12th', 'graduate', 'post_graduate', 'doctorate')),
    phone             VARCHAR(15) UNIQUE NOT NULL,
    email             VARCHAR(255) UNIQUE,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone);
CREATE INDEX IF NOT EXISTS idx_customers_name_trgm ON customers USING GIN (name gin_trgm_ops);

CREATE TRIGGER trg_customers_updated_at
    BEFORE UPDATE ON customers
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();

-- TABLE 2: loan_applications
CREATE TABLE IF NOT EXISTS loan_applications (
    application_id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id             UUID REFERENCES customers(customer_id),
    loan_type               VARCHAR(50) CHECK (loan_type IN ('personal', 'home', 'vehicle', 'education', 'business', 'gold', 'lap')),
    loan_amount             NUMERIC(15,2) NOT NULL CHECK (loan_amount > 0),
    tenure_months           SMALLINT CHECK (tenure_months >= 3 AND tenure_months <= 360),
    interest_rate_requested NUMERIC(5,2),
    purpose                 VARCHAR(255),
    application_date        DATE DEFAULT CURRENT_DATE,
    address                 TEXT,
    pincode                 VARCHAR(10),
    city                    VARCHAR(100),
    state                   VARCHAR(100),
    employment_type         VARCHAR(50) CHECK (employment_type IN ('salaried', 'self_employed', 'business_owner', 'freelance', 'retired', 'student', 'unemployed')),
    employer_name           VARCHAR(255),
    monthly_income          NUMERIC(15,2),
    other_income            NUMERIC(15,2) DEFAULT 0,
    monthly_obligations     NUMERIC(15,2) DEFAULT 0,
    credit_score            SMALLINT CHECK (credit_score >= 300 AND credit_score <= 900),
    credit_score_agency     VARCHAR(30) DEFAULT 'CIBIL',
    num_active_loans        SMALLINT DEFAULT 0,
    num_closed_loans        SMALLINT DEFAULT 0,
    num_enquiries_6m        SMALLINT DEFAULT 0,
    status                  VARCHAR(30) DEFAULT 'initiated' CHECK (status IN ('initiated', 'kyc_pending', 'fraud_check', 'underwriting', 'offer_presented', 'approved', 'rejected', 'withdrawn', 'sanctioned', 'disbursed', 'closed')),
    rejection_reason        TEXT,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_loan_apps_customer_id ON loan_applications(customer_id);
CREATE INDEX IF NOT EXISTS idx_loan_apps_status ON loan_applications(status);
CREATE INDEX IF NOT EXISTS idx_loan_apps_date ON loan_applications(application_date);

CREATE TRIGGER trg_loan_applications_updated_at
    BEFORE UPDATE ON loan_applications
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp();

-- TABLE 3: kyc_records
CREATE TABLE IF NOT EXISTS kyc_records (
    kyc_id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    application_id      UUID REFERENCES loan_applications(application_id) UNIQUE,
    customer_id         UUID REFERENCES customers(customer_id),
    pan_no              VARCHAR(10) NOT NULL,
    aadhaar_no          VARCHAR(12) NOT NULL,
    dob_from_aadhaar    DATE,
    name_on_pan         VARCHAR(255),
    name_on_aadhaar     VARCHAR(255),
    address_on_aadhaar  TEXT,
    pincode_on_aadhaar  VARCHAR(10),
    pan_verified        BOOLEAN DEFAULT FALSE,
    aadhaar_verified    BOOLEAN DEFAULT FALSE,
    name_match_score    NUMERIC(5,4) CHECK (name_match_score >= 0 AND name_match_score <= 1),
    address_match_score NUMERIC(5,4) CHECK (address_match_score >= 0 AND address_match_score <= 1),
    dob_age_match       BOOLEAN,
    pincode_match       BOOLEAN,
    verified_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_kyc_pan ON kyc_records(pan_no);
CREATE UNIQUE INDEX IF NOT EXISTS idx_kyc_aadhaar ON kyc_records(aadhaar_no);

-- TABLE 4: loan_history
CREATE TABLE IF NOT EXISTS loan_history (
    history_id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id         UUID REFERENCES customers(customer_id),
    lender_name         VARCHAR(255),
    loan_type           VARCHAR(50),
    loan_amount         NUMERIC(15,2),
    disbursement_date   DATE,
    original_tenure     SMALLINT,
    closure_date        DATE,
    status              VARCHAR(20) CHECK (status IN ('active', 'closed', 'defaulted', 'settled', 'written_off')),
    outstanding_amount  NUMERIC(15,2) DEFAULT 0,
    emi_amount          NUMERIC(15,2),
    overdue_amount      NUMERIC(15,2) DEFAULT 0,
    dpd_30              SMALLINT DEFAULT 0,
    dpd_60              SMALLINT DEFAULT 0,
    dpd_90              SMALLINT DEFAULT 0,
    settled             BOOLEAN DEFAULT FALSE,
    written_off         BOOLEAN DEFAULT FALSE,
    foreclosed          BOOLEAN DEFAULT FALSE,
    worst_dpd_ever      SMALLINT,
    avg_dpd             NUMERIC(5,2),
    source              VARCHAR(30) DEFAULT 'bureau' CHECK (source IN ('bureau', 'self_declared', 'simulated')),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_loan_history_customer_id ON loan_history(customer_id);
CREATE INDEX IF NOT EXISTS idx_loan_history_status ON loan_history(status);

-- TABLE 5: device_metadata
CREATE TABLE IF NOT EXISTS device_metadata (
    device_id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id          VARCHAR(64) NOT NULL,
    application_id      UUID REFERENCES loan_applications(application_id),
    ip_address          INET,
    user_agent          TEXT,
    device_fingerprint  VARCHAR(128),
    browser             VARCHAR(50),
    os                  VARCHAR(50),
    device_type         VARCHAR(20) CHECK (device_type IN ('mobile', 'tablet', 'desktop', 'bot', 'unknown')),
    geolocation_lat     NUMERIC(9,6),
    geolocation_lng     NUMERIC(9,6),
    geolocation_city    VARCHAR(100),
    timezone            VARCHAR(60),
    is_vpn              BOOLEAN DEFAULT FALSE,
    is_proxy            BOOLEAN DEFAULT FALSE,
    is_tor              BOOLEAN DEFAULT FALSE,
    is_emulator         BOOLEAN DEFAULT FALSE,
    ip_reputation_score NUMERIC(4,3),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_device_metadata_session_id ON device_metadata(session_id);
CREATE INDEX IF NOT EXISTS idx_device_metadata_ip ON device_metadata(ip_address);

-- TABLE 6: fraud_checks
CREATE TABLE IF NOT EXISTS fraud_checks (
    fraud_id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    application_id      UUID REFERENCES loan_applications(application_id) UNIQUE,
    fraud_score         NUMERIC(5,4) NOT NULL CHECK (fraud_score >= 0 AND fraud_score <= 1),
    fraud_flag          VARCHAR(10) CHECK (fraud_flag IN ('Low', 'Medium', 'High')),
    velocity_check      BOOLEAN,
    blacklist_check     BOOLEAN,
    id_mismatch_check   BOOLEAN,
    device_risk_check   BOOLEAN,
    anomaly_flags       JSONB DEFAULT '{}',
    model_version       VARCHAR(30),
    checked_at          TIMESTAMPTZ DEFAULT NOW()
);

-- TABLE 7: underwriting_results
CREATE TABLE IF NOT EXISTS underwriting_results (
    underwriting_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    application_id          UUID REFERENCES loan_applications(application_id) UNIQUE,
    risk_score              NUMERIC(5,4) NOT NULL CHECK (risk_score >= 0 AND risk_score <= 1),
    risk_band               VARCHAR(10) CHECK (risk_band IN ('A', 'B', 'C', 'D', 'E', 'F')),
    approval_status         BOOLEAN NOT NULL,
    interest_rate_offered   NUMERIC(5,2),
    max_eligible_amount     NUMERIC(15,2),
    approved_tenure_months  SMALLINT,
    rejection_reason        TEXT,
    model_version           VARCHAR(30),
    feature_importance      JSONB DEFAULT '{}',
    underwritten_at         TIMESTAMPTZ DEFAULT NOW()
);

-- TABLE 8: loan_offers
CREATE TABLE IF NOT EXISTS loan_offers (
    offer_id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    application_id      UUID REFERENCES loan_applications(application_id),
    loan_amount         NUMERIC(15,2) NOT NULL,
    interest_rate       NUMERIC(5,2) NOT NULL,
    tenure_months       SMALLINT NOT NULL,
    monthly_emi         NUMERIC(15,2) NOT NULL,
    processing_fee      NUMERIC(15,2) DEFAULT 0,
    total_payable       NUMERIC(15,2),
    offer_type          VARCHAR(20) DEFAULT 'standard' CHECK (offer_type IN ('standard', 'negotiated', 'counter', 'alternative')),
    offer_version       SMALLINT DEFAULT 1,
    accepted            BOOLEAN DEFAULT FALSE,
    accepted_at         TIMESTAMPTZ,
    expires_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_loan_offers_application_id ON loan_offers(application_id);

-- TABLE 9: documents
CREATE TABLE IF NOT EXISTS documents (
    document_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    application_id      UUID REFERENCES loan_applications(application_id),
    document_type       VARCHAR(50) CHECK (document_type IN ('pan_card', 'aadhaar_card', 'salary_slip', 'bank_statement', 'itr', 'form_16', 'address_proof', 'photo', 'other')),
    filename            VARCHAR(255) NOT NULL,
    file_path           VARCHAR(512) NOT NULL,
    file_size           BIGINT,
    mime_type           VARCHAR(100),
    checksum_sha256     VARCHAR(64),
    is_verified         BOOLEAN DEFAULT FALSE,
    uploaded_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_application_id ON documents(application_id);

-- TABLE 10: sanction_letters
CREATE TABLE IF NOT EXISTS sanction_letters (
    letter_id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    application_id      UUID REFERENCES loan_applications(application_id) UNIQUE,
    offer_id            UUID REFERENCES loan_offers(offer_id),
    sanction_number     VARCHAR(30) UNIQUE NOT NULL,
    pdf_path            VARCHAR(512),
    generated_at        TIMESTAMPTZ DEFAULT NOW(),
    valid_until         DATE,
    signed_by_customer  BOOLEAN DEFAULT FALSE,
    signed_at           TIMESTAMPTZ,
    disbursed           BOOLEAN DEFAULT FALSE,
    disbursed_amount    NUMERIC(15,2),
    disbursed_at        TIMESTAMPTZ,
    disbursal_ref       VARCHAR(100)
);

-- TABLE 11: chat_sessions
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id          VARCHAR(64) PRIMARY KEY,
    application_id      UUID REFERENCES loan_applications(application_id),
    state               JSONB NOT NULL DEFAULT '{}',
    stage               VARCHAR(50),
    interaction_count   INTEGER DEFAULT 0,
    workflow_history    JSONB DEFAULT '[]',
    last_activity       TIMESTAMPTZ DEFAULT NOW(),
    expires_at          TIMESTAMPTZ DEFAULT NOW() + INTERVAL '30 minutes',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_expires_at ON chat_sessions(expires_at);

-- TABLE 12: chat_logs
CREATE TABLE IF NOT EXISTS chat_logs (
    log_id              BIGSERIAL PRIMARY KEY,
    session_id          VARCHAR(64) REFERENCES chat_sessions(session_id),
    event_type          VARCHAR(50) CHECK (event_type IN ('message', 'status_change', 'action')),
    message_role        VARCHAR(20) CHECK (message_role IN ('user', 'assistant', 'system')),
    message_text        TEXT,
    status              VARCHAR(30),
    details             JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_logs_session_id ON chat_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_logs_created_at ON chat_logs(created_at);

-- TABLE 13: admin_users
CREATE TABLE IF NOT EXISTS admin_users (
    user_id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username            VARCHAR(64) UNIQUE NOT NULL,
    email               VARCHAR(255) UNIQUE NOT NULL,
    password_hash       TEXT NOT NULL,
    role                VARCHAR(20) DEFAULT 'viewer' CHECK (role IN ('admin', 'viewer', 'analyst')),
    is_active           BOOLEAN DEFAULT TRUE,
    last_login          TIMESTAMPTZ,
    failed_logins       SMALLINT DEFAULT 0,
    locked_until        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- TABLE 14: revoked_tokens
CREATE TABLE IF NOT EXISTS revoked_tokens (
    id                  SERIAL PRIMARY KEY,
    jti                 VARCHAR(120) UNIQUE NOT NULL,
    revoked_at          TIMESTAMPTZ DEFAULT NOW()
);

-- TABLE 15: tuning_content
CREATE TABLE IF NOT EXISTS tuning_content (
    content_id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    admin_id            UUID REFERENCES admin_users(user_id),
    type                VARCHAR(50) CHECK (type IN ('system_prompt', 'policy', 'product_info')),
    content             TEXT NOT NULL,
    filename            VARCHAR(255),
    is_active           BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Maintenance comments:
-- clean up expired sessions with: DELETE FROM chat_sessions WHERE expires_at < NOW();
-- clean up old tokens with: DELETE FROM revoked_tokens WHERE revoked_at < NOW() - INTERVAL '7 days';
