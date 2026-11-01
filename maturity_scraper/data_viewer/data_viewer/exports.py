import csv
import io
import json


METRIC_SCOPE_ORDER = (
    "repo",
    "commits",
    "issues",
    "prs",
    "releases",
    "activity",
)


def owner_metrics_to_csv(export_data: dict) -> str:
    repos = export_data["repos"]
    metric_columns = []
    scopes = {scope for repo in repos for scope in repo["metrics"]}
    ordered_scopes = [scope for scope in METRIC_SCOPE_ORDER if scope in scopes]
    ordered_scopes.extend(sorted(scopes - set(METRIC_SCOPE_ORDER)))
    for scope in ordered_scopes:
        names = {
            name
            for repo in repos
            for name in repo["metrics"].get(scope, {})
        }
        metric_columns.extend(f"{scope}.{name}" for name in sorted(names))

    fieldnames = ["owner", "repo", "run_id", "run_started_at", *metric_columns]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for repo in repos:
        row = {
            "owner": export_data["owner"],
            "repo": repo["repo"],
            "run_id": repo["run"]["id"],
            "run_started_at": repo["run"]["started_at"],
        }
        for scope, metrics in repo["metrics"].items():
            for name, value in metrics.items():
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, sort_keys=True)
                row[f"{scope}.{name}"] = value
        writer.writerow(row)
    return output.getvalue()


def owner_metrics_to_json(export_data: dict) -> str:
    return json.dumps(export_data, indent=2, sort_keys=True, default=str)
