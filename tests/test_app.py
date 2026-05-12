import tempfile
from pathlib import Path
import unittest

from jobboard import create_app
from jobboard.db import get_db


class TalentBridgeTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "test.sqlite3"
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE": str(database_path),
                "SEED_SAMPLE_DATA": False,
                "SECRET_KEY": "test-secret",
                "ADMIN_EMAIL": "admin@test.local",
                "ADMIN_PASSWORD": "Admin123!",
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def register(self, name, email, password, role, company=""):
        return self.client.post(
            "/register",
            data={
                "name": name,
                "email": email,
                "password": password,
                "role": role,
                "company": company,
            },
            follow_redirects=True,
        )

    def login(self, email, password):
        return self.client.post(
            "/login",
            data={"email": email, "password": password},
            follow_redirects=True,
        )

    def logout(self):
        return self.client.post("/logout", follow_redirects=True)

    def test_employer_can_post_and_seeker_can_apply(self):
        response = self.register(
            "Employer User",
            "employer@test.local",
            "Employer123!",
            "employer",
            "Acme Corp",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Total Jobs", response.data)
        self.assertIn(b"Recent Jobs", response.data)

        response = self.client.post(
            "/employer/jobs/new",
            data={
                "title": "Data Engineer",
                "description": "Build ETL jobs and maintain reporting pipelines.",
                "salary": "120000",
                "location": "Boston, MA",
                "category": "Engineering",
                "company": "Acme Corp",
                "status": "open",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Job listing published.", response.data)

        with self.app.app_context():
            job = get_db().execute("SELECT id FROM jobs WHERE title = 'Data Engineer'").fetchone()
            self.assertIsNotNone(job)
            job_id = job["id"]

        self.logout()

        response = self.register(
            "Seeker User",
            "seeker@test.local",
            "Seeker123!",
            "seeker",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Recommended Jobs", response.data)

        response = self.client.post(
            f"/jobs/{job_id}/apply",
            data={"cover_letter": "I have direct experience with data platforms."},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Application submitted.", response.data)

        with self.app.app_context():
            application = get_db().execute(
                "SELECT id, status FROM applications WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            self.assertIsNotNone(application)
            self.assertEqual(application["status"], "submitted")

    def test_admin_dashboard_is_available(self):
        response = self.login("admin@test.local", "Admin123!")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Recent Jobs", response.data)
        self.assertIn(b"Manage Users", response.data)


if __name__ == "__main__":
    unittest.main()
