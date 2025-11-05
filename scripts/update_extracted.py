import os
from glob import glob
import polars as pl
from libraries import load_pci_friendly_set, mark_pci_friendly, format_table

# Constants
DATA_EXTRACTED_DIR = "data_extracted"
SCIMAGO_FILE = os.path.join("data_extraction", "scimagojr.csv")
FILES_TO_SKIP = ["dafnee.csv"]


def remove_unused_characters(name: str) -> str:
    """Remove unused characters from journal names for normalization."""
    if name is None:
        return ""
    return str(name).replace("the ", "").replace("-", " ").replace("_", " ").strip()


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
        {"Title": "Journal_scimago", "SJR": "Scimago Rank_scimago", "Publisher": "Publisher_scimago"})

    scimago_df = scimago_df.with_columns(
        pl.col("Journal_scimago").str.to_lowercase().map_elements(remove_unused_characters, return_dtype=pl.Utf8).alias(
            "norm_journal_scimago")
    )

    # Keep only the necessary columns and remove duplicates
    scimago_lookup = scimago_df.select(
        ["norm_journal_scimago", "Scimago Rank_scimago", "Publisher_scimago"]
    ).unique(subset=["norm_journal_scimago"], keep="first")

    print(f"Successfully loaded and processed Scimago data from {SCIMAGO_FILE}")

    total_scimago_updates = 0
    total_publisher_updates = 0

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
                "norm_journal")
        )

        # Join with scimago data
        updated_df = target_df.join(
            scimago_lookup,
            left_on="norm_journal",
            right_on="norm_journal_scimago",
            how="left",
            coalesce=True,
        )

        # Calculate updates
        scimago_updates = updated_df.filter(
            pl.col("Scimago Rank").is_null() & pl.col("Scimago Rank_scimago").is_not_null()
        ).height
        publisher_updates = updated_df.filter(
            pl.col("Publisher").is_null() & pl.col("Publisher_scimago").is_not_null()
        ).height

        total_scimago_updates += scimago_updates
        total_publisher_updates += publisher_updates

        print(f"  - Scimago Rank updates: {scimago_updates}")
        print(f"  - Publisher updates: {publisher_updates}")

        # Update columns if they are null
        updated_df = updated_df.with_columns(
            pl.when(pl.col("Scimago Rank").is_null())
            .then(pl.col("Scimago Rank_scimago"))
            .otherwise(pl.col("Scimago Rank"))
            .alias("Scimago Rank")
        )
        updated_df = updated_df.with_columns(
            pl.when(pl.col("Publisher").is_null())
            .then(pl.col("Publisher_scimago"))
            .otherwise(pl.col("Publisher"))
            .alias("Publisher")
        )
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
    print(f"  - Total Scimago Rank updates: {total_scimago_updates}")
    print(f"  - Total Publisher updates: {total_publisher_updates}")


if __name__ == "__main__":
    main()
