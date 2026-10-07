# AcxiomCRM

Enterprise Role-Based Customer Relationship Management (CRM) application engineered with Python, Flask, raw PostgreSQL (`psycopg2`), and a strict layered architecture.

---

## 1. Project Overview

**AcxiomCRM** is a multi-role Customer Relationship Management system built without heavy ORM abstractions. It provides end-to-end commercial workflows covering Customer Management, Lead Nurturing, Atomic Lead Conversion, and Opportunity Pipeline Management with rigorous role-based access control (RBAC), SQL-level data ownership scoping, financial precision, and an immutable audit trail.

### Key Capabilities
- **Strict Layered Architecture:** Clear separation across Presentation (Routes/Templates) $\rightarrow$ Schemas $\rightarrow$ Application Services $\rightarrow$ Business Rules $\rightarrow$ Repositories (Pure Parameterized SQL) $\rightarrow$ PostgreSQL.
- **Role-Based Access Control (RBAC):** Hierarchical permissions across Administrator, Sales Manager, and Sales Executive roles.
- **SQL-Level Data Ownership:** Row-level multi-tenancy and data isolation enforced directly within SQL queries (`WHERE assigned_to = %s`), preventing in-memory filtering leaks and IDOR vulnerabilities.
- **Lead Lifecycle & Atomic Conversion:** Multi-state lead workflow (`New` $\rightarrow$ `Contacted` $\rightarrow$ `Qualified` $\rightarrow$ `Converted` / `Unqualified` / `Lost`) with transactional conversion creating Customer and Opportunity records in a single atomic database operation.
- **Opportunity Pipeline & Stage Engine:** Sales pipeline progression (`Qualification` $\rightarrow$ `Proposal` $\rightarrow$ `Negotiation` $\rightarrow$ `Won` / `Lost`) with terminal state enforcement, exact Decimal monetary arithmetic, and scope-aware Active and Weighted Pipeline calculations.
- **Enterprise Account Security:** Adaptive scrypt password hashing, complexity policy enforcement, automatic account lockout upon 5 consecutive failed attempts, and secure session rotation.
- **Immutable Audit Logging:** Append-only change log capturing previous and new state diffs in JSON, executed within the exact same database transaction as business mutations, protected by PostgreSQL database triggers.
- **Comprehensive Quality Assurance:** Automated test suite with 230 isolated integration and unit tests passing with zero regressions.

---

## 2. ASP.NET Requirement → Flask Equivalent

The table below outlines how standard enterprise ASP.NET Core architectural patterns are mapped to the Python / Flask ecosystem in AcxiomCRM:

| Requirement | ASP.NET Way | Flask Way | Extra Effort |
| :--- | :--- | :--- | :--- |
| **Users, roles, password hashing** | Identity | `users` & `roles` tables + Werkzeug hashing | Low |
| **Login, logout, register, sessions** | Identity cookies | Flask-Login or Flask session | Low |
| **Password policy** | Identity options | Your own validator function | Low |
| **Account lockout** | Built into Identity | Hand-built: failed count, lockout_end, admin unlock | Medium, and the one most likely to have bugs |
| **Role and ownership authorization** | `[Authorize(Roles=...)]` | Decorators plus `WHERE assigned_to = %s` | Medium |
| **Anti-forgery** | ValidateAntiForgeryToken | Flask-WTF CSRFProtect | Low |
| **SQL injection protection** | EF Core | Parameterized psycopg2 queries | Low, but you must whitelist sort/filter columns |
| **Client and server validation** | Razor and DataAnnotations | JS plus Python validator functions | Medium (you write each rule twice) |
| **DTOs, ViewModels** | Classes | Python dataclasses or serializer functions | Low |
| **REST API with status codes** | Controllers | Flask routes with jsonify | Low |
| **Rate limiting** | Middleware | Flask-Limiter | Low |
| **Dashboard, charts, reports** | Razor and Chart.js | Jinja and Chart.js | None, since Chart.js is the same |

---

## 3. Technology Stack

- **Backend Framework:** Python 3.14+, Flask (Application Factory pattern)
- **Database Engine:** PostgreSQL 16+
- **Database Driver:** `psycopg2-binary` (Pure SQL, raw connections, strictly no ORM)
- **Security & Crypto:** Werkzeug security (`generate_password_hash`, `check_password_hash`), Flask-WTF (CSRF)
- **Rate Limiting:** Flask-Limiter
- **Templating & UI:** Jinja2, Bootstrap 5.3, Vanilla JavaScript
- **Testing Framework:** `pytest` (230 test cases)

---

## 4. System Architecture

```text
HTTP Request
     │
     ▼
[ Routes / Presentation Layer ]
     │  - Authentication & Role verification (@login_required, @roles_required)
     │  - Request payload extraction & CSRF validation
     ▼
[ Schema Layer ]
     │  - Field presence, type casting, string length constraints
     ▼
[ Application Services Layer ]
     │  - Transaction boundaries (BEGIN / COMMIT / ROLLBACK)
     │  - Authorization & record access rules (can_access_record)
     │  - Audit log event coordination
     ▼
[ Domain Business Rules ]
     │  - State machine transition matrices (Lead, Opportunity)
     │  - Exact Decimal monetary validation (Amount > 0)
     │  - Date domain rules (Asia/Kolkata timezone compliance)
     ▼
[ Repositories (Data Access Layer) ]
     │  - Parameterized psycopg2 SQL statements (%s)
     │  - SQL-level row ownership filtering (WHERE assigned_to = ANY(%s))
     │  - Pessimistic row locking (SELECT ... FOR UPDATE)
     ▼
[ PostgreSQL Database ]
        - Foreign key constraints with ON DELETE RESTRICT
        - CHECK constraints on status, stage, probability, and amount
        - Append-only trigger protection on audit_logs
```

---

## 5. Core Modules

### 5.1 Authentication, Sessions & Security
- **Credential Storage:** Adaptive scrypt hashing with per-user unique salt.
- **Password Policy:** Minimum 8 characters, requiring at least one uppercase letter, one lowercase letter, one numeric digit, and one special symbol.
- **Account Lockout:** Locks account for 15 minutes after 5 consecutive failed login attempts; supports administrative manual reset.
- **Session Protection:** Session identifier regeneration on authentication, strict cookie hardening (`HttpOnly`, `SameSite=Lax`), and explicit logout invalidation.
- **Anti-CSRF:** Synchronizer token pattern enforced on all state-altering POST endpoints.

### 5.2 Role-Based Access Control & Ownership Scoping
- **Administrator:** Global system visibility and administrative configuration.
- **Sales Manager:** Departmental/team visibility across subordinate sales representatives.
- **Sales Executive:** Strict self-ownership boundary. Can view and manage only customer accounts, leads, and opportunities assigned to their own user ID.
- **IDOR Defense:** Direct object reference attempts to access unauthorized entities return HTTP 403 Forbidden via server-side verification.

### 5.3 Customer Management
- **Customer Lifecycle:** Active and Inactive customer states.
- **Auto-Generated Code:** Sequential identifier assignment (`CUST-001`, `CUST-002`, ...).
- **Integrity Constraints:** Unique email and phone validation across all customer records.
- **Safe Soft Deactivation:** Status-based archival preserving commercial history and foreign key integrity.

### 5.4 Lead Management & Atomic Lead Conversion
- **Lifecycle Engine:** Governed by state machine:
  - `New` $\rightarrow$ `Contacted`, `Unqualified`, `Lost`
  - `Contacted` $\rightarrow$ `Qualified`, `Unqualified`, `Lost`
  - `Qualified` $\rightarrow$ `Converted`, `Lost`
  - `Converted`, `Unqualified`, `Lost` are terminal states.
- **Lead-to-Deal Conversion:** Converting a `Qualified` lead executes inside a single PostgreSQL transaction:
  1. Verifies/matches or creates the Customer record.
  2. Updates Lead status to `Converted`.
  3. Optionally creates an initial Opportunity linked to both Customer and Lead.
  4. Writes comprehensive audit logs for all mutations.
  5. Rolls back entirely if any individual step fails.

### 5.5 Opportunity Management
- **Stage Progression Engine:** Linear sales milestone workflow:
  - `Qualification` $\rightarrow$ `Proposal` $\rightarrow$ `Negotiation` $\rightarrow$ `Won` / `Lost`
  - `Won` and `Lost` outcomes are strictly terminal and immutable.
- **Stage vs. Status Synchronization:**
  - Active stages (`Qualification`, `Proposal`, `Negotiation`) enforce `Status = 'Open'` and `closed_date = NULL`.
  - `Won` stage enforces `Status = 'Won'` with timestamped `closed_date`.
  - `Lost` stage enforces `Status = 'Lost'` with timestamped `closed_date`.
- **Financial Precision:** Currency stored as PostgreSQL `NUMERIC(14,2)` and manipulated strictly with Python `Decimal`. Floating-point arithmetic is strictly prohibited.
- **Pipeline Calculations:**
  - **Active Pipeline Value:** $\sum \text{Amount}$ for `Status = 'Open'` opportunities only. Historical won and lost deals are strictly excluded.
  - **Weighted Pipeline Value:** $\sum (\text{Amount} \times \frac{\text{Probability}}{100})$ for `Status = 'Open'` opportunities.
  - Calculations are scoped at the SQL layer according to the viewing user's role.

### 5.6 Immutable Audit Trail
- Logs every `CREATE`, `UPDATE`, and `STATUS_CHANGE` action with the executing user ID, IP address, timestamp, and JSON before/after state diffs.
- Sensitive data (passwords, tokens, secrets) is excluded from audit payloads.
- Database-level trigger `trg_protect_audit_logs` raises an exception on any attempted `UPDATE` or `DELETE` against the `audit_logs` table.

---

## 6. Installation and Setup

### Prerequisites
- Python 3.14+ (or Python 3.11+)
- PostgreSQL 16+ running locally or remotely

### Step 1: Clone Repository & Virtual Environment
```bash
git clone https://github.com/Dusi-81wb/AxciomCRM.git
cd AxciomCRM

python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Linux / macOS
source .venv/bin/activate
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 3: Configure Environment
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Ensure database credentials and settings are set:
```ini
SECRET_KEY=your-secure-random-secret-key
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/acxiomcrm
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/acxiomcrm_test
APPLICATION_TIMEZONE=Asia/Kolkata
```

### Step 4: Initialize and Seed Database
Run the CLI commands to provision tables and seed initial demo data:
```bash
flask init-db
flask seed-db
```

---

## 7. Demo Accounts

| Role | Username | Email | Password | Scope |
| :--- | :--- | :--- | :--- | :--- |
| **Administrator** | `admin` | `admin@acxiomcrm.com` | `Admin@123` | Full administrative visibility across all accounts and deals |
| **Sales Manager** | `manager` | `manager@acxiomcrm.com` | `Manager@123` | Management-level oversight across sales teams |
| **Sales Executive** | `sales1` | `sales@acxiomcrm.com` | `Sales@123` | Assigned customer accounts, leads, and opportunities |
| **Sales Executive** | `sales2` | `sales2@acxiomcrm.com` | `Sales@123` | Assigned customer accounts, leads, and opportunities |

---

## 8. Running the Application

Start the Flask development server:
```bash
python app.py
```
Or via Flask CLI:
```bash
flask run --port=5000
```
Navigate to `http://127.0.0.1:5000` to access the CRM portal.

---

## 9. Automated Testing

AcxiomCRM includes an automated test suite verifying security, business logic, transactions, and RBAC constraints.

To run the complete test suite:
```bash
python -m pytest -v
```

### Test Coverage Highlights:
- **Startup & Health:** App factory initialization, extension registration, connection teardown.
- **Database Foundation:** Schema constraints, primary/foreign keys, indexes, append-only audit trigger.
- **Authentication & Lockout:** Password policy validation, lockout after 5 failures, session fixation immunity.
- **Authorization & RBAC:** Role enforcement, manager/rep scope filtering, IDOR protection.
- **Customer Management:** Customer CRUD, validation, unique phone/email constraints, soft deactivation.
- **Lead Management & Conversion:** Lead state machine, conversion to Customer + Opportunity, atomicity rollback.
- **Opportunity Management:** Linear stage machine, stage/status synchronization, terminal states, Decimal pipeline sums.

```text
============================ 230 passed in 53.30s =============================
```

---

## 10. License

This project is licensed under the MIT License.
