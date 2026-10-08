"""
Comprehensive REST API Integration Tests for AcxiomCRM (Phase 11).

Covers all 56 API requirements:
- Part 1: API Authentication & Access Control (401 vs 403 vs 200)
- Part 2: Customer REST API (GET, GET /id, POST, PUT, 400, 404, 409, IDOR 403)
- Part 3: Lead REST API (GET, GET /id, POST, PUT, State Transitions, 400, 404, IDOR 403)
- Part 4: Opportunity REST API (GET, GET /id, POST, PUT, Stage Engine, Decimal, 400, 404, IDOR 403)
- Part 5: Security, DTO Hygiene, Audit Integration & Parameterized SQL
"""

import random
import uuid
from decimal import Decimal
import json
import pytest

from repositories import customer_repository, lead_repository, opportunity_repository, audit_repository
from services import audit_service


def login(client, identifier, password):
    """Helper to authenticate test user and store session cookie."""
    return client.post("/login", data={
        "identifier": identifier,
        "password": password
    }, follow_redirects=False)


def get_unique_suffix():
    """Generate a unique short string for email test isolation."""
    return uuid.uuid4().hex[:6]


def get_unique_phone():
    """Generate a unique 10-digit phone number with +91- prefix."""
    return f"+91-9{random.randint(100000000, 999999999)}"


# =============================================================================
# PART 1: API AUTHENTICATION & ACCESS CONTROL
# =============================================================================

def test_01_anonymous_get_customers_returns_401_json(client):
    """Anonymous GET to /api/customers returns HTTP 401 JSON without redirect."""
    resp = client.get("/api/customers")
    assert resp.status_code == 401
    assert resp.is_json
    data = resp.get_json()
    assert data["error"] == "Unauthorized"
    assert "Authentication required" in data["message"]


def test_02_anonymous_post_customers_returns_401_json(client):
    """Anonymous POST to /api/customers returns HTTP 401 JSON."""
    resp = client.post("/api/customers", json={"customer_name": "Test Anon"})
    assert resp.status_code == 401
    assert resp.is_json
    data = resp.get_json()
    assert data["error"] == "Unauthorized"


def test_03_anonymous_get_leads_returns_401_json(client):
    """Anonymous GET to /api/leads returns HTTP 401 JSON."""
    resp = client.get("/api/leads")
    assert resp.status_code == 401
    assert resp.is_json
    data = resp.get_json()
    assert data["error"] == "Unauthorized"


def test_04_anonymous_get_opportunities_returns_401_json(client):
    """Anonymous GET to /api/opportunities returns HTTP 401 JSON."""
    resp = client.get("/api/opportunities")
    assert resp.status_code == 401
    assert resp.is_json
    data = resp.get_json()
    assert data["error"] == "Unauthorized"


def test_05_authenticated_admin_can_access_api(client):
    """Admin user can access /api/customers and view organization-wide records."""
    login(client, "admin", "Admin@123")
    resp = client.get("/api/customers")
    assert resp.status_code == 200
    assert resp.is_json
    data = resp.get_json()
    assert "data" in data
    assert "pagination" in data
    assert len(data["data"]) > 0


def test_06_authenticated_manager_can_access_api(client):
    """Manager user can access /api/leads successfully."""
    login(client, "manager", "Manager@123")
    resp = client.get("/api/leads")
    assert resp.status_code == 200
    assert resp.is_json
    data = resp.get_json()
    assert "data" in data
    assert len(data["data"]) > 0


def test_07_authenticated_sales_exec_can_access_api(client):
    """Sales Executive can access /api/opportunities scoped to their records."""
    login(client, "sales1", "Sales@123")
    resp = client.get("/api/opportunities")
    assert resp.status_code == 200
    assert resp.is_json
    data = resp.get_json()
    assert "data" in data
    # All records for sales1 must belong to user 3
    for opp in data["data"]:
        assert opp["assigned_to"] == 3


def test_08_api_content_type_is_always_application_json(client):
    """All API responses carry Content-Type: application/json."""
    login(client, "admin", "Admin@123")
    for path in ("/api/customers", "/api/leads", "/api/opportunities"):
        resp = client.get(path)
        assert resp.headers["Content-Type"].startswith("application/json")


# =============================================================================
# PART 2: CUSTOMER REST API
# =============================================================================

def test_09_get_customers_list_returns_200_and_dtos(client):
    """GET /api/customers returns 200 with serialized Customer DTOs and pagination."""
    login(client, "admin", "Admin@123")
    resp = client.get("/api/customers?page=1&per_page=5")
    assert resp.status_code == 200
    res = resp.get_json()
    assert "data" in res
    assert "pagination" in res
    assert res["pagination"]["page"] == 1
    assert res["pagination"]["per_page"] == 5
    cust = res["data"][0]
    # DTO verification
    assert "customer_id" in cust
    assert "customer_code" in cust
    assert "customer_name" in cust
    assert "email" in cust
    assert "phone" in cust
    assert "status" in cust


def test_10_get_customer_by_id_returns_200_and_dto(client):
    """GET /api/customers/<id> returns 200 and single customer DTO."""
    login(client, "admin", "Admin@123")
    resp = client.get("/api/customers/1")
    assert resp.status_code == 200
    res = resp.get_json()
    assert "data" in res
    assert res["data"]["customer_id"] == 1
    assert res["data"]["customer_code"] == "CUST-001"


def test_11_get_customer_not_found_returns_404_json(client):
    """GET /api/customers/999999 returns 404 JSON."""
    login(client, "admin", "Admin@123")
    resp = client.get("/api/customers/999999")
    assert resp.status_code == 404
    assert resp.is_json
    res = resp.get_json()
    assert res["error"] == "Not Found"


def test_12_get_customer_invalid_id_returns_404_json(client):
    """GET /api/customers/not-an-int returns 404 JSON instead of 500 error."""
    login(client, "admin", "Admin@123")
    resp = client.get("/api/customers/invalid_text")
    assert resp.status_code == 404
    assert resp.is_json
    res = resp.get_json()
    assert res["error"] == "Not Found"


def test_13_sales_exec_cannot_view_unauthorized_customer_returns_403(client):
    """Sales Executive querying another rep's customer receives HTTP 403 Forbidden."""
    # Customer 3 belongs to sales2 (user 4)
    login(client, "sales1", "Sales@123")
    resp = client.get("/api/customers/3")
    assert resp.status_code == 403
    assert resp.is_json
    res = resp.get_json()
    assert res["error"] == "Forbidden"


def test_14_post_valid_customer_by_admin_returns_201(client):
    """Admin POST /api/customers with valid data creates customer and returns 201."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    phone = get_unique_phone()
    payload = {
        "customer_name": f"API Corp {suffix}",
        "email": f"contact_{suffix}@apicorp.example",
        "phone": phone,
        "company_name": "API Corp Global",
        "address": "404 Silicon Way",
        "city": "Bengaluru",
        "state": "Karnataka",
        "status": "Active",
        "assigned_to": 3
    }
    resp = client.post("/api/customers", json=payload)
    assert resp.status_code == 201
    assert resp.is_json
    res = resp.get_json()
    assert "data" in res
    assert res["data"]["customer_name"] == f"API Corp {suffix}"
    assert res["data"]["assigned_to"] == 3
    assert res["data"]["customer_code"].startswith("CUST-")


def test_15_post_customer_sales_exec_auto_self_assigned(client):
    """Sales Executive POST /api/customers automatically self-assigns ignoring client value."""
    login(client, "sales1", "Sales@123")
    suffix = get_unique_suffix()
    phone = get_unique_phone()
    payload = {
        "customer_name": f"Sales1 Self {suffix}",
        "email": f"self_{suffix}@sales1client.example",
        "phone": phone,
        "company_name": "Self Client",
        "assigned_to": 4  # Attempt to assign to user 4
    }
    resp = client.post("/api/customers", json=payload)
    assert resp.status_code == 201
    res = resp.get_json()
    # Server-side rule must override submitted assigned_to with authenticated user_id 3
    assert res["data"]["assigned_to"] == 3


def test_16_post_customer_missing_name_returns_400(client):
    """POST /api/customers missing customer_name returns 400 Bad Request."""
    login(client, "admin", "Admin@123")
    payload = {
        "email": "valid@email.example",
        "phone": "+91-9876543210"
    }
    resp = client.post("/api/customers", json=payload)
    assert resp.status_code == 400
    res = resp.get_json()
    assert res["error"] == "Validation failed"
    assert "customer_name" in res["details"]


def test_17_post_customer_invalid_email_returns_400(client):
    """POST /api/customers with malformed email returns 400 Bad Request."""
    login(client, "admin", "Admin@123")
    payload = {
        "customer_name": "Bad Email Corp",
        "email": "not-an-email",
        "phone": "+91-9876543210"
    }
    resp = client.post("/api/customers", json=payload)
    assert resp.status_code == 400
    res = resp.get_json()
    assert "email" in res["details"]


def test_18_post_customer_invalid_phone_returns_400(client):
    """POST /api/customers with short phone returns 400 Bad Request."""
    login(client, "admin", "Admin@123")
    payload = {
        "customer_name": "Bad Phone Corp",
        "email": "phone@example.com",
        "phone": "123"  # too short
    }
    resp = client.post("/api/customers", json=payload)
    assert resp.status_code == 400
    res = resp.get_json()
    assert "phone" in res["details"]


def test_19_post_customer_duplicate_email_returns_409(client):
    """POST /api/customers with existing email returns HTTP 409 Conflict."""
    login(client, "admin", "Admin@123")
    payload = {
        "customer_name": "Duplicate Email Corp",
        "email": "contact@apexsolutions.example",  # Seed customer 1 email
        "phone": "+91-9988776655"
    }
    resp = client.post("/api/customers", json=payload)
    assert resp.status_code == 409
    res = resp.get_json()
    assert res["error"] == "Conflict"
    assert "email" in res["details"]


def test_20_post_customer_duplicate_phone_returns_409(client):
    """POST /api/customers with existing phone returns HTTP 409 Conflict."""
    login(client, "admin", "Admin@123")
    payload = {
        "customer_name": "Duplicate Phone Corp",
        "email": "uniquephone@example.com",
        "phone": "+91-9876543210"  # Seed customer 1 phone
    }
    resp = client.post("/api/customers", json=payload)
    assert resp.status_code == 409
    res = resp.get_json()
    assert res["error"] == "Conflict"
    assert "phone" in res["details"]


def test_21_put_customer_valid_update_returns_200(client):
    """PUT /api/customers/<id> updates customer and returns 200."""
    login(client, "admin", "Admin@123")
    payload = {
        "customer_name": "Apex Global Solutions Updated",
        "email": "contact@apexsolutions.example",
        "phone": "+91-9876543210",
        "company_name": "Apex Worldwide",
        "city": "Bengaluru",
        "status": "Active"
    }
    resp = client.put("/api/customers/1", json=payload)
    assert resp.status_code == 200
    res = resp.get_json()
    assert res["data"]["customer_name"] == "Apex Global Solutions Updated"
    assert res["data"]["company_name"] == "Apex Worldwide"


def test_22_put_customer_sales_exec_cannot_reassign_or_change_status(client):
    """Sales Executive cannot reassign customer ownership or modify status via PUT."""
    login(client, "sales1", "Sales@123")
    payload = {
        "customer_name": "Apex Global Solutions",
        "email": "contact@apexsolutions.example",
        "phone": "+91-9876543210",
        "assigned_to": 4,          # Attempt reassign to sales2
        "status": "Inactive"       # Attempt soft deactivation
    }
    resp = client.put("/api/customers/1", json=payload)
    assert resp.status_code == 200
    res = resp.get_json()
    # Preserves ownership and status for Sales Exec
    assert res["data"]["assigned_to"] == 3
    assert res["data"]["status"] == "Active"


def test_23_put_customer_sales_exec_cannot_update_other_rep_returns_403(client):
    """Sales Executive attempting to PUT another rep's customer receives 403 Forbidden."""
    # Customer 3 belongs to sales2 (user 4)
    login(client, "sales1", "Sales@123")
    payload = {
        "customer_name": "Hacked Horizon",
        "email": "ops@horizonlogistics.example",
        "phone": "+91-9876543212"
    }
    resp = client.put("/api/customers/3", json=payload)
    assert resp.status_code == 403
    res = resp.get_json()
    assert res["error"] == "Forbidden"


def test_24_put_customer_not_found_returns_404(client):
    """PUT /api/customers/999999 returns 404 Not Found."""
    login(client, "admin", "Admin@123")
    resp = client.put("/api/customers/999999", json={"customer_name": "Ghost", "email": "g@g.com", "phone": "+91-9000000000"})
    assert resp.status_code == 404
    res = resp.get_json()
    assert res["error"] == "Not Found"


# =============================================================================
# PART 3: LEAD REST API
# =============================================================================

def test_25_get_leads_list_returns_200_and_dtos(client):
    """GET /api/leads returns 200 with lead DTO list and pagination."""
    login(client, "admin", "Admin@123")
    resp = client.get("/api/leads")
    assert resp.status_code == 200
    res = resp.get_json()
    assert "data" in res
    assert "pagination" in res
    lead = res["data"][0]
    assert "lead_id" in lead
    assert "lead_code" in lead
    assert "lead_name" in lead
    assert "status" in lead


def test_26_get_lead_by_id_returns_200_and_dto(client):
    """GET /api/leads/<id> returns 200 and single lead DTO."""
    login(client, "admin", "Admin@123")
    resp = client.get("/api/leads/1")
    assert resp.status_code == 200
    res = resp.get_json()
    assert res["data"]["lead_id"] == 1
    assert res["data"]["lead_code"] == "LEAD-001"


def test_27_get_lead_not_found_returns_404_json(client):
    """GET /api/leads/999999 returns 404 Not Found JSON."""
    login(client, "admin", "Admin@123")
    resp = client.get("/api/leads/999999")
    assert resp.status_code == 404
    res = resp.get_json()
    assert res["error"] == "Not Found"


def test_28_sales_exec_cannot_view_other_rep_lead_returns_403(client):
    """Sales Executive querying another rep's lead receives 403 Forbidden."""
    # Lead 3 belongs to sales2 (user 4)
    login(client, "sales1", "Sales@123")
    resp = client.get("/api/leads/3")
    assert resp.status_code == 403
    res = resp.get_json()
    assert res["error"] == "Forbidden"


def test_29_post_valid_lead_returns_201(client):
    """POST /api/leads with valid data creates lead and returns 201."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    phone = get_unique_phone()
    payload = {
        "lead_name": f"API Prospect {suffix}",
        "email": f"prospect_{suffix}@api.example",
        "phone": phone,
        "company_name": "Prospect Systems",
        "source": "Website",
        "status": "New",
        "expected_value": 150000.00,
        "assigned_to": 3
    }
    resp = client.post("/api/leads", json=payload)
    assert resp.status_code == 201
    res = resp.get_json()
    assert res["data"]["lead_name"] == f"API Prospect {suffix}"
    assert res["data"]["assigned_to"] == 3
    assert res["data"]["lead_code"].startswith("LEAD-")


def test_30_post_lead_sales_exec_auto_self_assigned(client):
    """Sales Executive POST /api/leads automatically self-assigns."""
    login(client, "sales1", "Sales@123")
    suffix = get_unique_suffix()
    phone = get_unique_phone()
    payload = {
        "lead_name": f"Rep Lead {suffix}",
        "email": f"inbound_{suffix}@leadrep.example",
        "phone": phone,
        "assigned_to": 4  # Attempt to assign to user 4
    }
    resp = client.post("/api/leads", json=payload)
    assert resp.status_code == 201
    res = resp.get_json()
    assert res["data"]["assigned_to"] == 3


def test_31_post_lead_admin_must_assign_active_sales_exec(client):
    """Admin POST /api/leads without assigned_to returns 400 Bad Request."""
    login(client, "admin", "Admin@123")
    payload = {
        "lead_name": "Unassigned Lead",
        "email": "unassigned@lead.example"
    }
    resp = client.post("/api/leads", json=payload)
    assert resp.status_code == 400
    res = resp.get_json()
    assert "assigned_to" in res["details"]


def test_32_post_lead_invalid_status_returns_400(client):
    """POST /api/leads with invalid status returns 400 Bad Request."""
    login(client, "admin", "Admin@123")
    payload = {
        "lead_name": "Invalid Status Lead",
        "email": "status@lead.example",
        "status": "RandomNonExistentStatus",
        "assigned_to": 3
    }
    resp = client.post("/api/leads", json=payload)
    assert resp.status_code == 400
    res = resp.get_json()
    assert "status" in res["details"]


def test_33_post_lead_invalid_email_returns_400(client):
    """POST /api/leads with invalid email returns 400 Bad Request."""
    login(client, "admin", "Admin@123")
    payload = {
        "lead_name": "Bad Email Lead",
        "email": "bademailformat",
        "assigned_to": 3
    }
    resp = client.post("/api/leads", json=payload)
    assert resp.status_code == 400
    res = resp.get_json()
    assert "email" in res["details"]


def test_34_put_lead_valid_transition_returns_200(client):
    """PUT /api/leads/<id> with valid status transition (New -> Contacted) returns 200."""
    login(client, "admin", "Admin@123")
    # Lead 1 is 'New' in seed data
    payload = {
        "lead_name": "Rohan Verma",
        "email": "rohan@innovatetech.example",
        "status": "Contacted"
    }
    resp = client.put("/api/leads/1", json=payload)
    assert resp.status_code == 200
    res = resp.get_json()
    assert res["data"]["status"] == "Contacted"


def test_35_put_lead_invalid_status_transition_returns_400(client):
    """PUT /api/leads/<id> attempting invalid transition from terminal state returns 400."""
    login(client, "admin", "Admin@123")
    # Lead 6 is 'Lost' (terminal) in seed data
    payload = {
        "lead_name": "Kavita Reddy",
        "email": "kavita@outdated.example",
        "status": "Qualified"  # Terminal states cannot be reopened
    }
    resp = client.put("/api/leads/6", json=payload)
    assert resp.status_code == 400
    res = resp.get_json()
    assert "status" in res["details"]


def test_36_put_lead_sales_exec_cannot_update_other_rep_returns_403(client):
    """Sales Executive attempting to PUT another rep's lead receives 403 Forbidden."""
    # Lead 3 belongs to sales2 (user 4)
    login(client, "sales1", "Sales@123")
    payload = {
        "lead_name": "Hacked Lead",
        "email": "amit@cloudcore.example"
    }
    resp = client.put("/api/leads/3", json=payload)
    assert resp.status_code == 403
    res = resp.get_json()
    assert res["error"] == "Forbidden"


# =============================================================================
# PART 4: OPPORTUNITY REST API
# =============================================================================

def test_37_get_opportunities_list_returns_200_and_dtos(client):
    """GET /api/opportunities returns 200 with opportunity DTOs and pipeline summary."""
    login(client, "admin", "Admin@123")
    resp = client.get("/api/opportunities")
    assert resp.status_code == 200
    res = resp.get_json()
    assert "data" in res
    assert "pagination" in res
    assert "pipeline_summary" in res
    assert "active_pipeline_amount" in res["pipeline_summary"]
    opp = res["data"][0]
    assert "opportunity_id" in opp
    assert "opportunity_name" in opp
    assert "amount" in opp
    assert "stage" in opp
    assert "probability" in opp


def test_38_get_opportunity_by_id_returns_200_and_dto(client):
    """GET /api/opportunities/<id> returns 200 and single opportunity DTO."""
    login(client, "admin", "Admin@123")
    resp = client.get("/api/opportunities/1")
    assert resp.status_code == 200
    res = resp.get_json()
    assert res["data"]["opportunity_id"] == 1
    assert res["data"]["opportunity_name"] == "Apex Cloud Migration"


def test_39_get_opportunity_not_found_returns_404_json(client):
    """GET /api/opportunities/999999 returns 404 Not Found JSON."""
    login(client, "admin", "Admin@123")
    resp = client.get("/api/opportunities/999999")
    assert resp.status_code == 404
    res = resp.get_json()
    assert res["error"] == "Not Found"


def test_40_sales_exec_cannot_view_other_rep_opportunity_returns_403(client):
    """Sales Executive querying another rep's opportunity receives 403 Forbidden."""
    # Opportunity 4 belongs to sales2 (user 4)
    login(client, "sales1", "Sales@123")
    resp = client.get("/api/opportunities/4")
    assert resp.status_code == 403
    res = resp.get_json()
    assert res["error"] == "Forbidden"


def test_41_post_valid_opportunity_returns_201(client):
    """POST /api/opportunities creates deal and returns 201."""
    login(client, "admin", "Admin@123")
    payload = {
        "opportunity_name": "API Enterprise Migration",
        "customer_id": 1,
        "amount": "250000.00",
        "stage": "Proposal",
        "probability": 60,
        "expected_close_date": "2026-12-15",
        "assigned_to": 3
    }
    resp = client.post("/api/opportunities", json=payload)
    assert resp.status_code == 201
    res = resp.get_json()
    assert res["data"]["opportunity_name"] == "API Enterprise Migration"
    assert res["data"]["amount"] == "250000.00"
    assert res["data"]["assigned_to"] == 3


def test_42_post_opportunity_sales_exec_auto_self_assigned(client):
    """Sales Executive POST /api/opportunities self-assigns automatically."""
    login(client, "sales1", "Sales@123")
    payload = {
        "opportunity_name": "Sales Rep Self Deal",
        "customer_id": 1,
        "amount": "120000.00",
        "stage": "Qualification",
        "probability": 30,
        "expected_close_date": "2026-11-20",
        "assigned_to": 4  # attempt override
    }
    resp = client.post("/api/opportunities", json=payload)
    assert resp.status_code == 201
    res = resp.get_json()
    assert res["data"]["assigned_to"] == 3


def test_43_post_opportunity_zero_or_negative_amount_rejected_returns_400(client):
    """POST /api/opportunities with zero or negative amount returns 400 Bad Request."""
    login(client, "admin", "Admin@123")
    payload = {
        "opportunity_name": "Zero Deal",
        "customer_id": 1,
        "amount": "0.00",
        "probability": 50,
        "expected_close_date": "2026-12-01",
        "assigned_to": 3
    }
    resp = client.post("/api/opportunities", json=payload)
    assert resp.status_code == 400
    res = resp.get_json()
    assert "amount" in res["details"]


def test_44_post_opportunity_invalid_probability_rejected_returns_400(client):
    """POST /api/opportunities with probability > 100 returns 400 Bad Request."""
    login(client, "admin", "Admin@123")
    payload = {
        "opportunity_name": "Over 100 Prob",
        "customer_id": 1,
        "amount": "50000.00",
        "probability": 150,  # Invalid
        "expected_close_date": "2026-12-01",
        "assigned_to": 3
    }
    resp = client.post("/api/opportunities", json=payload)
    assert resp.status_code == 400
    res = resp.get_json()
    assert "probability" in res["details"]


def test_45_post_opportunity_past_expected_close_date_rejected_returns_400(client):
    """POST /api/opportunities with past expected close date returns 400 Bad Request."""
    login(client, "admin", "Admin@123")
    payload = {
        "opportunity_name": "Past Date Deal",
        "customer_id": 1,
        "amount": "50000.00",
        "probability": 50,
        "expected_close_date": "2020-01-01",  # In the past
        "assigned_to": 3
    }
    resp = client.post("/api/opportunities", json=payload)
    assert resp.status_code == 400
    res = resp.get_json()
    assert "expected_close_date" in res["details"]


def test_46_post_opportunity_inactive_customer_rejected_returns_400(client):
    """POST /api/opportunities against inactive customer returns 400 Bad Request."""
    login(client, "admin", "Admin@123")
    # Customer 4 is Inactive in seed data
    payload = {
        "opportunity_name": "Inactive Cust Deal",
        "customer_id": 4,
        "amount": "50000.00",
        "probability": 50,
        "expected_close_date": "2026-12-01",
        "assigned_to": 4
    }
    resp = client.post("/api/opportunities", json=payload)
    assert resp.status_code == 400
    res = resp.get_json()
    assert "customer_id" in res["details"]


def test_47_post_opportunity_unauthorized_customer_rejected_returns_403(client):
    """Sales Executive creating opportunity for another rep's customer returns 403 Forbidden."""
    # Customer 3 belongs to sales2 (user 4)
    login(client, "sales1", "Sales@123")
    payload = {
        "opportunity_name": "IDOR Deal",
        "customer_id": 3,
        "amount": "50000.00",
        "probability": 50,
        "expected_close_date": "2026-12-01"
    }
    resp = client.post("/api/opportunities", json=payload)
    assert resp.status_code == 403
    res = resp.get_json()
    assert res["error"] == "Forbidden"


def test_48_post_opportunity_admin_must_select_active_sales_exec(client):
    """Admin creating opportunity without assigned_to returns 400 Bad Request."""
    login(client, "admin", "Admin@123")
    payload = {
        "opportunity_name": "Missing Assignment Deal",
        "customer_id": 1,
        "amount": "50000.00",
        "probability": 50,
        "expected_close_date": "2026-12-01"
    }
    resp = client.post("/api/opportunities", json=payload)
    assert resp.status_code == 400
    res = resp.get_json()
    assert "assigned_to" in res["details"]


def test_49_put_opportunity_valid_stage_transition_returns_200(client):
    """PUT /api/opportunities/<id> updates opportunity stage and returns 200."""
    login(client, "admin", "Admin@123")
    # Opportunity 2 is in 'Proposal' stage
    payload = {
        "opportunity_name": "Apex Security Suite",
        "customer_id": 1,
        "amount": "85000.00",
        "stage": "Negotiation",
        "probability": 70,
        "expected_close_date": "2026-12-01",
        "assigned_to": 3
    }
    resp = client.put("/api/opportunities/2", json=payload)
    assert resp.status_code == 200
    res = resp.get_json()
    assert res["data"]["stage"] == "Negotiation"
    assert res["data"]["probability"] == 70


def test_50_put_opportunity_terminal_won_lost_cannot_be_modified_returns_400(client):
    """PUT /api/opportunities/<id> on terminal Won/Lost deal returns 400 Bad Request."""
    login(client, "admin", "Admin@123")
    # Opportunity 4 is Won (terminal) in seed data
    payload = {
        "opportunity_name": "Horizon Fleet ERP Reopened",
        "customer_id": 3,
        "amount": "500000.00",
        "stage": "Negotiation",
        "probability": 70,
        "expected_close_date": "2026-12-01",
        "assigned_to": 4
    }
    resp = client.put("/api/opportunities/4", json=payload)
    assert resp.status_code == 400
    res = resp.get_json()
    assert "terminal" in str(res["details"]).lower() or "won and lost" in str(res["details"]).lower()


def test_51_put_opportunity_sales_exec_cannot_update_other_rep_returns_403(client):
    """Sales Executive attempting to PUT another rep's opportunity receives 403 Forbidden."""
    # Opportunity 4 belongs to sales2 (user 4)
    login(client, "sales1", "Sales@123")
    payload = {
        "opportunity_name": "Hacked Opp",
        "customer_id": 3,
        "amount": "500000.00",
        "stage": "Proposal",
        "probability": 50,
        "expected_close_date": "2026-12-01"
    }
    resp = client.put("/api/opportunities/4", json=payload)
    assert resp.status_code == 403
    res = resp.get_json()
    assert res["error"] == "Forbidden"


# =============================================================================
# PART 5: SECURITY, DTO HYGIENE & SYSTEM INTEGRITY
# =============================================================================

def test_52_api_responses_never_expose_password_hashes_or_tokens(client):
    """API responses must never expose password hashes, tokens, or session secrets."""
    login(client, "admin", "Admin@123")
    for path in ("/api/customers", "/api/leads", "/api/opportunities"):
        resp = client.get(path)
        data_text = resp.get_data(as_text=True)
        assert "password_hash" not in data_text
        assert "scrypt:" not in data_text
        assert "SECRET_KEY" not in data_text
        assert "session" not in data_text


def test_53_api_sql_injection_in_search_and_filters_is_safe(client):
    """SQL injection strings in API search parameters are safely parameterized."""
    login(client, "admin", "Admin@123")
    injection_strings = [
        "1' OR '1'='1",
        "'; DROP TABLE customers;--",
        "' UNION SELECT NULL, NULL, NULL--"
    ]
    for inj in injection_strings:
        resp = client.get(f"/api/customers?search={inj}")
        assert resp.status_code == 200
        assert resp.is_json
        data_text = resp.get_data(as_text=True)
        assert "syntax error" not in data_text.lower()
        assert "psycopg2" not in data_text


def test_54_api_malformed_json_returns_400_json(client):
    """Sending malformed JSON returns HTTP 400 JSON without stack trace."""
    login(client, "admin", "Admin@123")
    resp = client.post(
        "/api/customers",
        data="this is not valid json",
        content_type="application/json"
    )
    assert resp.status_code == 400
    assert resp.is_json
    res = resp.get_json()
    assert "error" in res


def test_55_api_mutations_create_atomic_audit_logs(client):
    """API mutations write audit logs atomically in the same PostgreSQL transaction."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    phone = get_unique_phone()
    payload = {
        "customer_name": f"Audit Customer {suffix}",
        "email": f"audit_{suffix}@example.com",
        "phone": phone,
        "assigned_to": 3
    }
    resp = client.post("/api/customers", json=payload)
    assert resp.status_code == 201
    new_id = resp.get_json()["data"]["customer_id"]

    logs = audit_repository.find_audit_logs(
        action=audit_service.ACTION_CREATE,
        entity_name=audit_service.ENTITY_CUSTOMER
    )
    matching = [log for log in logs if str(log.get("record_id")) == str(new_id)]
    assert len(matching) == 1
    assert matching[0]["user_id"] == 1
    assert matching[0]["result"] == "Success"


def test_56_opportunity_amount_and_weighted_pipeline_serialized_as_exact_decimal_string(client):
    """Opportunities serialize amount as exact two-decimal string format without float inaccuracy."""
    login(client, "admin", "Admin@123")
    resp = client.get("/api/opportunities/1")
    assert resp.status_code == 200
    res = resp.get_json()
    # Amount must be exact formatted string like '300000.00'
    amount_str = res["data"]["amount"]
    assert isinstance(amount_str, str)
    assert Decimal(amount_str) == Decimal("300000.00")
