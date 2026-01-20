# Where to Publish?

An interactive database of for-profit and non-profit scientific journals in biology.

🌐 **Website**: [wheretopublish.github.io](https://wheretopublish.github.io/)

📖 **Documentation**: [Wiki](https://github.com/WhereToPublish/WhereToPublish.github.io/wiki)

---

## Quick Links

| Resource | Link                                                                                                                     |
|----------|--------------------------------------------------------------------------------------------------------------------------|
| About the Project | [Wiki: About](https://github.com/WhereToPublish/WhereToPublish.github.io/wiki/1.-About)                                  |
| Using the Website | [Wiki: Using the Website](https://github.com/WhereToPublish/WhereToPublish.github.io/wiki/2.-Using-the-Website)          |
| Data Sources | [Wiki: The Data](https://github.com/WhereToPublish/WhereToPublish.github.io/wiki/3.-Data)                                |
| Contributing | [Wiki: Contributing](https://github.com/WhereToPublish/WhereToPublish.github.io/wiki/4.-Contributing)                    |
| Add a Journal | [Google Form](https://docs.google.com/forms/d/e/1FAIpQLSfTWQ8PaFCL_zabYwUidZZlh8GR_SZJ1rWaQfZWX3ZS98pm3g/viewform)       |
| Edit Data | [Google Sheets](https://docs.google.com/spreadsheets/d/1PRXViyQlo5ZMjpCJ_XpcHfsnZEJmmdCiXjnkazMyua8/edit?gid=897920130#gid=897920130) |
| Report Issues | [GitHub Issues](https://github.com/WhereToPublish/WhereToPublish.github.io/issues)                                       |

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
├── data/                   # Processed CSV files (used by website)
├── data_extracted/         # Raw CSV files from Google Sheets
├── data_extraction/        # External data sources (Scimago, OpenAPC, DOAJ)
├── scripts/                # Python and shell scripts for data processing
├── vendor/                 # Third-party libraries (DataTables, jQuery, etc.)
└── img/                    # Images and logo
```

### CSV Column Schema

Output CSV files in `data/` contain these columns in order:

```
Journal, Field, Publisher, Publisher type, Business model,
Institution, Institution type, Country, Website, APC Euros,
Scimago Rank, Scimago Quartile, H index, PCI partner
```

### Data Pipeline

The data is updated monthly via GitHub Actions:

```bash
# 1. Download raw data from Google Sheets
bash scripts/download_csv.sh

# 2. Enrich with external sources (Scimago, OpenAPC, DOAJ)
python scripts/update_extracted.py

# 3. Process, clean, and deduplicate
python scripts/data_process.py
```

**Important**: Run Python scripts from the repository root (not from `scripts/`):

```bash
# Correct
python scripts/data_process.py

# Incorrect
cd scripts && python data_process.py
```

### Key Scripts

| Script | Purpose |
|--------|---------|
| `scripts/download_csv.sh` | Downloads data from Google Sheets to `data_extracted/` |
| `scripts/download_extraction.sh` | Downloads external data sources to `data_extraction/` |
| `scripts/update_extracted.py` | Enriches raw data with Scimago, OpenAPC, DOAJ |
| `scripts/data_process.py` | Cleans, normalizes, deduplicates, and outputs to `data/` |
| `scripts/libraries.py` | Shared utility functions |
| `scripts/run.sh` | Runs the full pipeline |
| `scripts/clean_run.sh` | Clean run (removes intermediate files first) |

### External Data Sources

| Source | File | Description |
|--------|------|-------------|
| [Scimago](https://www.scimagojr.com/) | `data_extraction/scimagojr.csv.gz` | Journal rankings, quartiles, H-index |
| [OpenAPC](https://openapc.net/) | `data_extraction/openapc.csv.gz` | Article Processing Charges |
| [DOAJ](https://doaj.org/) | `data_extraction/DOAJ.csv.gz` | Open access journal metadata |

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

3. Run the data pipeline:
   ```bash
   bash scripts/run.sh
   ```

4. Serve locally (any static file server):
   ```bash
   python -m http.server 8000
   ```

5. Open [http://localhost:8000](http://localhost:8000)

---

## License

This project is open source. See the repository for license details.

## Contact

For maintainer inquiries: [thibault.latrille@ens-lyon.org](mailto:thibault.latrille@ens-lyon.org)
