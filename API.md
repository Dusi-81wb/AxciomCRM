# AcxiomCRM REST API Documentation

This document describes the REST API endpoints implemented for AcxiomCRM in **Phase 11**.

The API provides secure, layered JSON access to the core CRM resources:
1. **Customers** (`/api/customers`)
2. **Leads** (`/api/leads`)
3. **Opportunities** (`/api/opportunities`)

All endpoints adhere to architectural layers:
`HTTP Request` &rarr; `routes/api_routes.py` &rarr; `schemas/api_schema.py` (Validation & DTO serialization) &rarr; Domain Services (`services/`) &rarr; Repositories (`repositories/`) &rarr; PostgreSQL (`psycopg2`).

---

## 1. Architectural & Security Overview

### 1.1 Authentication
- **Mechanism**: Established server-side session authentication (`session['user_id']`).
- **Header / State**: Session cookie transmitted with HTTP requests.
- **Unauthenticated Handling**: Any request lacking an active session returns HTTP `401 Unauthorized` as pure JSON:
  ```json
  {
    "error": "Authentication required. Please log in."
  }
  ```
- **No HTML Leaks**: API routes never return HTML login forms or error pages.

### 1.2 CSRF Protection
- Following blueprint specifications, `/api/` endpoints are exempt from browser form CSRF token validation (`csrf.exempt(api_bp)`), enabling standard REST client interactions while relying on session authorization.

### 1.3 Role-Based Authorization & Ownership Scoping
- **Admin**: Global access across all CRM records. May explicitly assign any active Sales Executive.
- **Manager**: Scope access across team records. May explicitly assign any active Sales Executive.
- **Sales Executive**:
  - Read queries automatically restrict results to records assigned to the authenticated user (`WHERE assigned_to = %s`).
  - Accessing a record assigned to another sales executive results in HTTP `403 Forbidden` (preventing Insecure Direct Object References - IDOR).
  - Creation automatically enforces self-assignment (`assigned_to = current_user.user_id`). Submitted `assigned_to` fields are ignored or rejected.
  - Updates cannot reassign records to other sales representatives or alter restricted statuses.

### 1.4 Data Transfer Objects (DTOs)
- Database internal entities and column names are never exposed raw.
- Output serializers filter out all sensitive data:
  - **Excluded**: `password_hash`, session keys, internal database row IDs, tokens, database connection states.
- **Monetary Precision**: Money fields (e.g. `amount`, `weighted_pipeline`) are formatted as exact decimal strings with two decimal places (e.g., `"250000.00"`), avoiding IEEE-754 floating-point inaccuracies.
- **Datetime Formatting**: ISO 8601 strings (e.g., `"2026-10-08T14:30:00"`).

### 1.5 Standard HTTP Status Codes
| Status Code | Meaning | Usage |
|---|---|---|
| `200 OK` | Success | Successful `GET` listing, `GET` detail, or `PUT` update. |
| `201 Created` | Created | Successful `POST` creation of a resource. |
| `400 Bad Request` | Bad Request | Input validation error, invalid business state, or malformed JSON body. |
| `401 Unauthorized` | Unauthorized | Unauthenticated request (session cookie missing or invalid). |
| `403 Forbidden` | Forbidden | Authenticated, but lacking role permission or accessing another rep's record (IDOR). |
| `404 Not Found` | Not Found | Resource ID does not exist or URL is invalid. |
| `409 Conflict` | Conflict | Business uniqueness conflict (e.g. duplicate customer email or phone). |

---

## 2. Customer Endpoints

### 2.1 List Customers
- **Method**: `GET`
- **URL**: `/api/customers`
- **Authentication**: Session required.
- **Authorization**:
  - `Admin`: Sees all customers.
  - `Manager`: Sees team/scoped customers.
  - `Sales Executive`: Sees only assigned customers.
- **Query Parameters**:
  - `search` (string, optional): Search by customer name, company, email, or phone.
  - `status` (string, optional): Filter by status (`Active` or `Inactive`).
- **Response**: `200 OK`
  ```json
  {
    "data": [
      {
        "customer_id": 1,
        "customer_code": "CUST-001",
        "customer_name": "Apex Innovations Ltd",
        "email": "contact@apexinno.example.com",
        "phone": "+91-9876543210",
        "company_name": "Apex Innovations",
        "address": "42 Cyber City Phase 2",
        "city": "Bengaluru",
        "state": "Karnataka",
        "status": "Active",
        "created_by": 1,
        "assigned_to": 3,
        "assigned_to_name": "Rahul Verma",
        "created_date": "2026-10-01T10:00:00",
        "modified_date": "2026-10-01T10:00:00"
      }
    ],
    "count": 1
  }
  ```

---

### 2.2 Get Customer by ID
- **Method**: `GET`
- **URL**: `/api/customers/<id>`
- **Authentication**: Session required.
- **Authorization**:
  - `Admin`: Can view any customer.
  - `Manager`: Can view within scope.
  - `Sales Executive`: Can only view assigned customer. Accessing an unassigned customer returns `403 Forbidden`.
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "customer_id": 1,
      "customer_code": "CUST-001",
      "customer_name": "Apex Innovations Ltd",
      "email": "contact@apexinno.example.com",
      "phone": "+91-9876543210",
      "company_name": "Apex Innovations",
      "address": "42 Cyber City Phase 2",
      "city": "Bengaluru",
      "state": "Karnataka",
      "status": "Active",
      "created_by": 1,
      "assigned_to": 3,
      "assigned_to_name": "Rahul Verma",
      "created_date": "2026-10-01T10:00:00",
      "modified_date": "2026-10-01T10:00:00"
    }
  }
  ```
- **Error Responses**:
  - `401 Unauthorized`: Not logged in.
  - `403 Forbidden`: Sales Executive attempting to access another representative's customer.
  - `404 Not Found`: Customer does not exist.

---

### 2.3 Create Customer
- **Method**: `POST`
- **URL**: `/api/customers`
- **Authentication**: Session required.
- **Authorization**:
  - `Admin` & `Manager`: May specify `assigned_to` (must be an active Sales Executive).
  - `Sales Executive`: Automatically self-assigned. Any client-provided `assigned_to` is ignored.
- **Headers**: `Content-Type: application/json`
- **Request Body**:
  ```json
  {
    "customer_name": "Nexus Global Tech",
    "email": "info@nexusglobal.example.com",
    "phone": "+91-9812345678",
    "company_name": "Nexus Global",
    "address": "15 Electronic City",
    "city": "Bengaluru",
    "state": "Karnataka",
    "assigned_to": 3
  }
  ```
- **Validation**:
  - `customer_name`: Required, max 100 chars.
  - `email`: Required, valid email format, max 100 chars, unique across active and inactive customers.
  - `phone`: Required, valid phone (10-15 digits), max 20 chars, unique across customers.
  - `assigned_to`: If Admin/Manager, must be active Sales Executive.
- **Response**: `201 Created`
  ```json
  {
    "message": "Customer created successfully.",
    "data": {
      "customer_id": 6,
      "customer_code": "CUST-006",
      "customer_name": "Nexus Global Tech",
      "email": "info@nexusglobal.example.com",
      "phone": "+91-9812345678",
      "company_name": "Nexus Global",
      "address": "15 Electronic City",
      "city": "Bengaluru",
      "state": "Karnataka",
      "status": "Active",
      "created_by": 1,
      "assigned_to": 3,
      "assigned_to_name": "Rahul Verma",
      "created_date": "2026-10-08T18:00:00",
      "modified_date": "2026-10-08T18:00:00"
    }
  }
  ```
- **Error Responses**:
  - `400 Bad Request`: Input validation failed (e.g. invalid email format, missing required field).
  - `409 Conflict`: Customer with email or phone already exists.

---

### 2.4 Update Customer
- **Method**: `PUT`
- **URL**: `/api/customers/<id>`
- **Authentication**: Session required.
- **Authorization**:
  - `Admin` & `Manager`: Can update all details, reassign, or alter status (`Active` / `Inactive`).
  - `Sales Executive`: Can update details for assigned customer only; cannot reassign or change status.
- **Headers**: `Content-Type: application/json`
- **Request Body**:
  ```json
  {
    "customer_name": "Nexus Global Technologies Ltd",
    "email": "contact@nexusglobal.example.com",
    "phone": "+91-9812345678",
    "company_name": "Nexus Global",
    "address": "15 Electronic City Phase 1",
    "city": "Bengaluru",
    "state": "Karnataka"
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "message": "Customer updated successfully.",
    "data": {
      "customer_id": 6,
      "customer_code": "CUST-006",
      "customer_name": "Nexus Global Technologies Ltd",
      "email": "contact@nexusglobal.example.com",
      "phone": "+91-9812345678",
      "company_name": "Nexus Global",
      "address": "15 Electronic City Phase 1",
      "city": "Bengaluru",
      "state": "Karnataka",
      "status": "Active",
      "created_by": 1,
      "assigned_to": 3,
      "assigned_to_name": "Rahul Verma",
      "created_date": "2026-10-08T18:00:00",
      "modified_date": "2026-10-08T18:15:00"
    }
  }
  ```
- **Error Responses**:
  - `400 Bad Request`: Validation failure.
  - `403 Forbidden`: Unauthorized edit or attempted reassignment by Sales Executive.
  - `404 Not Found`: Customer not found.
  - `409 Conflict`: Email or phone conflicts with another customer.

---

## 3. Lead Endpoints

### 3.1 List Leads
- **Method**: `GET`
- **URL**: `/api/leads`
- **Authentication**: Session required.
- **Authorization**: Scoped by role (Admin sees all; Manager sees team; Sales Exec sees assigned).
- **Query Parameters**:
  - `search` (string, optional): Search by name, company, email, phone.
  - `status` (string, optional): Filter by status (`New`, `Contacted`, `Qualified`, `Unqualified`, `Converted`, `Lost`).
  - `assigned_to` (integer, optional): Filter by sales representative (Admin/Manager only).
- **Response**: `200 OK`
  ```json
  {
    "data": [
      {
        "lead_id": 1,
        "lead_code": "LEAD-001",
        "lead_name": "Vikram Sethi",
        "email": "vikram@example.com",
        "phone": "+91-9123456780",
        "company_name": "Sethi Enterprises",
        "source": "Website",
        "status": "New",
        "expected_value": "150000.00",
        "notes": "Initial web inquiry",
        "assigned_to": 3,
        "assigned_to_name": "Rahul Verma",
        "created_by": 1,
        "created_date": "2026-10-02T11:00:00",
        "modified_date": "2026-10-02T11:00:00"
      }
    ],
    "count": 1
  }
  ```

---

### 3.2 Get Lead by ID
- **Method**: `GET`
- **URL**: `/api/leads/<id>`
- **Authentication**: Session required.
- **Authorization**: Scoped to user's assigned records or role scope.
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "lead_id": 1,
      "lead_code": "LEAD-001",
      "lead_name": "Vikram Sethi",
      "email": "vikram@example.com",
      "phone": "+91-9123456780",
      "company_name": "Sethi Enterprises",
      "source": "Website",
      "status": "New",
      "expected_value": "150000.00",
      "notes": "Initial web inquiry",
      "assigned_to": 3,
      "assigned_to_name": "Rahul Verma",
      "created_by": 1,
      "created_date": "2026-10-02T11:00:00",
      "modified_date": "2026-10-02T11:00:00"
    }
  }
  ```
- **Error Responses**:
  - `401 Unauthorized`: Missing session.
  - `403 Forbidden`: Unauthorized IDOR access by Sales Executive.
  - `404 Not Found`: Lead does not exist.

---

### 3.3 Create Lead
- **Method**: `POST`
- **URL**: `/api/leads`
- **Authentication**: Session required.
- **Authorization**:
  - `Admin` & `Manager`: Must explicitly assign an active Sales Executive.
  - `Sales Executive`: Automatically self-assigned.
- **Headers**: `Content-Type: application/json`
- **Request Body**:
  ```json
  {
    "lead_name": "Priya Sharma",
    "email": "priya.sharma@example.com",
    "phone": "+91-9876543219",
    "company_name": "Sharma Consultancy",
    "source": "Referral",
    "status": "New",
    "expected_value": "200000.00",
    "notes": "Referred by existing client",
    "assigned_to": 3
  }
  ```
- **Validation**:
  - `lead_name`: Required, max 100 chars.
  - `email`: Required, valid email format.
  - `phone`: Required, valid phone.
  - `status`: Allowed statuses: `New`, `Contacted`, `Qualified`, `Unqualified`, `Lost` (initial creation cannot be `Converted`).
  - `expected_value`: Must be >= 0.
- **Response**: `201 Created`
  ```json
  {
    "message": "Lead created successfully.",
    "data": {
      "lead_id": 6,
      "lead_code": "LEAD-006",
      "lead_name": "Priya Sharma",
      "email": "priya.sharma@example.com",
      "phone": "+91-9876543219",
      "company_name": "Sharma Consultancy",
      "source": "Referral",
      "status": "New",
      "expected_value": "200000.00",
      "notes": "Referred by existing client",
      "assigned_to": 3,
      "assigned_to_name": "Rahul Verma",
      "created_by": 1,
      "created_date": "2026-10-08T18:20:00",
      "modified_date": "2026-10-08T18:20:00"
    }
  }
  ```
- **Error Responses**:
  - `400 Bad Request`: Validation failure or invalid status.
  - `403 Forbidden`: Unauthorized assignment.

---

### 3.4 Update Lead
- **Method**: `PUT`
- **URL**: `/api/leads/<id>`
- **Authentication**: Session required.
- **Authorization**: Scoped to user's assigned records or role scope.
- **Headers**: `Content-Type: application/json`
- **Request Body**:
  ```json
  {
    "lead_name": "Priya Sharma",
    "email": "priya.sharma@example.com",
    "phone": "+91-9876543219",
    "company_name": "Sharma Consultancy",
    "source": "Referral",
    "status": "Contacted",
    "expected_value": "250000.00",
    "notes": "Spoke on phone, scheduled follow-up."
  }
  ```
- **Business Rule Enforcement**:
  - Status updates must conform to the approved **Lead Transition Matrix**:
    - `New` &rarr; `Contacted`, `Unqualified`, `Lost`
    - `Contacted` &rarr; `Qualified`, `Unqualified`, `Lost`
    - `Qualified` &rarr; `Lost` (conversion to `Converted` happens only via the approved conversion workflow)
    - Terminal states (`Unqualified`, `Converted`, `Lost`) cannot transition to any other status.
- **Response**: `200 OK`
  ```json
  {
    "message": "Lead updated successfully.",
    "data": {
      "lead_id": 6,
      "lead_code": "LEAD-006",
      "lead_name": "Priya Sharma",
      "email": "priya.sharma@example.com",
      "phone": "+91-9876543219",
      "company_name": "Sharma Consultancy",
      "source": "Referral",
      "status": "Contacted",
      "expected_value": "250000.00",
      "notes": "Spoke on phone, scheduled follow-up.",
      "assigned_to": 3,
      "assigned_to_name": "Rahul Verma",
      "created_by": 1,
      "created_date": "2026-10-08T18:20:00",
      "modified_date": "2026-10-08T18:25:00"
    }
  }
  ```
- **Error Responses**:
  - `400 Bad Request`: Disallowed status transition or validation failure.
  - `403 Forbidden`: Sales Executive attempting to edit unassigned lead.
  - `404 Not Found`: Lead not found.

---

## 4. Opportunity Endpoints

### 4.1 List Opportunities
- **Method**: `GET`
- **URL**: `/api/opportunities`
- **Authentication**: Session required.
- **Authorization**: Scoped by role.
- **Query Parameters**:
  - `search` (string, optional): Search by deal name or customer name.
  - `stage` (string, optional): Filter by stage (`Qualification`, `Proposal`, `Negotiation`, `Won`, `Lost`).
  - `status` (string, optional): Filter by status (`Open`, `Won`, `Lost`).
- **Response**: `200 OK`
  ```json
  {
    "data": [
      {
        "opportunity_id": 1,
        "opportunity_name": "Enterprise ERP License",
        "customer_id": 1,
        "customer_name": "Apex Innovations Ltd",
        "lead_id": null,
        "amount": "250000.00",
        "stage": "Qualification",
        "probability": 25,
        "expected_close_date": "2026-11-15",
        "status": "Open",
        "assigned_to": 3,
        "assigned_to_name": "Rahul Verma",
        "created_date": "2026-10-01T12:00:00",
        "modified_date": "2026-10-01T12:00:00",
        "closed_date": null,
        "weighted_pipeline": "62500.00"
      }
    ],
    "count": 1
  }
  ```

---

### 4.2 Get Opportunity by ID
- **Method**: `GET`
- **URL**: `/api/opportunities/<id>`
- **Authentication**: Session required.
- **Authorization**: Scoped to user's assigned records or role scope.
- **Response**: `200 OK`
  ```json
  {
    "data": {
      "opportunity_id": 1,
      "opportunity_name": "Enterprise ERP License",
      "customer_id": 1,
      "customer_name": "Apex Innovations Ltd",
      "lead_id": null,
      "amount": "250000.00",
      "stage": "Qualification",
      "probability": 25,
      "expected_close_date": "2026-11-15",
      "status": "Open",
      "assigned_to": 3,
      "assigned_to_name": "Rahul Verma",
      "created_date": "2026-10-01T12:00:00",
      "modified_date": "2026-10-01T12:00:00",
      "closed_date": null,
      "weighted_pipeline": "62500.00"
    }
  }
  ```
- **Error Responses**:
  - `401 Unauthorized`: Missing session.
  - `403 Forbidden`: Sales Executive attempting to view another representative's deal.
  - `404 Not Found`: Deal does not exist.

---

### 4.3 Create Opportunity
- **Method**: `POST`
- **URL**: `/api/opportunities`
- **Authentication**: Session required.
- **Authorization**:
  - `Admin` & `Manager`: Must explicitly select an active Sales Executive.
  - `Sales Executive`: Automatically self-assigned.
- **Headers**: `Content-Type: application/json`
- **Request Body**:
  ```json
  {
    "opportunity_name": "Cloud Migration Services",
    "customer_id": 1,
    "amount": "500000.00",
    "stage": "Qualification",
    "probability": 30,
    "expected_close_date": "2026-12-31",
    "assigned_to": 3
  }
  ```
- **Validation & Business Rules**:
  - `opportunity_name`: Required, max 150 chars.
  - `customer_id`: Required; must reference an active, existing Customer within user's scope.
  - `amount`: For active (Open) opportunities, must be strictly greater than 0 (`amount > 0`).
  - `probability`: Integer between 0 and 100 inclusive.
  - `expected_close_date`: Must not be in the past (validated against `Asia/Kolkata` current business date).
  - Customer status: Must be `Active`. Deals cannot be created for Inactive customers.
- **Response**: `201 Created`
  ```json
  {
    "message": "Opportunity created successfully.",
    "data": {
      "opportunity_id": 5,
      "opportunity_name": "Cloud Migration Services",
      "customer_id": 1,
      "customer_name": "Apex Innovations Ltd",
      "lead_id": null,
      "amount": "500000.00",
      "stage": "Qualification",
      "probability": 30,
      "expected_close_date": "2026-12-31",
      "status": "Open",
      "assigned_to": 3,
      "assigned_to_name": "Rahul Verma",
      "created_date": "2026-10-08T18:30:00",
      "modified_date": "2026-10-08T18:30:00",
      "closed_date": null,
      "weighted_pipeline": "150000.00"
    }
  }
  ```
- **Error Responses**:
  - `400 Bad Request`: Invalid amount (<= 0), invalid probability (< 0 or > 100), past close date, or inactive customer.
  - `403 Forbidden`: Sales Executive attempting to create opportunity against another rep's customer.

---

### 4.4 Update Opportunity
- **Method**: `PUT`
- **URL**: `/api/opportunities/<id>`
- **Authentication**: Session required.
- **Authorization**: Scoped to user's assigned records or role scope.
- **Headers**: `Content-Type: application/json`
- **Request Body**:
  ```json
  {
    "opportunity_name": "Cloud Migration Services - Expanded",
    "customer_id": 1,
    "amount": "550000.00",
    "stage": "Proposal",
    "probability": 60,
    "expected_close_date": "2026-12-31"
  }
  ```
- **Stage Progression Rules**:
  - Active transitions:
    - `Qualification` &rarr; `Proposal`, `Lost`
    - `Proposal` &rarr; `Negotiation`, `Lost`
    - `Negotiation` &rarr; `Won`, `Lost`
  - Terminal stages (`Won`, `Lost`) are strictly locked and cannot be edited or reopened.
- **Response**: `200 OK`
  ```json
  {
    "message": "Opportunity updated successfully.",
    "data": {
      "opportunity_id": 5,
      "opportunity_name": "Cloud Migration Services - Expanded",
      "customer_id": 1,
      "customer_name": "Apex Innovations Ltd",
      "lead_id": null,
      "amount": "550000.00",
      "stage": "Proposal",
      "probability": 60,
      "expected_close_date": "2026-12-31",
      "status": "Open",
      "assigned_to": 3,
      "assigned_to_name": "Rahul Verma",
      "created_date": "2026-10-08T18:30:00",
      "modified_date": "2026-10-08T18:35:00",
      "closed_date": null,
      "weighted_pipeline": "330000.00"
    }
  }
  ```
- **Error Responses**:
  - `400 Bad Request`: Disallowed stage transition, or attempt to modify terminal Won/Lost opportunity.
  - `403 Forbidden`: Sales Executive attempting to update unassigned opportunity.
  - `404 Not Found`: Opportunity not found.

---

## 5. Security & Traceability Summary

1. **Anti-IDOR Policy**:
   All database SELECT, UPDATE, and INSERT queries resolve tenant and ownership boundaries using parameterized `WHERE assigned_to = %s` or `WHERE assigned_to = ANY(%s)`. The server never trusts client-supplied user IDs or ownership indicators.
2. **Atomic Audit Logging**:
   Every state-changing API operation (`POST`, `PUT`) writes an audit log entry in the `audit_logs` table within the same transaction block as the business record update.
3. **Pure JSON Guarantee**:
   All error handlers (`400`, `401`, `403`, `404`, `500`) dynamically return `{ "error": "..." }` when the request begins with `/api/` or sets `Accept: application/json`.
