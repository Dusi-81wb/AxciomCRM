"""
Dashboard Repository for AcxiomCRM (Phase 9).

Encapsulates all SQL aggregation queries for KPI cards and Chart.js visualizations
using raw psycopg2 with strict parameterization (%s) and server-side authorization scoping.

Adheres strictly to architectural requirements:
- Repositories DO NOT manage transactions or commit.
- All dynamic inputs are strictly parameterized (%s) to prevent SQL injection.
- Role-based ownership filtering enforced directly in SQL WHERE clauses.
- Monetary values aggregated using PostgreSQL NUMERIC and retrieved as Python Decimal.
"""

from decimal import Decimal
from database import get_db_connection


def _row_to_dict(cursor, row):
    """Convert database row tuple to dictionary using cursor descriptions."""
    if row is None:
        return None
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


def _rows_to_dicts(cursor, rows):
    """Convert database row tuples to list of dictionaries."""
    if not rows:
        return []
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, r)) for r in rows]


def get_customer_kpi(visible_user_ids=None, start_dt=None, end_dt=None, conn=None):
    """
    Count visible customers created within the given date window.
    """
    connection = conn or get_db_connection()
    query = """
        SELECT COUNT(*) AS total_customers
        FROM customers c
        WHERE (%s::int[] IS NULL OR c.assigned_to = ANY(%s::int[]))
          AND (%s::timestamptz IS NULL OR (c.created_date >= %s AND c.created_date < %s));
    """
    with connection.cursor() as cur:
        cur.execute(query, (visible_user_ids, visible_user_ids, start_dt, start_dt, end_dt))
        row = cur.fetchone()
        return row[0] if row else 0


def get_lead_kpis(visible_user_ids=None, start_dt=None, end_dt=None, conn=None):
    """
    Count total visible leads and open leads created within the given date window.
    Open Leads = status IN ('New', 'Contacted', 'Qualified') per Decision 98 #1.
    """
    connection = conn or get_db_connection()
    query = """
        SELECT
            COUNT(*) AS total_leads,
            COUNT(*) FILTER (WHERE status IN ('New', 'Contacted', 'Qualified')) AS open_leads
        FROM leads l
        WHERE (%s::int[] IS NULL OR l.assigned_to = ANY(%s::int[]))
          AND (%s::timestamptz IS NULL OR (l.created_date >= %s AND l.created_date < %s));
    """
    with connection.cursor() as cur:
        cur.execute(query, (visible_user_ids, visible_user_ids, start_dt, start_dt, end_dt))
        row = cur.fetchone()
        return {
            "total_leads": row[0] if row else 0,
            "open_leads": row[1] if row else 0,
        }


def get_opportunity_kpis(visible_user_ids=None, start_dt=None, end_dt=None, conn=None):
    """
    Count total visible opportunities and open opportunities (by CreatedDate),
    along with Total Pipeline Value (SUM(amount) for status = 'Open').
    """
    connection = conn or get_db_connection()
    query = """
        SELECT
            COUNT(*) AS total_opportunities,
            COUNT(*) FILTER (WHERE status = 'Open') AS open_opportunities,
            COALESCE(SUM(amount) FILTER (WHERE status = 'Open'), 0.00) AS total_pipeline_value
        FROM opportunities o
        WHERE (%s::int[] IS NULL OR o.assigned_to = ANY(%s::int[]))
          AND (%s::timestamptz IS NULL OR (o.created_date >= %s AND o.created_date < %s));
    """
    with connection.cursor() as cur:
        cur.execute(query, (visible_user_ids, visible_user_ids, start_dt, start_dt, end_dt))
        row = cur.fetchone()
        return {
            "total_opportunities": row[0] if row else 0,
            "open_opportunities": row[1] if row else 0,
            "total_pipeline_value": Decimal(str(row[2])) if row and row[2] is not None else Decimal("0.00"),
        }


def get_won_lost_kpis(visible_user_ids=None, start_dt=None, end_dt=None, conn=None):
    """
    Count Won and Lost opportunities using ClosedDate per Spec Notes 36 and 84.
    """
    connection = conn or get_db_connection()
    query = """
        SELECT
            COUNT(*) FILTER (WHERE status = 'Won') AS won_count,
            COUNT(*) FILTER (WHERE status = 'Lost') AS lost_count
        FROM opportunities o
        WHERE (%s::int[] IS NULL OR o.assigned_to = ANY(%s::int[]))
          AND (%s::timestamptz IS NULL OR (o.closed_date >= %s AND o.closed_date < %s));
    """
    with connection.cursor() as cur:
        cur.execute(query, (visible_user_ids, visible_user_ids, start_dt, start_dt, end_dt))
        row = cur.fetchone()
        return {
            "won_count": row[0] if row else 0,
            "lost_count": row[1] if row else 0,
        }


def get_lead_status_chart_counts(visible_user_ids=None, start_dt=None, end_dt=None, conn=None):
    """
    Aggregate counts of visible leads grouped by status within date range.
    Only queries the 5 categories required for the Lead Status chart:
    'New', 'Contacted', 'Qualified', 'Converted', 'Lost' per Decision 98 #3.
    """
    connection = conn or get_db_connection()
    query = """
        SELECT status, COUNT(*) AS cnt
        FROM leads l
        WHERE (%s::int[] IS NULL OR l.assigned_to = ANY(%s::int[]))
          AND (%s::timestamptz IS NULL OR (l.created_date >= %s AND l.created_date < %s))
          AND status IN ('New', 'Contacted', 'Qualified', 'Converted', 'Lost')
        GROUP BY status;
    """
    with connection.cursor() as cur:
        cur.execute(query, (visible_user_ids, visible_user_ids, start_dt, start_dt, end_dt))
        rows = cur.fetchall()
        return {r[0]: r[1] for r in rows}


def get_opportunity_pipeline_chart_counts(visible_user_ids=None, start_dt=None, end_dt=None, conn=None):
    """
    Aggregate counts of visible opportunities grouped by stage within date range.
    Stages: 'Qualification', 'Proposal', 'Negotiation', 'Won', 'Lost'.
    """
    connection = conn or get_db_connection()
    query = """
        SELECT stage, COUNT(*) AS cnt
        FROM opportunities o
        WHERE (%s::int[] IS NULL OR o.assigned_to = ANY(%s::int[]))
          AND (%s::timestamptz IS NULL OR (o.created_date >= %s AND o.created_date < %s))
        GROUP BY stage;
    """
    with connection.cursor() as cur:
        cur.execute(query, (visible_user_ids, visible_user_ids, start_dt, start_dt, end_dt))
        rows = cur.fetchall()
        return {r[0]: r[1] for r in rows}


def get_monthly_sales_chart_data(visible_user_ids=None, start_dt=None, end_dt=None, conn=None):
    """
    Monthly Sales chart data: SUM(amount) of Won opportunities grouped by month
    of closed_date (Asia/Kolkata timezone).
    Decision 98 #4.
    """
    connection = conn or get_db_connection()
    query = """
        SELECT
            TO_CHAR(o.closed_date AT TIME ZONE 'Asia/Kolkata', 'YYYY-MM') AS month_key,
            COALESCE(SUM(o.amount), 0.00) AS total_sales
        FROM opportunities o
        WHERE o.status = 'Won'
          AND o.closed_date IS NOT NULL
          AND (%s::int[] IS NULL OR o.assigned_to = ANY(%s::int[]))
          AND (%s::timestamptz IS NULL OR o.closed_date >= %s)
          AND (%s::timestamptz IS NULL OR o.closed_date < %s)
        GROUP BY month_key
        ORDER BY month_key ASC;
    """
    with connection.cursor() as cur:
        cur.execute(query, (visible_user_ids, visible_user_ids, start_dt, start_dt, end_dt, end_dt))
        rows = cur.fetchall()
        return {r[0]: Decimal(str(r[1])) for r in rows}

