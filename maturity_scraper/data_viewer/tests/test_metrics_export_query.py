from datetime import datetime, timezone
import sys
from pathlib import Path
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "data_viewer" / "data_viewer"))

from data import get_owner_metrics_export
from storage.models import Base, Metric, Repo, Run


class OwnerMetricsExportQueryTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.session = sessionmaker(bind=engine)()

    def tearDown(self):
        self.session.close()

    def test_uses_latest_metrics_run_for_each_repo(self):
        alpha = Repo(owner="example-org", name="alpha")
        beta = Repo(owner="example-org", name="beta")
        self.session.add_all([alpha, beta])
        self.session.flush()

        older_run = Run(repo_id=alpha.id, run_started_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        latest_run = Run(repo_id=alpha.id, run_started_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
        beta_run = Run(repo_id=beta.id, run_started_at=datetime(2026, 1, 3, tzinfo=timezone.utc))
        self.session.add_all([older_run, latest_run, beta_run])
        self.session.flush()
        self.session.add_all(
            [
                Metric(run_id=older_run.id, scope="repo", name="stars", value_int=1),
                Metric(run_id=latest_run.id, scope="repo", name="stars", value_int=2),
                Metric(run_id=beta_run.id, scope="commits", name="total_commits", value_int=3),
            ]
        )
        self.session.commit()

        export_data = get_owner_metrics_export(self.session, "example-org")

        self.assertEqual([repo["repo"] for repo in export_data["repos"]], ["alpha", "beta"])
        self.assertEqual(export_data["repos"][0]["run"]["id"], latest_run.id)
        self.assertEqual(export_data["repos"][0]["metrics"]["repo"]["stars"], 2)
        self.assertEqual(export_data["repos"][1]["metrics"]["commits"]["total_commits"], 3)


if __name__ == "__main__":
    unittest.main()
