"""
Job Opening Exporter.
Serializes structured job openings into Markdown documents with YAML frontmatter.
"""

import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .converter import html_to_markdown


class JobExporter:
    def __init__(
        self,
        output_dir: str = "./jobs",
        default_locale: str = "de",
        base_url: str = "https://adesso.talentry.com",
    ):
        self.output_dir = Path(output_dir)
        self.default_locale = default_locale
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def slugify(text: str) -> str:
        """Create a clean, filesystem-safe filename slug from a job title."""
        if not text:
            return "job"
        # Normalize unicode characters (e.g. ä -> ae, ö -> oe, ü -> ue, ß -> ss)
        text = text.replace("ä", "ae").replace("Ä", "Ae")
        text = text.replace("ö", "oe").replace("Ö", "Oe")
        text = text.replace("ü", "ue").replace("Ü", "Ue")
        text = text.replace("ß", "ss")

        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        # Replace non-alphanumeric chars with dashes
        text = re.sub(r"[^\w\s-]", "-", text)
        # Replace multiple spaces/dashes with single dash
        text = re.sub(r"[-\s]+", "-", text).strip("-").lower()
        return text[:100] if text else "job"

    def _get_translation_field(
        self, obj: Dict[str, Any], field: str, preferred_locale: Optional[str] = None
    ) -> Optional[str]:
        """Extract a translated field from an object's translations mapping."""
        translations = obj.get("translations") or {}
        locale = preferred_locale or self.default_locale

        # Try preferred locale
        if locale in translations and field in translations[locale]:
            val = translations[locale][field]
            if val:
                return val

        # Fallback to german
        if "de" in translations and field in translations["de"]:
            val = translations["de"][field]
            if val:
                return val

        # Fallback to english
        if "en" in translations and field in translations["en"]:
            val = translations["en"][field]
            if val:
                return val

        # Fallback to any available translation
        for lang_data in translations.values():
            if isinstance(lang_data, dict) and field in lang_data and lang_data[field]:
                return lang_data[field]

        return None

    def process_job_data(
        self,
        job_detail: Dict[str, Any],
        share_id: str,
        summary: Optional[Dict[str, Any]] = None,
        lookups: Optional[Tuple[Dict[int, Any], Dict[int, Any], Dict[int, Any]]] = None,
        preferred_locale: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process and extract clean, structured metadata and markdown content."""
        dept_lookup, loc_lookup, comp_lookup = lookups if lookups else ({}, {}, {})

        job_id = job_detail.get("id") or (summary.get("id") if summary else None)
        new_id = job_detail.get("newId") or (summary.get("newId") if summary else None)

        # Title
        title = (
            self._get_translation_field(job_detail, "name", preferred_locale)
            or (self._get_translation_field(summary, "name", preferred_locale) if summary else None)
            or f"Job {job_id}"
        )

        # Company
        company_name = "adesso SE"
        company_id = job_detail.get("companyId") or (summary.get("company", {}).get("id") if summary else None)
        if company_id:
            try:
                comp_obj = comp_lookup.get(int(company_id))
                if comp_obj:
                    company_name = self._get_translation_field(comp_obj, "name", preferred_locale) or company_name
            except Exception:
                pass
        if summary and summary.get("company"):
            company_name = self._get_translation_field(summary["company"], "name", preferred_locale) or company_name

        # Departments
        department_names: List[str] = []
        raw_depts = job_detail.get("departments") or (summary.get("departments") if summary else [])
        for d in raw_depts:
            if isinstance(d, dict):
                d_name = self._get_translation_field(d, "name", preferred_locale)
                if d_name:
                    department_names.append(d_name)
            elif isinstance(d, (int, str)):
                try:
                    d_obj = dept_lookup.get(int(d))
                    if d_obj:
                        d_name = self._get_translation_field(d_obj, "name", preferred_locale)
                        if d_name:
                            department_names.append(d_name)
                except Exception:
                    pass

        # Locations & Countries
        location_names: List[str] = []
        countries: List[str] = []
        raw_locs = job_detail.get("locations") or (summary.get("locations") if summary else [])
        for l in raw_locs:
            if isinstance(l, dict):
                loc_name = self._get_translation_field(l, "name", preferred_locale)
                if loc_name:
                    location_names.append(loc_name)
                country = l.get("country")
                if country and country not in countries:
                    countries.append(country)
            elif isinstance(l, (int, str)):
                try:
                    loc_obj = loc_lookup.get(int(l))
                    if loc_obj:
                        loc_name = self._get_translation_field(loc_obj, "name", preferred_locale)
                        if loc_name:
                            location_names.append(loc_name)
                        country = loc_obj.get("country")
                        if country and country not in countries:
                            countries.append(country)
                except Exception:
                    pass

        # Dates
        created_date = (
            job_detail.get("createdAt")
            or job_detail.get("creationDate")
            or (summary.get("creationDate") if summary else None)
        )
        if created_date and "T" in str(created_date):
            created_date = str(created_date).split("T")[0]

        last_change_date = (
            job_detail.get("lastChangeDate")
            or (summary.get("lastChangeDate") if summary else None)
            or created_date
        )
        if last_change_date and "T" in str(last_change_date):
            last_change_date = str(last_change_date).split("T")[0]

        # Contact person
        contact_name = job_detail.get("contactPersonName") or (summary.get("contactPersonName") if summary else None)
        contact_email = job_detail.get("contactPersonEmail") or (summary.get("contactPersonEmail") if summary else None)
        contact_phone = job_detail.get("contactPersonPhone") or (summary.get("contactPersonPhone") if summary else None)

        # Apply URL
        raw_apply_link = (
            job_detail.get("externalApplyLink")
            or (summary.get("externalApplyLink") if summary else None)
            or ""
        )
        if "{{id}}" in raw_apply_link:
            apply_url = raw_apply_link.replace("{{id}}", f"_s_{share_id}")
        else:
            apply_url = raw_apply_link

        talentry_url = f"{self.base_url}/app/talent/s/{share_id}/jobs/{job_id}/details"

        # HTML Description to Markdown
        html_desc = self._get_translation_field(job_detail, "description", preferred_locale) or ""
        markdown_body = html_to_markdown(html_desc)

        status = "active" if job_detail.get("isActive", True) and not job_detail.get("isDeleted", False) else "inactive"

        return {
            "id": job_id,
            "new_id": new_id,
            "title": title,
            "company": company_name,
            "departments": sorted(list(set(department_names))),
            "locations": sorted(list(set(location_names))),
            "countries": sorted(countries),
            "created_date": created_date,
            "last_change_date": last_change_date,
            "contact_person": {
                "name": contact_name,
                "email": contact_email,
                "phone": contact_phone,
            },
            "apply_url": apply_url,
            "talentry_url": talentry_url,
            "status": status,
            "body": markdown_body,
        }

    def format_markdown_document(self, job_data: Dict[str, Any]) -> str:
        """Format metadata into YAML frontmatter and standard Markdown body."""
        lines = ["---"]
        lines.append(f"id: {job_data['id']}")
        if job_data.get("new_id"):
            lines.append(f'new_id: "{job_data["new_id"]}"')
        # Escape quotes in title
        safe_title = str(job_data['title']).replace('"', '\\"')
        lines.append(f'title: "{safe_title}"')
        lines.append(f'company: "{job_data.get("company", "adesso SE")}"')

        # Departments
        lines.append("departments:")
        for d in job_data.get("departments", []):
            safe_d = str(d).replace('"', '\\"')
            lines.append(f'  - "{safe_d}"')

        # Locations
        lines.append("locations:")
        for loc in job_data.get("locations", []):
            safe_loc = str(loc).replace('"', '\\"')
            lines.append(f'  - "{safe_loc}"')

        # Countries
        lines.append("countries:")
        for c in job_data.get("countries", []):
            lines.append(f'  - "{c}"')

        lines.append(f'created_date: "{job_data.get("created_date") or ""}"')
        lines.append(f'last_change_date: "{job_data.get("last_change_date") or ""}"')

        # Contact person
        contact = job_data.get("contact_person") or {}
        lines.append("contact_person:")
        safe_cname = str(contact.get("name") or "").replace('"', '\\"')
        lines.append(f'  name: "{safe_cname}"')
        lines.append(f'  email: "{contact.get("email") or ""}"')
        lines.append(f'  phone: "{contact.get("phone") or ""}"')

        lines.append(f'apply_url: "{job_data.get("apply_url") or ""}"')
        lines.append(f'talentry_url: "{job_data.get("talentry_url") or ""}"')
        lines.append(f'status: "{job_data.get("status", "active")}"')
        lines.append("---")
        lines.append("")

        # Document Header
        lines.append(f"# {job_data['title']}")
        lines.append("")

        dept_str = ", ".join(job_data.get("departments", [])) or "N/A"
        loc_str = ", ".join(job_data.get("locations", [])) or "N/A"
        countries_str = f" ({', '.join(job_data.get('countries', []))})" if job_data.get("countries") else ""

        lines.append(f"**Unternehmen:** {job_data.get('company', 'adesso SE')}  ")
        lines.append(f"**Bereich / Department:** {dept_str}  ")
        lines.append(f"**Standorte:** {loc_str}{countries_str}  ")
        lines.append(f"**Erstellt:** {job_data.get('created_date') or 'N/A'} | **Aktualisiert:** {job_data.get('last_change_date') or 'N/A'}  ")

        if contact.get("name") or contact.get("email"):
            c_text = contact.get("name", "")
            if contact.get("email"):
                c_text += f" ([{contact['email']}](mailto:{contact['email']}))"
            lines.append(f"**Ansprechpartner:** {c_text}  ")

        if job_data.get("apply_url"):
            lines.append(f"**Bewerbungslink:** [Direkt bewerben]({job_data['apply_url']})  ")

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Stellenbeschreibung")
        lines.append("")

        body = job_data.get("body", "").strip()
        if body:
            lines.append(body)
        else:
            lines.append("*Keine detaillierte Beschreibung verf\u00fcgbar.*")

        lines.append("")
        return "\n".join(lines)

    def export_job(
        self,
        job_detail: Dict[str, Any],
        share_id: str,
        summary: Optional[Dict[str, Any]] = None,
        lookups: Optional[Tuple[Dict[int, Any], Dict[int, Any], Dict[int, Any]]] = None,
        preferred_locale: Optional[str] = None,
    ) -> Tuple[Path, Dict[str, Any]]:
        """Export a job to a Markdown file in the output directory."""
        job_data = self.process_job_data(
            job_detail,
            share_id=share_id,
            summary=summary,
            lookups=lookups,
            preferred_locale=preferred_locale,
        )
        doc_content = self.format_markdown_document(job_data)

        self.output_dir.mkdir(parents=True, exist_ok=True)
        slug = self.slugify(job_data["title"])
        filename = f"{job_data['id']}_{slug}.md"
        filepath = self.output_dir / filename

        filepath.write_text(doc_content, encoding="utf-8")
        job_data["file_path"] = str(filepath)
        job_data["file_name"] = filename
        return filepath, job_data
