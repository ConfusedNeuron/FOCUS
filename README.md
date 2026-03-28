# FOCUS: Funding Opportunity Classification & Understanding System
___

## AI-Powered Funding Intelligence – GSoC Screening Task

**Project:** ISSR4 – AI-Powered Funding Intelligence (FOA Ingestion + Semantic Tagging)

**Author:** Pranav Taneja

---

### Overview

This repository contains the screening task implementation for the ISSR4 project. It provides a lightweight, deterministic, and highly robust CLI pipeline that ingests Funding Opportunity Announcements (FOAs) from **Grants.gov** and the **National Science Foundation (NSF)**, normalizes the data into a strict schema, applies rule-based semantic tagging, and exports the results to reproducible JSON and CSV formats.

---

### Quick Start

#### Installation

```bash
## Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate  ## On Windows: venv\Scripts\activate

## Install requirements
pip install -r requirements.txt
```

#### Usage

The pipeline strictly adheres to the requested execution format and dynamically detects the source based on the provided URL.

**View Help Menu:**
You can view all available commands, descriptions, and optional flags (like custom file naming) using the built-in help argument:

```bash
python main.py -h
```

##### Grants.gov example

```bash
python main.py \
  --url "https://www.grants.gov/search-results-detail/349207" \
  --out_dir ./out
```

##### NSF example

```bash
python main.py \
  --url "https://www.nsf.gov/funding/opportunities/grfp-nsf-graduate-research-fellowship-program" \
  --out_dir ./out
```

#### 🛡️ Edge Case & Robustness Testing

This pipeline was engineered to handle highly variable structural anomalies that typical web scrapers fail on. Reviewers are encouraged to test the following edge-case URLs:

**1. The Grants.gov WAF Bypass (API Routing)**
Standard scrapers often receive a `403 Forbidden` or `405 Method Not Allowed` on this URL due to internal redirects. Our pipeline uses the `v1/api/fetchOpportunity` POST endpoint to ingest it flawlessly.
```bash
python main.py \
   --url "https://www.grants.gov/search-results-detail/352603" \
   --out_dir ./out
```

**2. The NSF Structural Anomaly (DOM Traversal)**
Many NSF pages lack a standard "Synopsis" tag, breaking regex-based extractors. Our heading-based DOM traversal dynamically captures the program description regardless of layout.

```Bash
python main.py \
   --url "https://www.nsf.gov/funding/opportunities/computer-and-information-science-and-engineering-core-programs" \
   --out_dir ./out
```
---

### Key Engineering Decisions

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

### Semantic Tagging Ontology

The `RuleBasedTagger` utilizes a strict deterministic dictionary covering 23 labels across 4 categories, triggered by keyword matching within the FOA title and description.

### Evaluation & Accuracy Metrics

To satisfy the "Basic Evaluation" requirement and ensure tagging consistency, this repository includes a standalone evaluation module. It calculates strict multi-label metrics (Precision, Recall, and F1-Score) by comparing the pipeline's deterministic output against a manually annotated Golden Dataset of diverse funding opportunities.

**Run the Evaluation:**
```bash
python evaluate.py
```
Note: The evaluation script imports the core tagger directly to test algorithmic accuracy in isolation, executing instantly without requiring live network requests.

#### Research domains

- Health & Medicine
- Engineering & Technology
- Physical Sciences
- Life Sciences
- Social Sciences
- Education
- Mathematics
- Environmental Sciences

#### Methods

- Clinical Trials
- Laboratory Research
- Computational Modeling
- Machine Learning
- Field Studies
- Survey Research

#### Populations

- General Public
- Children & Adolescents
- Elderly
- Veterans
- Underserved Communities

#### Themes

- Innovation & Entrepreneurship
- Workforce Development
- Climate & Sustainability
- STEM Education

---

### File Manifest

- `main.py` – Core object-oriented extraction and tagging pipeline.
- `evaluate.py` – Standalone evaluation module computing pipeline accuracy metrics.
- `requirements.txt` – Minimal dependencies (`requests`, `beautifulsoup4`).
- `README.md` – System documentation.
- `out/foa.json` – Sample structured JSON output.
- `out/foa.csv` – Sample flattened CSV output.

---

### Future Roadmap

While this script strictly follows the “minimal single URL” constraint of the screening task, the full GSoC implementation architecture will introduce:

- **Bulk ingestion layer:** Async processing of URL lists via CSV/TXT uploads.
- **Interactive UI:** A lightweight Streamlit dashboard allowing non-technical research teams to query and filter funding intelligence dynamically.
- **Advanced parsing:** Utilizing Cloudflare’s `/crawl` browser rendering endpoint to autonomously translate highly unstructured agency sites into LLM-ready markdown.
- **Hybrid tagging:** Transitioning from deterministic dictionaries to sentence-transformers for semantic similarity scoring.

