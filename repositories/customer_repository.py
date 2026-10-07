"""
Customer Repository for AcxiomCRM.

Encapsulates all SQL data access for the 'customers' table using raw psycopg2.
In accordance with MASTER_BLUEPRINT.md and SPECIFICATION_NOTES.md:
- Strictly parameterized SQL with %s placeholders.
- Scope and ownership enforcement INSIDE SQL queries using visible_user_ids.
- Whitelist sorting and filtering.
- Transaction boundaries controlled by optional 'conn' parameter.
"""

from database import get_db_connection

# Whitelist allowed sort columns to prevent SQL injection
ALLOWED_SORT_COLUMNS = {
    "customer_id": "c.customer_id",
    "customer_code": "c.customer_code",
    "customer_name": "c.customer_name",
    "email": "c.email",
    "phone": "c.phone",
    "company_name": "c.company_name",
    "status": "c.status",
    "created_date": "c.created_date",
}

ALLOWED_SORT_ORDERS = {
    "asc": "ASC",
    "desc": "DESC",
}


def _row_to_dict(cursor, row):
    """Convert a database row tuple into a dictionary using cursor descriptions."""
    if row is None:
        return None
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


def get_next_customer_code(conn=None):
    """
    Generate the next sequential customer code (e.g. 'CUST-005').
    Guarantees uniqueness against existing records.
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        # Determine highest existing customer_id or count
        cur.execute("SELECT COALESCE(MAX(customer_id), 0) + 1 FROM customers;")
        next_id = cur.fetchone()[0]

        while True:
            candidate_code = f"CUST-{next_id:03d}"
            cur.execute("SELECT 1 FROM customers WHERE customer_code = %s;", (candidate_code,))
            if cur.fetchone() is None:
                return candidate_code
            next_id += 1


def find_by_id(customer_id, conn=None):
    """
    Retrieve a customer by primary key ID, joined with assigned and creator usernames.
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            SELECT c.customer_id, c.customer_code, c.customer_name, c.email, c.phone,
                   c.company_name, c.address, c.city, c.state, c.status,
                   c.assigned_to, c.created_date, c.modified_date, c.created_by,
                   u.username AS assigned_to_name,
                   cb.username AS created_by_name
            FROM customers c
            LEFT JOIN users u ON c.assigned_to = u.user_id
            LEFT JOIN users cb ON c.created_by = cb.user_id
            WHERE c.customer_id = %s;
        """, (customer_id,))
        row = cur.fetchone()
        return _row_to_dict(cur, row)


def find_by_code(customer_code, conn=None):
    """Retrieve a customer by unique CustomerCode."""
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("SELECT * FROM customers WHERE customer_code = %s;", (customer_code,))
        row = cur.fetchone()
        return _row_to_dict(cur, row)


def find_by_email(email, exclude_id=None, conn=None):
    """
    Search for customer by email (case-insensitive) across both Active and Inactive records.
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        if exclude_id is not None:
            cur.execute("""
                SELECT * FROM customers 
                WHERE LOWER(email) = LOWER(%s) AND customer_id != %s;
            """, (email.strip(), exclude_id))
        else:
            cur.execute("""
                SELECT * FROM customers 
                WHERE LOWER(email) = LOWER(%s);
            """, (email.strip(),))
        row = cur.fetchone()
        return _row_to_dict(cur, row)


def find_by_phone(phone, exclude_id=None, conn=None):
    """
    Search for customer by phone across both Active and Inactive records.
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        if exclude_id is not None:
            cur.execute("""
                SELECT * FROM customers 
                WHERE phone = %s AND customer_id != %s;
            """, (phone.strip(), exclude_id))
        else:
            cur.execute("""
                SELECT * FROM customers 
                WHERE phone = %s;
            """, (phone.strip(),))
        row = cur.fetchone()
        return _row_to_dict(cur, row)


def create_customer(
    customer_code,
    customer_name,
    email,
    phone,
    company_name=None,
    address=None,
    city=None,
    state=None,
    status="Active",
    assigned_to=None,
    created_by=None,
    conn=None
):
    """
    Insert a new customer record using parameterized SQL.
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO customers (
                customer_code, customer_name, email, phone, company_name,
                address, city, state, status, assigned_to, created_by
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING customer_id, customer_code, customer_name, email, phone,
                      company_name, address, city, state, status, assigned_to,
                      created_date, modified_date, created_by;
        """, (
            customer_code, customer_name, email, phone, company_name,
            address, city, state, status, assigned_to, created_by
        ))
        row = cur.fetchone()
        record = _row_to_dict(cur, row)

    if conn is None:
        connection.commit()

    return record


def update_customer(
    customer_id,
    customer_name,
    email,
    phone,
    company_name=None,
    address=None,
    city=None,
    state=None,
    status=None,
    assigned_to=None,
    conn=None
):
    """
    Update an existing customer's attributes.
    Preserves customer_id, customer_code, created_date, and created_by.
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            UPDATE customers
            SET customer_name = %s,
                email = %s,
                phone = %s,
                company_name = %s,
                address = %s,
                city = %s,
                state = %s,
                status = COALESCE(%s, status),
                assigned_to = %s,
                modified_date = CURRENT_TIMESTAMP
            WHERE customer_id = %s
            RETURNING customer_id, customer_code, customer_name, email, phone,
                      company_name, address, city, state, status, assigned_to,
                      created_date, modified_date, created_by;
        """, (
            customer_name, email, phone, company_name, address, city,
            state, status, assigned_to, customer_id
        ))
        row = cur.fetchone()
        record = _row_to_dict(cur, row)

    if conn is None:
        connection.commit()

    return record


def update_status(customer_id, status, conn=None):
    """Update customer status (Active or Inactive)."""
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            UPDATE customers
            SET status = %s,
                modified_date = CURRENT_TIMESTAMP
            WHERE customer_id = %s
            RETURNING customer_id, customer_code, customer_name, status, modified_date;
        """, (status, customer_id))
        row = cur.fetchone()
        record = _row_to_dict(cur, row)

    if conn is None:
        connection.commit()

    return record


def find_customers(
    visible_user_ids=None,
    search=None,
    status=None,
    sort_by="created_date",
    sort_order="DESC",
    limit=50,
    offset=0,
    conn=None
):
    """
    Search and filter customers with database-level ownership/scope enforcement.

    Scope rules:
    - visible_user_ids is None: Admin/Manager scope (unrestricted).
    - visible_user_ids is list: Sales Executive scope (WHERE c.assigned_to = ANY(%s)).
    - visible_user_ids == []: Unauthenticated/inactive (WHERE 1 = 0).
    """
    connection = conn or get_db_connection()

    sort_col = ALLOWED_SORT_COLUMNS.get(sort_by.lower(), "c.created_date")
    order_dir = ALLOWED_SORT_ORDERS.get(sort_order.lower(), "DESC")

    conditions = []
    params = []

    # 1. Server-Side Scope / Ownership Enforcement
    if visible_user_ids is not None:
        if len(visible_user_ids) == 0:
            conditions.append("1 = 0")
        else:
            conditions.append("c.assigned_to = ANY(%s)")
            params.append(visible_user_ids)

    # 2. Status Filter
    if status:
        conditions.append("c.status = %s")
        params.append(status)

    # 3. Search Filter across Name, Email, Phone, Company
    if search and search.strip():
        term = f"%{search.strip()}%"
        conditions.append("""(
            LOWER(c.customer_name) LIKE LOWER(%s)
            OR LOWER(c.email) LIKE LOWER(%s)
            OR c.phone LIKE %s
            OR LOWER(c.company_name) LIKE LOWER(%s)
        )""")
        params.extend([term, term, term, term])

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT c.customer_id, c.customer_code, c.customer_name, c.email, c.phone,
               c.company_name, c.address, c.city, c.state, c.status,
               c.assigned_to, c.created_date, c.modified_date, c.created_by,
               u.username AS assigned_to_name,
               cb.username AS created_by_name
        FROM customers c
        LEFT JOIN users u ON c.assigned_to = u.user_id
        LEFT JOIN users cb ON c.created_by = cb.user_id
        {where_clause}
        ORDER BY {sort_col} {order_dir}
        LIMIT %s OFFSET %s;
    """
    params.extend([limit, offset])

    with connection.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
        return [_row_to_dict(cur, r) for r in rows]


def count_customers(visible_user_ids=None, search=None, status=None, conn=None):
    """
    Count total customers matching scope and search parameters for pagination.
    """
    connection = conn or get_db_connection()

    conditions = []
    params = []

    if visible_user_ids is not None:
        if len(visible_user_ids) == 0:
            conditions.append("1 = 0")
        else:
            conditions.append("c.assigned_to = ANY(%s)")
            params.append(visible_user_ids)

    if status:
        conditions.append("c.status = %s")
        params.append(status)

    if search and search.strip():
        term = f"%{search.strip()}%"
        conditions.append("""(
            LOWER(c.customer_name) LIKE LOWER(%s)
            OR LOWER(c.email) LIKE LOWER(%s)
            OR c.phone LIKE %s
            OR LOWER(c.company_name) LIKE LOWER(%s)
        )""")
        params.extend([term, term, term, term])

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"SELECT COUNT(*) FROM customers c {where_clause};"

    with connection.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]


def get_active_sales_executives(conn=None):
    """
    Retrieve active Sales Executives for assigning customers.
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            SELECT user_id, username, email 
            FROM users 
            WHERE role_id = 3 AND is_active = TRUE 
            ORDER BY username ASC;
        """)
        rows = cur.fetchall()
        return [_row_to_dict(cur, r) for r in rows]
