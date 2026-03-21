# India Jobs Data

Inspired by [karpathy/jobs](https://github.com/karpathy/jobs) — an interactive visualization of the US job market using Bureau of Labor Statistics data. This project aims to build the same thing for India using government microdata.

## Data Sources

- **[PLFS 2024](https://microdata.gov.in/NADA/index.php/catalog/254)** — Periodic Labour Force Survey (January-December 2024), person-level microdata from India's Ministry of Statistics (MoSPI). 415,549 person records with occupation codes, employment status, and earnings.
- **[NCO 2015](https://dgt.gov.in/nco-2015)** — National Classification of Occupations, India's equivalent of the US SOC system. Extracted from the official PDF into structured JSON.
- **AI Exposure Scores** — LLM-generated scores (0-10) for each occupation group using Gemini 3 Flash via OpenRouter, following the same methodology as karpathy/jobs.

## What We Have

| Dataset | File | Records |
|---|---|---|
| NCO-2015 occupation taxonomy | `public/data/nco_families.json` | 435 families across 127 groups |
| Employment & pay stats | `public/data/plfs_stats.json` | 127 occupation groups, ~467M workers |
| AI exposure scores | `public/data/ai_scores.json` | 127 groups scored 0-10 with rationale |

### Per-occupation data fields

- **workers** — estimated employment (weighted from PLFS sample)
- **median_monthly_pay** — weighted median monthly earnings in INR
- **pay_25th / pay_75th** — pay distribution percentiles
- **exposure** — AI exposure score (0-10) with rationale
- **skill_level** — NCO skill level (1-4)
- **education** — typical education requirement from NCO

## Key Differences from karpathy/jobs

| | karpathy/jobs (US) | This project (India) |
|---|---|---|
| Occupations | 342 (SOC-based) | 127 groups / 435 families (NCO 2015) |
| Employment data | BLS projections | PLFS 2024 microdata |
| Pay | Annual median (USD) | Monthly median (INR) |
| Outlook | 10-year BLS projection (%) | Not yet available — needs two PLFS rounds |
| AI scores | Gemini Flash via detailed BLS descriptions | Gemini Flash via occupation title + context |
| Total workers | ~160M | ~467M |

### What's missing

- **Outlook data** — requires downloading a second PLFS round and computing year-over-year employment change per occupation
- **Frontend visualization** — the interactive treemap is not built yet
- **Detailed occupation descriptions** — we score AI exposure using titles and stats rather than full job descriptions (BLS has rich multi-paragraph descriptions per occupation)

## Scripts

```bash
# Extract NCO occupation taxonomy from PDF
uv run python scripts/extract_nco.py

# Compute pay & employment stats from PLFS microdata
uv run python scripts/compute_plfs_stats.py

# Score AI exposure for each occupation (requires OPENROUTER_API_KEY)
uv run python scripts/score_ai_exposure.py
```

## Setup

```bash
uv sync
cp .envrc.example .envrc  # add your API keys
```

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).
