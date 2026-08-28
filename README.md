# Talentry - Crawl & Match

A Codex plugin that compares a supplied CV or candidate profile with open positions stored as Markdown files and returns an evidence-based ranked shortlist.

## What it does

- Asks how many positions the shortlist should contain.
- Uses an existing `jobs/` directory when one is available.
- If `jobs/` is missing, asks for a Talentry job-list link.
- Validates locally that the supplied URL is a supported HTTPS link on `talentry.com` or a genuine subdomain.
- Requests explicit permission before contacting Talentry or creating job files.
- Verifies the Talentry tenant and referral APIs before downloading job listings.
- Asks focused follow-up questions when candidate information is too ambiguous to rank reliably.
- Scores and ranks credible matches using candidate evidence, job requirements, seniority, and practical constraints.

The result is decision support only. Scores are comparative fit estimates, not hiring probabilities or automated hiring decisions.

## Repository layout

- `.codex-plugin/plugin.json` — plugin manifest
- `skills/talentry-crawl-and-match/` — matching workflow and Codex metadata
- `scripts/talentry_crawler.py` — verified Talentry crawler
- `scripts/retrieve_jobs.py` — local candidate-to-job retrieval helper
- `tests/` — unit, integration, and security tests with synthetic fixtures

## Development

The plugin requires Python 3 and uses only the Python standard library at runtime.

Run the test suite from the repository root:

```sh
python3 -m unittest discover -s tests -v
```

Generated job data is written to the workspace's `jobs/` directory and is intentionally excluded from version control because it may contain third-party job content.
