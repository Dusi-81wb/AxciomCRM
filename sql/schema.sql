-- =============================================================================
-- AcxiomCRM — Phase 1 Database Schema
-- 
-- PostgreSQL relational schema supporting layered architecture.
-- Adheres strictly to MASTER_BLUEPRINT.md and SPECIFICATION_NOTES.md.
-- No ORM is used; all operations execute via psycopg2 with parameterized SQL.
-- =============================================================================

-- Drop tables in reverse-dependency order if recreating schema
DROP TABLE IF EXISTS audit_logs CASCADE;
DROP TABLE IF EXISTS activities CASCADE;
DROP TABLE IF EXISTS followups CASCADE;
DROP TABLE IF EXISTS opportunities CASCADE;
DROP TABLE IF EXISTS leads CASCADE;
DROP TABLE IF EXISTS customers CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS roles CASCADE;

-- -----------------------------------------------------------------------------
-- 1. ROLES TABLE
-- Defines system roles for Role-Based Access Control (RBAC).
-- Fixed roles: Admin, Manager, Sales Executive.
-- -----------------------------------------------------------------------------
CREATE TABLE roles (
    role_id SERIAL PRIMARY KEY,
    role_name VARCHAR(50) NOT NULL UNIQUE,
    CONSTRAINT chk_role_name CHECK (role_name IN ('Admin', 'Manager', 'Sales Executive'))
);

-- -----------------------------------------------------------------------------
-- 2. USERS TABLE
-- Stores user accounts, authentication state, role assignment, and lockout tracking.
-- Passwords must be hashed with Werkzeug (never plaintext).
-- -----------------------------------------------------------------------------
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    failed_login_attempts INT NOT NULL DEFAULT 0,
    lockout_until TIMESTAMPTZ NULL,
    created_date TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_date TIMESTAMPTZ NULL,
    last_login_date TIMESTAMPTZ NULL,
    role_id INT NOT NULL REFERENCES roles(role_id) ON DELETE RESTRICT
);

-- -----------------------------------------------------------------------------
-- 3. CUSTOMERS TABLE
-- Manages customer organizations and accounts.
-- Enforces uniqueness for code, email, and phone.
-- Supports ownership assignment to Sales Executives.
-- -----------------------------------------------------------------------------
CREATE TABLE customers (
    customer_id SERIAL PRIMARY KEY,
    customer_code VARCHAR(50) NOT NULL UNIQUE,
    customer_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    phone VARCHAR(20) NOT NULL UNIQUE,
    company_name VARCHAR(100) NULL,
    address TEXT NULL,
    city VARCHAR(50) NULL,
    state VARCHAR(50) NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Active',
    assigned_to INT NULL REFERENCES users(user_id) ON DELETE SET NULL,
    created_date TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_date TIMESTAMPTZ NULL,
    created_by INT NULL REFERENCES users(user_id) ON DELETE SET NULL,
    CONSTRAINT chk_customer_status CHECK (status IN ('Active', 'Inactive'))
);

-- -----------------------------------------------------------------------------
-- 4. LEADS TABLE
-- Manages prospective customers through the lead lifecycle.
-- Supports 6 canonical lead statuses and monetary ExpectedValue (NUMERIC(14,2)).
-- -----------------------------------------------------------------------------
CREATE TABLE leads (
    lead_id SERIAL PRIMARY KEY,
    lead_code VARCHAR(50) NOT NULL UNIQUE,
    lead_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL,
    phone VARCHAR(20) NULL,
    company_name VARCHAR(100) NULL,
    source VARCHAR(50) NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'New',
    expected_value NUMERIC(14,2) NULL,
    created_date TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_date TIMESTAMPTZ NULL,
    assigned_to INT NULL REFERENCES users(user_id) ON DELETE SET NULL,
    CONSTRAINT chk_lead_status CHECK (status IN ('New', 'Contacted', 'Qualified', 'Unqualified', 'Converted', 'Lost')),
    CONSTRAINT chk_lead_expected_value CHECK (expected_value IS NULL OR expected_value >= 0)
);

-- -----------------------------------------------------------------------------
-- 5. OPPORTUNITIES TABLE
-- Manages sales pipeline deals associated with Customers and Leads.
-- Amount is NUMERIC(14,2) (never float).
-- Probability must be 0 to 100.
-- Stage and Status are maintained as distinct concepts.
-- -----------------------------------------------------------------------------
CREATE TABLE opportunities (
    opportunity_id SERIAL PRIMARY KEY,
    opportunity_name VARCHAR(100) NOT NULL,
    customer_id INT NULL REFERENCES customers(customer_id) ON DELETE RESTRICT,
    lead_id INT NULL REFERENCES leads(lead_id) ON DELETE SET NULL,
    amount NUMERIC(14,2) NOT NULL DEFAULT 0.00,
    stage VARCHAR(20) NOT NULL DEFAULT 'Qualification',
    probability INT NOT NULL DEFAULT 0,
    expected_close_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Open',
    created_date TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_date TIMESTAMPTZ NULL,
    closed_date TIMESTAMPTZ NULL,
    assigned_to INT NULL REFERENCES users(user_id) ON DELETE SET NULL,
    CONSTRAINT chk_opportunity_amount CHECK (amount >= 0),
    CONSTRAINT chk_opportunity_probability CHECK (probability >= 0 AND probability <= 100),
    CONSTRAINT chk_opportunity_stage CHECK (stage IN ('Qualification', 'Proposal', 'Negotiation', 'Won', 'Lost')),
    CONSTRAINT chk_opportunity_status CHECK (status IN ('Open', 'Won', 'Lost'))
);

-- -----------------------------------------------------------------------------
-- 6. FOLLOW-UPS TABLE
-- Tracks scheduled communications linked to Customers, Leads, or Opportunities.
-- -----------------------------------------------------------------------------
CREATE TABLE followups (
    followup_id SERIAL PRIMARY KEY,
    customer_id INT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    lead_id INT NULL REFERENCES leads(lead_id) ON DELETE CASCADE,
    opportunity_id INT NULL REFERENCES opportunities(opportunity_id) ON DELETE CASCADE,
    subject VARCHAR(150) NOT NULL,
    followup_date DATE NOT NULL,
    followup_type VARCHAR(50) NOT NULL,
    remarks TEXT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Planned',
    assigned_to INT NULL REFERENCES users(user_id) ON DELETE SET NULL,
    created_date TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_date TIMESTAMPTZ NULL,
    CONSTRAINT chk_followup_status CHECK (status IN ('Planned', 'Completed', 'Missed', 'Cancelled'))
);

-- -----------------------------------------------------------------------------
-- 7. ACTIVITIES TABLE
-- Maintains audit of sales interactions (Call, Meeting, Email, Task).
-- -----------------------------------------------------------------------------
CREATE TABLE activities (
    activity_id SERIAL PRIMARY KEY,
    activity_type VARCHAR(50) NOT NULL,
    subject VARCHAR(150) NOT NULL,
    description TEXT NULL,
    activity_date TIMESTAMPTZ NOT NULL,
    customer_id INT NULL REFERENCES customers(customer_id) ON DELETE SET NULL,
    lead_id INT NULL REFERENCES leads(lead_id) ON DELETE SET NULL,
    assigned_to INT NULL REFERENCES users(user_id) ON DELETE SET NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Completed',
    created_date TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_date TIMESTAMPTZ NULL,
    CONSTRAINT chk_activity_type CHECK (activity_type IN ('Call', 'Meeting', 'Email', 'Task'))
);

-- -----------------------------------------------------------------------------
-- 8. AUDIT LOG TABLE
-- Historical, append-oriented system audit trail.
-- Sensitive secrets (passwords, hashes, tokens) must NEVER be stored.
-- -----------------------------------------------------------------------------
CREATE TABLE audit_logs (
    audit_log_id SERIAL PRIMARY KEY,
    user_id INT NULL REFERENCES users(user_id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    entity_name VARCHAR(100) NOT NULL,
    record_id VARCHAR(50) NULL,
    old_value JSONB NULL,
    new_value JSONB NULL,
    result VARCHAR(50) NOT NULL DEFAULT 'Success',
    created_date TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(45) NULL
);

-- -----------------------------------------------------------------------------
-- AUDIT LOG IMMUTABILITY TRIGGER
-- Prevents UPDATE and DELETE operations on historical audit log records,
-- enforcing append-only security at the database engine level.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION prevent_audit_log_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit logs are append-only: UPDATE and DELETE operations are forbidden.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_protect_audit_logs
BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW
EXECUTE FUNCTION prevent_audit_log_modification();

-- =============================================================================
-- PERFORMANCE AND AUTHORIZATION INDEXES
-- Index frequently queried columns (lookups, foreign keys, RBAC filters).
-- =============================================================================

-- Users indexes
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role_id ON users(role_id);
CREATE INDEX idx_users_is_active ON users(is_active);

-- Customers indexes
CREATE INDEX idx_customers_email ON customers(email);
CREATE INDEX idx_customers_phone ON customers(phone);
CREATE INDEX idx_customers_assigned_to ON customers(assigned_to);
CREATE INDEX idx_customers_company_name ON customers(company_name);

-- Leads indexes
CREATE INDEX idx_leads_email ON leads(email);
CREATE INDEX idx_leads_status ON leads(status);
CREATE INDEX idx_leads_assigned_to ON leads(assigned_to);
CREATE INDEX idx_leads_company_name ON leads(company_name);

-- Opportunities indexes
CREATE INDEX idx_opportunities_stage ON opportunities(stage);
CREATE INDEX idx_opportunities_status ON opportunities(status);
CREATE INDEX idx_opportunities_assigned_to ON opportunities(assigned_to);
CREATE INDEX idx_opportunities_expected_close_date ON opportunities(expected_close_date);
CREATE INDEX idx_opportunities_customer_id ON opportunities(customer_id);

-- Follow-ups indexes
CREATE INDEX idx_followups_followup_date ON followups(followup_date);
CREATE INDEX idx_followups_status ON followups(status);
CREATE INDEX idx_followups_assigned_to ON followups(assigned_to);
CREATE INDEX idx_followups_customer_id ON followups(customer_id);
CREATE INDEX idx_followups_lead_id ON followups(lead_id);
CREATE INDEX idx_followups_opportunity_id ON followups(opportunity_id);

-- Activities indexes
CREATE INDEX idx_activities_activity_date ON activities(activity_date);
CREATE INDEX idx_activities_status ON activities(status);
CREATE INDEX idx_activities_assigned_to ON activities(assigned_to);
CREATE INDEX idx_activities_customer_id ON activities(customer_id);
CREATE INDEX idx_activities_lead_id ON activities(lead_id);

-- Audit logs indexes
CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_entity_name ON audit_logs(entity_name);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);
CREATE INDEX idx_audit_logs_created_date ON audit_logs(created_date);
