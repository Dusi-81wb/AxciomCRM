-- =============================================================================
-- AcxiomCRM — Phase 1 Seed / Demo Data
--
-- Inserts the three required system roles, sample users with secure Werkzeug hashes,
-- and realistic CRM sample records for demonstration and automated testing.
-- No plaintext passwords or real personal data are included.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. SEED ROLES
-- Mandatory roles defined by MASTER_BLUEPRINT.md Section 20.
-- -----------------------------------------------------------------------------
INSERT INTO roles (role_id, role_name) VALUES
    (1, 'Admin'),
    (2, 'Manager'),
    (3, 'Sales Executive')
ON CONFLICT (role_id) DO NOTHING;

-- -----------------------------------------------------------------------------
-- 2. SEED USERS
-- Demo credentials (documented in README.md):
--   - admin@acxiomcrm.com / Admin@123 (Role: Admin)
--   - manager@acxiomcrm.com / Manager@123 (Role: Manager)
--   - sales@acxiomcrm.com / Sales@123 (Role: Sales Executive)
--   - sales2@acxiomcrm.com / Sales@123 (Role: Sales Executive)
-- Hashes generated via Werkzeug scrypt (generate_password_hash).
-- -----------------------------------------------------------------------------
INSERT INTO users (user_id, username, email, password_hash, is_active, role_id) VALUES
    (1, 'admin', 'admin@acxiomcrm.com', 'scrypt:32768:8:1$MMzVlpfCZ6UnaBAZ$b89b3a16c68a9f9e762421aadf24ea0995cb9f1b68b9f2d924f18328c716516aa5e718c7cacf06bdb30266d048134ebd9067650902a4efdae122bfe63e1bf567', TRUE, 1),
    (2, 'manager', 'manager@acxiomcrm.com', 'scrypt:32768:8:1$wOFLpdPxDGf4YrcR$a5189fc12852d046e3fbcbe0f1fb27c344e37a35a83cdf7264982a3da710f84c97e0a2d3ff1032f693081cdfadee19d2c575f136fb660bf533727e2e8af8891c', TRUE, 2),
    (3, 'sales1', 'sales@acxiomcrm.com', 'scrypt:32768:8:1$wl4qwBf5YxEqirBM$5da6c6414d5169325ff176b7a818ae490c9524bf75aac21b32445f9556a9f7be47bde11f1d286ca1ea0f5ecffc2020018cf0617adeb31404e6d43eb7e14ca49c', TRUE, 3),
    (4, 'sales2', 'sales2@acxiomcrm.com', 'scrypt:32768:8:1$wl4qwBf5YxEqirBM$5da6c6414d5169325ff176b7a818ae490c9524bf75aac21b32445f9556a9f7be47bde11f1d286ca1ea0f5ecffc2020018cf0617adeb31404e6d43eb7e14ca49c', TRUE, 3)
ON CONFLICT (user_id) DO NOTHING;

-- -----------------------------------------------------------------------------
-- 3. SEED CUSTOMERS
-- Represents accounts with Active / Inactive states and sales assignment.
-- -----------------------------------------------------------------------------
INSERT INTO customers (customer_id, customer_code, customer_name, email, phone, company_name, address, city, state, status, assigned_to, created_by) VALUES
    (1, 'CUST-001', 'Apex Global Solutions', 'contact@apexsolutions.example', '+91-9876543210', 'Apex Solutions', '123 Tech Park', 'Bengaluru', 'Karnataka', 'Active', 3, 1),
    (2, 'CUST-002', 'Zenith Retail Corp', 'info@zenithretail.example', '+91-9876543211', 'Zenith Retail', '45 Market Road', 'Mumbai', 'Maharashtra', 'Active', 3, 1),
    (3, 'CUST-003', 'Horizon Logistics Ltd', 'ops@horizonlogistics.example', '+91-9876543212', 'Horizon Logistics', '88 Portway', 'Hyderabad', 'Telangana', 'Active', 4, 2),
    (4, 'CUST-004', 'Legacy Industries', 'support@legacyind.example', '+91-9876543213', 'Legacy Industries', '12 Industrial Area', 'Chennai', 'Tamil Nadu', 'Inactive', 4, 1)
ON CONFLICT (customer_id) DO NOTHING;

-- -----------------------------------------------------------------------------
-- 4. SEED LEADS
-- Demonstrates all 6 canonical lead statuses:
-- New, Contacted, Qualified, Unqualified, Converted, Lost.
-- -----------------------------------------------------------------------------
INSERT INTO leads (lead_id, lead_code, lead_name, email, phone, company_name, source, status, expected_value, assigned_to) VALUES
    (1, 'LEAD-001', 'Rohan Verma', 'rohan@innovatetech.example', '+91-9123456780', 'Innovate Tech', 'Website', 'New', 75000.00, 3),
    (2, 'LEAD-002', 'Priya Sharma', 'priya@finserve.example', '+91-9123456781', 'FinServe Corp', 'Referral', 'Contacted', 120000.00, 3),
    (3, 'LEAD-003', 'Amit Patel', 'amit@cloudcore.example', '+91-9123456782', 'CloudCore Systems', 'LinkedIn', 'Qualified', 250000.00, 4),
    (4, 'LEAD-004', 'Ananya Sen', 'ananya@retailplus.example', '+91-9123456783', 'RetailPlus', 'Cold Call', 'Unqualified', 15000.00, 4),
    (5, 'LEAD-005', 'Vikram Rao', 'vikram@apexsolutions.example', '+91-9123456784', 'Apex Solutions', 'Website', 'Converted', 300000.00, 3),
    (6, 'LEAD-006', 'Kavita Reddy', 'kavita@outdated.example', '+91-9123456785', 'Outdated Corp', 'Event', 'Lost', 50000.00, 3)
ON CONFLICT (lead_id) DO NOTHING;

-- -----------------------------------------------------------------------------
-- 5. SEED OPPORTUNITIES
-- Demonstrates stages (Qualification, Proposal, Negotiation, Won, Lost)
-- and statuses (Open, Won, Lost), with NUMERIC(14,2) currency amounts.
-- -----------------------------------------------------------------------------
INSERT INTO opportunities (opportunity_id, opportunity_name, customer_id, lead_id, amount, stage, probability, expected_close_date, status, closed_date, assigned_to) VALUES
    (1, 'Apex Cloud Migration', 1, 5, 300000.00, 'Negotiation', 70, '2026-11-15', 'Open', NULL, 3),
    (2, 'Apex Security Suite', 1, NULL, 85000.00, 'Proposal', 50, '2026-12-01', 'Open', NULL, 3),
    (3, 'Zenith POS Upgrade', 2, NULL, 150000.00, 'Qualification', 20, '2026-12-20', 'Open', NULL, 3),
    (4, 'Horizon Fleet ERP', 3, NULL, 500000.00, 'Won', 100, '2026-10-01', 'Won', '2026-10-01 10:00:00+05:30', 4),
    (5, 'Legacy Modernization Deal', 4, NULL, 200000.00, 'Lost', 0, '2026-09-15', 'Lost', '2026-09-15 16:30:00+05:30', 4)
ON CONFLICT (opportunity_id) DO NOTHING;

-- -----------------------------------------------------------------------------
-- 6. SEED FOLLOW-UPS
-- Demonstrates Planned, Completed, Missed, and Cancelled communication logs.
-- -----------------------------------------------------------------------------
INSERT INTO followups (followup_id, customer_id, lead_id, opportunity_id, subject, followup_date, followup_type, remarks, status, assigned_to) VALUES
    (1, 1, NULL, 1, 'Review cloud migration contract proposal', '2026-10-15', 'Meeting', 'Client agreed to review terms before sign-off.', 'Planned', 3),
    (2, NULL, 2, NULL, 'Call Priya regarding FinServe requirements', '2026-10-05', 'Call', 'Discussed budget and deployment expectations.', 'Completed', 3),
    (3, NULL, 1, NULL, 'Initial discovery call with Rohan', '2026-10-02', 'Call', 'Contact did not answer, left voicemail.', 'Missed', 3),
    (4, 4, NULL, 5, 'Follow up on legacy modernization proposal', '2026-09-10', 'Email', 'Deal lost to competitor; follow-up cancelled.', 'Cancelled', 4)
ON CONFLICT (followup_id) DO NOTHING;

-- -----------------------------------------------------------------------------
-- 7. SEED ACTIVITIES
-- Demonstrates activity interaction types: Call, Meeting, Email, Task.
-- -----------------------------------------------------------------------------
INSERT INTO activities (activity_id, activity_type, subject, description, activity_date, customer_id, lead_id, assigned_to, status) VALUES
    (1, 'Call', 'Initial inquiry discussion', 'Discussed customer requirements and product scope.', '2026-10-04 11:00:00+05:30', NULL, 2, 3, 'Completed'),
    (2, 'Meeting', 'Architecture review with CTO', 'Deep-dive into cloud security and migration architecture.', '2026-10-06 14:30:00+05:30', 1, NULL, 3, 'Completed'),
    (3, 'Email', 'Sent fleet ERP contract documentation', 'Emailed final signed agreements for Horizon deal.', '2026-09-28 09:15:00+05:30', 3, NULL, 4, 'Completed'),
    (4, 'Task', 'Prepare competitive pricing analysis', 'Analyze competitor offerings for the upcoming negotiation.', '2026-10-08 17:00:00+05:30', 1, NULL, 3, 'Completed')
ON CONFLICT (activity_id) DO NOTHING;

-- -----------------------------------------------------------------------------
-- 8. SEED AUDIT LOGS
-- Immutable, append-only historical audit records.
-- Demonstrates audit logging without exposing sensitive data.
-- -----------------------------------------------------------------------------
INSERT INTO audit_logs (audit_log_id, user_id, action, entity_name, record_id, old_value, new_value, result, created_date, ip_address) VALUES
    (1, 1, 'SYSTEM_INIT', 'System', '0', NULL, '{"event": "Database seeded with demonstration records"}', 'Success', CURRENT_TIMESTAMP, '127.0.0.1'),
    (2, 1, 'USER_CREATE', 'User', '1', NULL, '{"username": "admin", "role": "Admin"}', 'Success', CURRENT_TIMESTAMP, '127.0.0.1'),
    (3, 3, 'LEAD_CONVERSION', 'Lead', '5', '{"status": "Qualified"}', '{"status": "Converted", "customer_id": 1}', 'Success', CURRENT_TIMESTAMP, '127.0.0.1')
ON CONFLICT (audit_log_id) DO NOTHING;

-- Reset primary key sequences to ensure future INSERTs generate valid IDs
SELECT setval('roles_role_id_seq', (SELECT MAX(role_id) FROM roles));
SELECT setval('users_user_id_seq', (SELECT MAX(user_id) FROM users));
SELECT setval('customers_customer_id_seq', (SELECT MAX(customer_id) FROM customers));
SELECT setval('leads_lead_id_seq', (SELECT MAX(lead_id) FROM leads));
SELECT setval('opportunities_opportunity_id_seq', (SELECT MAX(opportunity_id) FROM opportunities));
SELECT setval('followups_followup_id_seq', (SELECT MAX(followup_id) FROM followups));
SELECT setval('activities_activity_id_seq', (SELECT MAX(activity_id) FROM activities));
SELECT setval('audit_logs_audit_log_id_seq', (SELECT MAX(audit_log_id) FROM audit_logs));
