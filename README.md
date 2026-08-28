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

- `.agents/plugins/marketplace.json` — repository marketplace catalog
- `plugins/talentry-crawl-and-match/.codex-plugin/plugin.json` — plugin manifest
- `plugins/talentry-crawl-and-match/skills/` — matching workflow and metadata
- `plugins/talentry-crawl-and-match/scripts/talentry_crawler.py` — verified Talentry crawler
- `plugins/talentry-crawl-and-match/scripts/retrieve_jobs.py` — local retrieval helper
- `plugins/talentry-crawl-and-match/tests/` — tests with synthetic fixtures

## Add the marketplace in ChatGPT

1. Clone this repository locally.
2. Open the cloned repository in Work mode or Codex in the ChatGPT desktop app.
3. Restart the ChatGPT desktop app so it discovers `.agents/plugins/marketplace.json`.
4. Open the Plugins Directory and select **Talentry - Crawl & Match** as the marketplace source.
5. Install the **Talentry - Crawl & Match** plugin and start a new conversation.

## Development

The plugin requires Python 3 and uses only the Python standard library at runtime.

Run the test suite from the plugin directory:

```sh
cd plugins/talentry-crawl-and-match
python3 -m unittest discover -s tests -v
```

Generated job data is written to the workspace's `jobs/` directory and is intentionally excluded from version control because it may contain third-party job content.
