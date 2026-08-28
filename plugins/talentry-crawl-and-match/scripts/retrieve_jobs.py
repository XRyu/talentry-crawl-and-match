#!/usr/bin/env python3
"""Load and lexically order every job for later semantic candidate matching."""

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from math import log
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple


STOPWORDS = frozenset(
    """
    a an and are as at be been by for from in into is it of on or that the this to was were will with
    der die das den dem des ein eine einer einem einen und mit von zu im in ist sind als auf fuer für
    de het een en met van voor op is zijn als bij naar
    le la les un une et avec de des du dans est sont pour sur au aux
    """.split()
)

COUNTRY_ALIASES = {
    "AT": "austria oesterreich österreich",
    "CH": "switzerland schweiz suisse svizzera",
    "DE": "germany deutschland",
    "ES": "spain espana españa",
    "FR": "france",
    "GB": "united kingdom britain uk",
    "IN": "india",
    "NL": "netherlands nederland",
    "RO": "romania",
    "TR": "turkey turkiye türkiye",
    "US": "united states usa",
}


@dataclass(frozen=True)
class JobRecord:
    path: Path
    job_id: str
    title: str
    company: str
    departments: Tuple[str, ...]
    locations: Tuple[str, ...]
    countries: Tuple[str, ...]
    apply_url: str
    talentry_url: str
    body: str


@dataclass(frozen=True)
class RetrievalResult:
    job: JobRecord
    retrieval_score: float
    matched_terms: Tuple[str, ...]


@dataclass(frozen=True)
class RetrievalReport:
    source: str
    results: Tuple[RetrievalResult, ...]
    warnings: Tuple[str, ...]
    skipped_files: Tuple[str, ...]


def normalize_terms(text: str) -> Tuple[str, ...]:
    """Return unique, normalized terms in stable lexical order."""
    normalized = unicodedata.normalize("NFKD", text).casefold()
    aliases = (
        (r"(?<!\w)c\+\+(?!\w)", " cplusplus "),
        (r"(?<!\w)\.net\b", " dotnet "),
        (r"\bci\s*/\s*cd\b", " cicd "),
        (r"\bs\s*/\s*4hana\b", " s4hana "),
    )
    for pattern, replacement in aliases:
        normalized = re.sub(pattern, replacement, normalized)
    normalized = "".join(character for character in normalized if not unicodedata.combining(character))
    return tuple(sorted(set(re.findall(r"[a-z0-9]+", normalized)).difference(STOPWORDS)))


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def parse_markdown_job(path: Path) -> JobRecord:
    """Parse supported frontmatter fields and the Markdown body."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing opening frontmatter delimiter")

    try:
        closing_index = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration as exc:
        raise ValueError("missing closing frontmatter delimiter") from exc

    scalars = {}
    lists = {"departments": [], "locations": [], "countries": []}
    active_list = ""
    for line in lines[1:closing_index]:
        key_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if key_match:
            key, value = key_match.groups()
            active_list = key if key in lists else ""
            if value:
                scalars[key] = _unquote(value)
            continue
        item_match = re.match(r"^\s+-\s+(.*)$", line)
        if item_match and active_list:
            lists[active_list].append(_unquote(item_match.group(1)))

    title = scalars.get("title", "").strip()
    if not title:
        raise ValueError("missing required title")

    return JobRecord(
        path=path.resolve(),
        job_id=scalars.get("id", "").strip(),
        title=title,
        company=scalars.get("company", "").strip(),
        departments=tuple(lists["departments"]),
        locations=tuple(lists["locations"]),
        countries=tuple(lists["countries"]),
        apply_url=scalars.get("apply_url", "").strip(),
        talentry_url=scalars.get("talentry_url", "").strip(),
        body="\n".join(lines[closing_index + 1 :]).strip(),
    )


def _weighted_term_map(job: JobRecord) -> dict:
    weighted = {}
    country_aliases = " ".join(COUNTRY_ALIASES.get(country.upper(), "") for country in job.countries)
    fields = (
        (job.body, 1.0),
        (" ".join(job.locations + job.countries) + " " + country_aliases, 1.5),
        (" ".join(job.departments), 2.0),
        (job.title, 3.0),
    )
    for text, weight in fields:
        for term in normalize_terms(text):
            weighted[term] = max(weighted.get(term, 0.0), weight)
    return weighted


def _resolve_index_path(jobs_dir: Path, file_path: str) -> Path:
    candidate = Path(file_path)
    if candidate.is_absolute():
        return candidate.resolve()
    if candidate.parts and candidate.parts[0] == "jobs":
        candidate = Path(*candidate.parts[1:])
    return (jobs_dir / candidate).resolve()


def load_jobs(jobs_dir: Path) -> Tuple[str, Tuple[JobRecord, ...], Tuple[str, ...], Tuple[str, ...]]:
    """Return source label, valid jobs, warnings, and skipped paths."""
    jobs_dir = jobs_dir.resolve()
    if not jobs_dir.is_dir():
        raise ValueError(f"jobs directory does not exist: {jobs_dir}")

    markdown_paths = tuple(sorted(path.resolve() for path in jobs_dir.glob("[0-9]*_*.md")))
    markdown_set = set(markdown_paths)
    warnings = []
    source = "markdown-scan"
    index_path = jobs_dir / "index.json"
    if index_path.is_file():
        try:
            index_data = json.loads(index_path.read_text(encoding="utf-8"))
            if not isinstance(index_data, list):
                raise ValueError("index root is not a list")
            indexed_paths = {
                _resolve_index_path(jobs_dir, entry["file_path"])
                for entry in index_data
                if isinstance(entry, dict) and isinstance(entry.get("file_path"), str)
            }
            complete_entries = len(indexed_paths) == len(index_data)
            if complete_entries and indexed_paths == markdown_set:
                source = "index+markdown"
            else:
                warnings.append("jobs/index.json is stale; scanned Markdown files directly")
        except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError):
            warnings.append("jobs/index.json is malformed or stale; scanned Markdown files directly")

    jobs = []
    skipped_files = []
    for path in markdown_paths:
        try:
            jobs.append(parse_markdown_job(path))
        except (OSError, UnicodeError, ValueError):
            skipped_files.append(str(path))

    return source, tuple(jobs), tuple(warnings), tuple(skipped_files)


def retrieve(candidate_text: str, jobs_dir: Path) -> RetrievalReport:
    """Return every valid job in deterministic lexical-relevance order."""
    if not candidate_text.strip():
        raise ValueError("candidate text is empty")

    source, jobs, warnings, skipped_files = load_jobs(jobs_dir)
    candidate_terms = set(normalize_terms(candidate_text))
    job_terms = tuple(_weighted_term_map(job) for job in jobs)
    document_frequency = {
        term: sum(1 for terms in job_terms if term in terms)
        for term in candidate_terms
    }

    results = []
    for job, weighted_terms in zip(jobs, job_terms):
        matched = tuple(sorted(candidate_terms.intersection(weighted_terms)))
        score = sum(
            weighted_terms[term] * (log((1 + len(jobs)) / (1 + document_frequency[term])) + 1.0)
            for term in matched
        )
        results.append(RetrievalResult(job=job, retrieval_score=round(score, 6), matched_terms=matched))

    results.sort(key=lambda result: (-result.retrieval_score, result.job.title.casefold(), result.job.job_id))
    return RetrievalReport(
        source=source,
        results=tuple(results),
        warnings=warnings,
        skipped_files=skipped_files,
    )


def report_to_dict(report: RetrievalReport) -> Dict[str, object]:
    """Convert a retrieval report to the stable JSON CLI contract."""
    return {
        "source": report.source,
        "warnings": list(report.warnings),
        "skipped_files": list(report.skipped_files),
        "results": [
            {
                "file_path": str(result.job.path),
                "job_id": result.job.job_id,
                "title": result.job.title,
                "company": result.job.company,
                "departments": list(result.job.departments),
                "locations": list(result.job.locations),
                "countries": list(result.job.countries),
                "apply_url": result.job.apply_url,
                "talentry_url": result.job.talentry_url,
                "retrieval_score": result.retrieval_score,
                "matched_terms": list(result.matched_terms),
            }
            for result in report.results
        ],
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run retrieval from a UTF-8 candidate file and print JSON."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-file", required=True, type=Path)
    parser.add_argument("--jobs-dir", required=True, type=Path)
    arguments = parser.parse_args(argv)

    try:
        candidate_text = arguments.candidate_file.read_text(encoding="utf-8")
        report = retrieve(candidate_text, arguments.jobs_dir)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    json.dump(report_to_dict(report), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
