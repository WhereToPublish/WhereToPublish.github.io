# Where to Publish?

An interactive database of for-profit and non-profit scientific journals in biology.

🌐 **Website**: [wheretopublish.github.io](https://wheretopublish.github.io/)

📖 **Documentation**: [Wiki](https://github.com/WhereToPublish/WhereToPublish.github.io/wiki)

---

## Quick Links

| Resource          | Link                                                                                                                                 |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| About the Project | [Wiki: About](https://github.com/WhereToPublish/WhereToPublish.github.io/wiki/1.-About)                                               |
| Using the Website | [Wiki: Using the Website](https://github.com/WhereToPublish/WhereToPublish.github.io/wiki/2.-Using-the-Website)                       |
| Data Sources      | [Wiki: The Data](https://github.com/WhereToPublish/WhereToPublish.github.io/wiki/3.-Data)                                             |
| Contributing      | [Wiki: Contributing](https://github.com/WhereToPublish/WhereToPublish.github.io/wiki/4.-Contributing)                                 |
| Add a Journal     | [Google Form](https://docs.google.com/forms/d/e/1FAIpQLSfTWQ8PaFCL_zabYwUidZZlh8GR_SZJ1rWaQfZWX3ZS98pm3g/viewform)                    |
| Edit Data         | [Google Sheets](https://docs.google.com/spreadsheets/d/1PRXViyQlo5ZMjpCJ_XpcHfsnZEJmmdCiXjnkazMyua8/edit?gid=897920130#gid=897920130) |
| Report Issues     | [GitHub Issues](https://github.com/WhereToPublish/WhereToPublish.github.io/issues)                                                    |

---

## Developer Documentation

### Technology Stack

- **Frontend**: HTML, CSS, JavaScript
- **Libraries**: [DataTables](https://datatables.net/) with extensions (responsive, buttons, column visibility, fixed header)
- **Data Processing**: Python 3 with [Polars](https://pola.rs/)
- **Hosting**: GitHub Pages

### Project Structure

```
├── index.html              # Main webpage
├── css/styles.css          # Stylesheet
├── js/scripts.js           # Application logic
├── config/                 # Configuration and lookup caches
│   ├── country_formatting.json   # Publisher→country mapping from the 'variables' Google Sheet tab
│   └── ISSN_type.csv             # ISSN type cache (print/electronic/linking) — built by Scimago_ISSN_type.py
├── data/                   # Processed CSV files (used by website)
├── data_extracted/         # Raw CSV files from Google Sheets
├── data_extraction/        # External data sources (Scimago, OpenAPC, DOAJ, APC Dataverse)
├── scripts/                # Python and shell scripts for data processing
├── vendor/                 # Third-party libraries (DataTables, jQuery, etc.)
└── img/                    # Images and logo
```

### Journal-table CSV Column Schema

Output CSV files in `data/` contain these 18 columns in order:

```
Journal, Field, Publisher, Publisher type, Business model,
Institution, Institution type, Country, Website, APC Euros,
Scimago Rank, Scimago Quartile, H index, Impact Factor (IF), PCI partner,
e-ISSN, p-ISSN, APC year
```

**Impact Factor (IF).** Scimago does not publish impact factors; `Impact Factor (IF)` is filled from Scimago's `Citations / Doc. (2years)` column (the average number of citations per document over a 2-year window, the closest equivalent of a 2-year impact factor), for every journal matched to Scimago. The website hides this column by default. The **Impact Factor** entry of the "Show/Hide more columns" dropdown first opens a modal explaining why the Impact Factor was originally left out (with a link to the DORA guidance). The modal has a "hold WhereToPublish harmless" checkbox, a **Display IF** button that is enabled only once the checkbox is ticked, and an **Ok, I don't want to display IF** button that closes the modal and leaves the column hidden. Once **Display IF** is used, the acceptance is kept in the `impactFactorAccepted` variable of `js/scripts.js` (no cookie or localStorage, so it is forgotten on page reload): the modal never reappears and the **Impact Factor** entry becomes a regular show/hide toggle, also after switching dataset or resetting the columns.

**APC and APC year.** `APC Euros` is the *latest* entry among the APC sources (OpenAPC, DOAJ, Dataverse), not an average across sources, and `APC year` is the year of that entry. The website shows it as `167 (2025)`; sorting, the APC range filter and the histogram use only the numeric amount. Per-source years: OpenAPC = latest year with payments for the journal (amount = mean of that year's payments), Dataverse = latest year with an APC, DOAJ = the year of the record's `Last updated Date`. A source value replaces the current one when its year is more recent (or the current row has no year); for the same year the highest APC is kept. Existing manual APCs have no year and are only kept when no source provides an APC. `APC year` is the last column, so the Google Sheet gains a new last column on the next upload.

The ISSN columns are filled from external sources in priority order: Scimago (via `config/ISSN_type.csv`) → OpenAPC → DOAJ. ISSN-L (linking ISSN) is stored in intermediate files in `data_extracted/` but is not published to the website.

**Business model / APC derivation rules** (applied after every enrichment step):

- If APC Euros > 0 and Business model is empty or `Subscription` → set Business model to `Hybrid`.
- If Business model is `OA diamond` → set APC Euros to `0`.
- If Business model is `Subscription` → set APC Euros to `null` (subscription journals do not charge APCs).

These rules are applied in the order listed so that a journal with `Subscription` + `APC > 0` is first promoted to `Hybrid` (keeping its APC) before the `Subscription → null` rule is evaluated.

**Scimago Business model derivation**: Scimago provides `Open Access Diamond` and `Open Access` flags but no APC column.

- `Open Access Diamond == Yes` → `OA diamond`
- `Open Access == Yes` → `OA`
- otherwise → no value (the journal keeps its current business model)

Intermediate files in `data_extracted/` (the Google Sheet tabs) carry more columns than the website CSVs. The sheet columns are, in order (`FINAL_COLUMNS` in `scripts/libraries.py`, which `upload_sheets.py` asserts before uploading):

```
Journal's MAIN field, Field, Journal, Website, Publisher type, Publisher,
Institution, Institution type, Country, Business model, APC Euros,
Alternative journal name, Present in Scimago, Present in DOAJ, Present in openAPC,
Present in Scholcommlab APC, Scimago Rank, Scimago Quartile, H index,
Impact Factor (IF), PCI partner, e-ISSN, p-ISSN, ISSN-L, APC year
```

The columns below are not published to the website:

- `Alternative journal name` — used as a fallback join key during enrichment when the primary journal name does not match an external source.
- `Present in Scimago`, `Present in DOAJ`, `Present in openAPC`, `Present in Scholcommlab APC` — records how each journal was matched to the corresponding external source (`Present in Scholcommlab APC` refers to the Dataverse file `scholcommlab_apc_dataset_2019_2025-2.csv.gz`, which only covers 14 publishers, so `No` there does not mean the journal has no APC). Possible values:

  - `"Yes"` — matched via normalized journal name
  - `"With alternative journal name"` — matched via the alternative journal name
  - `"ISSN-L match"` — matched via ISSN-L
  - `"e-ISSN match"` — matched via e-ISSN
  - `"p-ISSN match"` — matched via p-ISSN
  - `"Ambiguous"` — a candidate key was found in both tables but was duplicated on one side, or the only matching lookup row was already claimed by another journal
  - `"No"` — no match found by any key

  These columns are discarded by `data_process.py`.

The APC Explorer uses separate tables generated by `scripts/APC_process.py`. It creates
`APC_<Publisher>.csv` tables with yearly APC values and a last-recorded APC, plus
`APC_all.csv` with only the last-recorded APC. The APC display includes the year of its
latest available value (for example, `167 (2025)`); the year is stored separately from
the numeric amount so APC sorting and histogram filtering remain numeric. Yearly values
are hidden by default in publisher-specific tables; `APC_all.csv` does not include
yearly APC columns.

### Data Pipeline

The data is updated manually: a maintainer starts the *Extract Data* GitHub Action (there is no automatic schedule), which runs:

```bash
# 1. Download raw data from Google Sheets (via Sheets API)
python3 scripts/download_sheets.py

# 2. Enrich with external sources (Scimago, OpenAPC, DOAJ, Dataverse)
#    Matches each journal to external sources using unique keys. Scimago, OpenAPC, and
#    DOAJ use normalized title, alternative title, then ISSNs. Dataverse prioritizes
#    ISSN-L and its two ISSN values before normalized title matching.
#    A key is only used when it is unique on both sides; ambiguous matches are flagged.
#    Dataverse uses 2025 records when available, otherwise the journal's latest year.
#    Also generates logs/disagreements.csv — a CSV report of conflicts between
#    the dataset and external sources (Scimago, OpenAPC, DOAJ; not Dataverse),
#    plus an internal consistency check on Publisher type.
#    External columns checked: Publisher, Business model, e-ISSN, p-ISSN, APC Euros.
#    Internal Publisher type check: compares the dataset "Publisher type" against the
#    type inferred from the normalized "Publisher" name using config/country_formatting.json.
#    Society-run variants (e.g. "For-profit Society-Run") are not flagged when the inferred
#    base category matches (e.g. "For-profit"). Unknown publishers are not flagged here;
#    they are reported separately by data_process.py in missing_publisher_in_configs.csv.
#    Report columns: priority, journal, url, publisher, publisher_type, field, column,
#    dataset_value, expected_value, Scimago_value, DOAJ_value, OpenAPC_value.
#    Internal Publisher type mismatches are assigned priority "Utmost priority" so they
#    appear first in the report.
#    APC disagreement is flagged only when one source has 0 and another has non-zero.
python3 scripts/update_extracted.py

# 3. Process, clean, and deduplicate
#    Also generates logs/missing_publisher_in_configs.csv — journals whose publisher
#    is not found in config/country_formatting.json after normalization.
#    Report columns: journal, publisher, country, publisher_type
#    (sorted by publisher then journal).
python3 scripts/data_process.py

# 4. Upload enriched data and pipeline reports back to Google Sheets
#    - Uploads enriched field CSVs to their corresponding field tabs (in-place).
#    - Uploads logs/disagreements.csv to the "Disagreements" tab (values cleared then rewritten,
#      formatting preserved), including ISSN hyperlinks in value columns for ISSN disagreements.
#    - Uploads logs/missing_publisher_in_configs.csv to the "Missing publishers" tab
#      (values cleared then rewritten, formatting preserved).
#    Report tabs are styled on upload: Roboto size 10, left/top alignment, white data-cell
#    background, grey header row, and Publisher disagreement value cells colored by publisher type.
python3 scripts/upload_sheets.py
```

A Google service-account key is required. See [API_SETUP.md](API_SETUP.md) for
credential setup instructions (local and GitHub Actions).

**Important**: Run Python scripts from the repository root (not from `scripts/`):

```bash
# Correct
python scripts/data_process.py

# Incorrect
cd scripts && python data_process.py
```

### Key Scripts

| Script                             | Purpose                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `scripts/download_sheets.py`     | Downloads all field tabs from Google Sheets API to`data_extracted/`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `scripts/upload_sheets.py`       | Uploads enriched`data_extracted/` field CSVs back to Google Sheets (field tabs updated in-place). Also uploads `logs/disagreements.csv` to a **Disagreements** tab and `logs/missing_publisher_in_configs.csv` to a **Missing publishers** tab by clearing tab values then rewriting (tab formatting is preserved). ISSN values in Disagreements value columns are hyperlinked to the ISSN portal for ISSN disagreements. Report tabs are styled on upload (Roboto size 10, left/top alignment, grey header, white data cells); Publisher disagreement value cells are color-coded by publisher type. |
| `scripts/fetch_sheet.py`         | Downloads a single field tab (CLI helper)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `scripts/download_extraction.sh` | Downloads external data sources to`data_extraction/`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `scripts/update_extracted.py`    | Enriches raw data with Scimago, OpenAPC, DOAJ, and Dataverse. The APC is the latest entry (by dataset year) among OpenAPC, DOAJ and Dataverse; Dataverse uses its latest year with an APC, matching by ISSN-L and the dataset's ISSNs before falling back to journal title. Candidate keys must be unique on both sides; ambiguous matches are skipped. Fills the four `Present in …` match columns (including `Present in Scholcommlab APC` for Dataverse) and `Impact Factor (IF)` from Scimago. Also writes`logs/disagreements.csv` for Scimago, OpenAPC, and DOAJ conflicts.                                                                                                                                                                                 |
| `scripts/APC_process.py`         | Processes the 2019–2025 Harvard Dataverse APC dataset into publisher-specific yearly APC tables and the compact`APC_all.csv` table used by APC Explorer.                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `scripts/data_process.py`        | Cleans, normalizes, deduplicates, and outputs to`data/`. Also writes `logs/missing_publisher_in_configs.csv` — journals whose publisher (after normalization) is not found in `config/country_formatting.json`, with columns `journal`, `publisher`, `country`, `publisher_type` (sorted by `publisher`, then `journal`).                                                                                                                                                                                                                                                                            |
| `scripts/libraries.py`           | Shared utility functions                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `scripts/sheets_client.py`       | Google Sheets API client (shared by download and upload scripts)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `scripts/run.sh`                 | Runs the full pipeline                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `scripts/Scimago_ISSN_type.py`   | Classifies Scimago ISSNs as print/electronic/linking via the[ISSN Portal API](https://portal.issn.org/); results cached in `config/ISSN_type.csv`. Run with `--limit N` for incremental processing (~50k ISSNs total, first run is slow). Used by `update_extracted.py` to populate e-ISSN and p-ISSN from Scimago data.                                                                                                                                                                                                                                                                                           |

### External Data Sources

| Source                                         | File                                                            | Description                                                                                                                                    |
| ---------------------------------------------- | --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| [Scimago](https://www.scimagojr.com/)           | `data_extraction/scimagojr.csv.gz`                            | Journal rankings, quartiles, H-index, impact factor (`Citations / Doc. (2years)`)                                                              |
| [OpenAPC](https://openapc.net/)                 | `data_extraction/openapc.csv.gz`                              | Article Processing Charges — uses only the most recent year's records per journal; journals with no data within the last 3 years are excluded |
| [DOAJ](https://doaj.org/)                       | `data_extraction/DOAJ.csv.gz`                                 | Open access journal metadata                                                                                                                   |
| [Dataverse](https://doi.org/10.7910/DVN/AZ985C) | `data_extraction/scholcommlab_apc_dataset_2019_2025-2.csv.gz` | Annual APC list prices for 14 publishers, 2019–2025                                                                                           |

### Local Development

1. Clone the repository:

   ```bash
   git clone https://github.com/WhereToPublish/WhereToPublish.github.io.git
   cd WhereToPublish.github.io
   ```
2. Install Python dependencies:

   ```bash
   pip install -r requirements.txt
   ```
3. Set up Google Sheets API credentials (required for download/upload steps):

   ```bash
   # See API_SETUP.md for full instructions
   mkdir -p ~/.config/wheretopublish
   cp /path/to/google_service_account.json ~/.config/wheretopublish/google_service_account.json
   ```
4. Generate the APC website tables locally (does not upload to Google Sheets):

   ```bash
   python -m scripts.APC_process
   ```

   `APC_process.py` reads `data_extraction/scholcommlab_apc_dataset_2019_2025-2.csv.gz`
   and writes the resulting APC tables to `data/`.
5. Run the data pipeline:

   ```bash
   bash scripts/run.sh
   ```
6. Serve locally (any static file server):

   ```bash
   python -m http.server 8000
   ```
7. Open [http://localhost:8000](http://localhost:8000)

---

## License

This project is open source. See the repository for license details.

## Contact

For maintainer inquiries: [thibault.latrille@ens-lyon.org](mailto:thibault.latrille@ens-lyon.org)
