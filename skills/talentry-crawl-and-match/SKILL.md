---
name: talentry-crawl-and-match
description: Compare supplied candidate text or documents with Markdown job openings in a workspace jobs directory and return an evidence-based ranked shortlist. Use for candidate-to-role matching, not employer-side hiring decisions or automatic applications.
---

# Talentry - Crawl & Match

Match a candidate to roles without altering the candidate source or job corpus. Treat the result as decision support, never as a hiring decision or hiring-probability estimate.

## Intake

1. Read pasted candidate text directly. For an attached document, use an available format-aware reader to extract its text. If extraction is unavailable or unreliable, ask the user to paste the relevant content or supply a readable replacement.
2. Ask how many positions the shortlist should contain. Require a positive integer before retrieval.
3. Extract only explicit job-relevant evidence: roles, responsibilities, outcomes, technologies, domains, experience depth, relevant education or certifications, language ability, location preferences, and practical constraints.
4. Decide whether any missing or ambiguous fact could materially change which roles qualify or their order. Ask the smallest focused follow-up question only when it could. Otherwise continue without a questionnaire.

Never embellish candidate claims. Ignore age, gender, gender identity, sexual orientation, appearance, ethnicity, religion, disability, health, family status, and other protected or job-irrelevant characteristics. Consider nationality only when the user explicitly identifies a legal work-authorization constraint.

## Locate or Build the Corpus

Use the active workspace root and look for a `jobs/` directory directly beneath it. When it exists, use it without crawling or refreshing it.

When `jobs/` is missing:

1. Ask the user for the complete Talentry job-list link unless they already supplied it. Never infer a URL, use a built-in default, or accept a raw share ID.
2. Resolve the bundled crawler relative to this skill: the plugin root is two directories above this `SKILL.md`, and the crawler is `scripts/talentry_crawler.py` beneath that root.
3. Run the crawler with `--validate-only` first. This performs only local URL validation and must accept exclusively HTTPS links whose host is exactly `talentry.com` or a real subdomain of it, whose port is standard HTTPS, and whose path contains a supported Talentry share shape. It must reject credentials, HTTP, foreign hosts, lookalike domains, raw share IDs, and unrelated paths.
4. If local validation succeeds, tell the user that the next step contacts the supplied Talentry tenant and creates `<workspace root>/jobs/`, then request explicit permission to continue.
5. Only after permission, run the crawler without `--validate-only`. Its first network operations verify both the Talentry tenant endpoint and the supplied referral/share endpoint. It must not request job listings or details and must not create the output directory until both responses have the expected Talentry API structure.
6. If platform verification fails, stop and explain that the link could not be confirmed as a working Talentry job share. Do not try another host, weaken validation, or create the jobs directory.
7. After a successful crawl, confirm that `jobs/index.json` and numbered job Markdown files exist, then continue with matching.

Use this local-only preflight command before asking for network permission:

```text
python3 <resolved-crawler-path> --url <user-supplied-url> --validate-only
```

After permission, use:

```text
python3 <resolved-crawler-path> --url <user-supplied-url> --output-dir <workspace-root>/jobs --quiet
```

Do not refresh an existing corpus unless the user explicitly requests a refresh. Never overwrite existing job data merely because the matcher was invoked.

## Retrieve a Broad Pool

Save the extracted candidate text to a temporary UTF-8 file so candidate data is not placed directly in a command argument. Resolve the helper relative to this skill: the plugin root is two directories above this `SKILL.md`, and the helper is `scripts/retrieve_jobs.py` beneath that root.

Run the helper with:

```text
python3 <resolved-helper-path> --candidate-file <temporary-text-path> --jobs-dir <workspace-jobs-path> --limit <pool-size>
```

Set `pool-size` to the greater of 25 or five times the requested shortlist size. Read its JSON output. `retrieval_score` is only a lexical recall signal; never show it as the final fit score or use it without full semantic review.

Read every returned Markdown job file in full. If the helper reports warnings or skipped files, disclose them concisely. If retrieval fails because the candidate text is empty, the jobs directory is absent, or its inputs are unreadable, explain the specific issue and stop.

## Evaluate and Rank

Score each credible role from 0 to 100 using evidence from the candidate source and full job description:

- Skills and technologies: 0–40
- Relevant responsibilities and demonstrated outcomes: 0–25
- Seniority and experience depth: 0–20
- Location, language, and practical constraints: 0–15

Give partial credit for credible transferable experience and explain the connection. An explicit contradiction on a mandatory requirement may exclude a role or cap its score. Missing information receives no assumed credit. If a newly discovered ambiguity could materially change the shortlist, ask a focused clarification before finalizing it.

Rank by final evidence-based fit, not by lexical retrieval order. Return fewer positions than requested when fewer credible matches exist. If none are credible, explain the strongest recurring gaps instead of manufacturing a ranking.

## Output

Begin with a short candidate-match summary, the requested shortlist size, and any necessary assumptions. For each role include:

- Rank and final fit score, including the four score components
- Job title, company, department, locations, and countries
- A clickable link to the absolute local Markdown file
- Application and Talentry links when present
- Explicit candidate evidence supporting the match
- Important gaps, risks, or unresolved uncertainty
- A concise explanation of why the role holds its rank

Clearly label reasoned inference and distinguish it from source facts. Use the user's language where practical while preserving source-language job titles. State that scores are comparative decision-support estimates, not hiring probabilities.
