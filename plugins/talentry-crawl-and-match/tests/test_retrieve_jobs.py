from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCRIPT = PLUGIN_ROOT / "scripts" / "retrieve_jobs.py"


@contextmanager
def copied_fixture_jobs():
    with tempfile.TemporaryDirectory() as temporary_directory:
        jobs_dir = Path(temporary_directory) / "jobs"
        shutil.copytree(FIXTURES / "jobs", jobs_dir)
        yield jobs_dir


class RetrieveJobsTests(unittest.TestCase):
    def setUp(self):
        self.jobs_dir = FIXTURES / "jobs"
        self.candidate = (FIXTURES / "candidate_mlops.txt").read_text(encoding="utf-8")

    def test_normalize_terms_is_case_and_diacritic_insensitive(self):
        try:
            from scripts.retrieve_jobs import normalize_terms
        except (ImportError, ModuleNotFoundError) as exc:
            self.fail(f"retrieval helper is missing: {exc}")

        self.assertEqual(normalize_terms("KÜBERNETES kubernetes"), ("kubernetes",))

    def test_normalize_terms_preserves_technology_aliases(self):
        from scripts.retrieve_jobs import normalize_terms

        terms = normalize_terms("C++ .NET CI/CD S/4HANA")

        self.assertIn("cplusplus", terms)
        self.assertIn("dotnet", terms)
        self.assertIn("cicd", terms)
        self.assertIn("s4hana", terms)

    def test_normalize_terms_removes_common_multilingual_stopwords(self):
        from scripts.retrieve_jobs import normalize_terms

        self.assertEqual(
            normalize_terms("the and with der die und het een met le les et avec Python"),
            ("python",),
        )

    def test_parse_markdown_job_reads_frontmatter_and_body(self):
        try:
            from scripts.retrieve_jobs import parse_markdown_job
        except ImportError as exc:
            self.fail(f"Markdown parser is missing: {exc}")

        job = parse_markdown_job(FIXTURES / "jobs" / "101_mlops-engineer.md")

        self.assertEqual(job.job_id, "101")
        self.assertEqual(job.title, "Senior MLOps Engineer")
        self.assertIn("Utrecht", job.locations)
        self.assertIn("Kubernetes", job.body)

    def test_retrieve_places_relevant_role_first(self):
        try:
            from scripts.retrieve_jobs import retrieve
        except ImportError as exc:
            self.fail(f"broad retrieval is missing: {exc}")

        report = retrieve(self.candidate, self.jobs_dir)

        self.assertEqual(report.results[0].job.job_id, "101")
        self.assertGreater(report.results[0].retrieval_score, report.results[1].retrieval_score)
        self.assertIn("kubernetes", report.results[0].matched_terms)

    def test_stale_index_falls_back_to_markdown_scan(self):
        from scripts.retrieve_jobs import retrieve

        with copied_fixture_jobs() as jobs_dir:
            (jobs_dir / "index.json").write_text("[]", encoding="utf-8")
            report = retrieve(self.candidate, jobs_dir)

        self.assertEqual(report.source, "markdown-scan")
        self.assertTrue(any("stale" in warning.casefold() for warning in report.warnings))

    def test_matching_index_is_used_as_metadata_source(self):
        from scripts.retrieve_jobs import retrieve

        report = retrieve(self.candidate, self.jobs_dir)

        self.assertEqual(report.source, "index+markdown")
        self.assertEqual(report.warnings, ())

    def test_non_job_markdown_does_not_stale_index_or_get_skipped(self):
        from scripts.retrieve_jobs import retrieve

        with copied_fixture_jobs() as jobs_dir:
            (jobs_dir / "README.md").write_text("# Job catalog", encoding="utf-8")
            report = retrieve(self.candidate, jobs_dir)

        self.assertEqual(report.source, "index+markdown")
        self.assertEqual(report.warnings, ())
        self.assertEqual(report.skipped_files, ())

    def test_country_names_match_country_code_metadata(self):
        from scripts.retrieve_jobs import retrieve

        report = retrieve("MLOps engineer open to the Netherlands", self.jobs_dir)

        self.assertEqual(report.results[0].job.job_id, "101")
        self.assertIn("netherlands", report.results[0].matched_terms)

    def test_malformed_job_is_skipped_and_reported(self):
        from scripts.retrieve_jobs import retrieve

        with copied_fixture_jobs() as jobs_dir:
            bad = jobs_dir / "999_broken.md"
            bad.write_text("---\nid: 999\n# no closing frontmatter", encoding="utf-8")
            try:
                report = retrieve(self.candidate, jobs_dir)
            except ValueError as exc:
                self.fail(f"one malformed job stopped retrieval: {exc}")

        self.assertIn(str(bad.resolve()), report.skipped_files)
        self.assertTrue(report.results)

    def test_cli_emits_parseable_json(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--candidate-file",
                str(FIXTURES / "candidate_mlops.txt"),
                "--jobs-dir",
                str(self.jobs_dir),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"CLI did not emit JSON: {exc}")
        self.assertEqual(payload["results"][0]["job_id"], "101")

    def test_cli_returns_every_valid_job_including_zero_term_matches(self):
        with copied_fixture_jobs() as jobs_dir:
            unrelated = jobs_dir / "999_pastry-chef.md"
            unrelated.write_text(
                "---\nid: 999\ntitle: Pastry Chef\n---\nCreates plated desserts and chocolate sculptures.\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--candidate-file",
                    str(FIXTURES / "candidate_mlops.txt"),
                    "--jobs-dir",
                    str(jobs_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual({result["job_id"] for result in payload["results"]}, {"101", "102", "999"})
        unrelated_result = next(result for result in payload["results"] if result["job_id"] == "999")
        self.assertEqual(unrelated_result["retrieval_score"], 0)


if __name__ == "__main__":
    unittest.main()
