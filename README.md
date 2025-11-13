# Where to Publish?

![Logo](https://raw.githubusercontent.com/WhereToPublish/WhereToPublish.github.io/main/img/logo128px.png)

An interactive web tool that helps researchers identify suitable journals for their publications based on scientific domains and publisher types. The database visually distinguishes between for-profit, not-for-profit, and university press journals.

## Data Sources

This tool uses data from multiple sources:

- **DAFNEE database for Ecology and Evolution**: We gratefully acknowledge the [DAFNEE database](https://dafnee.isem-evolution.fr/) which provides comprehensive information about journals in the fields of Ecology and Evolution.
- Custom curated data for other biology fields.

## How to contribute

There are several ways to contribute to this project:

### Add new journals

Add a new journal to the database by filling out the form below. The journal will be reviewed and added to the database if it meets the criteria:
https://docs.google.com/forms/d/e/1FAIpQLSfTWQ8PaFCL_zabYwUidZZlh8GR_SZJ1rWaQfZWX3ZS98pm3g/viewform

### Edit existing data

Edit the database directly in suggestion mode. The changes will be reviewed and merged by the maintainers:
https://docs.google.com/spreadsheets/d/1PRXViyQlo5ZMjpCJ_XpcHfsnZEJmmdCiXjnkazMyua8/edit?resourcekey=&gid=1775942038#gid=1775942038

### Report issues or suggest features

Create an issue to report a problem or suggest a new feature:
https://github.com/WhereToPublish/WhereToPublish.github.io/issues

### Become a maintainer

Become a maintainer by contacting us at:
thibault.latrille@ens-lyon.org


HTML, CSS, JS files
The website is built using plain HTML, CSS, and JS, using only
Jquery, jquery.dataTables.js, and dataTables.responsive.js libraries.
The main files are:
- index.html: The main HTML file that contains the structure of the webpage.
- styles.css: The CSS file that contains the styles for the webpage.
- script.js: The JS file that contains the logic for filtering journals based on user input and rendering the results.
- data/: A directory that contains the processed CSV files used by the JS code to display journal information.
- img/: A directory that contains images used in the webpage (e.g., logo).

The columns in each CSV file are as follows in this order:
    "Journal",
    "Field",
    "Publisher",
    "Publisher type",
    "Business model",
    "Institution",
    "Institution type",
    "Country",
    "Website",
    "APC Euros",
    "Scimago Rank",
    "Scimago Quartile",
    "H index",
    "PCI partner"

The raw data is downloaded and stored in the data_extracted/ directory, using the scripts/download_csv.sh script.
The data is processed using Python scripts located in the "scripts/" directory, using mainly the polars library.
First, the script "scripts/update_extracted.py" is used to update the raw data from various sources (DOAJ, Scimago, OpenAPC) and complete missing information or correct existing information. The input csv files are in the folder "data_extracted/" and the output csv are re-written in the same folder. 
The data sources are:
- DOAJ: Directory of Open Access Journals, providing information about open access journals, including publisher and country, in the file "data_extraction/DOAJ.csv".
- Scimago: Journal ranking data, providing information about journal ranks and quartiles, in the file "data_extraction/scimagor.csv".
- OpenAPC: Open Article Processing Charges data, providing information about APCs and business, in the file "data_extraction/openapc.csv".
Second, the script "scripts/data_merge_dafnee.py" is used to merge the DAFNEE data (data_extracted/dafnee.csv) with the other data sources (data_extracted/*.csv). Mainly it spreads the DAFNEE data the csv files ecology_evolution.csv and generalist.csv. The input csv files are in the folder "data_extracted/" and the output csv are in the folder "data_merged/". 
Third, the script "scripts/data_process.py" is used to process the merged data and generate the final CSV files used by the JS code. Mainly it formats and cleans the data, removes duplicates, and concatenates the various csv files into a single csv file "data/all_biology.csv". The input csv files are in the folder "data_merged/" ("data_merged/*.csv") and the output csv files are in the folder ("data/*.csv").
The file "scipts/libraries.py" contains helper functions used by the other scripts (e.g., formatting functions, etc.).
Always run scripts from the root directory (e.g., python3 scripts/data_process.py) due to relative paths.