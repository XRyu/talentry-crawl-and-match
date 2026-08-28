#!/usr/bin/env python3
"""Secure, dependency-free Talentry job crawler bundled with the plugin."""

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    from .crawler.client import TalentryClient
    from .crawler.exporter import JobExporter
    from .crawler.indexer import generate_index
except ImportError:
    from crawler.client import TalentryClient
    from crawler.exporter import JobExporter
    from crawler.indexer import generate_index


@dataclass(frozen=True)
class TalentryTarget:
    base_url: str
    share_id: str


class TalentryVerificationError(RuntimeError):
    """Raised when a URL cannot be confirmed as a working Talentry job share."""


def validate_talentry_url(raw_url: str) -> TalentryTarget:
    """Validate a Talentry job-list URL without making a network request."""
    parsed = urllib.parse.urlsplit(raw_url.strip())
    hostname = (parsed.hostname or "").casefold()
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid URL port") from exc

    if parsed.scheme.casefold() != "https":
        raise ValueError("Talentry URL must use HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Talentry URL must not contain credentials")
    if port not in (None, 443):
        raise ValueError("Talentry URL must use the standard HTTPS port")
    if hostname != "talentry.com" and not hostname.endswith(".talentry.com"):
        raise ValueError("URL host is not talentry.com or a Talentry subdomain")

    patterns = (
        r"^/list/([A-Za-z0-9_-]+)(?:/|$)",
        r"^/app/talent/s/([A-Za-z0-9_-]+)(?:/|$)",
        r"^/s/([A-Za-z0-9_-]+)(?:/|$)",
    )
    match = next((match for pattern in patterns if (match := re.search(pattern, parsed.path))), None)
    if not match:
        raise ValueError("unsupported Talentry job-list URL")
    return TalentryTarget(
        base_url=f"https://{hostname}",
        share_id=match.group(1),
    )


def verify_talentry_platform(client: object, share_id: str) -> Dict[str, object]:
    """Verify Talentry-specific tenant and referral API responses."""
    try:
        tenant = client.init_tenant()
        referral = client.get_share_info(share_id)
    except Exception as exc:
        raise TalentryVerificationError(f"Talentry API verification failed: {exc}") from exc

    if not isinstance(tenant, dict) or tenant.get("id") in (None, ""):
        raise TalentryVerificationError("Talentry tenant response is missing its ID")
    if not isinstance(referral, dict) or not referral:
        raise TalentryVerificationError("Talentry referral response is missing or invalid")
    return {
        "tenant_id": tenant["id"],
        "tenant_name": tenant.get("name", ""),
        "share_id": share_id,
    }


def crawl_jobs(
    target_url: str,
    output_dir: str = "./jobs",
    workers: int = 10,
    limit: Optional[int] = None,
    locale: str = "de",
    create_index: bool = True,
    quiet: bool = False,
    client_factory: Optional[Callable[..., object]] = None,
) -> List[Dict[str, Any]]:
    """Verify the target before creating output or starting the crawl."""
    target = validate_talentry_url(target_url)
    factory = client_factory or TalentryClient
    client = factory(base_url=target.base_url)
    verification = verify_talentry_platform(client, target.share_id)

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    exporter = JobExporter(
        output_dir=str(out_path),
        default_locale=locale,
        base_url=target.base_url,
    )

    if not quiet:
        print(
            "Verified Talentry tenant "
            f"{verification.get('tenant_name') or verification['tenant_id']} "
            f"and share {target.share_id}."
        )

    lookups = client.load_lookups()
    summaries = client.fetch_all_job_summaries(
        share_id=target.share_id,
        page_size=100,
        locale=locale,
        limit=limit,
    )
    if not summaries:
        if not quiet:
            print("No job postings were returned by the verified Talentry share.")
        return []

    processed_jobs: List[Dict[str, Any]] = []
    errors = []

    def fetch_and_export(summary: Dict[str, Any]):
        detail = client.get_job_details(summary["id"])
        return exporter.export_job(
            job_detail=detail,
            share_id=target.share_id,
            summary=summary,
            lookups=lookups,
            preferred_locale=locale,
        )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_summary = {
            executor.submit(fetch_and_export, summary): summary
            for summary in summaries
        }
        for future in as_completed(future_to_summary):
            summary = future_to_summary[future]
            try:
                _, job_data = future.result()
                processed_jobs.append(job_data)
            except Exception as exc:
                errors.append((summary.get("id"), str(exc)))

    processed_jobs.sort(key=lambda job: str(job.get("id", "")))
    if create_index and processed_jobs:
        generate_index(processed_jobs, out_path)

    if not quiet:
        print(f"Exported {len(processed_jobs)} jobs to {out_path.resolve()}.")
        if errors:
            print(f"Failed to export {len(errors)} jobs.", file=sys.stderr)

    return processed_jobs


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="HTTPS Talentry job-list URL")
    parser.add_argument("--output-dir", default="./jobs")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--locale", default="de")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the URL shape locally without network access or filesystem writes",
    )
    parser.add_argument("--quiet", action="store_true")
    arguments = parser.parse_args(argv)

    try:
        target = validate_talentry_url(arguments.url)
        if arguments.validate_only:
            print(json.dumps({"base_url": target.base_url, "share_id": target.share_id}))
            return 0
        crawl_jobs(
            target_url=arguments.url,
            output_dir=arguments.output_dir,
            workers=arguments.workers,
            limit=arguments.limit,
            locale=arguments.locale,
            quiet=arguments.quiet,
        )
        return 0
    except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
