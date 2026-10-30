# Perioperative and wound-related safety signals of psoriasis biologics in FAERS

Analysis code and derived data for a disproportionality analysis, with case-level
attribution assessment, of five biologics used in psoriasis and psoriatic arthritis
(adalimumab, secukinumab, ixekizumab, ustekinumab, guselkumab) and wound-healing,
infection, and surgery-related adverse events reported to the US FDA Adverse Event
Reporting System (FAERS).

## Data source and provenance

All counts and records are derived from the public **openFDA Drug Event API**
(https://open.fda.gov), covering reports received from 1 January 2004 through
1 July 2026 (inclusive). The underlying individual case safety reports are publicly
available from openFDA and are **not** redistributed here; this repository contains
only the aggregate counts, derived record tables, and analysis code needed to
reproduce the published results.

Adverse events were identified by MedDRA Preferred Terms as coded in the FAERS
dataset served by openFDA. Because reports span 2004–2026, terms reflect the MedDRA
version current at the time each report was coded; no single MedDRA version applies
to the dataset.

## Repository layout

```
scripts/
  01_query_single_biologic.py     openFDA count queries -> single-biologic universe (main analysis)
  02_retrieve_single_records.py   full single-biologic record retrieval (characteristics, time-to-report)
  03_query_hcp_only.py            healthcare-professional-only sensitivity queries
  04_report_characteristics.py    report-characteristics counts (Table 1)
  05_compute_disproportionality.py  ROR/PRR/IC computation from the universe files (no network)
data/
  universe/   P, N0, N0xterm, and per drug-PT single-biologic counts (main + HCP)
  records/    single-biologic record-level tables and drug-start-to-report intervals
  results/    computed result tables (main, HCP, staged, characteristics, time, source)
```

## Reproducing the analysis

1. **Data retrieval** (requires a free openFDA API key; scripts 01–04). Paste your key
   into the `API_KEY` variable of each script and run it. These scripts query the
   openFDA API and write the files in `data/universe/` and `data/records/`.
2. **Disproportionality computation** (no network; script 05). Run
   `python scripts/05_compute_disproportionality.py` to regenerate
   `data/results/RESULT_table2_v4_main.csv` and `data/results/faers_v6_hcp_results.csv`
   from the universe files.

## Method summary

For each drug–PT combination a 2×2 table is built within a single-biologic analytic
universe U′ (reports listing none, or exactly one, of the five target biologics), so
that all four cells derive from the same population:

- `a` = single-biologic reports for the drug mentioning the PT
- `b` = `n_single(drug) − a`
- `c` = PT count in U′ − a
- `d` = (U′ − `n_single(drug)`) − c

Measures: ROR and PRR (0.5 continuity correction, 95% CI from log standard error);
information component IC = log2((a+0.5)/(E+0.5)) with E = (a+b)(a+c)/U′ and IC025 by
the Norén (2006) approximation. A signal requires the lower 95% bound of both ROR and
PRR > 1, a ≥ 3, and IC025 > 0.

Key universe totals (main analysis): source population P = 673,670; multi-biologic
reports excluded = 16,338 (2.4%); single-biologic universe U′ = 657,332. HCP-only
sensitivity universe U′ = 322,218.

## Software

Computation and figures: Python 3.13 (pandas 3.0.5, numpy 2.5.3, scipy 1.18.1,
matplotlib 3.11.2). Data retrieval used the Python `requests` library.

## Notes and caveats

- Disproportionality measures quantify relative reporting, not incidence or risk.
- openFDA `drugcharacterization` follows the ICH E2B structure (1 = suspect,
  2 = concomitant, 3 = interacting) and does not distinguish primary from secondary
  suspect; a suspect-role filter (`drugcharacterization` = 1) was used.
- The drug-start-to-report interval is a reporting-latency-laden proxy and does not
  localize event onset.

## License

Suggested: released under CC-BY-4.0 (data) and MIT (code). Add a LICENSE file before
archiving if required by the repository host.

## Citation

Add the manuscript citation and the archive DOI (e.g., Zenodo/OSF) here upon
deposit/acceptance.
