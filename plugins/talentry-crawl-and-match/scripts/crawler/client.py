"""
Talentry REST API Client.
Handles share resolution, metadata lookups, paginated search, and job detail retrieval.
"""

import json
import re
import time
import urllib.parse
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Tuple


def validate_talentry_response_url(url: str) -> None:
    """Reject redirects away from HTTPS Talentry origins."""
    parsed = urllib.parse.urlsplit(url)
    hostname = (parsed.hostname or "").casefold()
    try:
        port = parsed.port
    except ValueError as exc:
        raise RuntimeError("Talentry response used an invalid port") from exc
    if parsed.scheme.casefold() != "https":
        raise RuntimeError("Talentry response redirected away from HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise RuntimeError("Talentry response URL contained credentials")
    if port not in (None, 443):
        raise RuntimeError("Talentry response used a non-standard HTTPS port")
    if hostname != "talentry.com" and not hostname.endswith(".talentry.com"):
        raise RuntimeError("Talentry response redirected to a foreign host")


class TalentryClient:
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        base_url: str = "https://adesso.talentry.com",
        user_agent: Optional[str] = None,
        timeout: int = 20,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        self.tenant_id: Optional[int] = None
        self.tenant_info: Optional[Dict[str, Any]] = None
        self._departments: Optional[Dict[int, Dict[str, Any]]] = None
        self._locations: Optional[Dict[int, Dict[str, Any]]] = None
        self._companies: Optional[Dict[int, Dict[str, Any]]] = None

    def _request(
        self,
        endpoint: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        referer: Optional[str] = None,
    ) -> Any:
        url = endpoint if endpoint.startswith("http") else f"{self.base_url}{endpoint}"
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{query}"

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
        }
        if referer:
            headers["Referer"] = referer

        body_bytes = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            body_bytes = json.dumps(data).encode("utf-8")

        for attempt in range(self.max_retries):
            try:
                req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    validate_talentry_response_url(resp.geturl())
                    resp_bytes = resp.read()
                    if not resp_bytes:
                        return None
                    return json.loads(resp_bytes.decode("utf-8"))
            except urllib.error.HTTPError as e:
                # 429 Too Many Requests or 5xx Server Errors are retryable
                if (e.code == 429 or 500 <= e.code < 600) and attempt < self.max_retries - 1:
                    sleep_time = self.retry_delay * (2 ** attempt)
                    time.sleep(sleep_time)
                    continue
                error_body = ""
                try:
                    error_body = e.read().decode("utf-8")
                except Exception:
                    pass
                raise RuntimeError(
                    f"HTTP {e.code} ({e.reason}) for {method} {url}: {error_body}"
                ) from e
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < self.max_retries - 1:
                    sleep_time = self.retry_delay * (2 ** attempt)
                    time.sleep(sleep_time)
                    continue
                raise RuntimeError(f"Network error requesting {url}: {e}") from e

    def extract_share_id(self, url_or_id: str) -> str:
        """Extract share / referral ID from various URL shapes or raw ID."""
        if "/" not in url_or_id:
            return url_or_id

        # Matches /list/<shareId>/<channel> or /app/talent/s/<shareId>/...
        patterns = [
            r"/list/([a-zA-Z0-9_-]+)",
            r"/app/talent/s/([a-zA-Z0-9_-]+)",
            r"/s/([a-zA-Z0-9_-]+)",
        ]
        for pat in patterns:
            match = re.search(pat, url_or_id)
            if match:
                return match.group(1)

        # Fallback to last non-numeric path token
        parts = [p for p in url_or_id.strip("/").split("/") if p and not p.isdigit()]
        if parts:
            return parts[-1]
        return url_or_id

    def init_tenant(self) -> Dict[str, Any]:
        """Fetch tenant information (ID, name, branding, etc.)."""
        if self.tenant_info is not None:
            return self.tenant_info

        tenant_data = self._request("/api/v1/tenantForDomain")
        self.tenant_info = tenant_data
        self.tenant_id = tenant_data["id"]
        return tenant_data

    def get_share_info(self, share_id: str) -> Dict[str, Any]:
        """Fetch metadata for a share / referral link."""
        return self._request(f"/api/v1/referral/{share_id}")

    def load_lookups(self) -> Tuple[Dict[int, Dict[str, Any]], Dict[int, Dict[str, Any]], Dict[int, Dict[str, Any]]]:
        """Pre-fetch and cache departments, locations, and companies lookups."""
        if self.tenant_id is None:
            self.init_tenant()

        if self._departments is None:
            depts = self._request(f"/api/v1/tenant/{self.tenant_id}/departments") or []
            self._departments = {d["id"]: d for d in depts if "id" in d}

        if self._locations is None:
            locs = self._request(f"/api/v1/tenant/{self.tenant_id}/locations") or []
            self._locations = {l["id"]: l for l in locs if "id" in l}

        if self._companies is None:
            comps = self._request(f"/api/v1/tenants/{self.tenant_id}/companies") or []
            self._companies = {c["id"]: c for c in comps if "id" in c}

        return self._departments, self._locations, self._companies

    def search_jobs(
        self,
        share_id: str,
        offset: int = 0,
        page_size: int = 100,
        locale: str = "de",
        sort: str = "lastChangeDate",
        desc: int = 1,
        department_ids: str = "0",
        location_ids: str = "0",
        company_ids: str = "0",
        search_query: str = "",
    ) -> Dict[str, Any]:
        """Query a page of jobs from the Talentry search endpoint."""
        if self.tenant_id is None:
            self.init_tenant()

        endpoint = f"/api/v1/tenants/{self.tenant_id}/jobs/search/{share_id}"
        params = {
            "locale": locale,
            "offset": offset,
            "pageSize": page_size,
            "sort": sort,
            "desc": desc,
        }
        payload = {
            "tenantId": self.tenant_id,
            "shareId": share_id,
            "requiredVisibilities": "",
            "excludedVisibilities": "",
            "departmentIds": department_ids,
            "locationIds": location_ids,
            "companyIds": company_ids,
            "pageSize": page_size,
            "tagData": {},
        }
        referer = f"{self.base_url}/app/talent/s/{share_id}/jobs"
        return self._request(endpoint, method="POST", params=params, data=payload, referer=referer)

    def fetch_all_job_summaries(
        self,
        share_id: str,
        page_size: int = 100,
        locale: str = "de",
        limit: Optional[int] = None,
        department_ids: str = "0",
        location_ids: str = "0",
        company_ids: str = "0",
        search_query: str = "",
        progress_callback: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch all job summaries by paginating through search results."""
        all_jobs: List[Dict[str, Any]] = []
        offset = 0
        total_count = None

        while True:
            actual_page_size = page_size
            if limit is not None:
                remaining = limit - len(all_jobs)
                if remaining <= 0:
                    break
                actual_page_size = min(page_size, remaining)

            resp = self.search_jobs(
                share_id=share_id,
                offset=offset,
                page_size=actual_page_size,
                locale=locale,
                department_ids=department_ids,
                location_ids=location_ids,
                company_ids=company_ids,
                search_query=search_query,
            )

            total_count = resp.get("count", 0)
            items = resp.get("list", [])
            if not items:
                break

            all_jobs.extend(items)
            offset += len(items)

            if progress_callback:
                progress_callback(len(all_jobs), total_count)

            if len(all_jobs) >= total_count or (limit and len(all_jobs) >= limit):
                break

        return all_jobs

    def get_job_details(self, job_id: Any) -> Dict[str, Any]:
        """Fetch full job details including HTML description and links."""
        if self.tenant_id is None:
            self.init_tenant()

        # Try API v2 first, fallback to v1
        try:
            return self._request(f"/api/v2/tenants/{self.tenant_id}/jobs/{job_id}")
        except Exception:
            return self._request(f"/api/v1/tenants/{self.tenant_id}/jobs/{job_id}")
