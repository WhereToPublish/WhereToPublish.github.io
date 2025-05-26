# Scientific Journal Database

This project displays a searchable, filterable table of scientific journals using DataTables.js. The data is loaded from a CSV file and presented in an interactive web interface.

## Features

- Interactive data table with sorting, filtering, and pagination
- Responsive design that works on desktop and mobile devices
- Custom filtering for journal status (For-profit, Not-for-profit, University Press)
- Domain filter buttons to quickly filter journals by domain
- Hidden domain columns with expandable rows to view domain details
- Clear display of domain coverage for each journal
- Easy to deploy to GitHub Pages

## Files

- `database.csv` - The source data file containing journal information
- `index.html` - A copy of index.html for easier GitHub Pages access
- `README.md` - This documentation file

## How to Deploy to GitHub Pages

1. Create a new GitHub repository
2. Upload all files to the repository
3. Go to the repository settings
4. Scroll down to the "GitHub Pages" section
5. Select the branch you want to deploy (usually `main` or `master`)
6. Select the root folder as the source
7. Click "Save"
8. Wait a few minutes for GitHub to build and deploy your site
9. Access your site at `https://[your-username].github.io/[repository-name]/`

## File Structure

The repository includes:

- `index.html` - The original HTML file that loads and displays the data
- (`https://[your-username].github.io/[repository-name]/`)

You can use either file, but the `index.html` file will be automatically loaded when someone visits your GitHub Pages site without specifying a filename.

## Local Testing

To test the site locally before deploying:

1. Make sure all files (`database.csv`, `index.html`) are in the same directory
2. Open `index.html`in a web browser
3. If you see any errors, check the browser's developer console for details

## Customization

You can customize the appearance by modifying the CSS styles in the `<style>` section of the HTML file.
