#!/usr/bin/env python3
"""
FOA Intelligence Pipeline - Screening Task
Robust script for single FOA ingestion with deterministic rule-based tagging
and production-ready data normalization.

Usage: python main.py --url "FOA_URL" --out_dir ./out
"""

import argparse
import json
import csv
import re
import sys
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict, field

import requests
from bs4 import BeautifulSoup

# For enhanced terminal output
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule

console = Console()


@dataclass
class FOA:
    """FOA data structure matching required schema"""
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
        """Convert to dictionary for JSON export (preserves lists)"""
        return asdict(self)

    def to_csv_row(self) -> dict:
        """Convert to CSV row, flattening lists to pipe-separated strings"""
        row = asdict(self)
        row['tags_research_domains'] = "|".join(row['tags_research_domains'])
        row['tags_methods'] = "|".join(row['tags_methods'])
        row['tags_populations'] = "|".join(row['tags_populations'])
        row['tags_themes'] = "|".join(row['tags_themes'])
        return row


class RuleBasedTagger:
    """Deterministic semantic tagger using keyword matching"""

    ONTOLOGY = {
        "research_domains": {
            "Health & Medicine": ["health", "medical", "clinical", "disease", "patient", "healthcare"],
            "Engineering & Technology": ["engineering", "technology", "computer", "software", "algorithm", "data"],
            "Physical Sciences": ["physics", "chemistry", "materials", "astronomy"],
            "Life Sciences": ["biology", "ecology", "genetics", "neuroscience"],
            "Social Sciences": ["psychology", "sociology", "economics", "political"],
            "Education": ["education", "pedagogy", "teaching", "learning", "student"],
            "Mathematics": ["mathematics", "mathematical", "statistics", "computational"],
            "Environmental Sciences": ["environment", "climate", "sustainability", "conservation"],
        },
        "methods": {
            "Clinical Trials": ["clinical trial", "randomized", "placebo", "rct"],
            "Laboratory Research": ["laboratory", "lab", "experimental", "in vitro"],
            "Computational Modeling": ["simulation", "mathematical model", "computational"],
            "Machine Learning": ["machine learning", "deep learning", "neural network", "ai", "nlp"],
            "Field Studies": ["field study", "field work", "ethnography"],
            "Survey Research": ["survey", "questionnaire", "interview"],
        },
        "populations": {
            "General Public": ["general public", "population", "community"],
            "Children & Adolescents": ["children", "pediatric", "youth", "adolescent"],
            "Elderly": ["elderly", "senior", "geriatric"],
            "Veterans": ["veteran", "military", "service member"],
            "Underserved Communities": ["underserved", "marginalized", "health disparity"],
        },
        "themes": {
            "Innovation & Entrepreneurship": ["innovation", "entrepreneurship", "startup", "commercialization"],
            "Workforce Development": ["workforce", "training", "career", "professional development"],
            "Climate & Sustainability": ["climate", "sustainability", "renewable", "green"],
            "STEM Education": ["stem", "science education", "technology education"],
        }
    }

    def tag(self, title: str, description: str) -> Dict[str, List[str]]:
        """Apply rule-based tagging to title and description"""
        text_lower = f"{title} {description}".lower()

        tags = {
            "research_domains": [],
            "methods": [],
            "populations": [],
            "themes": []
        }

        for category, labels in self.ONTOLOGY.items():
            for label, keywords in labels.items():
                if any(keyword.lower() in text_lower for keyword in keywords):
                    tags[category].append(label)

        return tags


class GrantsGovAdapter:
    """Adapter for Grants.gov FOAs using the modern REST API"""

    API_BASE = "https://api.grants.gov/v1/api/fetchOpportunity"

    def extract_opp_id(self, url: str) -> str:
        """Extract opportunity ID from URL"""
        match = re.search(r'(?:detail/|oppId=)(\d+)', url)
        if match:
            return match.group(1)
        raise ValueError(f"Could not extract opportunity ID from {url}")

    def fetch(self, url: str) -> FOA:
        """Fetch and parse Grants.gov FOA using modern JSON API"""
        opp_id = self.extract_opp_id(url)

        console.print(f"[dim]Fetching from API: {self.API_BASE} (POST)[/dim]")

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json; charset=UTF-8"
        }

        payload = {"opportunityId": int(opp_id)}

        response = requests.post(self.API_BASE, json=payload, headers=headers, timeout=30)
        response.raise_for_status()

        response_json = response.json()

        data = response_json.get('data', {})
        if not data:
            raise ValueError(f"No data found in API response. Raw response: {response_json}")

        synopsis_dict = data.get('synopsis', data)
        synopsis_desc = synopsis_dict.get('synopsisDesc', data.get('description', ''))

        clean_desc = BeautifulSoup(synopsis_desc, "html.parser").get_text(separator=' ') if synopsis_desc else "No description available"

        foa = FOA(
            foa_id=f"grants_gov_{opp_id}",
            title=data.get('opportunityTitle', 'Unknown Title'),
            agency=data.get('agencyName', data.get('agencyCode', 'Unknown Agency')),
            source="grants_gov",
            source_url=url,
            posted_date=data.get('postDate', synopsis_dict.get('postDate', None)),
            close_date=data.get('closeDate', synopsis_dict.get('closeDate', None)),
            description=clean_desc,
            eligibility=synopsis_dict.get('additionalInfoOnEligibility', None),
            award_floor=float(synopsis_dict.get('awardFloor', 0)) if synopsis_dict.get('awardFloor') else None,
            award_ceiling=float(synopsis_dict.get('awardCeiling', 0)) if synopsis_dict.get('awardCeiling') else None,
            extracted_at=datetime.now().isoformat()
        )
        return foa


class NSFAdapter:
    """Adapter for NSF FOAs using robust DOM traversal"""

    def fetch(self, url: str) -> FOA:
        """Fetch and parse NSF FOA"""
        console.print(f"[dim]Fetching from URL: {url}[/dim]")

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        title_elem = soup.find('h1')
        title = title_elem.get_text(strip=True) if title_elem else "Unknown"

        sections = {}
        for header in soup.find_all(['h2', 'h3']):
            section_name = header.get_text(strip=True).lower()
            content = []

            for sibling in header.find_next_siblings():
                if sibling.name in ['h2', 'h3']:
                    break
                content.append(sibling.get_text(strip=True))

            sections[section_name] = ' '.join(content)

        description = (
            sections.get('program description', '') or
            sections.get('synopsis of program', '') or
            sections.get('synopsis', '') or
            "No description available"
        )

        eligibility = sections.get('eligibility', None)

        award_floor, award_ceiling = None, None
        award_text = sections.get('award information', '')
        if award_text:
            amounts = re.findall(r'\$[\d,]+', award_text)
            if len(amounts) >= 2:
                try:
                    award_floor = float(amounts[0].replace('$', '').replace(',', ''))
                    award_ceiling = float(amounts[1].replace('$', '').replace(',', ''))
                except ValueError:
                    pass

        foa_id = f"nsf_{hashlib.md5(url.encode()).hexdigest()[:8]}"

        foa = FOA(
            foa_id=foa_id,
            title=title,
            agency="NSF",
            source="nsf",
            source_url=url,
            posted_date=None,
            close_date=None,
            description=description[:5000],
            eligibility=eligibility,
            award_floor=award_floor,
            award_ceiling=award_ceiling,
            extracted_at=datetime.now().isoformat()
        )
        return foa


def detect_source(url: str) -> str:
    """Detect which source the URL is from"""
    url_lower = url.lower()
    if "grants.gov" in url_lower:
        return "grants_gov"
    elif "nsf.gov" in url_lower:
        return "nsf"
    else:
        raise ValueError(f"Unsupported URL source: {url}")


def apply_tags(foa: FOA, tagger: RuleBasedTagger) -> FOA:
    """Apply semantic tags to FOA preserving array structures"""
    tags = tagger.tag(foa.title, foa.description)

    foa.tags_research_domains = tags["research_domains"]
    foa.tags_methods = tags["methods"]
    foa.tags_populations = tags["populations"]
    foa.tags_themes = tags["themes"]

    return foa


def export_json(foa: FOA, output_path: Path):
    """Export FOA to JSON format"""
    data = foa.to_dict()
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    console.print(f"[bold green]✓[/bold green] JSON exported to [cyan]{output_path}[/cyan]")


def export_csv(foa: FOA, output_path: Path):
    """Export FOA to CSV format"""
    data = foa.to_csv_row()
    fieldnames = [
        'foa_id', 'title', 'agency', 'source', 'source_url',
        'posted_date', 'close_date', 'award_floor', 'award_ceiling',
        'eligibility', 'description',
        'tags_research_domains', 'tags_methods', 'tags_populations', 'tags_themes',
        'extracted_at'
    ]

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerow(data)
    console.print(f"[bold green]✓[/bold green] CSV exported to [cyan]{output_path}[/cyan]")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='FOA Intelligence Pipeline - Extract and tag funding opportunities'
    )
    parser.add_argument('--url', required=True, help='FOA URL (Grants.gov or NSF)')
    parser.add_argument('--out_dir', default='./out', help='Output directory (default: ./out)')
    parser.add_argument('--filename', default='foa', help='Base name for output files (default: foa)')
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Rich Header
    console.print("\n")
    console.print(Rule("[bold cyan]FOCUS: Funding Opportunity Classification & Understanding System[/bold cyan]", style="cyan"))
    console.print("[bold dim]FOA Intelligence Pipeline - Screening Task[/bold dim]", justify="center")
    console.print("\n")

    try:
        source = detect_source(args.url)
        console.print(f"[*] Detected source: [bold magenta]{source}[/bold magenta]")

        if source == "grants_gov":
            adapter = GrantsGovAdapter()
            foa = adapter.fetch(args.url)
        elif source == "nsf":
            adapter = NSFAdapter()
            foa = adapter.fetch(args.url)

        console.print(f"[bold green]✓[/bold green] Extracted FOA: [bold]{foa.title}[/bold]")

        tagger = RuleBasedTagger()
        foa = apply_tags(foa, tagger)

        export_json(foa, out_dir / f'{args.filename}.json')
        export_csv(foa, out_dir / f'{args.filename}.csv')

        console.print("\n")

        # Rich Table
        tag_table = Table(show_header=True, header_style="bold magenta")
        tag_table.add_column("Category", style="cyan")
        tag_table.add_column("Assigned Tags", style="green")

        tag_table.add_row("Research Domains", ", ".join(foa.tags_research_domains) if foa.tags_research_domains else "None")
        tag_table.add_row("Methods", ", ".join(foa.tags_methods) if foa.tags_methods else "None")
        tag_table.add_row("Populations", ", ".join(foa.tags_populations) if foa.tags_populations else "None")
        tag_table.add_row("Themes", ", ".join(foa.tags_themes) if foa.tags_themes else "None")

        # Rich Success Panel
        success_panel = Panel(
            tag_table,
            title=f"[bold green]✅ Successfully Extracted: {foa.foa_id}[/bold green]",
            subtitle=f"[dim]Saved to {out_dir}/{args.filename}.json[/dim]",
            expand=False,
            border_style="green"
        )
        console.print(success_panel)
        console.print("\n")

    except Exception as e:
        # Rich Error Panel
        error_panel = Panel(
            f"[bold red]{str(e)}[/bold red]",
            title="[bold red]❌ Fatal Error[/bold red]",
            expand=False,
            border_style="red"
        )
        console.print("\n")
        console.print(error_panel)
        console.print("\n")
        sys.exit(1)


if __name__ == '__main__':
    main()
