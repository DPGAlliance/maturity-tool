import json
import sys
from pathlib import Path
import unittest


VIEWER_MODULE_DIR = Path(__file__).resolve().parents[1] / "data_viewer"
sys.path.insert(0, str(VIEWER_MODULE_DIR))

from exports import owner_metrics_to_csv, owner_metrics_to_json


class OwnerMetricsExportTests(unittest.TestCase):
    def setUp(self):
        self.export_data = {
            "owner": "example-org",
            "generated_at": "2026-09-05T12:00:00+00:00",
            "repos": [
                {
                    "repo": "alpha",
                    "run": {"id": 2, "started_at": "2026-09-05T11:00:00+00:00"},
                    "metrics": {
                        "issues": {"backlog_size": 4},
                        "repo": {"stars": 9},
                        "activity": {"score_90d": 2.5},
                    },
                },
                {
                    "repo": "beta",
                    "run": {"id": 3, "started_at": "2026-09-05T11:30:00+00:00"},
                    "metrics": {
                        "commits": {"total_commits": 7},
                        "repo": {"stars": 1},
                    },
                },
            ],
        }

    def test_csv_has_one_row_per_repo_and_thematic_columns(self):
        rows = owner_metrics_to_csv(self.export_data).splitlines()

        self.assertEqual(len(rows), 3)
        self.assertEqual(
            rows[0].split(","),
            [
                "owner",
                "repo",
                "run_id",
                "run_started_at",
                "repo.stars",
                "commits.total_commits",
                "issues.backlog_size",
                "activity.score_90d",
            ],
        )
        self.assertTrue(rows[1].startswith("example-org,alpha,2,"))
        self.assertTrue(rows[2].startswith("example-org,beta,3,"))

    def test_json_preserves_grouped_metrics(self):
        payload = json.loads(owner_metrics_to_json(self.export_data))

        self.assertEqual(payload["owner"], "example-org")
        self.assertEqual(payload["repos"][0]["metrics"]["issues"]["backlog_size"], 4)
        self.assertEqual(payload["repos"][1]["metrics"]["commits"]["total_commits"], 7)


if __name__ == "__main__":
    unittest.main()
