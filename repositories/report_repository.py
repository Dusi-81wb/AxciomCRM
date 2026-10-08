"""
Report Repository for AcxiomCRM (Phase 10).

Encapsulates all SQL queries for the 8 system reports:
1. Customer Report
2. Lead Report
3. Follow-Up Report
4. Opportunity Report
5. Pipeline Report
6. Sales / Conversion Report
7. User Activity Report
8. Audit Report

Adheres strictly to architectural requirements:
- Repositories DO NOT manage transactions or commit.
- All dynamic inputs are strictly parameterized (%s) to prevent SQL injection.
- Role-based ownership filtering enforced directly in SQL WHERE clauses.
- Order by columns strictly validated against static whitelists.
- Monetary values aggregated using PostgreSQL NUMERIC and retrieved as Python Decimal.
"""

from decimal import Decimal
from database import get_db_connection


def _rows_to_dicts(cursor, rows):
    """Convert database row tuples to list of dictionaries."""
    if not rows:
        return []
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, r)) for r in rows]


def _row_to_dict(cursor, row):
    """Convert database row tuple to dictionary."""
    if row is None:
        return None
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


# =============================================================================
# 1. CUSTOMER REPORT
# =============================================================================

CUSTOMER_SORT_COLUMNS = {
    "customer_code": "c.customer_code",
    "customer_name": "c.customer_name",
    "email": "c.email",
    "phone": "c.phone",
    "company_name": "c.company_name",
    "city": "c.city",
    "state": "c.state",
    "status": "c.status",
    "created_date": "c.created_date",
    "assigned_to": "u.username",
}


def get_customer_report(
    visible_user_ids=None,
    search=None,
    status=None,
    assigned_to=None,
    sort_by="customer_name",
    sort_order="ASC",
    limit=20,
    offset=0,
    conn=None,
):
    """Query customer records with role scope, filtering, sorting, and pagination."""
    connection = conn or get_db_connection()
    sort_col = CUSTOMER_SORT_COLUMNS.get(sort_by, "c.customer_name")
    sort_dir = "DESC" if str(sort_order).upper() == "DESC" else "ASC"

    where_clauses = [
        "(%s::int[] IS NULL OR c.assigned_to = ANY(%s::int[]))",
        "(%s::varchar IS NULL OR c.status = %s)",
    ]
    params = [visible_user_ids, visible_user_ids, status, status]

    if assigned_to is not None:
        where_clauses.append("(%s::int IS NULL OR c.assigned_to = %s)")
        params.extend([assigned_to, assigned_to])

    if search:
        search_pattern = f"%{search.strip()}%"
        where_clauses.append(
            "(c.customer_name ILIKE %s OR c.email ILIKE %s OR c.phone ILIKE %s OR c.company_name ILIKE %s)"
        )
        params.extend([search_pattern, search_pattern, search_pattern, search_pattern])

    where_sql = " AND ".join(where_clauses)

    count_query = f"SELECT COUNT(*) FROM customers c WHERE {where_sql};"

    data_query = f"""
        SELECT
            c.customer_id,
            c.customer_code,
            c.customer_name,
            c.email,
            c.phone,
            c.company_name,
            c.city,
            c.state,
            c.status,
            c.created_date,
            c.assigned_to,
            u.username AS assigned_to_name
        FROM customers c
        LEFT JOIN users u ON c.assigned_to = u.user_id
        WHERE {where_sql}
        ORDER BY {sort_col} {sort_dir}
        LIMIT %s OFFSET %s;
    """

    with connection.cursor() as cur:
        cur.execute(count_query, params)
        total_count = cur.fetchone()[0]

        data_params = params + [limit, offset]
        cur.execute(data_query, data_params)
        rows = _rows_to_dicts(cur, cur.fetchall())

    return rows, total_count


# =============================================================================
# 2. LEAD REPORT
# =============================================================================

LEAD_SORT_COLUMNS = {
    "lead_code": "l.lead_code",
    "lead_name": "l.lead_name",
    "email": "l.email",
    "phone": "l.phone",
    "company_name": "l.company_name",
    "source": "l.source",
    "status": "l.status",
    "expected_value": "l.expected_value",
    "created_date": "l.created_date",
    "assigned_to": "u.username",
}


def get_lead_report(
    visible_user_ids=None,
    search=None,
    status=None,
    source=None,
    assigned_to=None,
    sort_by="lead_name",
    sort_order="ASC",
    limit=20,
    offset=0,
    conn=None,
):
    """Query lead records with role scope, filtering across all 6 statuses, sorting, and pagination."""
    connection = conn or get_db_connection()
    sort_col = LEAD_SORT_COLUMNS.get(sort_by, "l.lead_name")
    sort_dir = "DESC" if str(sort_order).upper() == "DESC" else "ASC"

    where_clauses = [
        "(%s::int[] IS NULL OR l.assigned_to = ANY(%s::int[]))",
        "(%s::varchar IS NULL OR l.status = %s)",
        "(%s::varchar IS NULL OR l.source = %s)",
    ]
    params = [visible_user_ids, visible_user_ids, status, status, source, source]

    if assigned_to is not None:
        where_clauses.append("(%s::int IS NULL OR l.assigned_to = %s)")
        params.extend([assigned_to, assigned_to])

    if search:
        search_pattern = f"%{search.strip()}%"
        where_clauses.append(
            "(l.lead_name ILIKE %s OR l.company_name ILIKE %s OR l.email ILIKE %s OR l.phone ILIKE %s)"
        )
        params.extend([search_pattern, search_pattern, search_pattern, search_pattern])

    where_sql = " AND ".join(where_clauses)

    count_query = f"SELECT COUNT(*) FROM leads l WHERE {where_sql};"

    data_query = f"""
        SELECT
            l.lead_id,
            l.lead_code,
            l.lead_name,
            l.email,
            l.phone,
            l.company_name,
            l.source,
            l.status,
            COALESCE(l.expected_value, 0.00) AS expected_value,
            l.created_date,
            l.assigned_to,
            u.username AS assigned_to_name
        FROM leads l
        LEFT JOIN users u ON l.assigned_to = u.user_id
        WHERE {where_sql}
        ORDER BY {sort_col} {sort_dir}
        LIMIT %s OFFSET %s;
    """

    with connection.cursor() as cur:
        cur.execute(count_query, params)
        total_count = cur.fetchone()[0]

        data_params = params + [limit, offset]
        cur.execute(data_query, data_params)
        rows = _rows_to_dicts(cur, cur.fetchall())

    return rows, total_count


# =============================================================================
# 3. FOLLOW-UP REPORT
# =============================================================================

FOLLOWUP_SORT_COLUMNS = {
    "followup_date": "f.followup_date",
    "subject": "f.subject",
    "followup_type": "f.followup_type",
    "status": "f.status",
    "created_date": "f.created_date",
    "assigned_to": "u.username",
}


def get_followup_report(
    visible_user_ids=None,
    start_date=None,
    end_date=None,
    status=None,
    followup_type=None,
    assigned_to=None,
    related_type=None,
    customer_id=None,
    lead_id=None,
    opportunity_id=None,
    sort_by="followup_date",
    sort_order="ASC",
    limit=20,
    offset=0,
    conn=None,
):
    """Query follow-ups with related record information, filters, and role scope."""
    connection = conn or get_db_connection()
    sort_col = FOLLOWUP_SORT_COLUMNS.get(sort_by, "f.followup_date")
    sort_dir = "DESC" if str(sort_order).upper() == "DESC" else "ASC"

    where_clauses = [
        "(%s::int[] IS NULL OR f.assigned_to = ANY(%s::int[]))",
        "(%s::varchar IS NULL OR f.status = %s)",
        "(%s::varchar IS NULL OR f.followup_type = %s)",
        "(%s::date IS NULL OR f.followup_date >= %s)",
        "(%s::date IS NULL OR f.followup_date < %s)",
    ]
    params = [
        visible_user_ids,
        visible_user_ids,
        status,
        status,
        followup_type,
        followup_type,
        start_date,
        start_date,
        end_date,
        end_date,
    ]

    if assigned_to is not None:
        where_clauses.append("(%s::int IS NULL OR f.assigned_to = %s)")
        params.extend([assigned_to, assigned_to])

    if customer_id is not None:
        where_clauses.append("(%s::int IS NULL OR f.customer_id = %s)")
        params.extend([customer_id, customer_id])

    if lead_id is not None:
        where_clauses.append("(%s::int IS NULL OR f.lead_id = %s)")
        params.extend([lead_id, lead_id])

    if opportunity_id is not None:
        where_clauses.append("(%s::int IS NULL OR f.opportunity_id = %s)")
        params.extend([opportunity_id, opportunity_id])

    if related_type:
        rt = related_type.strip().lower()
        if rt == "customer":
            where_clauses.append("f.customer_id IS NOT NULL")
        elif rt == "lead":
            where_clauses.append("f.lead_id IS NOT NULL")
        elif rt == "opportunity":
            where_clauses.append("f.opportunity_id IS NOT NULL")

    where_sql = " AND ".join(where_clauses)

    count_query = f"SELECT COUNT(*) FROM followups f WHERE {where_sql};"

    data_query = f"""
        SELECT
            f.followup_id,
            f.subject,
            f.followup_date,
            f.followup_type,
            f.status,
            f.remarks,
            f.created_date,
            f.assigned_to,
            u.username AS assigned_to_name,
            f.customer_id,
            c.customer_name,
            f.lead_id,
            l.lead_name,
            f.opportunity_id,
            o.opportunity_name
        FROM followups f
        LEFT JOIN users u ON f.assigned_to = u.user_id
        LEFT JOIN customers c ON f.customer_id = c.customer_id
        LEFT JOIN leads l ON f.lead_id = l.lead_id
        LEFT JOIN opportunities o ON f.opportunity_id = o.opportunity_id
        WHERE {where_sql}
        ORDER BY {sort_col} {sort_dir}
        LIMIT %s OFFSET %s;
    """

    with connection.cursor() as cur:
        cur.execute(count_query, params)
        total_count = cur.fetchone()[0]

        data_params = params + [limit, offset]
        cur.execute(data_query, data_params)
        rows = _rows_to_dicts(cur, cur.fetchall())

    return rows, total_count


# =============================================================================
# 4. OPPORTUNITY REPORT
# =============================================================================

OPPORTUNITY_SORT_COLUMNS = {
    "opportunity_name": "o.opportunity_name",
    "amount": "o.amount",
    "stage": "o.stage",
    "probability": "o.probability",
    "expected_close_date": "o.expected_close_date",
    "status": "o.status",
    "created_date": "o.created_date",
    "closed_date": "o.closed_date",
    "assigned_to": "u.username",
}


def get_opportunity_report(
    visible_user_ids=None,
    search=None,
    stage=None,
    status=None,
    assigned_to=None,
    sort_by="opportunity_name",
    sort_order="ASC",
    limit=20,
    offset=0,
    conn=None,
):
    """Query opportunities with Customer linkages, stage/status filters, and role scope."""
    connection = conn or get_db_connection()
    sort_col = OPPORTUNITY_SORT_COLUMNS.get(sort_by, "o.opportunity_name")
    sort_dir = "DESC" if str(sort_order).upper() == "DESC" else "ASC"

    where_clauses = [
        "(%s::int[] IS NULL OR o.assigned_to = ANY(%s::int[]))",
        "(%s::varchar IS NULL OR o.stage = %s)",
        "(%s::varchar IS NULL OR o.status = %s)",
    ]
    params = [visible_user_ids, visible_user_ids, stage, stage, status, status]

    if assigned_to is not None:
        where_clauses.append("(%s::int IS NULL OR o.assigned_to = %s)")
        params.extend([assigned_to, assigned_to])

    if search:
        search_pattern = f"%{search.strip()}%"
        where_clauses.append(
            "(o.opportunity_name ILIKE %s OR c.customer_name ILIKE %s)"
        )
        params.extend([search_pattern, search_pattern])

    where_sql = " AND ".join(where_clauses)

    count_query = f"""
        SELECT COUNT(*)
        FROM opportunities o
        LEFT JOIN customers c ON o.customer_id = c.customer_id
        WHERE {where_sql};
    """

    data_query = f"""
        SELECT
            o.opportunity_id,
            o.opportunity_name,
            o.amount,
            o.stage,
            o.probability,
            o.expected_close_date,
            o.status,
            o.created_date,
            o.closed_date,
            o.customer_id,
            c.customer_name,
            o.lead_id,
            l.lead_name,
            o.assigned_to,
            u.username AS assigned_to_name
        FROM opportunities o
        LEFT JOIN customers c ON o.customer_id = c.customer_id
        LEFT JOIN leads l ON o.lead_id = l.lead_id
        LEFT JOIN users u ON o.assigned_to = u.user_id
        WHERE {where_sql}
        ORDER BY {sort_col} {sort_dir}
        LIMIT %s OFFSET %s;
    """

    with connection.cursor() as cur:
        cur.execute(count_query, params)
        total_count = cur.fetchone()[0]

        data_params = params + [limit, offset]
        cur.execute(data_query, data_params)
        rows = _rows_to_dicts(cur, cur.fetchall())

    return rows, total_count


# =============================================================================
# 5. PIPELINE REPORT
# =============================================================================

PIPELINE_SORT_COLUMNS = {
    "opportunity_name": "o.opportunity_name",
    "amount": "o.amount",
    "probability": "o.probability",
    "weighted_value": "(o.amount * o.probability / 100.0)",
    "stage": "o.stage",
    "expected_close_date": "o.expected_close_date",
    "assigned_to": "u.username",
}


def get_pipeline_report(
    visible_user_ids=None,
    stage=None,
    sort_by="expected_close_date",
    sort_order="ASC",
    limit=20,
    offset=0,
    conn=None,
):
    """
    Query active pipeline (status = 'Open').
    Calculates exact totals, stage summaries, and detailed paginated list.
    """
    connection = conn or get_db_connection()
    sort_col = PIPELINE_SORT_COLUMNS.get(sort_by, "o.expected_close_date")
    sort_dir = "DESC" if str(sort_order).upper() == "DESC" else "ASC"

    where_clauses = [
        "o.status = 'Open'",
        "(%s::int[] IS NULL OR o.assigned_to = ANY(%s::int[]))",
        "(%s::varchar IS NULL OR o.stage = %s)",
    ]
    params = [visible_user_ids, visible_user_ids, stage, stage]
    where_sql = " AND ".join(where_clauses)

    # 1. Overall active pipeline aggregates
    summary_query = f"""
        SELECT
            COUNT(*) AS total_open_deals,
            COALESCE(SUM(o.amount), 0.00) AS total_pipeline_value,
            COALESCE(SUM(o.amount * o.probability / 100.0), 0.00) AS total_weighted_value
        FROM opportunities o
        WHERE {where_sql};
    """

    # 2. Stage breakdown aggregates
    stage_breakdown_query = f"""
        SELECT
            o.stage,
            COUNT(*) AS deal_count,
            COALESCE(SUM(o.amount), 0.00) AS stage_amount,
            COALESCE(SUM(o.amount * o.probability / 100.0), 0.00) AS stage_weighted_amount
        FROM opportunities o
        WHERE {where_sql}
        GROUP BY o.stage
        ORDER BY o.stage ASC;
    """

    # 3. Paginated detail rows
    data_query = f"""
        SELECT
            o.opportunity_id,
            o.opportunity_name,
            o.amount,
            o.probability,
            (o.amount * o.probability / 100.0) AS weighted_value,
            o.stage,
            o.status,
            o.expected_close_date,
            o.customer_id,
            c.customer_name,
            o.assigned_to,
            u.username AS assigned_to_name
        FROM opportunities o
        LEFT JOIN customers c ON o.customer_id = c.customer_id
        LEFT JOIN users u ON o.assigned_to = u.user_id
        WHERE {where_sql}
        ORDER BY {sort_col} {sort_dir}
        LIMIT %s OFFSET %s;
    """

    with connection.cursor() as cur:
        cur.execute(summary_query, params)
        sum_row = cur.fetchone()
        summary = {
            "total_open_deals": sum_row[0] if sum_row else 0,
            "total_pipeline_value": Decimal(str(sum_row[1])) if sum_row and sum_row[1] is not None else Decimal("0.00"),
            "total_weighted_value": Decimal(str(sum_row[2])) if sum_row and sum_row[2] is not None else Decimal("0.00"),
        }

        cur.execute(stage_breakdown_query, params)
        stage_rows = _rows_to_dicts(cur, cur.fetchall())
        stage_summaries = []
        for r in stage_rows:
            stage_summaries.append({
                "stage": r["stage"],
                "deal_count": r["deal_count"],
                "stage_amount": Decimal(str(r["stage_amount"])),
                "stage_weighted_amount": Decimal(str(r["stage_weighted_amount"])),
            })

        data_params = params + [limit, offset]
        cur.execute(data_query, data_params)
        detail_rows = _rows_to_dicts(cur, cur.fetchall())

    return detail_rows, summary, stage_summaries


# =============================================================================
# 6. SALES / CONVERSION REPORT
# =============================================================================

def get_sales_conversion_report(
    visible_user_ids=None,
    start_date=None,
    end_date=None,
    conn=None,
):
    """
    Computes Dual Conversion metrics (Decision 99 #2):
    - Lead Conversion: Total Leads, Converted Leads, Lead Conversion Rate %.
    - Deal Win Rate: Total Closed Deals (Won + Lost), Won Deals, Lost Deals, Win Rate %.
    - Won Sales Revenue: SUM(amount) for Won deals by closed_date.
    - Also lists Won and Converted achievements in the period.
    """
    connection = conn or get_db_connection()

    # 1. Lead Conversion Metrics (created_date in period)
    lead_query = """
        SELECT
            COUNT(*) AS total_leads,
            COUNT(*) FILTER (WHERE status = 'Converted') AS converted_leads
        FROM leads l
        WHERE (%s::int[] IS NULL OR l.assigned_to = ANY(%s::int[]))
          AND (%s::timestamptz IS NULL OR l.created_date >= %s)
          AND (%s::timestamptz IS NULL OR l.created_date < %s);
    """

    # 2. Opportunity Win / Loss & Revenue Metrics (closed_date in period)
    deal_query = """
        SELECT
            COUNT(*) FILTER (WHERE status = 'Won') AS won_count,
            COUNT(*) FILTER (WHERE status = 'Lost') AS lost_count,
            COALESCE(SUM(amount) FILTER (WHERE status = 'Won'), 0.00) AS total_won_revenue
        FROM opportunities o
        WHERE (%s::int[] IS NULL OR o.assigned_to = ANY(%s::int[]))
          AND o.status IN ('Won', 'Lost')
          AND o.closed_date IS NOT NULL
          AND (%s::timestamptz IS NULL OR o.closed_date >= %s)
          AND (%s::timestamptz IS NULL OR o.closed_date < %s);
    """

    # 3. Won Deals Detail List
    won_deals_query = """
        SELECT
            o.opportunity_id,
            o.opportunity_name,
            o.amount,
            o.stage,
            o.status,
            o.closed_date,
            c.customer_name,
            o.assigned_to,
            u.username AS assigned_to_name
        FROM opportunities o
        LEFT JOIN customers c ON o.customer_id = c.customer_id
        LEFT JOIN users u ON o.assigned_to = u.user_id
        WHERE (%s::int[] IS NULL OR o.assigned_to = ANY(%s::int[]))
          AND o.status = 'Won'
          AND o.closed_date IS NOT NULL
          AND (%s::timestamptz IS NULL OR o.closed_date >= %s)
          AND (%s::timestamptz IS NULL OR o.closed_date < %s)
        ORDER BY o.closed_date DESC;
    """

    with connection.cursor() as cur:
        # Lead stats
        cur.execute(lead_query, (visible_user_ids, visible_user_ids, start_date, start_date, end_date, end_date))
        lead_row = cur.fetchone()
        total_leads = lead_row[0] if lead_row else 0
        converted_leads = lead_row[1] if lead_row else 0
        lead_conversion_rate = Decimal("0.00")
        if total_leads > 0:
            lead_conversion_rate = (Decimal(converted_leads) / Decimal(total_leads) * Decimal("100.0")).quantize(Decimal("0.01"))

        # Opportunity Win stats
        cur.execute(deal_query, (visible_user_ids, visible_user_ids, start_date, start_date, end_date, end_date))
        deal_row = cur.fetchone()
        won_count = deal_row[0] if deal_row else 0
        lost_count = deal_row[1] if deal_row else 0
        total_won_revenue = Decimal(str(deal_row[2])) if deal_row and deal_row[2] is not None else Decimal("0.00")
        total_closed_deals = won_count + lost_count
        opportunity_win_rate = Decimal("0.00")
        if total_closed_deals > 0:
            opportunity_win_rate = (Decimal(won_count) / Decimal(total_closed_deals) * Decimal("100.0")).quantize(Decimal("0.01"))

        # Won deals list
        cur.execute(won_deals_query, (visible_user_ids, visible_user_ids, start_date, start_date, end_date, end_date))
        won_deals = _rows_to_dicts(cur, cur.fetchall())

    return {
        "total_leads": total_leads,
        "converted_leads": converted_leads,
        "lead_conversion_rate": lead_conversion_rate,
        "won_count": won_count,
        "lost_count": lost_count,
        "total_closed_deals": total_closed_deals,
        "opportunity_win_rate": opportunity_win_rate,
        "total_won_revenue": total_won_revenue,
        "won_deals": won_deals,
    }


# =============================================================================
# 7. USER ACTIVITY REPORT
# =============================================================================

ACTIVITY_SORT_COLUMNS = {
    "activity_date": "a.activity_date",
    "activity_type": "a.activity_type",
    "subject": "a.subject",
    "status": "a.status",
    "assigned_to": "u.username",
}


def get_user_activity_report(
    visible_user_ids=None,
    assigned_to_user_id=None,
    activity_type=None,
    status=None,
    start_date=None,
    end_date=None,
    sort_by="activity_date",
    sort_order="DESC",
    limit=20,
    offset=0,
    conn=None,
):
    """
    Query CRM Sales Activities (Calls, Meetings, Emails, Tasks) per Decision 99 #1.
    Scoped by ownership and filterable by rep, type, status, and activity date.
    """
    connection = conn or get_db_connection()
    sort_col = ACTIVITY_SORT_COLUMNS.get(sort_by, "a.activity_date")
    sort_dir = "DESC" if str(sort_order).upper() == "DESC" else "ASC"

    where_clauses = [
        "(%s::int[] IS NULL OR a.assigned_to = ANY(%s::int[]))",
        "(%s::int IS NULL OR a.assigned_to = %s)",
        "(%s::varchar IS NULL OR a.activity_type = %s)",
        "(%s::varchar IS NULL OR a.status = %s)",
        "(%s::timestamptz IS NULL OR a.activity_date >= %s)",
        "(%s::timestamptz IS NULL OR a.activity_date < %s)",
    ]
    params = [
        visible_user_ids,
        visible_user_ids,
        assigned_to_user_id,
        assigned_to_user_id,
        activity_type,
        activity_type,
        status,
        status,
        start_date,
        start_date,
        end_date,
        end_date,
    ]

    where_sql = " AND ".join(where_clauses)

    count_query = f"SELECT COUNT(*) FROM activities a WHERE {where_sql};"

    data_query = f"""
        SELECT
            a.activity_id,
            a.activity_type,
            a.subject,
            a.description,
            a.activity_date,
            a.status,
            a.assigned_to,
            u.username AS assigned_to_name,
            a.customer_id,
            c.customer_name,
            a.lead_id,
            l.lead_name
        FROM activities a
        LEFT JOIN users u ON a.assigned_to = u.user_id
        LEFT JOIN customers c ON a.customer_id = c.customer_id
        LEFT JOIN leads l ON a.lead_id = l.lead_id
        WHERE {where_sql}
        ORDER BY {sort_col} {sort_dir}
        LIMIT %s OFFSET %s;
    """

    with connection.cursor() as cur:
        cur.execute(count_query, params)
        total_count = cur.fetchone()[0]

        data_params = params + [limit, offset]
        cur.execute(data_query, data_params)
        rows = _rows_to_dicts(cur, cur.fetchall())

    return rows, total_count


# =============================================================================
# 8. AUDIT REPORT (ADMIN ONLY)
# =============================================================================

AUDIT_SORT_COLUMNS = {
    "created_date": "al.created_date",
    "action": "al.action",
    "entity_name": "al.entity_name",
    "result": "al.result",
    "username": "u.username",
}


def get_audit_report(
    user_id=None,
    entity_name=None,
    action=None,
    start_date=None,
    end_date=None,
    sort_by="created_date",
    sort_order="DESC",
    limit=20,
    offset=0,
    conn=None,
):
    """
    Query immutable system audit log entries for Administrators (Decision 99 #4).
    Excludes sensitive secrets (passwords, hashes, tokens).
    """
    connection = conn or get_db_connection()
    sort_col = AUDIT_SORT_COLUMNS.get(sort_by, "al.created_date")
    sort_dir = "DESC" if str(sort_order).upper() == "DESC" else "ASC"

    where_clauses = [
        "(%s::int IS NULL OR al.user_id = %s)",
        "(%s::varchar IS NULL OR al.entity_name = %s)",
        "(%s::varchar IS NULL OR al.action = %s)",
        "(%s::timestamptz IS NULL OR al.created_date >= %s)",
        "(%s::timestamptz IS NULL OR al.created_date < %s)",
    ]
    params = [
        user_id,
        user_id,
        entity_name,
        entity_name,
        action,
        action,
        start_date,
        start_date,
        end_date,
        end_date,
    ]

    where_sql = " AND ".join(where_clauses)

    count_query = f"SELECT COUNT(*) FROM audit_logs al WHERE {where_sql};"

    data_query = f"""
        SELECT
            al.audit_log_id,
            al.user_id,
            u.username,
            al.action,
            al.entity_name,
            al.record_id,
            al.old_value,
            al.new_value,
            al.result,
            al.created_date,
            al.ip_address
        FROM audit_logs al
        LEFT JOIN users u ON al.user_id = u.user_id
        WHERE {where_sql}
        ORDER BY {sort_col} {sort_dir}
        LIMIT %s OFFSET %s;
    """

    with connection.cursor() as cur:
        cur.execute(count_query, params)
        total_count = cur.fetchone()[0]

        data_params = params + [limit, offset]
        cur.execute(data_query, data_params)
        rows = _rows_to_dicts(cur, cur.fetchall())

    return rows, total_count
