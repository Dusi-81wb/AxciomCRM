"""
Opportunity Repository for AcxiomCRM (Phase 7).

Encapsulates all SQL data access for the 'opportunities' entity using raw psycopg2
with strict parameterization and architectural isolation:
- All SQL queries use %s parameter placeholders to prevent SQL injection.
- Scope-aware ownership filtering is enforced directly in SQL WHERE clauses.
- Accepts optional 'conn' parameter to participate in atomic service transactions.
- Never commits when 'conn' is provided by an external caller (service boundary).
"""

from decimal import Decimal
from database import get_db_connection

# Whitelist for dynamic sorting columns to prevent SQL injection
ALLOWED_SORT_COLUMNS = {
    "opportunity_name": "o.opportunity_name",
    "customer_name": "c.customer_name",
    "amount": "o.amount",
    "stage": "o.stage",
    "probability": "o.probability",
    "expected_close_date": "o.expected_close_date",
    "status": "o.status",
    "created_date": "o.created_date",
}

ALLOWED_SORT_ORDERS = {
    "asc": "ASC",
    "desc": "DESC",
}


def _row_to_dict(cursor, row):
    """Convert database row tuple to dictionary using cursor descriptions."""
    if row is None:
        return None
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


def find_by_id(opportunity_id, conn=None, for_update=False):
    """
    Retrieve opportunity by primary key, joined with customer, lead, and assigned user.

    :param opportunity_id: Integer primary key.
    :param conn: Optional active database connection.
    :param for_update: If True, locks the row FOR UPDATE OF o.
    :return: Opportunity dictionary or None.
    """
    connection = conn or get_db_connection()
    lock_clause = "FOR UPDATE OF o" if for_update else ""
    with connection.cursor() as cur:
        cur.execute(f"""
            SELECT o.opportunity_id, o.opportunity_name, o.customer_id, o.lead_id,
                   o.amount, o.stage, o.probability, o.expected_close_date,
                   o.status, o.created_date, o.modified_date, o.closed_date,
                   o.assigned_to,
                   c.customer_code, c.customer_name, c.company_name, c.status AS customer_status,
                   l.lead_code, l.lead_name,
                   u.username AS assigned_to_name,
                   r.role_name AS assigned_to_role
            FROM opportunities o
            LEFT JOIN customers c ON o.customer_id = c.customer_id
            LEFT JOIN leads l ON o.lead_id = l.lead_id
            LEFT JOIN users u ON o.assigned_to = u.user_id
            LEFT JOIN roles r ON u.role_id = r.role_id
            WHERE o.opportunity_id = %s
            {lock_clause};
        """, (opportunity_id,))
        row = cur.fetchone()
        return _row_to_dict(cur, row)


def create_opportunity(
    opportunity_name,
    customer_id,
    amount,
    stage="Qualification",
    probability=0,
    expected_close_date=None,
    status="Open",
    assigned_to=None,
    lead_id=None,
    closed_date=None,
    conn=None
):
    """
    Insert a new Opportunity record into the database.

    :return: Inserted Opportunity dictionary.
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO opportunities (
                opportunity_name, customer_id, lead_id, amount,
                stage, probability, expected_close_date, status,
                assigned_to, closed_date
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING opportunity_id, opportunity_name, customer_id, lead_id,
                      amount, stage, probability, expected_close_date, status,
                      created_date, modified_date, closed_date, assigned_to;
        """, (
            opportunity_name,
            customer_id,
            lead_id,
            amount,
            stage,
            probability,
            expected_close_date,
            status,
            assigned_to,
            closed_date
        ))
        row = cur.fetchone()
        record = _row_to_dict(cur, row)

    if conn is None:
        connection.commit()

    return record


def update_opportunity(
    opportunity_id,
    opportunity_name,
    customer_id,
    amount,
    stage,
    probability,
    expected_close_date,
    status,
    assigned_to,
    lead_id=None,
    closed_date=None,
    conn=None
):
    """
    Update mutable opportunity details and stamp modified_date.
    Preserves immutable fields (opportunity_id, created_date).

    :return: Updated Opportunity dictionary.
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            UPDATE opportunities
            SET opportunity_name = %s,
                customer_id = %s,
                lead_id = %s,
                amount = %s,
                stage = %s,
                probability = %s,
                expected_close_date = %s,
                status = %s,
                assigned_to = %s,
                closed_date = %s,
                modified_date = CURRENT_TIMESTAMP
            WHERE opportunity_id = %s
            RETURNING opportunity_id, opportunity_name, customer_id, lead_id,
                      amount, stage, probability, expected_close_date, status,
                      created_date, modified_date, closed_date, assigned_to;
        """, (
            opportunity_name,
            customer_id,
            lead_id,
            amount,
            stage,
            probability,
            expected_close_date,
            status,
            assigned_to,
            closed_date,
            opportunity_id
        ))
        row = cur.fetchone()
        record = _row_to_dict(cur, row)

    if conn is None:
        connection.commit()

    return record


def update_stage_status(
    opportunity_id,
    stage,
    status,
    closed_date=None,
    conn=None
):
    """
    Perform a targeted update of stage, status, and closed_date with modified_date stamp.

    :return: Updated Opportunity dictionary.
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            UPDATE opportunities
            SET stage = %s,
                status = %s,
                closed_date = %s,
                modified_date = CURRENT_TIMESTAMP
            WHERE opportunity_id = %s
            RETURNING opportunity_id, opportunity_name, customer_id, lead_id,
                      amount, stage, probability, expected_close_date, status,
                      created_date, modified_date, closed_date, assigned_to;
        """, (stage, status, closed_date, opportunity_id))
        row = cur.fetchone()
        record = _row_to_dict(cur, row)

    if conn is None:
        connection.commit()

    return record


def find_opportunities(
    allowed_user_ids=None,
    search=None,
    customer_id=None,
    stage=None,
    status=None,
    assigned_to=None,
    sort_by="created_date",
    sort_order="DESC",
    limit=10,
    offset=0,
    conn=None
):
    """
    Search and filter opportunities incorporating SQL-level ownership scope.

    :param allowed_user_ids: List of authorized user IDs for scope, or None for unrestricted.
    :param search: Substring to match across Opportunity name, Customer name, or Company name.
    :param customer_id: Exact Customer ID filter.
    :param stage: Exact Stage filter.
    :param status: Exact Status filter.
    :param assigned_to: Exact assigned Sales Executive ID filter.
    :param sort_by: Column key for sorting (validated against whitelist).
    :param sort_order: Sort direction ('ASC' or 'DESC').
    :param limit: Page size.
    :param offset: Pagination offset.
    :param conn: Optional active database connection.
    :return: List of Opportunity dictionaries.
    """
    connection = conn or get_db_connection()
    conditions = ["1=1"]
    params = []

    # 1. SQL-level ownership scope
    if allowed_user_ids is not None:
        conditions.append("o.assigned_to = ANY(%s)")
        params.append(allowed_user_ids)

    # 2. Search filter across Opportunity name, Customer name, or Company name
    if search:
        search_pattern = f"%{search.strip().lower()}%"
        conditions.append("""(
            LOWER(o.opportunity_name) LIKE %s
            OR LOWER(c.customer_name) LIKE %s
            OR LOWER(COALESCE(c.company_name, '')) LIKE %s
        )""")
        params.extend([search_pattern, search_pattern, search_pattern])

    # 3. Customer ID filter
    if customer_id:
        conditions.append("o.customer_id = %s")
        params.append(int(customer_id))

    # 4. Stage filter
    if stage:
        conditions.append("o.stage = %s")
        params.append(stage.strip())

    # 5. Status filter
    if status:
        conditions.append("o.status = %s")
        params.append(status.strip())

    # 6. Assigned Sales Executive filter
    if assigned_to:
        conditions.append("o.assigned_to = %s")
        params.append(int(assigned_to))

    # 7. Whitelisted sorting
    col = ALLOWED_SORT_COLUMNS.get(sort_by, "o.created_date")
    order = ALLOWED_SORT_ORDERS.get(sort_order.lower(), "DESC")

    # 8. Pagination limits
    params.extend([limit, offset])

    query = f"""
        SELECT o.opportunity_id, o.opportunity_name, o.customer_id, o.lead_id,
               o.amount, o.stage, o.probability, o.expected_close_date,
               o.status, o.created_date, o.modified_date, o.closed_date,
               o.assigned_to,
               c.customer_code, c.customer_name, c.company_name,
               l.lead_code, l.lead_name,
               u.username AS assigned_to_name,
               r.role_name AS assigned_to_role
        FROM opportunities o
        LEFT JOIN customers c ON o.customer_id = c.customer_id
        LEFT JOIN leads l ON o.lead_id = l.lead_id
        LEFT JOIN users u ON o.assigned_to = u.user_id
        LEFT JOIN roles r ON u.role_id = r.role_id
        WHERE {' AND '.join(conditions)}
        ORDER BY {col} {order}
        LIMIT %s OFFSET %s;
    """

    with connection.cursor() as cur:
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        return [_row_to_dict(cur, row) for row in rows]


def count_opportunities(
    allowed_user_ids=None,
    search=None,
    customer_id=None,
    stage=None,
    status=None,
    assigned_to=None,
    conn=None
):
    """
    Count total matching opportunities for pagination under SQL ownership scope.
    """
    connection = conn or get_db_connection()
    conditions = ["1=1"]
    params = []

    if allowed_user_ids is not None:
        conditions.append("o.assigned_to = ANY(%s)")
        params.append(allowed_user_ids)

    if search:
        search_pattern = f"%{search.strip().lower()}%"
        conditions.append("""(
            LOWER(o.opportunity_name) LIKE %s
            OR LOWER(c.customer_name) LIKE %s
            OR LOWER(COALESCE(c.company_name, '')) LIKE %s
        )""")
        params.extend([search_pattern, search_pattern, search_pattern])

    if customer_id:
        conditions.append("o.customer_id = %s")
        params.append(int(customer_id))

    if stage:
        conditions.append("o.stage = %s")
        params.append(stage.strip())

    if status:
        conditions.append("o.status = %s")
        params.append(status.strip())

    if assigned_to:
        conditions.append("o.assigned_to = %s")
        params.append(int(assigned_to))

    query = f"""
        SELECT COUNT(*)
        FROM opportunities o
        LEFT JOIN customers c ON o.customer_id = c.customer_id
        WHERE {' AND '.join(conditions)};
    """

    with connection.cursor() as cur:
        cur.execute(query, tuple(params))
        return cur.fetchone()[0]


def calculate_pipeline_totals(allowed_user_ids=None, conn=None):
    """
    Calculate scope-aware pipeline totals using exact Decimal arithmetic in SQL:
    - Total Pipeline Value = SUM(amount) for Open opportunities only.
    - Weighted Pipeline Value = SUM(amount * probability / 100) for Open opportunities only.
    - Counts for Open, Won, Lost, and Total deals.
    Won and Lost deals are strictly excluded from active pipeline values.

    :param allowed_user_ids: List of authorized user IDs for scope, or None for unrestricted.
    :param conn: Optional database connection.
    :return: Dictionary with total_pipeline_value, weighted_pipeline_value, open_count, won_count, lost_count.
    """
    connection = conn or get_db_connection()
    conditions = ["1=1"]
    params = []

    if allowed_user_ids is not None:
        conditions.append("o.assigned_to = ANY(%s)")
        params.append(allowed_user_ids)

    query = f"""
        SELECT
            COALESCE(SUM(CASE WHEN o.status = 'Open' THEN o.amount ELSE 0.00 END), 0.00) AS total_pipeline_value,
            COALESCE(SUM(CASE WHEN o.status = 'Open' THEN ROUND((o.amount * o.probability / 100.0), 2) ELSE 0.00 END), 0.00) AS weighted_pipeline_value,
            COUNT(CASE WHEN o.status = 'Open' THEN 1 END) AS open_count,
            COUNT(CASE WHEN o.status = 'Won' THEN 1 END) AS won_count,
            COUNT(CASE WHEN o.status = 'Lost' THEN 1 END) AS lost_count,
            COUNT(*) AS total_count
        FROM opportunities o
        WHERE {' AND '.join(conditions)};
    """

    with connection.cursor() as cur:
        cur.execute(query, tuple(params))
        row = cur.fetchone()
        return _row_to_dict(cur, row)


def get_active_customers(conn=None):
    """
    Fetch all active customers (status = 'Active') for selection in Opportunity forms.
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            SELECT customer_id, customer_code, customer_name, company_name
            FROM customers
            WHERE status = 'Active'
            ORDER BY customer_name ASC;
        """)
        rows = cur.fetchall()
        return [_row_to_dict(cur, row) for row in rows]


def get_active_sales_executives(conn=None):
    """
    Fetch all active users with role 'Sales Executive' (role_id = 3).
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            SELECT u.user_id, u.username, u.email, r.role_name
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            WHERE u.is_active = TRUE AND u.role_id = 3
            ORDER BY u.username ASC;
        """)
        rows = cur.fetchall()
        return [_row_to_dict(cur, row) for row in rows]
