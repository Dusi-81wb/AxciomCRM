"""
Database connection and schema management for AcxiomCRM.

Provides psycopg2 connection management using Flask application context (g)
and utilities to execute initialization and seed scripts.
In accordance with Phase 1 requirements:
- Uses raw psycopg2 with parameterized SQL (no ORM, no SQLAlchemy, no migrations framework).
- Closes connections automatically at the end of each request via Flask context teardown.
- Exposes init_db() and seed_db() functions and Flask CLI commands for database setup.
"""

import os
import click
import psycopg2
from flask import current_app, g


def get_db_connection(db_url=None):
    """
    Get or establish a PostgreSQL database connection for the current request.

    The connection is stored on Flask's 'g' context object so that multiple operations
    within the same request lifecycle reuse the same database connection.
    If db_url is provided and we are outside an application context, returns a direct connection.
    """
    if db_url:
        return psycopg2.connect(db_url)

    if "db_conn" not in g:
        url = current_app.config.get("DATABASE_URL")
        if not url:
            raise ValueError("DATABASE_URL is not configured in application settings.")
        g.db_conn = psycopg2.connect(url)
    return g.db_conn


def close_db_connection(exception=None):
    """
    Close the current request's database connection if one was opened.

    Registered with Flask's application context teardown to prevent connection leaks.
    """
    db_conn = g.pop("db_conn", None)
    if db_conn is not None and not db_conn.closed:
        db_conn.close()


def execute_sql_file(file_path, db_url=None):
    """
    Execute a raw SQL script file against PostgreSQL using psycopg2.

    :param file_path: Path to the .sql file to execute.
    :param db_url: Optional explicit database URL. If None, uses application context connection.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"SQL script not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        sql = f.read()

    if db_url:
        conn = psycopg2.connect(db_url)
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
        finally:
            conn.close()
    else:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


def init_db(schema_file="sql/schema.sql", db_url=None):
    """
    Execute schema.sql to create tables, constraints, indexes, and triggers.
    """
    execute_sql_file(schema_file, db_url=db_url)


def seed_db(seed_file="sql/seed.sql", db_url=None):
    """
    Execute seed.sql to populate roles, demo users, and sample CRM records.
    """
    execute_sql_file(seed_file, db_url=db_url)


@click.command("init-db")
def init_db_command():
    """Flask CLI command to initialize database schema."""
    init_db()
    click.echo("Initialized database schema.")


@click.command("seed-db")
def seed_db_command():
    """Flask CLI command to insert demo seed data."""
    seed_db()
    click.echo("Seeded database with demonstration records.")


def init_app(app):
    """
    Register database connection lifecycle handlers and CLI commands with the Flask application.
    """
    app.teardown_appcontext(close_db_connection)
    app.teardown_request(close_db_connection)
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_db_command)

