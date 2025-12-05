import os
from glob import glob
from libraries import *
import re

# Constants
DATA_EXTRACTED_DIR = "data_extracted"
SCIMAGO_FILE = os.path.join("data_extraction", "scimagojr.csv.gz")
OPENAPC_FILE = os.path.join("data_extraction", "openapc.csv.gz")
DOAJ_FILE = os.path.join("data_extraction", "DOAJ.csv.gz")
FILES_TO_SKIP = []

# Columns that should be updated from each data source
FILE_COLS = {"scimago": [("Scimago Rank", True),
                         ("Publisher", False),
                         ("Business model", False),
                         ("Scimago Quartile", True),
                         ("H index", True)],
             "openapc": [("APC Euros", True),
                         ("Publisher", False),
                         ("Business model", False)],
             "doaj": [("Publisher", False),
                      ("Country", False),
                      ("Website", False),
                      ("Institution", False),
                      ("APC Euros", False)]}

COLUMNS_TO_UPDATE = set([col for cols in FILE_COLS.values() for col, _ in cols])
print(f"Columns to update: {COLUMNS_TO_UPDATE}")


def validate_no_duplicates_for_join(right_df: pl.DataFrame, join_key: str, left_keys: set, source_name: str) -> None:
    """Validate that the right DataFrame has no duplicates on the join key for keys that exist in the left DataFrame.

    Args:
        right_df: Right DataFrame in the join (lookup table)
        join_key: Column name to check for duplicates in the right DataFrame
        left_keys: Set of key values from the left DataFrame that will be joined
        source_name: Name of the data source (for error messages)

    Raises:
        ValueError: If duplicates are found on the join key for keys that will be joined
    """
    # Filter right_df to only include rows where the join key is in left_keys
    relevant_rows = right_df.filter(pl.col(join_key).is_in(list(left_keys)))

    # Count rows and unique values for the join key in relevant rows
    total_rows = relevant_rows.height
    if total_rows == 0:
        # No matching keys, nothing to validate
        return

    unique_values = relevant_rows[join_key].n_unique()

    if total_rows != unique_values:
        duplicates_count = total_rows - unique_values
        # Find the duplicate values
        duplicates = relevant_rows.group_by(join_key).agg(
            pl.count().alias("count")
        ).filter(pl.col("count") > 1).sort("count", descending=True)

        error_msg = (
            f"ERROR: Found {duplicates_count} duplicate entries in {source_name} on join key '{join_key}' "
            f"for keys that will be joined.\n"
            f"Total relevant rows: {total_rows}, Unique values: {unique_values}\n"
            f"Top duplicates:\n{duplicates.head(10)}"
        )
        raise ValueError(error_msg)


def format_scimago_quartile_from_categories(categories_str: str | None, best_quartile: str | None) -> str | None:
    """Return a string like 'Q1 (Oncology and Cancer; Medicine)' built from the Categories field.

    Logic:
    - Parse categories like 'Oncology and Cancer (Q1); Medicine (miscellaneous) (Q1)'.
    - Determine the best quartile (prefer the provided best_quartile; if missing, infer best from categories).
    - Keep only categories with that best quartile.
    - Remove '(*)' from category names and strip trailing spaces.
    - Format as 'Qx (Cat1; Cat2)'. If no categories found, return just 'Qx'. If nothing available, return None.
    """
    if categories_str is None:
        categories_str = ""

    # Split individual category entries
    raw_items = [part.strip() for part in categories_str.split(";") if part.strip()]

    # Extract (clean_name, 'Qn' or None)
    extracted: list[tuple[str, str | None]] = []
    q_pat = re.compile(r"\(Q([1-4])\)")
    set_extracted = set()
    for item in raw_items:
        # Find quartile tag, typically at the end
        m = q_pat.search(item)
        q = f"Q{m.group(1)}" if m else None
        # Remove the quartile tag and '(miscellaneous)' tag from the name
        name = q_pat.sub("", item)
        # Remove anything between parentheses at the end (e.g., miscellaneous)
        name = re.sub(r"\s*\(.*?\)\s*$", "", name)
        name = name.strip()
        # Guard against empty after cleaning
        if name and name not in set_extracted:
            set_extracted.add(name)
            extracted.append((name, q))

    # Keep only categories with that best quartile
    best_items = [name for name, q in extracted if q == best_quartile]
    if best_items:
        return f"{best_quartile} ({'; '.join(best_items)})"
    # If we have no category names but we do know best quartile, return just best
    return best_quartile


def load_scimago_lookup() -> pl.DataFrame:
    """Load and process Scimago data into a lookup table.

    Returns:
        pl.DataFrame: Processed Scimago lookup table with normalized journal names.
    """
    scimago_df = load_csv(SCIMAGO_FILE, separator=';')
    scimago_df = scimago_df.rename({
        "Title": "Journal_scimago",
        "SJR": "Scimago Rank_scimago",
        "Publisher": "Publisher_scimago",
        "SJR Best Quartile": "Scimago Quartile_scimago",
        "H index": "H index_scimago",
        "Country": "Country_scimago",
        "Areas": "Areas_scimago",
        "Categories": "Categories_scimago",
        "Open Access": "Open Access_scimago",
        "Open Access Diamond": "Open Access Diamond_scimago",
    })

    scimago_df = scimago_df.with_columns([
        pl.col("Journal_scimago").map_elements(norm_name, return_dtype=pl.Utf8).alias("norm_journal_scimago"),
        pl.col("Scimago Quartile_scimago").alias("Best Quartile_scimago"),
        pl.when(pl.col("Open Access Diamond_scimago") == "Yes")
        .then(pl.lit("OA diamond"))
        .when(pl.col("Open Access_scimago") == "Yes")
        .then(pl.lit("OA"))
        .otherwise(None)
        .alias("Business model_scimago")
    ])

    # Format Scimago Rank to standard numeric format
    scimago_df = format_Scimago_Rank(scimago_df, "Scimago Rank_scimago")

    # Build formatted Scimago Quartile from Categories + best quartile
    scimago_df = scimago_df.with_columns(
        pl.struct(["Categories_scimago", "Best Quartile_scimago"]).map_elements(
            lambda s: format_scimago_quartile_from_categories(
                s.get("Categories_scimago"),
                s.get("Best Quartile_scimago")
            ),
            return_dtype=pl.Utf8,
        ).alias("Scimago Quartile_scimago")
    )

    # Keep only necessary columns and remove duplicates
    return scimago_df.select([
        "norm_journal_scimago",
        "Scimago Rank_scimago",
        "Publisher_scimago",
        "Business model_scimago",
        "Scimago Quartile_scimago",
        "H index_scimago",
        "Country_scimago"
    ]).unique(subset=["norm_journal_scimago"], keep="first")


def load_openapc_lookup() -> pl.DataFrame:
    """Load and process OpenAPC data into a lookup table.

    Returns:
        pl.DataFrame: Processed OpenAPC lookup table with normalized journal names and aggregated data from last 5 years.
    """
    openapc_df = load_csv(OPENAPC_FILE)
    openapc_df = openapc_df.rename(
        {"journal_full_title": "Journal_openapc",
         "euro": "APC Euros_openapc",
         "publisher": "Publisher_openapc"}
    )

    # Normalize journal names first
    openapc_df = openapc_df.with_columns(
        pl.col("Journal_openapc").map_elements(norm_name, return_dtype=pl.Utf8).alias("norm_journal_openapc")
    )

    # For each journal, determine the last 5 years with available data
    # First, find the max period (latest year) for each journal
    max_periods = openapc_df.group_by("norm_journal_openapc").agg(
        pl.col("period").max().alias("max_period")
    )

    # Join back and filter to keep only last 5 years of data per journal
    openapc_df = openapc_df.join(max_periods, on="norm_journal_openapc", how="left")
    openapc_df = openapc_df.filter(
        pl.col("period") > (pl.col("max_period") - 5)
    )

    # Group by normalized journal name and aggregate:
    # - Mean APC Euros from last 5 years
    # - Most frequent publisher from last 5 years
    # - Majority vote for is_hybrid (if more than 50% are hybrid, mark as Hybrid)
    openapc_df = openapc_df.group_by("norm_journal_openapc").agg([
        pl.col("APC Euros_openapc").mean().alias("APC Euros_openapc"),
        pl.col("Publisher_openapc").mode().first().alias("Publisher_openapc"),
        pl.when(pl.col("is_hybrid").mean() > 0.5)
        .then(pl.lit("Hybrid"))
        .otherwise(None)
        .alias("Business model_openapc"),
    ])

    return format_APC_Euros(openapc_df, "APC Euros_openapc")


def load_doaj_lookup() -> pl.DataFrame:
    """Load and process DOAJ data into a lookup table.

    Returns:
        pl.DataFrame: Processed DOAJ lookup table with normalized journal names.
    """
    doaj_df = load_csv(DOAJ_FILE)

    # Rename columns to match our naming convention
    doaj_df = doaj_df.rename({
        "Journal title": "Journal_doaj",
        "Publisher": "Publisher_doaj",
        "Country of publisher": "Country_doaj",
        "Other organisation": "Institution_doaj",
        "Journal URL": "Website_doaj",
        "APC amount": "APC Euros_doaj",
    })

    # Normalize journal names
    doaj_df = doaj_df.with_columns(
        pl.col("Journal_doaj").map_elements(norm_name, return_dtype=pl.Utf8).alias("norm_journal_doaj")
    )

    # Filter APC Euros to only include EUR currency
    # The APC amount column typically has format like "1000 EUR" or "2000 USD"
    doaj_df = doaj_df.with_columns(
        pl.when(pl.col("APC Euros_doaj").cast(pl.Utf8).str.contains("EUR"))
        .then(pl.col("APC Euros_doaj"))
        .otherwise(None)
        .alias("APC Euros_doaj")
    )

    # Standardize country names
    doaj_df = doaj_df.with_columns(
        pl.col("Country_doaj").map_elements(standardize_country_name, return_dtype=pl.Utf8).alias("Country_doaj")
    )

    # Clean institution names
    doaj_df = doaj_df.with_columns(
        pl.col("Institution_doaj").map_elements(normalize_institution, return_dtype=pl.Utf8).alias("Institution_doaj")
    )

    # Clean publisher names
    doaj_df = doaj_df.with_columns(
        pl.col("Publisher_doaj").map_elements(normalize_publisher, return_dtype=pl.Utf8).alias("Publisher_doaj")
    )

    # Format APC Euros (extract numeric value)
    doaj_df = format_APC_Euros(doaj_df, "APC Euros_doaj")
    doaj_df = format_urls(doaj_df, "Website_doaj")

    # Keep only necessary columns and remove duplicates (keep first occurrence)
    return doaj_df.select([
        "norm_journal_doaj",
        "Publisher_doaj",
        "Country_doaj",
        "Institution_doaj",
        "Website_doaj",
        "APC Euros_doaj"
    ]).unique(subset=["norm_journal_doaj"], keep="first")


def update_column_from_source(df: pl.DataFrame, col: str, source_col: str,
                              always_overwrite: bool = False) -> tuple[pl.DataFrame, int]:
    """Update a column from a source column, optionally overwriting existing values.

    Args:
        df: DataFrame to update
        col: Target column name
        source_col: Source column name (with suffix like _scimago or _openapc)
        always_overwrite: If True, always overwrite with source when available

    Returns:
        Tuple of (updated DataFrame, number of updates made)
    """
    # Fill null values
    filled = df.filter(pl.col(col).is_null() & pl.col(source_col).is_not_null()).height
    df = df.with_columns(
        pl.when(pl.col(col).is_null())
        .then(pl.col(source_col))
        .otherwise(pl.col(col))
        .alias(col)
    )

    updates = filled
    # Optionally overwrite existing values
    if always_overwrite:
        changed = df.filter(
            pl.col(source_col).is_not_null() &
            (pl.col(col).cast(pl.Utf8) != pl.col(source_col).cast(pl.Utf8))
        ).height
        updates += changed
        df = df.with_columns(
            pl.when(pl.col(source_col).is_not_null())
            .then(pl.col(source_col))
            .otherwise(pl.col(col))
            .alias(col)
        )

    return df, updates


def update_and_log_statistics(df: pl.DataFrame, totals: dict, source: str = "scimago") -> pl.DataFrame:
    """Update columns from data source and log statistics.

    Args:
        df: The DataFrame to update
        totals: Dictionary to store total update counts
        source: The data source ("scimago" or "openapc")

    Returns:
        Updated DataFrame
    """

    list_cols = FILE_COLS.get(source, [])
    # For OpenAPC, only update APC Euros when it's null
    for col, overwrite in list_cols:
        df, updates = update_column_from_source(df, col, f"{col}_{source}", always_overwrite=overwrite)
        totals[col] += updates
        if updates > 0:
            action = "updates" if overwrite else "empty filled"
            print(f"\t- '{col}' {action} from {source}: {updates}")
    return df


def process_csv_file(csv_path: str, scimago_lookup: pl.DataFrame, openapc_lookup: pl.DataFrame,
                     doaj_lookup: pl.DataFrame, pci_friendly_set: set, totals: dict) -> None:
    """Process a single CSV file with Scimago, OpenAPC, and DOAJ data.

    Args:
        csv_path: Path to the CSV file to process
        scimago_lookup: Scimago lookup table
        openapc_lookup: OpenAPC lookup table
        doaj_lookup: DOAJ lookup table
        pci_friendly_set: Set of PCI-friendly journal names
        totals: Dictionary to accumulate update counts
    """
    print(f"Processing file: {csv_path}")
    target_df = load_csv(csv_path, ignore_errors=True)

    # Keep track of original columns to avoid persisting helper columns
    original_cols = target_df.columns.copy()

    # Add normalized journal name for joining
    target_df = target_df.with_columns(
        pl.col("Journal").map_elements(norm_name, return_dtype=pl.Utf8)
        .alias("norm_journal")
    )
    # Get the set of keys that will be used for joining
    left_keys = set(target_df["norm_journal"].unique().to_list())

    # Validate Scimago lookup has no duplicates for keys that will be joined
    validate_no_duplicates_for_join(scimago_lookup, "norm_journal_scimago", left_keys, "Scimago")
    # Join with Scimago data
    updated_df = target_df.join(
        scimago_lookup,
        left_on="norm_journal",
        right_on="norm_journal_scimago",
        how="left",
        coalesce=False,
    )
    # Update columns from Scimago
    updated_df = update_and_log_statistics(updated_df, totals, source="scimago")

    # Validate OpenAPC lookup has no duplicates for keys that will be joined
    validate_no_duplicates_for_join(openapc_lookup, "norm_journal_openapc", left_keys, "OpenAPC")
    # Join with OpenAPC data
    updated_df = updated_df.join(
        openapc_lookup,
        left_on="norm_journal",
        right_on="norm_journal_openapc",
        how="left",
        coalesce=False,
    )
    # Update APC Euros from OpenAPC
    updated_df = update_and_log_statistics(updated_df, totals, source="openapc")

    # Validate DOAJ lookup has no duplicates for keys that will be joined
    validate_no_duplicates_for_join(doaj_lookup, "norm_journal_doaj", left_keys, "DOAJ")
    # Join with DOAJ data
    updated_df = updated_df.join(
        doaj_lookup,
        left_on="norm_journal",
        right_on="norm_journal_doaj",
        how="left",
        coalesce=False,
    )
    # Update columns from DOAJ
    updated_df = update_and_log_statistics(updated_df, totals, source="doaj")

    # Apply formatting and normalization
    updated_df = format_table(updated_df)
    # Mark PCI friendly journals
    updated_df = mark_pci_friendly(updated_df, pci_friendly_set)
    # Select original columns only (avoid helper/join columns)
    final_df = updated_df.select(original_cols)

    # Overwrite the existing file
    check_consistency(final_df)
    final_df.write_csv(csv_path)
    print(f"Successfully updated and saved {csv_path}")


def main():
    """Main function to update Scimago and OpenAPC information in CSV files."""
    print("Starting script to update Scimago, OpenAPC, and DOAJ info...")

    # Load lookup tables
    pci_friendly_set = load_pci_friendly_set()
    scimago_lookup = load_scimago_lookup()
    print(f"Successfully loaded and processed Scimago data from {SCIMAGO_FILE}")

    openapc_lookup = load_openapc_lookup()
    print(f"Successfully loaded and processed OpenAPC data from {OPENAPC_FILE}")

    doaj_lookup = load_doaj_lookup()
    print(f"Successfully loaded and processed DOAJ data from {DOAJ_FILE}")

    # Initialize totals for tracking updates
    totals = {col: 0 for col in COLUMNS_TO_UPDATE}

    # Process each CSV file in the data_extracted directory
    for csv_path in sorted(glob(os.path.join(DATA_EXTRACTED_DIR, "*.csv"))):
        filename = os.path.basename(csv_path)
        if filename in FILES_TO_SKIP:
            print(f"Skipping file: {filename}")
            continue

        process_csv_file(csv_path, scimago_lookup, openapc_lookup, doaj_lookup, pci_friendly_set, totals)

    # Print summary
    print("\nScript finished.")
    if sum(totals.values()) > 0:
        print("\t- No updates were made.")
    for col, total in totals.items():
        if total > 0:
            print(f"\t- Total {col} updates: {total}")


if __name__ == "__main__":
    main()
