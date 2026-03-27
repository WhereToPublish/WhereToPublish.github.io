"""
Process APC_dataverse.txt.gz into per-publisher CSV tables for the APC page.

Data source: Butler, L.-A., Hare, M., Schönfelder, N., Schares, E., Alperin, J. P., & Haustein, S. (2024).
An open dataset of article processing charges from six large scholarly publishers (2019-2023).
https://doi.org/10.7910/DVN/CR1MMV

Output:
  - data/APC_<Publisher>.csv  (one per publisher, with per-year APC columns)
  - data/APC_all.csv          (all publishers, only last recorded APC)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from libraries import *

INPUT_FILE = os.path.join("data_extraction", "APC_dataverse.txt.gz")
OUTPUT_DIR = "data"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Publisher colors (used by JavaScript, kept here for reference)
PUBLISHERS = ["Elsevier", "Frontiers", "MDPI", "PLOS", "Springer Nature", "Wiley"]


def clean_journal_name(name):
    """Clean journal name to remove weird/garbled characters."""
    if name is None:
        return ""
    return clean_string(name)


def map_oa_status(status: str) -> str:
    """Map OA_status values to Business model labels."""
    if status == "Gold":
        return "OA"
    elif status == "Hybrid":
        return "Hybrid"
    return ""


def process_apc_data():
    print(f"Loading {INPUT_FILE}...")
    df = load_csv(INPUT_FILE, separator='\t', encoding="utf8-lossy")

    print(f"  Raw rows: {df.height}")

    # Only keep rows where APC was actually provided
    df = df.filter(pl.col("APC_provided") == "yes")
    print(f"  After filtering APC_provided=='yes': {df.height}")

    # Clean journal names
    df = df.with_columns(
        pl.col("Journal").map_elements(clean_journal_name, return_dtype=pl.Utf8).alias("Journal")
    )

    # Map OA_status to Business model
    df = df.with_columns(
        pl.col("OA_status").map_elements(map_oa_status, return_dtype=pl.Utf8).alias("Business model")
    )

    # Format APC_EUR as integer
    df = df.with_columns(
        pl.col("APC_EUR").cast(pl.Utf8).map_elements(format_APC, return_dtype=pl.Utf8).cast(pl.Int64, strict=False).alias("APC_EUR")
    )

    # Drop rows with no valid APC
    df = df.filter(pl.col("APC_EUR").is_not_null() & (pl.col("APC_EUR") > 0))
    print(f"  After filtering valid APC: {df.height}")

    # Get all available years, sorted
    years = sorted(df["APC_year"].unique().to_list())
    print(f"  Years available: {years}")

    # Get unique publishers
    publishers = sorted(df["Publisher"].unique().to_list())
    print(f"  Publishers: {publishers}")

    # For each journal+publisher, compute the APC per year and last recorded APC
    # Group by Journal, Publisher, Business model, APC_year -> mean APC per year
    journal_year = df.group_by(["Journal", "Publisher", "Business model", "APC_year"]).agg(
        pl.col("APC_EUR").mean().round(0).cast(pl.Int64).alias("APC_EUR")
    )

    # Pivot to get one column per year
    pivoted = journal_year.pivot(
        on="APC_year",
        index=["Journal", "Publisher", "Business model"],
        values="APC_EUR",
    )

    # Rename year columns to "APC YYYY (€)"
    rename_map = {}
    for col in pivoted.columns:
        if col not in ["Journal", "Publisher", "Business model"]:
            rename_map[col] = f"APC {col} (€)"
    pivoted = pivoted.rename(rename_map)

    # Sort year columns
    year_cols = sorted([c for c in pivoted.columns if c.startswith("APC ") and c.endswith(" (€)")])

    # Compute last recorded APC: the value from the most recent year that has data
    pivoted = pivoted.with_columns(
        pl.struct(year_cols).map_elements(
            lambda s: next((s[col] for col in reversed(year_cols) if s[col] is not None), None),
            return_dtype=pl.Int64
        ).alias("APC (€)")
    )

    # Sort by Journal name
    pivoted = pivoted.sort("Journal")

    # Define column order for per-publisher files
    per_publisher_cols = ["Journal", "Publisher", "Business model"] + year_cols + ["APC (€)"]

    # Ensure all year columns exist
    for col in per_publisher_cols:
        if col not in pivoted.columns:
            pivoted = pivoted.with_columns(pl.lit(None).cast(pl.Int64).alias(col))

    # Select and order columns
    pivoted = pivoted.select(per_publisher_cols)

    # Write per-publisher CSV files
    for publisher in publishers:
        pub_df = pivoted.filter(pl.col("Publisher") == publisher)
        safe_name = publisher.replace(" ", "_")
        out_path = os.path.join(OUTPUT_DIR, f"APC_{safe_name}.csv")
        pub_df.write_csv(out_path)
        print(f"  Wrote {out_path}: {pub_df.height} journals")

    # Write APC_all.csv (all publishers, only last recorded APC, no per-year columns)
    all_cols = ["Journal", "Publisher", "Business model", "APC (€)"]
    all_df = pivoted.select(all_cols).sort("Journal")
    all_path = os.path.join(OUTPUT_DIR, "APC_all.csv")
    all_df.write_csv(all_path)
    print(f"  Wrote {all_path}: {all_df.height} journals")

    print("Done.")


if __name__ == "__main__":
    process_apc_data()
