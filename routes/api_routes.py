"""
REST API Routes for AcxiomCRM (Phase 11).

Exposes secure, role-scoped RESTful endpoints for:
1. Customers (/api/customers)
2. Leads (/api/leads)
3. Opportunities (/api/opportunities)

Adheres strictly to MASTER_BLUEPRINT.md Section 93-99 and SPECIFICATION_NOTES.md:
- Authentication: Session-cookie authenticated via get_current_user().
- Status Codes: Correct semantics (200 OK, 201 Created, 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 409 Conflict).
- Content-Type: application/json for both successful and error responses.
- Service Layer Reuse: Directly delegates to existing domain services without duplicating SQL or business rules.
- Ownership & Scope: Row-level security strictly enforced in PostgreSQL (WHERE assigned_to = %s).
- DTO Isolation: Raw database records are serialized through explicit schemas; no sensitive fields exposed.
"""

from functools import wraps
from flask import Blueprint, request, jsonify
from security.authentication import get_current_user
from services import customer_service, lead_service, opportunity_service
from schemas import api_schema

api_bp = Blueprint("api", __name__, url_prefix="/api")


# =============================================================================
# API AUTHENTICATION DECORATOR
# =============================================================================

def api_login_required(f):
    """
    Decorator for API endpoints requiring an authenticated user.
    Returns HTTP 401 JSON when unauthenticated without redirecting to HTML login.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        current_user = get_current_user()
        if not current_user:
            return jsonify({
                "error": "Unauthorized",
                "message": "Authentication required. Please authenticate with valid credentials."
            }), 401
        return f(*args, **kwargs)
    return decorated_function


# =============================================================================
# 1. CUSTOMER API ENDPOINTS
# =============================================================================

@api_bp.route("/customers", methods=["GET"])
@api_login_required
def get_customers():
    """
    GET /api/customers
    List customers scoped to the authenticated user's role and ownership.
    Query params: search, status, sort_by, sort_order, page, per_page.
    """
    current_user = get_current_user()
    search = request.args.get("search", "").strip() or None
    status = request.args.get("status", "").strip() or None
    sort_by = request.args.get("sort_by", "created_date")
    sort_order = request.args.get("sort_order", "DESC")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)

    customers, total_count, total_pages = customer_service.get_customers_list(
        current_user=current_user,
        search=search,
        status=status,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=per_page,
    )

    return jsonify({
        "data": [api_schema.serialize_customer(c) for c in customers],
        "pagination": {
            "total_count": total_count,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
        }
    }), 200


@api_bp.route("/customers/<int:customer_id>", methods=["GET"])
@api_login_required
def get_customer_by_id(customer_id):
    """
    GET /api/customers/<id>
    Retrieve a single customer by ID with IDOR protection.
    """
    current_user = get_current_user()
    customer, error_code = customer_service.get_customer_detail(customer_id, current_user)

    if error_code == 404:
        return jsonify({"error": "Not Found", "message": "Customer not found."}), 404
    if error_code == 403:
        return jsonify({"error": "Forbidden", "message": "You are not authorized to view this customer."}), 403

    return jsonify({"data": api_schema.serialize_customer(customer)}), 200


@api_bp.route("/customers", methods=["POST"])
@api_login_required
def create_customer_endpoint():
    """
    POST /api/customers
    Create a new customer record.
    Returns 201 Created on success, 400 on validation failure, 409 on duplicate conflict.
    """
    current_user = get_current_user()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Bad Request", "message": "Valid JSON body is required."}), 400

    cleaned, val_errors = api_schema.validate_customer_input(payload, is_edit=False)
    if val_errors:
        return jsonify({"error": "Validation failed", "details": val_errors}), 400

    success, customer, srv_errors = customer_service.create_customer(cleaned, current_user)
    if not success:
        # Check for duplicate email or phone conflict
        err_text = str(srv_errors).lower()
        if "already registered" in err_text:
            return jsonify({"error": "Conflict", "details": srv_errors}), 409
        return jsonify({"error": "Validation failed", "details": srv_errors}), 400

    return jsonify({
        "data": api_schema.serialize_customer(customer),
        "message": "Customer created successfully."
    }), 201


@api_bp.route("/customers/<int:customer_id>", methods=["PUT"])
@api_login_required
def update_customer_endpoint(customer_id):
    """
    PUT /api/customers/<id>
    Update an existing customer with IDOR verification and audit trail.
    """
    current_user = get_current_user()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Bad Request", "message": "Valid JSON body is required."}), 400

    cleaned, val_errors = api_schema.validate_customer_input(payload, is_edit=True)
    if val_errors:
        return jsonify({"error": "Validation failed", "details": val_errors}), 400

    success, customer, srv_errors, status_code = customer_service.update_customer(
        customer_id=customer_id,
        form_data=cleaned,
        current_user=current_user
    )

    if status_code == 404:
        return jsonify({"error": "Not Found", "message": "Customer not found."}), 404
    if status_code == 403:
        return jsonify({"error": "Forbidden", "message": "You are not authorized to update this customer."}), 403

    if not success:
        err_text = str(srv_errors).lower()
        if "already registered" in err_text:
            return jsonify({"error": "Conflict", "details": srv_errors}), 409
        return jsonify({"error": "Validation failed", "details": srv_errors}), 400

    return jsonify({
        "data": api_schema.serialize_customer(customer),
        "message": "Customer updated successfully."
    }), 200


# =============================================================================
# 2. LEAD API ENDPOINTS
# =============================================================================

@api_bp.route("/leads", methods=["GET"])
@api_login_required
def get_leads():
    """
    GET /api/leads
    List leads scoped to the authenticated user's role and ownership.
    Query params: search, status, assigned_to, sort_by, sort_order, page, per_page.
    """
    current_user = get_current_user()
    search = request.args.get("search", "").strip() or None
    status = request.args.get("status", "").strip() or None
    assigned_to = request.args.get("assigned_to", type=int)
    sort_by = request.args.get("sort_by", "created_date")
    sort_order = request.args.get("sort_order", "DESC")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)

    leads, total_count, total_pages = lead_service.get_leads_list(
        current_user=current_user,
        search=search,
        status=status,
        assigned_to=assigned_to,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=per_page,
    )

    return jsonify({
        "data": [api_schema.serialize_lead(l) for l in leads],
        "pagination": {
            "total_count": total_count,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
        }
    }), 200


@api_bp.route("/leads/<int:lead_id>", methods=["GET"])
@api_login_required
def get_lead_by_id(lead_id):
    """
    GET /api/leads/<id>
    Retrieve a single lead with ownership authorization.
    """
    current_user = get_current_user()
    lead, status_code = lead_service.get_lead_detail(lead_id, current_user)

    if status_code == 404:
        return jsonify({"error": "Not Found", "message": "Lead not found."}), 404
    if status_code == 403:
        return jsonify({"error": "Forbidden", "message": "You are not authorized to view this lead."}), 403

    return jsonify({"data": api_schema.serialize_lead(lead)}), 200


@api_bp.route("/leads", methods=["POST"])
@api_login_required
def create_lead_endpoint():
    """
    POST /api/leads
    Create a new lead with validation and assignment rules.
    """
    current_user = get_current_user()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Bad Request", "message": "Valid JSON body is required."}), 400

    cleaned, val_errors = api_schema.validate_lead_input(payload, is_edit=False)
    if val_errors:
        return jsonify({"error": "Validation failed", "details": val_errors}), 400

    success, lead, srv_errors = lead_service.create_lead(
        form_data=cleaned,
        current_user=current_user,
        ip_address=request.remote_addr,
    )

    if not success:
        return jsonify({"error": "Validation failed", "details": srv_errors}), 400

    return jsonify({
        "data": api_schema.serialize_lead(lead),
        "message": "Lead created successfully."
    }), 201


@api_bp.route("/leads/<int:lead_id>", methods=["PUT"])
@api_login_required
def update_lead_endpoint(lead_id):
    """
    PUT /api/leads/<id>
    Update an existing lead with status transition matrix enforcement.
    """
    current_user = get_current_user()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Bad Request", "message": "Valid JSON body is required."}), 400

    cleaned, val_errors = api_schema.validate_lead_input(payload, is_edit=True)
    if val_errors:
        return jsonify({"error": "Validation failed", "details": val_errors}), 400

    success, lead, srv_errors, status_code = lead_service.update_lead(
        lead_id=lead_id,
        form_data=cleaned,
        current_user=current_user,
        ip_address=request.remote_addr,
    )

    if status_code == 404:
        return jsonify({"error": "Not Found", "message": "Lead not found."}), 404
    if status_code == 403:
        return jsonify({"error": "Forbidden", "message": "You are not authorized to update this lead."}), 403

    if not success:
        return jsonify({"error": "Validation failed", "details": srv_errors}), 400

    return jsonify({
        "data": api_schema.serialize_lead(lead),
        "message": "Lead updated successfully."
    }), 200


# =============================================================================
# 3. OPPORTUNITY API ENDPOINTS
# =============================================================================

@api_bp.route("/opportunities", methods=["GET"])
@api_login_required
def get_opportunities():
    """
    GET /api/opportunities
    List opportunities scoped to the authenticated user's role.
    Includes pipeline summary aggregates computed with exact Decimal arithmetic.
    """
    current_user = get_current_user()
    search = request.args.get("search", "").strip() or None
    customer_id = request.args.get("customer_id", type=int)
    stage = request.args.get("stage", "").strip() or None
    status = request.args.get("status", "").strip() or None
    assigned_to = request.args.get("assigned_to", type=int)
    sort_by = request.args.get("sort_by", "created_date")
    sort_order = request.args.get("sort_order", "DESC")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)

    opportunities, total_count, total_pages, pipeline_summary = opportunity_service.get_opportunities_list(
        current_user=current_user,
        search=search,
        customer_id=customer_id,
        stage=stage,
        status=status,
        assigned_to=assigned_to,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=per_page,
    )

    return jsonify({
        "data": [api_schema.serialize_opportunity(o) for o in opportunities],
        "pagination": {
            "total_count": total_count,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
        },
        "pipeline_summary": {
            "active_pipeline_amount": api_schema.format_decimal(pipeline_summary.get("active_pipeline_amount")),
            "weighted_pipeline_amount": api_schema.format_decimal(pipeline_summary.get("weighted_pipeline_amount")),
            "open_deals_count": pipeline_summary.get("open_deals_count", 0),
        }
    }), 200


@api_bp.route("/opportunities/<int:opportunity_id>", methods=["GET"])
@api_login_required
def get_opportunity_by_id(opportunity_id):
    """
    GET /api/opportunities/<id>
    Retrieve a single opportunity with IDOR verification and exact Decimal weighted value.
    """
    current_user = get_current_user()
    opp, status_code = opportunity_service.get_opportunity_detail(opportunity_id, current_user)

    if status_code == 404:
        return jsonify({"error": "Not Found", "message": "Opportunity not found."}), 404
    if status_code == 403:
        return jsonify({"error": "Forbidden", "message": "You are not authorized to view this opportunity."}), 403

    return jsonify({"data": api_schema.serialize_opportunity(opp)}), 200


@api_bp.route("/opportunities", methods=["POST"])
@api_login_required
def create_opportunity_endpoint():
    """
    POST /api/opportunities
    Create a new opportunity.
    Validates Active Customer requirement, positive amount, probability 0-100, and future expected close date.
    """
    current_user = get_current_user()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Bad Request", "message": "Valid JSON body is required."}), 400

    cleaned, val_errors = api_schema.validate_opportunity_input(payload, is_edit=False)
    if val_errors:
        return jsonify({"error": "Validation failed", "details": val_errors}), 400

    success, opp, srv_errors, status_code = opportunity_service.create_opportunity(
        form_data=cleaned,
        current_user=current_user,
        ip_address=request.remote_addr,
    )

    if status_code == 404:
        return jsonify({"error": "Not Found", "details": srv_errors}), 404
    if status_code == 403:
        return jsonify({"error": "Forbidden", "details": srv_errors}), 403
    if not success or status_code == 400:
        return jsonify({"error": "Validation failed", "details": srv_errors}), 400

    return jsonify({
        "data": api_schema.serialize_opportunity(opp),
        "message": "Opportunity created successfully."
    }), 201


@api_bp.route("/opportunities/<int:opportunity_id>", methods=["PUT"])
@api_login_required
def update_opportunity_endpoint(opportunity_id):
    """
    PUT /api/opportunities/<id>
    Update an existing opportunity with terminal stage protection and audit trail.
    """
    current_user = get_current_user()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Bad Request", "message": "Valid JSON body is required."}), 400

    cleaned, val_errors = api_schema.validate_opportunity_input(payload, is_edit=True)
    if val_errors:
        return jsonify({"error": "Validation failed", "details": val_errors}), 400

    success, opp, srv_errors, status_code = opportunity_service.update_opportunity(
        opportunity_id=opportunity_id,
        form_data=cleaned,
        current_user=current_user,
        ip_address=request.remote_addr,
    )

    if status_code == 404:
        return jsonify({"error": "Not Found", "message": "Opportunity not found."}), 404
    if status_code == 403:
        return jsonify({"error": "Forbidden", "message": "You are not authorized to update this opportunity."}), 403
    if not success or status_code == 400:
        return jsonify({"error": "Validation failed", "details": srv_errors}), 400

    return jsonify({
        "data": api_schema.serialize_opportunity(opp),
        "message": "Opportunity updated successfully."
    }), 200
