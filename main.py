#!/usr/bin/env python3
"""
FOCUS: Funding Opportunity Classification & Understanding System

Command‑line pipeline for ingesting a single Funding Opportunity Announcement
(FOA) from Grants.gov or NSF, normalizing it into a strict schema, applying
deterministic rule‑based semantic tagging, and exporting JSON/CSV artifacts.

Usage:
    python main.py --url "FOA_URL" --out_dir ./out
"""

import argparse
import csv
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

console = Console()

__version__ = "1.0.0"
__author__ = "Pranav Taneja"


@dataclass
class FOA:
    """
    Structured representation of a single Funding Opportunity Announcement.

    This mirrors the required schema and is the central data structure that
    flows through extraction, tagging, and export stages.
    """

    foa_id: str
    title: str
    agency: str
    source: str
    source_url: str
    posted_date: Optional[str]
    close_date: Optional[str]
    description: str
    eligibility: Optional[str] = None
    award_floor: Optional[float] = None
    award_ceiling: Optional[float] = None
    tags_research_domains: List[str] = field(default_factory=list)
    tags_methods: List[str] = field(default_factory=list)
    tags_populations: List[str] = field(default_factory=list)
    tags_themes: List[str] = field(default_factory=list)
    extracted_at: str = ""

    def to_dict(self) -> dict:
        """
        Convert the FOA to a plain dictionary for JSON export.

        List fields are preserved as lists so downstream consumers can treat
        them as proper arrays instead of flattened strings.
        """
        return asdict(self)

    def to_csv_row(self) -> dict:
        """
        Convert the FOA to a flat dictionary suitable for CSV export.

        List fields are serialized as pipe‑separated strings so that the CSV
        remains single‑row, single‑cell per field.
        """
        row = asdict(self)
        row["tags_research_domains"] = "|".join(row["tags_research_domains"])
        row["tags_methods"] = "|".join(row["tags_methods"])
        row["tags_populations"] = "|".join(row["tags_populations"])
        row["tags_themes"] = "|".join(row["tags_themes"])
        return row


class RuleBasedTagger:
    """
    Deterministic semantic tagger using simple keyword matching.

    The ontology below enumerates labels for each category and associates
    each label with a small keyword list. Tag assignment is performed by
    lower‑casing the concatenated title+description and checking membership.
    """

    ONTOLOGY: Dict[str, Dict[str, List[str]]] = {
        "research_domains": {
            "Health & Medicine": [
                "health",
                "medical",
                "clinical",
                "disease",
                "patient",
                "healthcare",
            ],
            "Engineering & Technology": [
                "engineering",
                "technology",
                "computer",
                "software",
                "algorithm",
                "data",
            ],
            "Physical Sciences": [
                "physics",
                "chemistry",
                "materials",
                "astronomy",
            ],
            "Life Sciences": [
                "biology",
                "ecology",
                "genetics",
                "neuroscience",
            ],
            "Social Sciences": [
                "psychology",
                "sociology",
                "economics",
                "political",
            ],
            "Education": [
                "education",
                "pedagogy",
                "teaching",
                "learning",
                "student",
            ],
            "Mathematics": [
                "mathematics",
                "mathematical",
                "statistics",
                "computational",
            ],
            "Environmental Sciences": [
                "environment",
                "climate",
                "sustainability",
                "conservation",
            ],
        },
        "methods": {
            "Clinical Trials": [
                "clinical trial",
                "randomized",
                "placebo",
                "rct",
            ],
            "Laboratory Research": [
                "laboratory",
                "lab",
                "experimental",
                "in vitro",
            ],
            "Computational Modeling": [
                "simulation",
                "mathematical model",
                "computational",
            ],
            "Machine Learning": [
                "machine learning",
                "deep learning",
                "neural network",
                "ai",
                "nlp",
            ],
            "Field Studies": [
                "field study",
                "field work",
                "ethnography",
            ],
            "Survey Research": [
                "survey",
                "questionnaire",
                "interview",
            ],
        },
        "populations": {
            "General Public": [
                "general public",
                "population",
                "community",
            ],
            "Children & Adolescents": [
                "children",
                "pediatric",
                "youth",
                "adolescent",
            ],
            "Elderly": [
                "elderly",
                "senior",
                "geriatric",
            ],
            "Veterans": [
                "veteran",
                "military",
                "service member",
            ],
            "Underserved Communities": [
                "underserved",
                "marginalized",
                "health disparity",
            ],
        },
        "themes": {
            "Innovation & Entrepreneurship": [
                "innovation",
                "entrepreneurship",
                "startup",
                "commercialization",
            ],
            "Workforce Development": [
                "workforce",
                "training",
                "career",
                "professional development",
            ],
            "Climate & Sustainability": [
                "climate",
                "sustainability",
                "renewable",
                "green",
            ],
            "STEM Education": [
                "stem",
                "science education",
                "technology education",
            ],
        },
    }

    def tag(self, title: str, description: str) -> Dict[str, List[str]]:
        """
        Apply rule‑based tagging to the given FOA title and description.

        The method returns a dictionary with the same top‑level keys as the
        ontology (research_domains, methods, populations, themes), each
        containing a list of label strings.
        """
        text_lower = f"{title} {description}".lower()

        tags: Dict[str, List[str]] = {
            "research_domains": [],
            "methods": [],
            "populations": [],
            "themes": [],
        }

        for category, labels in self.ONTOLOGY.items():
            for label, keywords in labels.items():
                if any(keyword.lower() in text_lower for keyword in keywords):
                    tags[category].append(label)

        return tags


class GrantsGovAdapter:
    """
    Adapter for Grants.gov FOAs using the modern JSON REST API.

    This avoids brittle HTML scraping and Grants.gov's WAF issues by using
    the documented unauthenticated `v1/api/fetchOpportunity` endpoint.
    """

    API_BASE = "https://api.grants.gov/v1/api/fetchOpportunity"

    @staticmethod
    def extract_opp_id(url: str) -> str:
        """
        Extract the numeric opportunity ID from a Grants.gov detail URL.

        Raises:
            ValueError: If the opportunity ID cannot be parsed from the URL.
        """
        match = re.search(r"(?:detail/|oppId=)(\d+)", url)
        if match:
            return match.group(1)
        raise ValueError(f"Could not extract opportunity ID from {url!r}.")

    def fetch(self, url: str) -> FOA:
        """
        Fetch and parse a Grants.gov FOA into an FOA object.

        This performs a POST request to the JSON API, normalizes the fields into
        the FOA schema, and strips HTML from the synopsis for a clean
        description.
        """
        opp_id = self.extract_opp_id(url)

        console.print(
            f"[dim]Fetching from API: {self.API_BASE} (POST) for "
            f"opportunity {opp_id}[/dim]"
        )

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36"
            ),
            "Accept": "application/json",
            "Content-Type": "application/json; charset=UTF-8",
        }

        payload = {"opportunityId": int(opp_id)}

        response = requests.post(
            self.API_BASE,
            json=payload,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()

        response_json = response.json()
        data = response_json.get("data", {})
        if not data:
            raise ValueError(
                "No data found in API response. "
                f"Raw response: {response_json!r}"
            )

        synopsis_dict = data.get("synopsis", data)
        synopsis_desc = synopsis_dict.get(
            "synopsisDesc",
            data.get("description", ""),
        )

        if synopsis_desc:
            clean_desc = BeautifulSoup(
                synopsis_desc,
                "html.parser",
            ).get_text(separator=" ")
        else:
            clean_desc = "No description available"

        foa = FOA(
            foa_id=f"grants_gov_{opp_id}",
            title=data.get("opportunityTitle", "Unknown Title"),
            agency=data.get("agencyName", data.get("agencyCode", "Unknown Agency")),
            source="grants_gov",
            source_url=url,
            posted_date=data.get("postDate", synopsis_dict.get("postDate")),
            close_date=data.get("closeDate", synopsis_dict.get("closeDate")),
            description=clean_desc,
            eligibility=synopsis_dict.get("additionalInfoOnEligibility"),
            award_floor=(
                float(synopsis_dict.get("awardFloor", 0))
                if synopsis_dict.get("awardFloor")
                else None
            ),
            award_ceiling=(
                float(synopsis_dict.get("awardCeiling", 0))
                if synopsis_dict.get("awardCeiling")
                else None
            ),
            extracted_at=datetime.now().isoformat(),
        )
        return foa


class NSFAdapter:
    """
    Adapter for NSF FOAs using robust heading‑based DOM traversal.

    The NSF site is structurally inconsistent, so we walk `<h2>/<h3>` headers,
    capturing sibling content until the next header to form logical sections.
    """

    @staticmethod
    def _build_sections(soup: BeautifulSoup) -> Dict[str, str]:
        """
        Build a mapping from normalized section name to concatenated text.

        Section names are lower‑cased header text; content is all sibling text
        up to (but not including) the next header tag.
        """
        sections: Dict[str, str] = {}

        for header in soup.find_all(["h2", "h3"]):
            section_name = header.get_text(strip=True).lower()
            content_parts: List[str] = []

            for sibling in header.find_next_siblings():
                if sibling.name in {"h2", "h3"}:
                    break
                content_parts.append(sibling.get_text(strip=True))

            sections[section_name] = " ".join(content_parts)

        return sections

    def fetch(self, url: str) -> FOA:
        """
        Fetch and parse an NSF FOA into an FOA object.

        This performs a plain GET, extracts the title and key sections
        (description, eligibility, award information) using DOM traversal, and
        then normalizes them into the FOA schema.
        """
        console.print(f"[dim]Fetching from URL: {url}[/dim]")

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36"
            )
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        title_elem = soup.find("h1")
        title = title_elem.get_text(strip=True) if title_elem else "Unknown"

        sections = self._build_sections(soup)

        description = (
            sections.get("program description")
            or sections.get("synopsis of program")
            or sections.get("synopsis")
            or "No description available"
        )

        eligibility = sections.get("eligibility")

        # Attempt to infer award floor/ceiling from a free‑text "award information"
        # section using simple currency regexes.
        award_floor: Optional[float] = None
        award_ceiling: Optional[float] = None
        award_text = sections.get("award information", "")
        if award_text:
            amounts = re.findall(r"\$[\d,]+", award_text)
            if len(amounts) >= 2:
                try:
                    award_floor = float(amounts[0].replace("$", "").replace(",", ""))
                    award_ceiling = float(amounts[1].replace("$", "").replace(",", ""))
                except ValueError:
                    # If parsing fails, leave award fields as None.
                    pass

        # Deterministic ID so the same URL always maps to the same identifier.
        foa_id = f"nsf_{hashlib.md5(url.encode()).hexdigest()[:8]}"

        foa = FOA(
            foa_id=foa_id,
            title=title,
            agency="NSF",
            source="nsf",
            source_url=url,
            posted_date=None,
            close_date=None,
            description=description[:5000],  # hard cap to avoid giant blobs
            eligibility=eligibility,
            award_floor=award_floor,
            award_ceiling=award_ceiling,
            extracted_at=datetime.now().isoformat(),
        )
        return foa


def detect_source(url: str) -> str:
    """
    Detect which upstream source the given URL belongs to.

    Returns:
        "grants_gov" or "nsf".

    Raises:
        ValueError: If the URL does not match a supported provider.
    """
    url_lower = url.lower()
    if "grants.gov" in url_lower:
        return "grants_gov"
    if "nsf.gov" in url_lower:
        return "nsf"
    raise ValueError(f"Unsupported URL source: {url!r}.")


def apply_tags(foa: FOA, tagger: RuleBasedTagger) -> FOA:
    """
    Enrich an FOA instance with semantic tags using the provided tagger.

    The original FOA object is mutated in place for convenience and is
    also returned so the function is chainable.
    """
    tags = tagger.tag(foa.title, foa.description)

    foa.tags_research_domains = tags["research_domains"]
    foa.tags_methods = tags["methods"]
    foa.tags_populations = tags["populations"]
    foa.tags_themes = tags["themes"]

    return foa


def export_json(foa: FOA, output_path: Path) -> None:
    """
    Export a single FOA to a pretty‑printed UTF‑8 JSON file.
    """
    data = foa.to_dict()
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)

    console.print(
        "[bold green]✓[/bold green] JSON exported to "
        f"[cyan]{output_path}[/cyan]"
    )


def export_csv(foa: FOA, output_path: Path) -> None:
    """
    Export a single FOA to a one‑row CSV file.

    The CSV header is fixed to keep the schema explicit and reproducible.
    """
    data = foa.to_csv_row()
    fieldnames = [
        "foa_id",
        "title",
        "agency",
        "source",
        "source_url",
        "posted_date",
        "close_date",
        "award_floor",
        "award_ceiling",
        "eligibility",
        "description",
        "tags_research_domains",
        "tags_methods",
        "tags_populations",
        "tags_themes",
        "extracted_at",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()
        writer.writerow(data)

    console.print(
        "[bold green]✓[/bold green] CSV exported to "
        f"[cyan]{output_path}[/cyan]"
    )


def main() -> None:
    """
    CLI entry point for the FOCUS FOA intelligence pipeline.

    Parses arguments, detects the source (Grants.gov vs NSF), runs the
    appropriate adapter, applies semantic tagging, and writes JSON/CSV
    outputs along with a Rich summary panel.
    """
    parser = argparse.ArgumentParser(
        description=f"FOCUS v{__version__} - FOA Intelligence Pipeline",
        epilog="For issues: https://github.com/ConfusedNeuron/FOCUS.git",
    )
    parser.add_argument(
        "--url",
        required=True,
        help="FOA URL (Grants.gov or NSF).",
    )
    parser.add_argument(
        "--out_dir",
        default="./out",
        help="Output directory (default: ./out).",
    )
    parser.add_argument(
        "--filename",
        default="foa",
        help="Base name for output files (default: foa).",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Rich header for a nicer CLI UX.
    console.print()
    console.print(
        Rule(
            "[bold cyan]FOCUS: Funding Opportunity Classification & "
            "Understanding System[/bold cyan]",
            style="cyan",
        )
    )
    console.print(
        "[bold dim]FOA Intelligence Pipeline - Screening Task[/bold dim]",
        justify="center",
    )
    console.print()

    try:
        source = detect_source(args.url)
        console.print(
            "[*] Detected source: "
            f"[bold magenta]{source}[/bold magenta]"
        )

        if source == "grants_gov":
            adapter = GrantsGovAdapter()
        else:
            adapter = NSFAdapter()

        foa = adapter.fetch(args.url)

        console.print(
            "[bold green]✓[/bold green] Extracted FOA: "
            f"[bold]{foa.title}[/bold]"
        )

        tagger = RuleBasedTagger()
        apply_tags(foa, tagger)

        json_path = out_dir / f"{args.filename}.json"
        csv_path = out_dir / f"{args.filename}.csv"
        export_json(foa, json_path)
        export_csv(foa, csv_path)

        console.print()

        # Render a compact Rich table summarizing assigned tags by category.
        tag_table = Table(
            show_header=True,
            header_style="bold magenta",
        )
        tag_table.add_column("Category", style="cyan")
        tag_table.add_column("Assigned Tags", style="green")

        tag_table.add_row(
            "Research Domains",
            ", ".join(foa.tags_research_domains) or "None",
        )
        tag_table.add_row(
            "Methods",
            ", ".join(foa.tags_methods) or "None",
        )
        tag_table.add_row(
            "Populations",
            ", ".join(foa.tags_populations) or "None",
        )
        tag_table.add_row(
            "Themes",
            ", ".join(foa.tags_themes) or "None",
        )

        success_panel = Panel(
            tag_table,
            title=(
                "[bold green]✅ Successfully Extracted: "
                f"{foa.foa_id}[/bold green]"
            ),
            subtitle=f"[dim]Saved to {json_path}[/dim]",
            expand=False,
            border_style="green",
        )
        console.print(success_panel)
        console.print()

    except Exception as exc:  # noqa: BLE001
        # Fail fast with a clear, visually distinct error panel.
        error_panel = Panel(
            f"[bold red]{exc}[/bold red]",
            title="[bold red]❌ Fatal Error[/bold red]",
            expand=False,
            border_style="red",
        )
        console.print()
        console.print(error_panel)
        console.print()
        sys.exit(1)


if __name__ == "__main__":
    main()
