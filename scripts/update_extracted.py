import os
from glob import glob
import polars as pl
from libraries import load_pci_friendly_set, mark_pci_friendly, format_table

# Constants
DATA_EXTRACTED_DIR = "data_extracted"
SCIMAGO_FILE = os.path.join("data_extraction", "scimagojr.csv")
FILES_TO_SKIP = []
COLUMNS_TO_UPDATE = [
    "Scimago Rank",
    "Publisher",
    "Business model",
    "Scimago Quartile",
    "H index"
]


def remove_unused_characters(name: str) -> str:
    """Remove unused characters from journal names for normalization."""
    if name is None:
        return ""
    return str(name).replace("the ", "").replace("-", " ").replace("_", " ").strip()


def update_and_log_statistics(df: pl.DataFrame, totals: dict) -> pl.DataFrame:
    """
    Update columns from Scimago data and log statistics.

    Args:
        df (pl.DataFrame): The DataFrame to update.
        totals (dict): A dictionary to store the total update counts.

    Returns:
        pl.DataFrame: The updated DataFrame.
    """
    for col in COLUMNS_TO_UPDATE:
        if col not in df.columns:
            print(f"  - Warning: Column '{col}' not found in DataFrame.")
            continue
        scimago_col = f"{col}_scimago"
        updates = df.filter(pl.col(col).is_null() & pl.col(scimago_col).is_not_null()).height
        totals[col] += updates
        print(f"  - {col} updates: {updates}")
        df = df.with_columns(
            pl.when(pl.col(col).is_null())
            .then(pl.col(scimago_col))
            .otherwise(pl.col(col))
            .alias(col)
        )
    return df


def main():
    """
    Main function to update Scimago Rank and Publisher information in CSV files,
    and apply formatting/normalization also used in data_process.py.
    """
    print("Starting script to update Scimago and Publisher info...")

    # Load PCI-friendly set once
    pci_friendly_set = load_pci_friendly_set()

    # Load Scimago data
    scimago_df = pl.read_csv(SCIMAGO_FILE, separator=';')
    scimago_df = scimago_df.rename(
        {
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
        }
    )

    scimago_df = scimago_df.with_columns(
        pl.col("Journal_scimago").str.to_lowercase().map_elements(remove_unused_characters, return_dtype=pl.Utf8).alias(
            "norm_journal_scimago"
        ),
        pl.when(pl.col("Open Access Diamond_scimago") == "Yes")
        .then(pl.lit("OA diamond"))
        .when(pl.col("Open Access_scimago") == "Yes")
        .then(pl.lit("OA"))
        .otherwise(None)
        .alias("Business model_scimago"),
        pl.col("Areas_scimago").str.split(";").list.first().alias("Journal's MAIN field_scimago"),
        pl.col("Categories_scimago").str.split(";").list.first().str.replace(r" \(Q\d\)", "").str.replace(" (miscellaneous)", "", literal=True).alias("Field_scimago"),
    )

    # Keep only the necessary columns and remove duplicates
    scimago_lookup = scimago_df.select(
        [
            "norm_journal_scimago",
            "Scimago Rank_scimago",
            "Publisher_scimago",
            "Business model_scimago",
            "Scimago Quartile_scimago",
            "H index_scimago",
            "Country_scimago",
            "Journal's MAIN field_scimago",
            "Field_scimago",
        ]
    ).unique(subset=["norm_journal_scimago"], keep="first")

    print(f"Successfully loaded and processed Scimago data from {SCIMAGO_FILE}")

    totals = {col: 0 for col in COLUMNS_TO_UPDATE}

    # Process each CSV file in the data_extracted directory
    for csv_path in glob(os.path.join(DATA_EXTRACTED_DIR, "*.csv")):
        filename = os.path.basename(csv_path)
        if filename in FILES_TO_SKIP:
            print(f"Skipping file: {filename}")
            continue

        print(f"Processing file: {csv_path}")
        target_df = pl.read_csv(csv_path)

        # Keep track of original columns to avoid persisting helper columns
        original_cols = target_df.columns.copy()

        target_df = target_df.with_columns(
            pl.col("Journal").str.to_lowercase().map_elements(remove_unused_characters, return_dtype=pl.Utf8).alias(
                "norm_journal"
            )
        )

        # Join with scimago data
        updated_df = target_df.join(
            scimago_lookup,
            left_on="norm_journal",
            right_on="norm_journal_scimago",
            how="left",
            coalesce=True,
        )

        # Update columns and log statistics
        updated_df = update_and_log_statistics(updated_df, totals)

        updated_df = format_table(updated_df)
        # Mark PCI friendly
        updated_df = mark_pci_friendly(updated_df, pci_friendly_set)

        # Select original columns only (avoid helper/join columns)
        final_df = updated_df.select(original_cols)

        # Overwrite the existing file
        final_df.write_csv(csv_path)
        print(f"Successfully updated and saved {csv_path}")
    print("Script finished.")
    print("\nTotal updates:")
    for col, total in totals.items():
        print(f"  - Total {col} updates: {total}")


if __name__ == "__main__":
    main()
