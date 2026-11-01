import unittest
from unittest.mock import patch

from scripts import summarize


class BuildOrgQueryResultsTests(unittest.TestCase):
    def test_counts_all_analyzed_repositories_and_ranks_activity(self):
        repos = [
            {
                "owner": "example",
                "repo": "quiet",
                "metrics": {"activity": {"score_90d": 0, "last_commit_at": "2026-01-01"}},
            },
            {
                "owner": "example",
                "repo": "active",
                "metrics": {
                    "activity": {
                        "score_90d": 12.5,
                        "commits_90d": 4,
                        "prs_merged_90d": 2,
                        "issues_closed_90d": 3,
                        "last_commit_at": "2026-02-01",
                    }
                },
            },
            {
                "owner": "example",
                "repo": "missing-activity",
                "metrics": {},
            },
        ]

        result = summarize.build_org_query_results(repos, top_n=2)

        self.assertEqual(result["repo_count"], 3)
        self.assertEqual(result["top_active_window_days"], 90)
        self.assertEqual([repo["repo"] for repo in result["top_active_repos"]], ["active", "quiet"])
        self.assertEqual(result["top_active_repos"][0]["prs_merged_90d"], 2)
        self.assertEqual(result["top_active_repos"][1]["last_commit_at"], "2026-01-01")

    def test_summarize_org_injects_deterministic_query_results(self):
        repos = [
            {
                "owner": "example",
                "repo": "active",
                "metrics": {"activity": {"score_90d": 12}},
            }
        ]
        with (
            patch.object(summarize, "get_json", return_value=repos),
            patch.object(summarize, "get_org_latest_summary", return_value=None),
            patch.object(summarize, "should_summarize", return_value=(True, ["forced"])),
            patch.object(summarize, "load_prompt", return_value=("prompt", "v2")),
            patch.object(summarize, "call_openai", return_value="summary") as call_openai,
            patch.object(summarize, "post_json"),
        ):
            summarize.summarize_org(
                session=None,
                client=None,
                base_url="http://api",
                owner="example",
                prompt_path="unused",
                model="unused",
                history_limit=5,
                max_age_days=30,
                force=True,
            )

        openai_payload = call_openai.call_args.args[3]
        self.assertEqual(openai_payload["query_results"]["repo_count"], 1)
        self.assertEqual(openai_payload["query_results"]["top_active_repos"][0]["repo"], "active")


if __name__ == "__main__":
    unittest.main()
