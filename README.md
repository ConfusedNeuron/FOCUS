# AI-Powered Funding Intelligence – GSoC Screening Task

**Project:** ISSR4 – AI-Powered Funding Intelligence (FOA Ingestion + Semantic Tagging)
**Author:** Pranav Taneja

---

## Overview

This repository contains the screening task implementation for the ISSR4 project. It provides a lightweight, deterministic, and highly robust CLI pipeline that ingests Funding Opportunity Announcements (FOAs) from **Grants.gov** and the **National Science Foundation (NSF)**, normalizes the data into a strict schema, applies rule-based semantic tagging, and exports the results to reproducible JSON and CSV formats.

---

## Quick Start

### Installation

```bash
# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

### Usage

The pipeline strictly adheres to the requested execution format and dynamically detects the source based on the provided URL.

#### Grants.gov example

```bash
python main.py \
  --url "https://www.grants.gov/search-results-detail/349207" \
  --out_dir ./out
```

#### NSF example

```bash
python main.py \
  --url "https://www.nsf.gov/funding/pgm_summ.jsp?pims_id=505658" \
  --out_dir ./out
```

---

## Key Engineering Decisions

To ensure the pipeline is resilient, scalable, and reproducible, several specific architectural choices were made over standard web scraping techniques:

1. **Grants.gov: WAF evasion via official v1 API**

   Standard GET requests to Grants.gov frequently fail due to their Web Application Firewall (WAF) and internal server redirects (resulting in `405 Method Not Allowed` errors).

   **Solution:** Instead of relying on brittle headless browsers (e.g., Selenium) or legacy endpoints, this pipeline interfaces directly with the modern, unauthenticated `v1/api/fetchOpportunity` REST API using structured JSON POST payloads. This guarantees stable, structured data retrieval.

2. **NSF: Heading-based DOM traversal**

   NSF HTML pages exhibit high structural variability, making standard regex extraction highly brittle, particularly for the **Eligibility** and **Synopsis** sections.

   **Solution:** The `NSFAdapter` utilizes intelligent DOM traversal via BeautifulSoup. It detects `<h2>` and `<h3>` tags and captures all sibling elements until the next major header. This layout-agnostic approach drastically reduces extraction errors.

3. **Data integrity & reproducibility**

   - **Deterministic IDs:** NSF URLs are parsed using MD5 hashing to ensure the generated `foa_id` is identical across every run.
   - **Type preservation:** Semantic tags are preserved as strict JSON arrays in `foa.json` for downstream data engineering, and gracefully flattened into pipe-separated strings (`|`) for the `foa.csv` export.

---

## Semantic Tagging Ontology

The `RuleBasedTagger` utilizes a strict deterministic dictionary covering 23 labels across 4 categories, triggered by keyword matching within the FOA title and description.

### Research domains

- Health & Medicine
- Engineering & Technology
- Physical Sciences
- Life Sciences
- Social Sciences
- Education
- Mathematics
- Environmental Sciences

### Methods

- Clinical Trials
- Laboratory Research
- Computational Modeling
- Machine Learning
- Field Studies
- Survey Research

### Populations

- General Public
- Children & Adolescents
- Elderly
- Veterans
- Underserved Communities

### Themes

- Innovation & Entrepreneurship
- Workforce Development
- Climate & Sustainability
- STEM Education

---

## File Manifest

- `main.py` – Core object-oriented extraction and tagging pipeline.
- `requirements.txt` – Minimal dependencies (`requests`, `beautifulsoup4`).
- `README.md` – System documentation.
- `out/foa.json` – Sample structured JSON output.
- `out/foa.csv` – Sample flattened CSV output.

---

## Future Roadmap (GSoC Proposal Teaser)

While this script strictly follows the “minimal single URL” constraint of the screening task, the full GSoC implementation architecture will introduce:

- **Bulk ingestion layer:** Async processing of URL lists via CSV/TXT uploads.
- **Interactive UI:** A lightweight Streamlit dashboard allowing non-technical research teams to query and filter funding intelligence dynamically.
- **Advanced parsing:** Utilizing Cloudflare’s `/crawl` browser rendering endpoint to autonomously translate highly unstructured agency sites into LLM-ready markdown.
- **Hybrid tagging:** Transitioning from deterministic dictionaries to sentence-transformers for semantic similarity scoring.

