# From the list of .csv files in the 'data' directory, extract the journal names and write them to a concatenated text file in data_extracted/journals.txt
import os
import polars as pl
from glob import glob

col="Title of the journal"
input_directory = "data_raw"
output_file = "data_extracted/journals.txt"
os.makedirs("data_extracted", exist_ok=True)
journal_names = set()
for csv_file in glob(os.path.join(input_directory, "*.csv")):
    if "dafnee" in os.path.basename(csv_file).lower():
        continue  # Skip dafnee files
    print(f"Processing file: {csv_file}")
    df = pl.read_csv(csv_file)
    if col in df.columns:
        # Remove the suffix after the first open parenthesis
        df = df.with_columns(pl.col(col).str.replace(r"\s*\(.*$", "", literal=False).alias(col))
        journals = df[col].unique().to_list()
        # Remove empty strings or nan
        journals = [j.strip() for j in journals if (j and j.strip() != "")]
        journal_names.update(journals)
    else:
        print(f"Warning: 'f{col}' column not found in {csv_file}")
print(list(sorted(journal_names)))
with open(output_file, "w") as f:
    f.write("\n".join(sorted(journal_names)) + "\n")
print(f"Extracted {len(journal_names)} unique journal names to {output_file}")
