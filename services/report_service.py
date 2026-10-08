"""
Report Service for AcxiomCRM (Phase 10).

Orchestrates business validation, date range boundaries in Asia/Kolkata,
role-based scoping, financial Decimal calculations, and view-model formatting
for the 8 CRM Reports.

Adheres strictly to architectural requirements:
- READ-ONLY: Never modifies CRM records, audit logs, or users.
- Server-side scope: Computes report datasets strictly within actor's authorized scope.
- Timezone: Asia/Kolkata timezone used for all report date filters.
- Money exactness: Preserves Decimal precision (no float conversions for currency).
- Security: Parameterized inputs, whitelisted sort columns, sanitized audit payloads.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from security.authorization import visible_user_ids
from repositories import report_repository
from repositories import customer_repository

TIMEZONE_KOLKATA = ZoneInfo("Asia/Kolkata")


def parse_report_date_range(start_str=None, end_str=None):
    """
    Validate and convert start/end date strings (YYYY-MM-DD) to timezone-aware datetimes.

    :param start_str: Optional string 'YYYY-MM-DD'.
    :param end_str: Optional string 'YYYY-MM-DD'.
    :return: Tuple of (start_dt, end_dt) in Asia/Kolkata.
    :raises ValueError: On malformed date formats or if start > end.
    """
    start_dt = None
    end_dt = None

    if start_str and start_str.strip():
        try:
            sd = datetime.strptime(start_str.strip(), "%Y-%m-%d").date()
            start_dt = datetime(sd.year, sd.month, sd.day, 0, 0, 0, tzinfo=TIMEZONE_KOLKATA)
        except ValueError:
            raise ValueError("Invalid start date format. Please use YYYY-MM-DD.")

    if end_str and end_str.strip():
        try:
            ed = datetime.strptime(end_str.strip(), "%Y-%m-%d").date()
            # End boundary is exclusive +1 day to cover all of end_date up to midnight
            end_dt = datetime(ed.year, ed.month, ed.day, 0, 0, 0, tzinfo=TIMEZONE_KOLKATA) + timedelta(days=1)
        except ValueError:
            raise ValueError("Invalid end date format. Please use YYYY-MM-DD.")

    if start_dt and end_dt and start_dt >= end_dt:
        raise ValueError("Start date cannot be after end date.")

    return start_dt, end_dt


def calculate_pagination(total_count, page=1, per_page=20):
    """Calculate pagination metadata."""
    safe_page = max(1, int(page or 1))
    safe_per_page = max(1, min(100, int(per_page or 20)))
    total_pages = max(1, (total_count + safe_per_page - 1) // safe_per_page)
    offset = (safe_page - 1) * safe_per_page
    return safe_page, safe_per_page, total_pages, offset


# =============================================================================
# 1. CUSTOMER REPORT
# =============================================================================

def get_customer_report_data(
    current_user,
    search=None,
    status=None,
    assigned_to=None,
    sort_by="customer_name",
    sort_order="ASC",
    page=1,
    per_page=20,
):
    """Orchestrate customer report retrieval with role scoping, assigned rep filter, and pagination."""
    visible_ids = visible_user_ids(current_user)
    clean_sort_by = sort_by if sort_by in report_repository.CUSTOMER_SORT_COLUMNS else "customer_name"
    clean_sort_order = "DESC" if str(sort_order).upper() == "DESC" else "ASC"
    clean_status = status.strip() if status and status.strip() in ("Active", "Inactive") else None
    clean_assigned_to = None
    if assigned_to:
        try:
            clean_assigned_to = int(assigned_to)
        except (ValueError, TypeError):
            clean_assigned_to = None

    # Dummy count to get total_pages first
    _, total_count = report_repository.get_customer_report(
        visible_user_ids=visible_ids,
        search=search,
        status=clean_status,
        assigned_to=clean_assigned_to,
        sort_by=clean_sort_by,
        sort_order=clean_sort_order,
        limit=1,
        offset=0,
    )

    page, per_page, total_pages, offset = calculate_pagination(total_count, page, per_page)

    records, _ = report_repository.get_customer_report(
        visible_user_ids=visible_ids,
        search=search,
        status=clean_status,
        assigned_to=clean_assigned_to,
        sort_by=clean_sort_by,
        sort_order=clean_sort_order,
        limit=per_page,
        offset=offset,
    )

    sales_executives = customer_repository.get_active_sales_executives()

    return {
        "records": records,
        "total_count": total_count,
        "current_page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "search": search or "",
        "status": clean_status or "",
        "assigned_to": str(clean_assigned_to) if clean_assigned_to else "",
        "sales_executives": sales_executives,
        "sort_by": clean_sort_by,
        "sort_order": clean_sort_order,
    }


# =============================================================================
# 2. LEAD REPORT
# =============================================================================

VALID_LEAD_STATUSES = ("New", "Contacted", "Qualified", "Unqualified", "Converted", "Lost")


def get_lead_report_data(
    current_user,
    search=None,
    status=None,
    source=None,
    assigned_to=None,
    sort_by="lead_name",
    sort_order="ASC",
    page=1,
    per_page=20,
):
    """Orchestrate lead report retrieval across all 6 lead statuses with assigned rep filter."""
    visible_ids = visible_user_ids(current_user)
    clean_sort_by = sort_by if sort_by in report_repository.LEAD_SORT_COLUMNS else "lead_name"
    clean_sort_order = "DESC" if str(sort_order).upper() == "DESC" else "ASC"
    clean_status = status.strip() if status and status.strip() in VALID_LEAD_STATUSES else None
    clean_source = source.strip() if source and source.strip() else None
    clean_assigned_to = None
    if assigned_to:
        try:
            clean_assigned_to = int(assigned_to)
        except (ValueError, TypeError):
            clean_assigned_to = None

    _, total_count = report_repository.get_lead_report(
        visible_user_ids=visible_ids,
        search=search,
        status=clean_status,
        source=clean_source,
        assigned_to=clean_assigned_to,
        sort_by=clean_sort_by,
        sort_order=clean_sort_order,
        limit=1,
        offset=0,
    )

    page, per_page, total_pages, offset = calculate_pagination(total_count, page, per_page)

    records, _ = report_repository.get_lead_report(
        visible_user_ids=visible_ids,
        search=search,
        status=clean_status,
        source=clean_source,
        assigned_to=clean_assigned_to,
        sort_by=clean_sort_by,
        sort_order=clean_sort_order,
        limit=per_page,
        offset=offset,
    )

    sales_executives = customer_repository.get_active_sales_executives()

    return {
        "records": records,
        "total_count": total_count,
        "current_page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "search": search or "",
        "status": clean_status or "",
        "source": clean_source or "",
        "assigned_to": str(clean_assigned_to) if clean_assigned_to else "",
        "sales_executives": sales_executives,
        "sort_by": clean_sort_by,
        "sort_order": clean_sort_order,
    }


# =============================================================================
# 3. FOLLOW-UP REPORT
# =============================================================================

VALID_FOLLOWUP_STATUSES = ("Planned", "Completed", "Missed", "Cancelled")
VALID_FOLLOWUP_TYPES = ("Call", "Meeting", "Email")


def get_followup_report_data(
    current_user,
    start_str=None,
    end_str=None,
    status=None,
    followup_type=None,
    assigned_to=None,
    related_type=None,
    customer_id=None,
    lead_id=None,
    opportunity_id=None,
    sort_by="followup_date",
    sort_order="ASC",
    page=1,
    per_page=20,
):
    """Orchestrate follow-up report retrieval with date boundaries, assigned reps, and related records."""
    visible_ids = visible_user_ids(current_user)
    start_dt, end_dt = parse_report_date_range(start_str, end_str)

    clean_sort_by = sort_by if sort_by in report_repository.FOLLOWUP_SORT_COLUMNS else "followup_date"
    clean_sort_order = "DESC" if str(sort_order).upper() == "DESC" else "ASC"
    clean_status = status.strip() if status and status.strip() in VALID_FOLLOWUP_STATUSES else None
    clean_type = followup_type.strip() if followup_type and followup_type.strip() in VALID_FOLLOWUP_TYPES else None

    clean_assigned_to = None
    if assigned_to:
        try:
            clean_assigned_to = int(assigned_to)
        except (ValueError, TypeError):
            clean_assigned_to = None

    clean_customer_id = None
    if customer_id:
        try:
            clean_customer_id = int(customer_id)
        except (ValueError, TypeError):
            clean_customer_id = None

    clean_lead_id = None
    if lead_id:
        try:
            clean_lead_id = int(lead_id)
        except (ValueError, TypeError):
            clean_lead_id = None

    clean_opportunity_id = None
    if opportunity_id:
        try:
            clean_opportunity_id = int(opportunity_id)
        except (ValueError, TypeError):
            clean_opportunity_id = None

    clean_related_type = None
    if related_type and related_type.strip().capitalize() in ("Customer", "Lead", "Opportunity"):
        clean_related_type = related_type.strip().capitalize()

    _, total_count = report_repository.get_followup_report(
        visible_user_ids=visible_ids,
        start_date=start_dt.date() if start_dt else None,
        end_date=end_dt.date() if end_dt else None,
        status=clean_status,
        followup_type=clean_type,
        assigned_to=clean_assigned_to,
        related_type=clean_related_type,
        customer_id=clean_customer_id,
        lead_id=clean_lead_id,
        opportunity_id=clean_opportunity_id,
        sort_by=clean_sort_by,
        sort_order=clean_sort_order,
        limit=1,
        offset=0,
    )

    page, per_page, total_pages, offset = calculate_pagination(total_count, page, per_page)

    records, _ = report_repository.get_followup_report(
        visible_user_ids=visible_ids,
        start_date=start_dt.date() if start_dt else None,
        end_date=end_dt.date() if end_dt else None,
        status=clean_status,
        followup_type=clean_type,
        assigned_to=clean_assigned_to,
        related_type=clean_related_type,
        customer_id=clean_customer_id,
        lead_id=clean_lead_id,
        opportunity_id=clean_opportunity_id,
        sort_by=clean_sort_by,
        sort_order=clean_sort_order,
        limit=per_page,
        offset=offset,
    )

    sales_executives = customer_repository.get_active_sales_executives()

    return {
        "records": records,
        "total_count": total_count,
        "current_page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "start_date": start_str or "",
        "end_date": end_str or "",
        "status": clean_status or "",
        "followup_type": clean_type or "",
        "assigned_to": str(clean_assigned_to) if clean_assigned_to else "",
        "related_type": clean_related_type or "",
        "customer_id": str(clean_customer_id) if clean_customer_id else "",
        "lead_id": str(clean_lead_id) if clean_lead_id else "",
        "opportunity_id": str(clean_opportunity_id) if clean_opportunity_id else "",
        "sales_executives": sales_executives,
        "sort_by": clean_sort_by,
        "sort_order": clean_sort_order,
    }


# =============================================================================
# 4. OPPORTUNITY REPORT
# =============================================================================

VALID_OPP_STAGES = ("Qualification", "Proposal", "Negotiation", "Won", "Lost")
VALID_OPP_STATUSES = ("Open", "Won", "Lost")


def get_opportunity_report_data(
    current_user,
    search=None,
    stage=None,
    status=None,
    assigned_to=None,
    sort_by="opportunity_name",
    sort_order="ASC",
    page=1,
    per_page=20,
):
    """Orchestrate opportunity report retrieval with assigned rep filter."""
    visible_ids = visible_user_ids(current_user)
    clean_sort_by = sort_by if sort_by in report_repository.OPPORTUNITY_SORT_COLUMNS else "opportunity_name"
    clean_sort_order = "DESC" if str(sort_order).upper() == "DESC" else "ASC"
    clean_stage = stage.strip() if stage and stage.strip() in VALID_OPP_STAGES else None
    clean_status = status.strip() if status and status.strip() in VALID_OPP_STATUSES else None

    clean_assigned_to = None
    if assigned_to:
        try:
            clean_assigned_to = int(assigned_to)
        except (ValueError, TypeError):
            clean_assigned_to = None

    _, total_count = report_repository.get_opportunity_report(
        visible_user_ids=visible_ids,
        search=search,
        stage=clean_stage,
        status=clean_status,
        assigned_to=clean_assigned_to,
        sort_by=clean_sort_by,
        sort_order=clean_sort_order,
        limit=1,
        offset=0,
    )

    page, per_page, total_pages, offset = calculate_pagination(total_count, page, per_page)

    records, _ = report_repository.get_opportunity_report(
        visible_user_ids=visible_ids,
        search=search,
        stage=clean_stage,
        status=clean_status,
        assigned_to=clean_assigned_to,
        sort_by=clean_sort_by,
        sort_order=clean_sort_order,
        limit=per_page,
        offset=offset,
    )

    sales_executives = customer_repository.get_active_sales_executives()

    return {
        "records": records,
        "total_count": total_count,
        "current_page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "search": search or "",
        "stage": clean_stage or "",
        "status": clean_status or "",
        "assigned_to": str(clean_assigned_to) if clean_assigned_to else "",
        "sales_executives": sales_executives,
        "sort_by": clean_sort_by,
        "sort_order": clean_sort_order,
    }


# =============================================================================
# 5. PIPELINE REPORT
# =============================================================================

def get_pipeline_report_data(
    current_user,
    stage=None,
    sort_by="expected_close_date",
    sort_order="ASC",
    page=1,
    per_page=20,
):
    """
    Orchestrates Pipeline Report with exact financial Decimal calculations.
    Active pipeline is based on Status = 'Open'.
    Calculates Weighted Value = Amount * Probability / 100.
    """
    visible_ids = visible_user_ids(current_user)
    clean_sort_by = sort_by if sort_by in report_repository.PIPELINE_SORT_COLUMNS else "expected_close_date"
    clean_sort_order = "DESC" if str(sort_order).upper() == "DESC" else "ASC"
    clean_stage = stage.strip() if stage and stage.strip() in ("Qualification", "Proposal", "Negotiation") else None

    # Retrieve overall active pipeline summary & stage summaries
    records, summary, stage_summaries = report_repository.get_pipeline_report(
        visible_user_ids=visible_ids,
        stage=clean_stage,
        sort_by=clean_sort_by,
        sort_order=clean_sort_order,
        limit=per_page,
        offset=0,
    )

    total_count = summary["total_open_deals"]
    page, per_page, total_pages, offset = calculate_pagination(total_count, page, per_page)

    if offset > 0:
        records, _, _ = report_repository.get_pipeline_report(
            visible_user_ids=visible_ids,
            stage=clean_stage,
            sort_by=clean_sort_by,
            sort_order=clean_sort_order,
            limit=per_page,
            offset=offset,
        )

    # Format monetary values
    formatted_summary = {
        "total_open_deals": summary["total_open_deals"],
        "total_pipeline_value": summary["total_pipeline_value"],
        "total_pipeline_value_formatted": f"{summary['total_pipeline_value']:,.2f}",
        "total_weighted_value": summary["total_weighted_value"],
        "total_weighted_value_formatted": f"{summary['total_weighted_value']:,.2f}",
    }

    formatted_stages = []
    for stg in stage_summaries:
        formatted_stages.append({
            "stage": stg["stage"],
            "deal_count": stg["deal_count"],
            "stage_amount": stg["stage_amount"],
            "stage_amount_formatted": f"{stg['stage_amount']:,.2f}",
            "stage_weighted_amount": stg["stage_weighted_amount"],
            "stage_weighted_amount_formatted": f"{stg['stage_weighted_amount']:,.2f}",
        })

    formatted_records = []
    for r in records:
        amt = Decimal(str(r["amount"]))
        prob = int(r["probability"])
        weighted = (amt * Decimal(prob) / Decimal(100)).quantize(Decimal("0.01"))
        formatted_records.append({
            **r,
            "amount_formatted": f"{amt:,.2f}",
            "weighted_value_formatted": f"{weighted:,.2f}",
        })

    return {
        "records": formatted_records,
        "summary": formatted_summary,
        "stage_summaries": formatted_stages,
        "total_count": total_count,
        "current_page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "stage": clean_stage or "",
        "sort_by": clean_sort_by,
        "sort_order": clean_sort_order,
    }


# =============================================================================
# 6. SALES / CONVERSION REPORT
# =============================================================================

def get_sales_conversion_report_data(
    current_user,
    start_str=None,
    end_str=None,
):
    """
    Orchestrates Dual Conversion & Sales Report (Decision 99 #2):
    - Lead Conversion Rate %: Converted Leads / Total Leads * 100
    - Deal Win Rate %: Won Deals / (Won + Lost Deals) * 100
    - Total Won Revenue: SUM(Amount) for Won deals by ClosedDate
    """
    visible_ids = visible_user_ids(current_user)
    start_dt, end_dt = parse_report_date_range(start_str, end_str)

    data = report_repository.get_sales_conversion_report(
        visible_user_ids=visible_ids,
        start_date=start_dt,
        end_date=end_dt,
    )

    data["total_won_revenue_formatted"] = f"{data['total_won_revenue']:,.2f}"
    data["won_opportunities"] = data["won_count"]
    data["lost_opportunities"] = data["lost_count"]
    data["total_closed_opportunities"] = data["total_closed_deals"]

    formatted_deals = []
    for d in data["won_deals"]:
        amt = Decimal(str(d["amount"]))
        formatted_deals.append({
            **d,
            "amount_formatted": f"{amt:,.2f}",
        })
    data["won_deals"] = formatted_deals
    data["start_date"] = start_str or ""
    data["end_date"] = end_str or ""

    return data


# =============================================================================
# 7. USER ACTIVITY REPORT
# =============================================================================

VALID_ACTIVITY_TYPES = ("Call", "Meeting", "Email", "Task")
VALID_ACTIVITY_STATUSES = ("Completed", "Planned")


def get_user_activity_report_data(
    current_user,
    assigned_to_user_id=None,
    activity_type=None,
    status=None,
    start_str=None,
    end_str=None,
    sort_by="activity_date",
    sort_order="DESC",
    page=1,
    per_page=20,
):
    """
    Orchestrate CRM Sales Activities Report (Decision 99 #1).
    Scoped by ownership and filterable by rep, type, status, and date.
    """
    visible_ids = visible_user_ids(current_user)
    start_dt, end_dt = parse_report_date_range(start_str, end_str)

    clean_sort_by = sort_by if sort_by in report_repository.ACTIVITY_SORT_COLUMNS else "activity_date"
    clean_sort_order = "DESC" if str(sort_order).upper() == "DESC" else "ASC"
    clean_type = activity_type.strip() if activity_type and activity_type.strip() in VALID_ACTIVITY_TYPES else None
    clean_status = status.strip() if status and status.strip() in VALID_ACTIVITY_STATUSES else None

    # If Sales Exec specifies assigned_to, enforce that it can only be their own user_id
    clean_rep_id = None
    if assigned_to_user_id:
        try:
            clean_rep_id = int(assigned_to_user_id)
            if visible_ids is not None and clean_rep_id not in visible_ids:
                # Disallow unauthorized rep filter
                clean_rep_id = -1
        except ValueError:
            clean_rep_id = None

    _, total_count = report_repository.get_user_activity_report(
        visible_user_ids=visible_ids,
        assigned_to_user_id=clean_rep_id,
        activity_type=clean_type,
        status=clean_status,
        start_date=start_dt,
        end_date=end_dt,
        sort_by=clean_sort_by,
        sort_order=clean_sort_order,
        limit=1,
        offset=0,
    )

    page, per_page, total_pages, offset = calculate_pagination(total_count, page, per_page)

    records, _ = report_repository.get_user_activity_report(
        visible_user_ids=visible_ids,
        assigned_to_user_id=clean_rep_id,
        activity_type=clean_type,
        status=clean_status,
        start_date=start_dt,
        end_date=end_dt,
        sort_by=clean_sort_by,
        sort_order=clean_sort_order,
        limit=per_page,
        offset=offset,
    )

    return {
        "records": records,
        "total_count": total_count,
        "current_page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "activity_type": clean_type or "",
        "status": clean_status or "",
        "start_date": start_str or "",
        "end_date": end_str or "",
        "assigned_to": str(clean_rep_id) if clean_rep_id and clean_rep_id > 0 else "",
        "sort_by": clean_sort_by,
        "sort_order": clean_sort_order,
    }


# =============================================================================
# 8. AUDIT REPORT (ADMIN ONLY)
# =============================================================================

def get_audit_report_data(
    user_id=None,
    entity_name=None,
    action=None,
    start_str=None,
    end_str=None,
    sort_by="created_date",
    sort_order="DESC",
    page=1,
    per_page=20,
):
    """
    Orchestrate immutable audit log reporting for Administrators (Decision 99 #4).
    Sanitizes any accidentally sensitive values before template display.
    """
    start_dt, end_dt = parse_report_date_range(start_str, end_str)

    clean_sort_by = sort_by if sort_by in report_repository.AUDIT_SORT_COLUMNS else "created_date"
    clean_sort_order = "DESC" if str(sort_order).upper() == "DESC" else "ASC"
    clean_entity = entity_name.strip() if entity_name and entity_name.strip() else None
    clean_action = action.strip() if action and action.strip() else None

    clean_user_id = None
    if user_id:
        try:
            clean_user_id = int(user_id)
        except ValueError:
            clean_user_id = None

    _, total_count = report_repository.get_audit_report(
        user_id=clean_user_id,
        entity_name=clean_entity,
        action=clean_action,
        start_date=start_dt,
        end_date=end_dt,
        sort_by=clean_sort_by,
        sort_order=clean_sort_order,
        limit=1,
        offset=0,
    )

    page, per_page, total_pages, offset = calculate_pagination(total_count, page, per_page)

    records, _ = report_repository.get_audit_report(
        user_id=clean_user_id,
        entity_name=clean_entity,
        action=clean_action,
        start_date=start_dt,
        end_date=end_dt,
        sort_by=clean_sort_by,
        sort_order=clean_sort_order,
        limit=per_page,
        offset=offset,
    )

    return {
        "records": records,
        "total_count": total_count,
        "current_page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "user_id": str(clean_user_id) if clean_user_id else "",
        "entity_name": clean_entity or "",
        "action": clean_action or "",
        "start_date": start_str or "",
        "end_date": end_str or "",
        "sort_by": clean_sort_by,
        "sort_order": clean_sort_order,
    }
