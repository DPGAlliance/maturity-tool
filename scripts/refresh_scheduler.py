import logging
import os
import subprocess
import time
from collections import deque
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from maturity_tools.github_call import GitHubRateLimitError
from storage.db import get_session, init_db
from storage.logging_config import configure_logging
from storage.secrets import get_secret


logger = logging.getLogger("refresh_scheduler")
status_logger = logging.getLogger("refresh.status")


def _format_duration(seconds: float) -> str:
    total_seconds = int(round(seconds))
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def _parse_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_owners(value: str | None) -> list[str]:
    if not value:
        return []
    owners = [part.strip() for part in value.split(",")]
    return [o for o in owners if o]


def _sleep_for_rate_limit(exc: GitHubRateLimitError, *, owner: str, repo: str) -> None:
    sleep_seconds = exc.sleep_seconds()
    reset_at = exc.reset_at.isoformat() if exc.reset_at else None
    logger.warning(
        "GitHub rate limit paused refresh for %s/%s at stage=%s; sleeping %s until %s",
        owner,
        repo,
        exc.request_name or "unknown",
        _format_duration(sleep_seconds),
        reset_at,
    )
    status_logger.info(
        "owner=%s repo=%s stage=%s status=rate_limited sleep=%s reset_at=%s remaining=%s",
        owner,
        repo,
        exc.request_name or "unknown",
        _format_duration(sleep_seconds),
        reset_at,
        exc.remaining,
    )
    time.sleep(sleep_seconds)


def _run_logged_subprocess(cmd: list[str], *, owner: str) -> None:
    recent_lines: deque[str] = deque(maxlen=50)
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    try:
        for line in process.stdout:
            rendered = line.rstrip()
            recent_lines.append(rendered)
            logger.info("[summarize:%s] %s", owner, rendered)
    finally:
        process.stdout.close()
    returncode = process.wait()
    if returncode != 0:
        logger.error(
            "Summarization failed for %s (exit=%s). Last output:\n%s",
            owner,
            returncode,
            "\n".join(recent_lines) or "(no output)",
        )
        raise subprocess.CalledProcessError(returncode, cmd)


def run_cycle(*, token: str, owners: list[str], repo_override: str | None, force_refresh: bool) -> None:
    import refresh_cache

    session = get_session()
    try:
        for owner in owners:
            while True:
                try:
                    repos = [repo_override] if repo_override else refresh_cache.fetch_repos_for_owner(owner, token)
                    break
                except GitHubRateLimitError as exc:
                    session.rollback()
                    session.close()
                    _sleep_for_rate_limit(exc, owner=owner, repo="*")
                    session = get_session()
            for repo in repos:
                while True:
                    logger.info(f"Refreshing {owner}/{repo} (force_refresh={force_refresh})")
                    try:
                        refresh_cache.collect_for_repo(
                            session=session,
                            owner=owner,
                            repo=repo,
                            token=token,
                            force_refresh=force_refresh,
                        )
                        break
                    except GitHubRateLimitError as exc:
                        session.rollback()
                        session.close()
                        _sleep_for_rate_limit(exc, owner=owner, repo=repo)
                        session = get_session()
                    except Exception:
                        # Keep going so a single repo doesn't block the whole cycle (and summaries).
                        session.rollback()
                        logger.exception("Refresh failed for %s/%s; continuing", owner, repo)
                        session.close()
                        session = get_session()
                        break
    finally:
        session.close()


def run_summaries(*, owners: list[str]) -> None:
    base_url = os.getenv("SUMMARY_BASE_URL", "http://api:8000").rstrip("/")
    model = os.getenv("SUMMARY_MODEL")
    history = os.getenv("SUMMARY_HISTORY")
    max_age_days = os.getenv("SUMMARY_MAX_AGE_DAYS")
    force = _parse_bool(os.getenv("SUMMARY_FORCE"))
    no_store = _parse_bool(os.getenv("SUMMARY_NO_STORE"))

    for owner in owners:
        cmd: list[str] = [
            "python",
            "scripts/summarize.py",
            "--owner",
            owner,
            "--base-url",
            base_url,
        ]
        if model:
            cmd += ["--model", model]
        if history:
            cmd += ["--history", str(int(history))]
        if max_age_days:
            cmd += ["--max-age-days", str(int(max_age_days))]
        if force:
            cmd += ["--force"]
        if no_store:
            cmd += ["--no_store"]

        logger.info(f"Summarizing owner {owner} via {base_url}")
        try:
            _run_logged_subprocess(cmd, owner=owner)
        except subprocess.CalledProcessError as exc:
            logger.error(
                "Summarization failed for %s (exit=%s). Continuing.",
                owner,
                exc.returncode,
            )


def main() -> None:
    configure_logging()

    # Keep local-dev behavior: load repo-root .env if present.
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    load_dotenv(os.path.join(repo_root, ".env"))

    token = get_secret("GITHUB_TOKEN", required=True)

    # Prefer day-based interval (human-friendly). Keep seconds as an override for compatibility.
    interval_days_raw = os.getenv("REFRESH_INTERVAL_DAYS")
    interval_seconds_raw = os.getenv("REFRESH_INTERVAL_SECONDS")
    if interval_days_raw is not None and interval_days_raw.strip() != "":
        interval_days = float(interval_days_raw)
        if interval_days <= 0:
            raise SystemExit("REFRESH_INTERVAL_DAYS must be > 0")
        interval_seconds = int(interval_days * 24 * 60 * 60)
    elif interval_seconds_raw is not None and interval_seconds_raw.strip() != "":
        interval_seconds = int(interval_seconds_raw)
    else:
        interval_seconds = 7 * 24 * 60 * 60
    repo_override = os.getenv("REFRESH_REPO") or None
    force_refresh = _parse_bool(os.getenv("FORCE_REFRESH"))
    run_summaries_after_refresh = _parse_bool(os.getenv("RUN_SUMMARIES", "true"))

    owners = _parse_owners(os.getenv("REFRESH_OWNERS"))
    if not owners:
        try:
            from data_viewer.data_viewer.distinguished_owners import DISTINGUISHED_OWNERS

            owners = list(DISTINGUISHED_OWNERS)
        except Exception:
            owners = []

    if not owners:
        raise SystemExit(
            "No owners configured. Set REFRESH_OWNERS=owner1,owner2 (recommended) or ensure DISTINGUISHED_OWNERS is importable."
        )

    init_db()

    logger.info(
        f"Starting refresh scheduler (owners={owners}, repo_override={repo_override}, interval_seconds={interval_seconds}, force_refresh={force_refresh})"
    )

    cycle = 0
    while True:
        cycle += 1
        start = time.time()
        logger.info("Starting refresh cycle %s", cycle)
        status_logger.info("owner=* repo=* stage=cycle_start status=begin cycle=%s", cycle)
        try:
            run_cycle(
                token=token,
                owners=owners,
                repo_override=repo_override,
                force_refresh=force_refresh,
            )

            if run_summaries_after_refresh:
                run_summaries(owners=owners)
        except Exception:
            logger.exception("Refresh cycle failed")

        elapsed = time.time() - start
        sleep_for = max(0, interval_seconds - int(elapsed))
        next_start = datetime.now(timezone.utc) + timedelta(seconds=sleep_for)
        logger.info(
            "Cycle %s complete in %s; sleeping %s (next start %s)",
            cycle,
            _format_duration(elapsed),
            _format_duration(sleep_for),
            next_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        status_logger.info(
            "owner=* repo=* stage=cycle_sleep status=next_start at=%s in=%s",
            next_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            _format_duration(sleep_for),
        )
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
