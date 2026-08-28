from pathlib import Path
import tempfile
import unittest


class TalentryCrawlerSecurityTests(unittest.TestCase):
    def test_valid_talentry_list_url_is_accepted(self):
        try:
            from scripts.talentry_crawler import validate_talentry_url
        except (ImportError, ModuleNotFoundError) as exc:
            self.fail(f"bundled Talentry crawler is missing: {exc}")

        target = validate_talentry_url(
            "https://adesso.talentry.com/list/1CeTqMXAojdhkJU9TR6bpZ/3"
        )

        self.assertEqual(target.base_url, "https://adesso.talentry.com")
        self.assertEqual(target.share_id, "1CeTqMXAojdhkJU9TR6bpZ")

    def test_supported_talentry_app_url_is_accepted(self):
        from scripts.talentry_crawler import validate_talentry_url

        try:
            target = validate_talentry_url(
                "https://adesso.talentry.com/app/talent/s/share_123/jobs"
            )
        except ValueError as exc:
            self.fail(f"supported Talentry app URL was rejected: {exc}")

        self.assertEqual(target.share_id, "share_123")

    def test_untrusted_url_shapes_are_rejected(self):
        from scripts.talentry_crawler import validate_talentry_url

        untrusted_urls = (
            "http://adesso.talentry.com/list/share123/3",
            "https://adesso.talentry.com.evil.example/list/share123/3",
            "https://talentry.com@evil.example/list/share123/3",
            "https://adesso.talentry.com:8443/list/share123/3",
            "share123",
            "https://adesso.talentry.com/not-a-job-list/share123",
        )

        for url in untrusted_urls:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    validate_talentry_url(url)

    def test_api_response_redirect_to_foreign_host_is_rejected(self):
        try:
            from scripts.crawler.client import validate_talentry_response_url
        except ImportError as exc:
            self.fail(f"Talentry response-host validation is missing: {exc}")

        validate_talentry_response_url(
            "https://adesso.talentry.com/api/v1/tenantForDomain"
        )
        with self.assertRaises(RuntimeError):
            validate_talentry_response_url(
                "https://attacker.example/api/v1/tenantForDomain"
            )

    def test_talentry_api_probe_requires_tenant_and_referral_shapes(self):
        try:
            from scripts.talentry_crawler import (
                TalentryVerificationError,
                verify_talentry_platform,
            )
        except ImportError as exc:
            self.fail(f"Talentry API verification is missing: {exc}")

        class ValidClient:
            def init_tenant(self):
                return {"id": 42, "name": "Example Tenant"}

            def get_share_info(self, share_id):
                return {"id": share_id, "type": "PUBLIC_JOB_LIST"}

        class InvalidClient:
            def init_tenant(self):
                return {"name": "Not verified"}

            def get_share_info(self, share_id):
                return {"id": share_id}

        verification = verify_talentry_platform(ValidClient(), "share123")
        self.assertEqual(verification["tenant_id"], 42)
        self.assertEqual(verification["share_id"], "share123")

        with self.assertRaises(TalentryVerificationError):
            verify_talentry_platform(InvalidClient(), "share123")

    def test_failed_api_probe_creates_no_jobs_directory(self):
        try:
            from scripts.talentry_crawler import (
                TalentryVerificationError,
                crawl_jobs,
            )
        except ImportError as exc:
            self.fail(f"guarded crawl pipeline is missing: {exc}")

        class InvalidClient:
            def init_tenant(self):
                return {"name": "Not verified"}

            def get_share_info(self, share_id):
                return {"id": share_id}

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory) / "jobs"
            with self.assertRaises(TalentryVerificationError):
                crawl_jobs(
                    target_url="https://adesso.talentry.com/list/share123/3",
                    output_dir=str(output_dir),
                    quiet=True,
                    client_factory=lambda base_url: InvalidClient(),
                )

            self.assertFalse(output_dir.exists())


class TalentryCrawlerIntegrationTests(unittest.TestCase):
    def test_verified_talentry_share_exports_markdown_and_index(self):
        from scripts.talentry_crawler import crawl_jobs

        class ValidClient:
            def init_tenant(self):
                return {"id": 42, "name": "Example Tenant"}

            def get_share_info(self, share_id):
                return {"id": share_id, "type": "PUBLIC_JOB_LIST"}

            def load_lookups(self):
                departments = {
                    10: {"id": 10, "translations": {"en": {"name": "Data & Analytics"}}}
                }
                locations = {
                    20: {
                        "id": 20,
                        "country": "DE",
                        "translations": {"en": {"name": "Berlin"}},
                    }
                }
                companies = {
                    30: {"id": 30, "translations": {"en": {"name": "Example SE"}}}
                }
                return departments, locations, companies

            def fetch_all_job_summaries(self, **kwargs):
                return [{"id": 101, "newId": "new-101"}]

            def get_job_details(self, job_id):
                return {
                    "id": job_id,
                    "newId": "new-101",
                    "companyId": 30,
                    "departments": [10],
                    "locations": [20],
                    "createdAt": "2026-08-01T12:00:00Z",
                    "lastChangeDate": "2026-08-20T12:00:00Z",
                    "translations": {
                        "en": {
                            "name": "Senior MLOps Engineer",
                            "description": "<p>Build <strong>ML platforms</strong>.</p>",
                        }
                    },
                }

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory) / "jobs"
            try:
                processed = crawl_jobs(
                    target_url="https://example.talentry.com/list/share123/3",
                    output_dir=str(output_dir),
                    workers=1,
                    locale="en",
                    quiet=True,
                    client_factory=lambda base_url: ValidClient(),
                )
            except TypeError as exc:
                self.fail(f"verified crawl pipeline is incomplete: {exc}")

            job_files = list(output_dir.glob("101_*.md"))
            self.assertEqual(len(processed), 1)
            self.assertEqual(len(job_files), 1)
            self.assertTrue((output_dir / "index.json").is_file())
            self.assertTrue((output_dir / "README.md").is_file())
            job_markdown = job_files[0].read_text(encoding="utf-8")
            self.assertIn("Senior MLOps Engineer", job_markdown)
            self.assertIn("Build **ML platforms**.", job_markdown)


if __name__ == "__main__":
    unittest.main()
