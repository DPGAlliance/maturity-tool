"""This module contains functions to interact with the GitHub API."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import os
import threading
import time
import requests
from typing import Any, Dict, Optional
from maturity_tools.queries import branches_query, commits_query, releases_query, issues_query, pr_query
import pandas as pd


logger = logging.getLogger("maturity_tools.github_call")

GITHUB_API_HEARTBEAT_SECONDS = float(os.getenv("GITHUB_API_HEARTBEAT_SECONDS", "60"))


@dataclass
class GitHubRateLimitError(Exception):
    message: str
    status_code: int | None
    owner: str | None
    repo: str | None
    request_name: str | None
    retry_after_seconds: int | None
    reset_at: datetime | None
    remaining: int | None
    resource: str | None
    request_id: str | None
    response_body_snippet: str | None

    def sleep_seconds(self) -> int:
        if self.retry_after_seconds is not None and self.retry_after_seconds > 0:
            return self.retry_after_seconds
        if self.reset_at is not None:
            return max(1, int((self.reset_at - datetime.now(timezone.utc)).total_seconds()) + 1)
        return 60

    def __str__(self) -> str:
        location = "/".join(part for part in [self.owner, self.repo] if part)
        request = self.request_name or "unknown"
        parts = [f"GitHub rate limit hit during {request}"]
        if location:
            parts.append(f"for {location}")
        if self.status_code is not None:
            parts.append(f"(status={self.status_code})")
        parts.append(f": {self.message}")
        return " ".join(parts)


def _header_int(headers, name: str) -> int | None:
    value = headers.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _reset_at_from_headers(headers) -> datetime | None:
    reset_epoch = _header_int(headers, "x-ratelimit-reset")
    if reset_epoch is None:
        return None
    try:
        return datetime.fromtimestamp(reset_epoch, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _response_text_snippet(response: requests.Response | None, limit: int = 500) -> str | None:
    if response is None:
        return None
    text = (response.text or "").strip()
    if not text:
        return None
    return text[:limit]


def _is_rate_limit_response(response: requests.Response, data: dict | None = None) -> bool:
    headers = response.headers
    remaining = _header_int(headers, "x-ratelimit-remaining")
    retry_after = _header_int(headers, "retry-after")
    if remaining == 0 or retry_after is not None:
        return True

    body_text = _response_text_snippet(response) or ""
    if "rate limit" in body_text.lower():
        return True

    if data and isinstance(data.get("errors"), list):
        for err in data["errors"]:
            if "rate limit" in str(err.get("message", "")).lower():
                return True
    return False


def _build_rate_limit_error(
    response: requests.Response,
    *,
    variables: dict,
    request_name: str | None,
    data: dict | None = None,
) -> GitHubRateLimitError:
    headers = response.headers
    owner = variables.get("owner")
    repo = variables.get("repo")
    remaining = _header_int(headers, "x-ratelimit-remaining")
    retry_after = _header_int(headers, "retry-after")
    reset_at = _reset_at_from_headers(headers)
    request_id = headers.get("x-github-request-id")
    resource = headers.get("x-ratelimit-resource")
    message = "GitHub API rate limit exceeded"
    if data and isinstance(data.get("errors"), list) and data["errors"]:
        message = "; ".join(str(err.get("message", message)) for err in data["errors"])
    else:
        snippet = _response_text_snippet(response)
        if snippet:
            message = snippet

    error = GitHubRateLimitError(
        message=message,
        status_code=response.status_code,
        owner=owner,
        repo=repo,
        request_name=request_name,
        retry_after_seconds=retry_after,
        reset_at=reset_at,
        remaining=remaining,
        resource=resource,
        request_id=request_id,
        response_body_snippet=_response_text_snippet(response),
    )
    logger.warning(
        "GitHub rate limit hit request=%s owner=%s repo=%s status=%s remaining=%s retry_after=%s reset_at=%s resource=%s request_id=%s body=%s",
        request_name or "unknown",
        owner,
        repo,
        response.status_code,
        remaining,
        retry_after,
        reset_at.isoformat() if reset_at else None,
        resource,
        request_id,
        error.response_body_snippet,
    )
    return error


def _start_request_heartbeat(request_name: str | None, variables: dict):
    if GITHUB_API_HEARTBEAT_SECONDS <= 0:
        return None, None

    owner = variables.get("owner")
    repo = variables.get("repo")
    stop_event = threading.Event()
    started_at = time.monotonic()

    def heartbeat() -> None:
        while not stop_event.wait(GITHUB_API_HEARTBEAT_SECONDS):
            elapsed_seconds = int(time.monotonic() - started_at)
            logger.info(
                "Still waiting on GitHub request=%s owner=%s repo=%s elapsed=%ss",
                request_name or "unknown",
                owner,
                repo,
                elapsed_seconds,
            )

    thread = threading.Thread(target=heartbeat, name="github-api-heartbeat", daemon=True)
    thread.start()
    return stop_event, thread


def _stop_request_heartbeat(stop_event, thread) -> None:
    if stop_event is None:
        return
    stop_event.set()
    if thread is not None:
        thread.join(timeout=0.1)



def github_api_call(
    query: str,
    variables: dict,
    GITHUB_TOKEN,
    *,
    request_name: str | None = None,
):
    """
    Make a call to the github api.
    Args:
        query (str): The graphql query to make.
        variables (dict): The variables to pass to the query.
        GITHUB_TOKEN (str): The github token to use.

    Returns:
        Response of the github api.
    """
    url = 'https://api.github.com/graphql'
    headers = {
        'Authorization': f'bearer {GITHUB_TOKEN}',
        'Content-Type': 'application/json'
    }
    heartbeat_stop, heartbeat_thread = _start_request_heartbeat(request_name, variables)

    try:
        response = requests.post(
            url,
            headers=headers,
            json={'query': query, 'variables': variables},
        )
        if response.status_code >= 400:
            if _is_rate_limit_response(response):
                raise _build_rate_limit_error(
                    response,
                    variables=variables,
                    request_name=request_name,
                )
            logger.error(
                "GitHub API HTTP error request=%s owner=%s repo=%s status=%s request_id=%s body=%s",
                request_name or "unknown",
                variables.get("owner"),
                variables.get("repo"),
                response.status_code,
                response.headers.get("x-github-request-id"),
                _response_text_snippet(response),
            )
            response.raise_for_status() # Raise an exception for bad status codes
        data = response.json()

        if 'errors' in data:
            if _is_rate_limit_response(response, data):
                raise _build_rate_limit_error(
                    response,
                    variables=variables,
                    request_name=request_name,
                    data=data,
                )
            logger.error(
                "GraphQL errors request=%s owner=%s repo=%s errors=%s",
                request_name or "unknown",
                variables.get("owner"),
                variables.get("repo"),
                data["errors"],
            )
            return None
    except GitHubRateLimitError:
        raise
    except Exception:
        raise # we only handle if it makes sense.
    finally:
        _stop_request_heartbeat(heartbeat_stop, heartbeat_thread)
    return data

def process_branches(variables, GITHUB_TOKEN) -> Optional[pd.DataFrame]:
    all_branches_data = []
    after_cursor_branches = None
    has_next_page_branches = True
    variables['first_branches'] = 100  # Number of branches to fetch per page
    variables['after_branches'] = None  # Cursor for pagination

    while has_next_page_branches:
        variables.update({"after_branches": after_cursor_branches})
        # print("Fetching branches with cursor:", after_cursor_branches) # Optional: to show progress
        data = github_api_call(branches_query, variables, GITHUB_TOKEN, request_name="branches")

        if data and 'data' in data and data['data'] and 'repository' in data['data'] and data['data']['repository'] and 'refs' in data['data']['repository']:
            branches_data = data['data']['repository']['refs']['edges']

            # Extract required information from each branch and append to the list
            for branch_edge in branches_data:
                branch_node = branch_edge['node']
                branch_name = branch_node['name']
                commit_count = branch_node['target']['history']['totalCount'] if branch_node['target'] and 'history' in branch_node['target'] else None
                last_commit_date = branch_node['target']['authoredDate'] if branch_node['target'] and 'authoredDate' in branch_node['target'] else None
                head_oid = branch_node['target']['oid'] if branch_node['target'] and 'oid' in branch_node['target'] else None

                all_branches_data.append({
                    'branch_name': branch_name,
                    'total_commits': commit_count,
                    'last_commit_date': last_commit_date,
                    'head_oid': head_oid,
                })

            page_info_branches = data['data']['repository']['refs']['pageInfo']
            after_cursor_branches = page_info_branches['endCursor']
            has_next_page_branches = page_info_branches['hasNextPage']
        else:
            logger.error("Could not retrieve branch data or unexpected data structure")
            break

    logger.info("Fetched details for %s branches", len(all_branches_data))

    # Create a pandas DataFrame from the collected data
    df_branches = pd.DataFrame(all_branches_data)

    # Convert 'last_commit_date' to datetime objects
    if not df_branches.empty:
        df_branches['last_commit_date'] = pd.to_datetime(df_branches['last_commit_date'])
    return df_branches


def _extract_commit_rows(commit_edges) -> list[dict]:
    commit_data_list = []
    for commit in commit_edges:
        commit_node = commit['node']
        commit_data = {
            'oid': commit_node['oid'],
            'authoredDate': commit_node['authoredDate'],
            'messageHeadline': commit_node['messageHeadline'],
            'additions': commit_node['additions'],
            'deletions': commit_node['deletions'],
            # these may be redundant
            'author_name': commit_node['author']['name'],
            # 'author_email': commit_node['author']['email'],
            'author_login': commit_node['author']['user']['login'] if commit_node['author']['user'] else None
        }
        commit_data_list.append(commit_data)

    return commit_data_list


def fetch_commit_page(variables, GITHUB_TOKEN, *, after_cursor=None, first=100) -> tuple[list[dict], dict]:
    page_variables = dict(variables)
    page_variables.update({"first": first, "after": after_cursor})
    data = github_api_call(commits_query, page_variables, GITHUB_TOKEN, request_name="commits")

    if data and 'data' in data and data['data'] and 'repository' in data['data'] and data['data']['repository'] and 'ref' in data['data']['repository'] and data['data']['repository']['ref'] and 'target' in data['data']['repository']['ref'] and data['data']['repository']['ref']['target'] and 'history' in data['data']['repository']['ref']['target']:
        history = data['data']['repository']['ref']['target']['history']
        return _extract_commit_rows(history['edges']), history['pageInfo']

    logger.error("Could not retrieve commit data or unexpected data structure")
    return [], {"endCursor": None, "hasNextPage": False}


def process_commits(variables, GITHUB_TOKEN) -> Optional[pd.DataFrame]:
    all_commits = []
    after_cursor = None
    has_next_page = True
    # Note: since parameter is already in variables if provided for time filtering

    while has_next_page:
        commit_rows, page_info = fetch_commit_page(
            variables,
            GITHUB_TOKEN,
            after_cursor=after_cursor,
            first=100,
        )
        all_commits.extend(commit_rows)
        after_cursor = page_info['endCursor']
        has_next_page = page_info['hasNextPage']

    logger.info("Fetched %s commits", len(all_commits))

    logger.info("Extracted data for %s commits", len(all_commits))
    df_commits = pd.DataFrame(all_commits)
    if df_commits.empty:
        df_commits = df_commits.reindex(
            columns=[
                'oid',
                'authoredDate',
                'messageHeadline',
                'additions',
                'deletions',
                'author_name',
                'author_login',
            ]
        )
    return df_commits


def process_releases(variables, GITHUB_TOKEN) -> Optional[pd.DataFrame]:
    all_releases = []
    after_cursor_releases = None
    has_next_page_releases = True
    variables['first_releases'] = 100  # Number of releases to fetch per page
    variables['after_releases'] = None  # Cursor for pagination

    while has_next_page_releases:
        variables.update({"after_releases": after_cursor_releases})
        logger.debug("Fetching releases page with cursor=%s", after_cursor_releases)
        data = github_api_call(releases_query, variables, GITHUB_TOKEN, request_name="releases")

        if data and 'data' in data and data['data'] and 'repository' in data['data'] and data['data']['repository'] and 'releases' in data['data']['repository']:
            releases_data = data['data']['repository']['releases']['edges']
            all_releases.extend(releases_data)
            page_info_releases = data['data']['repository']['releases']['pageInfo']
            after_cursor_releases = page_info_releases['endCursor']
            has_next_page_releases = page_info_releases['hasNextPage']
        else:
            logger.error("Could not retrieve release data or unexpected data structure")
            logger.debug("Response data: %s", data)
            break

    logger.info("Fetched %s releases", len(all_releases))

    # process 'all_releases' to extract release dates and total download counts per release
    release_data_list = []
    for release_edge in all_releases:
        release_node = release_edge['node']
        release_name = release_node['name'] if release_node['name'] else release_node['tagName'] # Use tag name if name is empty
        created_at = release_node['createdAt']
        tag_name = release_node['tagName']
        total_downloads = sum(asset_edge['node']['downloadCount'] for asset_edge in release_node['releaseAssets']['edges'])

        release_data_list.append({
            'name': release_name,
            'tag_name': tag_name,
            'created_at': created_at,
            'total_downloads': total_downloads
        })

    # Create a pandas DataFrame from the collected data
    df_releases = pd.DataFrame(release_data_list)
    logger.info("Extracted data for %s releases", len(df_releases))
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Releases data preview: %s", df_releases.head().to_dict("records") if not df_releases.empty else [])
    # Convert 'created_at' to datetime objects
    if not df_releases.empty:
        df_releases['created_at'] = pd.to_datetime(df_releases['created_at'])
    return df_releases


def process_issues(variables, GITHUB_TOKEN) -> Optional[pd.DataFrame]:
    ISSUE_COLUMNS = [
        "id",
        "createdAt",
        "closedAt",
        "state",
        "author_login",
        "first_comment_createdAt",
        "first_comment_author",
        "labels",
    ]
    all_issues = []
    after_cursor_issues = None
    has_next_page_issues = True
    variables['first_issues'] = 100
    variables['after_issues'] = None
    # Note: since parameter is already in variables if provided for time filtering

    while has_next_page_issues:
        variables.update({"after_issues": after_cursor_issues})
        data = github_api_call(issues_query, variables, GITHUB_TOKEN, request_name="issues")

        if data and 'data' in data and data['data'] and 'repository' in data['data'] and data['data']['repository'] and 'issues' in data['data']['repository']:
            issues_data = data['data']['repository']['issues']['edges']
            all_issues.extend(issues_data)
            page_info_issues = data['data']['repository']['issues']['pageInfo']
            after_cursor_issues = page_info_issues['endCursor']
            has_next_page_issues = page_info_issues['hasNextPage']
        else:
            logger.error("Could not retrieve issue data or unexpected data structure")
            break

    logger.info("Fetched %s issues", len(all_issues))

    # lets unpack them and create a dataframe
    issue_data_list = []
    for issue_edge in all_issues:
        issue_node = issue_edge['node']
        first_comment = None
        first_comment_author = None
        
        if issue_node['comments']['nodes']:
            first_comment = issue_node['comments']['nodes'][0]['createdAt']
            first_comment_author = issue_node['comments']['nodes'][0]['author']['login'] if issue_node['comments']['nodes'][0]['author'] else None

        labels = [label['name'] for label in issue_node['labels']['nodes']]

        issue_data_list.append({
            'id': issue_node['id'],
            'createdAt': pd.to_datetime(issue_node['createdAt'], utc=True),
            'closedAt': pd.to_datetime(issue_node['closedAt'], utc=True) if issue_node['closedAt'] else None,
            'state': issue_node['state'],
            'author_login': issue_node['author']['login'] if issue_node['author'] else None,
            'first_comment_createdAt': pd.to_datetime(first_comment, utc=True) if first_comment else None,
            'first_comment_author': first_comment_author,
            'labels': labels
        })

    # Ensure stable schema even when there are zero issues (pd.DataFrame([]) has no columns).
    df_issues = pd.DataFrame(issue_data_list)
    return df_issues.reindex(columns=ISSUE_COLUMNS)

def process_prs(variables, GITHUB_TOKEN) -> Optional[pd.DataFrame]:
    PR_COLUMNS = [
        "id",
        "createdAt",
        "mergedAt",
        "closedAt",
        "state",
        "author_login",
        "first_comment_createdAt",
        "first_comment_author",
        "labels",
    ]
    all_prs = []
    after_cursor_prs = None
    has_next_page_prs = True
    variables['first_prs'] = 100
    variables['after_prs'] = None
    # Note: since parameter is already in variables if provided for time filtering

    while has_next_page_prs:
        variables.update({"after_prs": after_cursor_prs})
        data = github_api_call(pr_query, variables, GITHUB_TOKEN, request_name="prs")

        if data and 'data' in data and data['data'] and 'repository' in data['data'] and data['data']['repository'] and 'pullRequests' in data['data']['repository']:
            prs_data = data['data']['repository']['pullRequests']['edges']
            all_prs.extend(prs_data)
            page_info_prs = data['data']['repository']['pullRequests']['pageInfo']
            after_cursor_prs = page_info_prs['endCursor']
            has_next_page_prs = page_info_prs['hasNextPage']
        else:
            logger.error("Could not retrieve PR data or unexpected data structure")
            break

    logger.info("Fetched %s pull requests", len(all_prs))

    pr_data_list = []
    for pr_edge in all_prs:
        pr_node = pr_edge['node']
        first_comment_pr = None
        first_comment_author_pr = None

        if pr_node['comments']['nodes']:
            first_comment_pr = pr_node['comments']['nodes'][0]['createdAt']
            first_comment_author_pr = pr_node['comments']['nodes'][0]['author']['login'] if pr_node['comments']['nodes'][0]['author'] else None

        labels_pr = [label['name'] for label in pr_node['labels']['nodes']]

        pr_data_list.append({
            'id': pr_node['id'],
            'createdAt': pd.to_datetime(pr_node['createdAt'], utc=True),
            'mergedAt': pd.to_datetime(pr_node['mergedAt'], utc=True) if pr_node['mergedAt'] else None,
            'closedAt': pd.to_datetime(pr_node['closedAt'], utc=True) if pr_node['closedAt'] else None,
            'state': pr_node['state'],
            'author_login': pr_node['author']['login'] if pr_node['author'] else None,
            'first_comment_createdAt': pd.to_datetime(first_comment_pr, utc=True) if first_comment_pr else None,
            'first_comment_author': first_comment_author_pr,
            'labels': labels_pr
        })

    # Ensure stable schema even when there are zero PRs (pd.DataFrame([]) has no columns).
    df_prs = pd.DataFrame(pr_data_list)
    return df_prs.reindex(columns=PR_COLUMNS)
