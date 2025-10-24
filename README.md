# Where to Publish?

![Logo](https://raw.githubusercontent.com/WhereToPublish/WhereToPublish.github.io/main/img/logo128px.png)

An interactive web tool that helps researchers identify suitable journals for their publications based on scientific domains and publisher types. The database visually distinguishes between for-profit, not-for-profit, and university press journals.

## Data Sources

This tool uses data from multiple sources:

- **DAFNEE database for Ecology and Evolution**: We gratefully acknowledge the [DAFNEE database](https://dafnee.isem-evolution.fr/) which provides comprehensive information about journals in the fields of Ecology and Evolution.
- Custom curated data for Neurosciences and other biology fields.

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

*data_merge_extraction.py*
From the list of .csv files in the 'INPUT_DIR' (data_ray) directory, process each file.
Then for each .csv file, extract information available in 'INPUT_EXTRACTION_PATH' ('extraction.tsv') and merge that information into the processed data.
If an entry (a cell of the table) is already present in the .csv file, keep the information from the .csv file, not from 'INPUT_EXTRACTION_PATH' ('extraction.tsv').
Both the input and output files should have the following columns (in this order for the output):
"Journal,Website,Journal's MAIN field,Field,Publisher type,Publisher,Institution,Institution type,Country,Business model,APC Euros,Scimago Rank,PCI partner"

The match between the columns in 'INPUT_EXTRACTION_PATH' ('extraction.tsv') and the other .csv files are the following:
journal: Journal;
APC_euros: APC Euros;
PCI_partnership: PCI partner;
SJR: Scimago Rank;
business_model: Business model;
publisher: Publisher;
website: Website;
The journal name matching (between .csv files and 'extraction.tsv') should be case insensitive and ignore leading/trailing spaces, removing special characters (like '-', '_', etc.), multiple spaces and anything between parentheses.

The information from 'INPUT_EXTRACTION_PATH' ('extraction.tsv') should only take the first source available and remove the information of the source. 
For example, "DOAJ:Springer|Scimago:Springer Science and Business Media Deutschland GmbH" should become "Springer" in the "Publisher" column.

dafnee.csv is a special case:
dafnee.csv should be merged into ecology_evolution.csv but only for the rows that are not "general" (for the column "Field" in dafnee.csv).
For entries merged into ecology_evolution.csv, the "Journal's MAIN field" column should be set to "Ecology and Evolution".
dafnee.csv should be merged into generalist.csv but only for the rows that are "general" (for the column "Field" in dafnee.csv).
For entries merged into generalist.csv the "Journal's MAIN field" column should be set to "Generalist".
dafnee.csv should not be written in the output folder.

If no information is present for the Journal's status ("for-profit", "not-profit", "university press", "predatory") it should try to be inferred from the "Publisher" name using the following rules:
- If the publisher name contains "university press" it should be classified as "University Press".
- If the publisher name contains "springer", "elsevier", "wiley", "taylor", francis", "frontiers", "informa", "sciendo", "nature" it should be classified as "for-profit".
- If it contains "mdpi" or "hindawi" it should be classified as "predatory".

Finally, for each dataframe it should be written with the same file name to a new directory 'OUTPUT_DIR' (data_merged), while dafnee.csv should not be written.

*data_process.py*
From the list of .csv files in the 'data_merge' directory, process each file to have it formatted with specific columns and write them to a new directory 'data'.
Both the input and output files should have the following columns (in this order for the output):
"Journal,Website,Journal's MAIN field,Field,Publisher type,Publisher,Institution,Institution type,Country,Business model,APC Euros,Scimago Rank,PCI partner"
For each file, ensure that only these columns are present (in this order).
Assert that there are no duplicated rows in each processed file (based on the "Journal" column).
Sort the entries alphabetically by the "Journal" column before writing the output file.
Create one more csv file in the 'data' directory: all_biology.csv.
The all_biology.csv file should contain all entries from the processed csv files concatenated together (and deduplicated if necessary).

HTML, CSS, JS files
The website is built using plain HTML, CSS, and JS, using only
Jquery, jquery.dataTables.js, and dataTables.responsive.js libraries.
The main files are:
- index.html: The main HTML file that contains the structure of the webpage.
- styles.css: The CSS file that contains the styles for the webpage.
- script.js: The JS file that contains the logic for filtering journals based on user input and rendering the results.
- data/: A directory that contains the processed CSV files used by the JS code to display journal information.
- img/: A directory that contains images used in the webpage (e.g., logo).

Change the HTML, CSS, JS files to include all the csv files in the 'data' directory for filtering and displaying journal information.
The default view should show the generalist journals.
Add the predatory journals as a separate color: black.
Add a legend to explain the color coding of the journal types (for-profit, not-profit, university press, predatory).
