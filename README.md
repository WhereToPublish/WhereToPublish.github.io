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

In the column "Field", changes values:
"General" -> "Generalist"
In the column "Publisher type", changes values:
"for-profit" -> "For-profit"
"university press" -> "University press"
"non-profit" -> "Non-profit"
In the column "Business model", changes values:
"oa" -> "OA"
"gold_OA" -> "Gold OA"
"diamond_OA" -> "Diamond OA"
"hybrid" -> "Hybrid"
"subscription" -> "Subscription"

