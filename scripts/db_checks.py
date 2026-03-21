import argparse
import os

from sqlalchemy import text

from storage.db import get_engine


DEFAULT_TABLES = [
    "repos",
    "runs",
    "fetch_log",
    "commits",
    "branches",
    "releases",
    "issues",
    "pull_requests",
    "metrics",
    "summaries",
]


def _print_rows(result) -> None:
    rows = result.fetchall()
    if not rows:
        print("(no rows)")
        return
    headers = result.keys()
    print("\t".join(headers))
    for row in rows:
        print("\t".join(str(value) for value in row))


def run_sql(engine, sql: str) -> None:
    with engine.begin() as conn:
        result = conn.execute(text(sql))
        if result.returns_rows:
            _print_rows(result)
        else:
            print(f"Rows affected: {result.rowcount}")


def list_tables(engine) -> None:
    dialect = engine.dialect.name
    if dialect == "sqlite":
        sql = "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    else:
        sql = "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name"
    run_sql(engine, sql)


def list_owners(engine) -> None:
    run_sql(engine, "SELECT DISTINCT owner FROM repos ORDER BY owner")


def list_repos(engine, owner: str | None, limit: int) -> None:
    if owner:
        sql = "SELECT owner, name FROM repos WHERE owner = :owner ORDER BY owner, name LIMIT :limit"
        with engine.begin() as conn:
            result = conn.execute(text(sql), {"owner": owner, "limit": limit})
            _print_rows(result)
        return
    sql = "SELECT owner, name FROM repos ORDER BY owner, name LIMIT :limit"
    with engine.begin() as conn:
        result = conn.execute(text(sql), {"limit": limit})
        _print_rows(result)


def table_counts(engine, tables: list[str]) -> None:
    with engine.begin() as conn:
        for table in tables:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = result.scalar_one()
            print(f"{table}\t{count}")


def reset_all(engine, tables: list[str]) -> None:
    dialect = engine.dialect.name
    if dialect == "sqlite":
        with engine.begin() as conn:
            for table in tables:
                conn.execute(text(f"DELETE FROM {table}"))
        print("SQLite tables cleared.")
        return

    table_list = ", ".join(tables)
    sql = f"TRUNCATE {table_list} RESTART IDENTITY CASCADE"
    run_sql(engine, sql)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run basic DB checks against the maturity tool database.")
    parser.add_argument("--sql", action="append", help="Run a raw SQL statement (can be used multiple times)")
    parser.add_argument("--list-owners", action="store_true", help="List distinct repo owners")
    parser.add_argument("--list-repos", action="store_true", help="List repos (optionally filter by --owner)")
    parser.add_argument("--owner", help="Owner filter for --list-repos")
    parser.add_argument("--limit", type=int, default=100, help="Limit for list operations (default: 100)")
    parser.add_argument("--counts", action="store_true", help="Show row counts for default tables")
    parser.add_argument("--tables", action="store_true", help="List database tables")
    parser.add_argument("--reset-all", action="store_true", help="Truncate all default tables (DANGEROUS)")
    parser.add_argument(
        "--confirm-reset",
        help="Required with --reset-all. Must equal RESET to proceed.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    engine = get_engine(os.getenv("DATABASE_URL"))

    if args.reset_all:
        if args.confirm_reset != "RESET":
            raise SystemExit("--reset-all requires --confirm-reset RESET")
        reset_all(engine, DEFAULT_TABLES)
        return

    if args.tables:
        list_tables(engine)

    if args.list_owners:
        list_owners(engine)

    if args.list_repos:
        list_repos(engine, args.owner, args.limit)

    if args.counts:
        table_counts(engine, DEFAULT_TABLES)

    if args.sql:
        for statement in args.sql:
            run_sql(engine, statement)


if __name__ == "__main__":
    main()
