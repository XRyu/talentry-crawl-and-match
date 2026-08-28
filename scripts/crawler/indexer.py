"""
Index and catalog generator for crawled Talentry jobs.
Creates a comprehensive README.md index table and an index.json catalog.
"""

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


def generate_index(jobs: List[Dict[str, Any]], output_dir: Path) -> Tuple[Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Generate index.json (excluding heavy body text for fast lookups)
    catalog = []
    for job in jobs:
        entry = {k: v for k, v in job.items() if k != "body"}
        catalog.append(entry)

    json_path = output_dir / "index.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    # 2. Generate README.md
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_jobs = len(jobs)

    # Calculate stats
    dept_counter = Counter()
    loc_counter = Counter()
    for job in jobs:
        for d in job.get("departments", []):
            dept_counter[d] += 1
        for l in job.get("locations", []):
            loc_counter[l] += 1

    lines = []
    lines.append("# adesso Stellenangebote (Talentry Job Index)")
    lines.append("")
    lines.append(f"> **Zuletzt aktualisiert:** {now_str} | **Gesamtanzahl:** {total_jobs} offene Stellen")
    lines.append("")

    # Statistics Section
    lines.append("## Übersicht & Statistiken")
    lines.append("")
    lines.append(f"- **Offene Stellen:** {total_jobs}")
    lines.append(f"- **Fachbereiche / Departments:** {len(dept_counter)}")
    lines.append(f"- **Standorte:** {len(loc_counter)}")
    lines.append("")

    # Top Departments
    lines.append("### Top Fachbereiche")
    lines.append("")
    for dept, count in dept_counter.most_common(8):
        lines.append(f"- **{dept}:** {count} Positionen")
    lines.append("")

    # Table of All Jobs
    lines.append("## Alle Stellenangebote")
    lines.append("")
    lines.append("| Titel | Bereich | Standorte | Aktualisiert | Bewerbung |")
    lines.append("| :--- | :--- | :--- | :--- | :--- |")

    # Sort jobs by title or last_change_date
    sorted_jobs = sorted(jobs, key=lambda x: str(x.get("title", "")).lower())

    for job in sorted_jobs:
        title = job.get("title", "Job").replace("|", "\\|")
        file_name = job.get("file_name", f"{job.get('id')}.md")
        dept_str = ", ".join(job.get("departments", [])) or "-"
        dept_str = dept_str.replace("|", "\\|")
        loc_str = ", ".join(job.get("locations", [])) or "-"
        loc_str = loc_str.replace("|", "\\|")
        updated = job.get("last_change_date") or "-"
        apply_url = job.get("apply_url")
        apply_link = f"[Bewerben]({apply_url})" if apply_url else "-"

        lines.append(f"| [{title}]({file_name}) | {dept_str} | {loc_str} | {updated} | {apply_link} |")

    lines.append("")

    readme_path = output_dir / "README.md"
    readme_path.write_text("\n".join(lines), encoding="utf-8")

    return json_path, readme_path
