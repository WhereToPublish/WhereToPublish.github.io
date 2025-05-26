# Where to Publish?

An interactive web tool that helps researchers identify suitable journals for their publications based on scientific domains and publisher types. The database visually distinguishes between for-profit, not-for-profit, and university press journals.

## Features

- **Interactive data table** with sorting and searching capabilities
- **Color-coded journal types**:
  - For-profit journals (light red)
  - Not-for-profit journals (light green)
  - University Press journals (light yellow)

## Data Structure

The `data.csv` file contains the following information:

- **Journal name**
- **Domain coverage** (columns for Biology, Neurosciences, Cognitive Science, etc.)
  - Values: 1 (Yes), 0 (No), or ? (Unknown)
- **Status** (FP = For-profit, NP/NFP = Not-for-profit, UP = University Press)
- **Publisher** name
- **Country** of publication

## Files

- `data.csv` - The source data file containing journal information
- `index.html` - The web interface that displays the data
- `README.md` - This documentation file