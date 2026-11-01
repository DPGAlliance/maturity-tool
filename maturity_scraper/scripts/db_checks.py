import argparse
import csv
import sys
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


def _format_value(value) -> str:
    if value is None:
        return ""
    return str(value)


def _print_table(headers, rows, output_format: str) -> None:
    if not rows:
        print("(no rows)")
        return

    formatted_rows = [[_format_value(value) for value in row] for row in rows]

    if output_format == "csv":
        writer = csv.writer(sys.stdout)
        writer.writerow(headers)
        writer.writerows(formatted_rows)
        return

    if output_format == "markdown":
        markdown_headers = [header.replace("|", r"\|") for header in headers]
        print("| " + " | ".join(markdown_headers) + " |")
        print("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in formatted_rows:
            escaped = [value.replace("|", r"\|").replace("\n", "<br>") for value in row]
            print("| " + " | ".join(escaped) + " |")
        return

    print("\t".join(headers))
    for row in formatted_rows:
        print("\t".join(row))


def _print_rows(result, output_format: str) -> None:
    rows = result.fetchall()
    if not rows:
        print("(no rows)")
        return
    headers = result.keys()
    _print_table(headers, rows, output_format)


def run_sql(engine, sql: str, output_format: str) -> None:
    with engine.begin() as conn:
        result = conn.execute(text(sql))
        if result.returns_rows:
            _print_rows(result, output_format)
        else:
            print(f"Rows affected: {result.rowcount}")


def read_sql_file(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as file:
        return file.read()


def list_tables(engine, output_format: str) -> None:
    sql = "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name"
    run_sql(engine, sql, output_format)


def list_owners(engine, output_format: str) -> None:
    run_sql(engine, "SELECT DISTINCT owner FROM repos ORDER BY owner", output_format)


def list_repos(engine, owner: str | None, limit: int, output_format: str) -> None:
    if owner:
        sql = "SELECT owner, name FROM repos WHERE owner = :owner ORDER BY owner, name LIMIT :limit"
        with engine.begin() as conn:
            result = conn.execute(text(sql), {"owner": owner, "limit": limit})
            _print_rows(result, output_format)
        return
    sql = "SELECT owner, name FROM repos ORDER BY owner, name LIMIT :limit"
    with engine.begin() as conn:
        result = conn.execute(text(sql), {"limit": limit})
        _print_rows(result, output_format)


def table_counts(engine, tables: list[str], output_format: str) -> None:
    rows = []
    with engine.begin() as conn:
        for table in tables:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = result.scalar_one()
            rows.append((table, count))
    _print_table(["table", "count"], rows, output_format)


def reset_all(engine, tables: list[str]) -> None:
    table_list = ", ".join(tables)
    sql = f"TRUNCATE {table_list} RESTART IDENTITY CASCADE"
    run_sql(engine, sql, "tsv")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run basic DB checks against the maturity tool database.")
    parser.add_argument("--sql", action="append", help="Run a raw SQL statement (can be used multiple times)")
    parser.add_argument(
        "--sql-file",
        action="append",
        help="Run SQL from a file, or use '-' to read from stdin (can be used multiple times)",
    )
    parser.add_argument("--list-owners", action="store_true", help="List distinct repo owners")
    parser.add_argument("--list-repos", action="store_true", help="List repos (optionally filter by --owner)")
    parser.add_argument("--owner", help="Owner filter for --list-repos")
    parser.add_argument("--limit", type=int, default=100, help="Limit for list operations (default: 100)")
    parser.add_argument(
        "--format",
        choices=["tsv", "csv", "markdown"],
        default="tsv",
        help="Output format for row results (default: tsv)",
    )
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
    engine = get_engine()

    if args.reset_all:
        if args.confirm_reset != "RESET":
            raise SystemExit("--reset-all requires --confirm-reset RESET")
        reset_all(engine, DEFAULT_TABLES)
        return

    if args.tables:
        list_tables(engine, args.format)

    if args.list_owners:
        list_owners(engine, args.format)

    if args.list_repos:
        list_repos(engine, args.owner, args.limit, args.format)

    if args.counts:
        table_counts(engine, DEFAULT_TABLES, args.format)

    if args.sql:
        for statement in args.sql:
            run_sql(engine, statement, args.format)

    if args.sql_file:
        for path in args.sql_file:
            run_sql(engine, read_sql_file(path), args.format)


if __name__ == "__main__":
    main()
