# From the list of .csv files in the 'data_merged' directory, process each file to have it formatted with specific columns and write them to a new directory 'data'.
# Create one more csv file in the 'data' directory: all_biology.csv containing all entries (deduplicated if necessary).
import os
from glob import glob
import polars as pl

INPUT_DIR = "data_merged"
OUTPUT_DIR = "data"

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Expected columns and their required order
EXPECTED_COLUMNS = [
    "Journal",
    "Field",
    "Publisher",
    "Publisher type",
    "Business model",
    "Institution",
    "Institution type",
    "Website",
    "APC Euros",
    "Scimago Rank",
    "PCI partner",
]


def ensure_columns_and_order(df: pl.DataFrame) -> pl.DataFrame:
    """Ensure the dataframe has exactly the EXPECTED_COLUMNS in order, adding missing columns with nulls."""
    # Add any missing expected columns as nulls
    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        df = df.with_columns([pl.lit(None).alias(c) for c in missing])
    # Select only the expected columns in the exact order
    df = df.select(EXPECTED_COLUMNS)
    return df


def format_APC_Euros(df: pl.DataFrame) -> pl.DataFrame:
    """Format the 'APC Euros' column to be integer, extracting only the part before any comma or period, then removing non-digit characters."""
    return df.with_columns(
        pl.col("APC Euros")
        .cast(pl.Utf8)
        .str.replace_all(r"[,.].*", "")  # Remove comma/period and everything after
        .str.replace_all(r"[^\d]", "")  # Remove remaining non-digits
        .cast(pl.Int64, strict=False)
        .alias("APC Euros")
    )


def drop_empty_journals(df: pl.DataFrame, source_name: str) -> pl.DataFrame:
    """Drop rows where Journal is null or empty after trimming."""
    before = df.height
    df = df.with_columns(Journal=pl.col("Journal").cast(pl.Utf8).str.strip_chars())
    df = df.filter(pl.col("Journal").is_not_null() & (pl.col("Journal") != ""))
    after = df.height
    removed = before - after
    if removed > 0:
        print(f"Info: removed {removed} row(s) with empty Journal in {source_name}.")
    return df


def dedupe_by_journal(df: pl.DataFrame, source_name: str) -> pl.DataFrame:
    """Deduplicate by Journal (case-insensitive, trimmed). Keep first occurrence and log a warning if any were removed."""
    df_norm = df.with_columns(
        norm_journal=pl.col("Journal").cast(pl.Utf8).str.to_lowercase().str.strip_chars()
    )
    before = df_norm.height
    df_norm = df_norm.unique(subset=["norm_journal"], keep="first")
    after = df_norm.height
    if after < before:
        removed = before - after
        # Show up to 5 example duplicate journal names to keep logs concise
        dup_names = (
            df_norm.select(pl.col("Journal").cast(pl.Utf8).fill_null("")).head(5).get_column("Journal").to_list()
        )
        sample = ", ".join(
            [name for name in dup_names if isinstance(name, str) and name != ""]) or "(no non-empty Journal names)"
        print(
            f"Warning: removed {removed} duplicate Journal entrie(s) in {source_name}. "
            f"Sample Journals kept: {sample}"
        )
    return df_norm.drop(["norm_journal"]) if "norm_journal" in df_norm.columns else df_norm


def fill_field_from_main_field(df_in: pl.DataFrame) -> pl.DataFrame:
    """If 'Field' is empty/null (or missing), use the column "Journal's MAIN field" to fill it.

    This runs before column selection so that the source column can be dropped later.
    """
    # Perform the backfill
    return df_in.with_columns(
        pl.when(
            pl.col("Field").is_null() | (pl.col("Field").cast(pl.Utf8).str.strip_chars() == "")
        )
        .then(pl.col("Journal's MAIN field").cast(pl.Utf8).str.strip_chars())
        .otherwise(pl.col("Field"))
        .alias("Field")
    )


def normalize_field(df_in: pl.DataFrame) -> pl.DataFrame:
    """Normalize a journal name for deduplication: lowercase and trim."""
    return df_in.with_columns(Field=pl.col("Field").cast(pl.Utf8).str.replace_all("_", " ").str.to_titlecase())


def main():
    processed_frames: list[pl.DataFrame] = []

    # Process each CSV in the input directory
    for csv_path in sorted(glob(os.path.join(INPUT_DIR, "*.csv"))):
        print(f"Processing file: {csv_path}")
        df = pl.read_csv(csv_path)

        # Backfill Field from "Journal's MAIN field" when empty/missing
        df = normalize_field(fill_field_from_main_field(df))

        # Format APC Euros to be numeric
        df = format_APC_Euros(df)

        # Ensure required columns and order
        df = ensure_columns_and_order(df)

        # Drop rows with empty/null Journal
        df = drop_empty_journals(df, os.path.basename(csv_path))

        # Deduplicate by Journal (case-insensitive, trimmed)
        df = dedupe_by_journal(df, os.path.basename(csv_path))

        # Sort alphabetically by Journal
        df = df.sort(by=["Journal"], descending=[False])

        # Write to output directory using same filename
        out_path = os.path.join(OUTPUT_DIR, os.path.basename(csv_path))
        # Write using "" surrounding for all fields to ensure proper CSV formatting
        df.write_csv(out_path, quote_char='"', quote_style="always")
        print(f"Wrote formatted data to: {out_path}")

        processed_frames.append(df)

    # Create all_biology.csv as the concatenation of all processed frames, deduplicated by Journal
    if processed_frames:
        all_df = pl.concat(processed_frames, how="vertical_relaxed")
        # Deduplicate by normalized Journal to be safe across files
        all_df = all_df.with_columns(
            norm_journal=pl.col("Journal").cast(pl.Utf8).str.to_lowercase().str.strip_chars()
        )
        all_df = all_df.unique(subset=["norm_journal"], keep="first").drop(["norm_journal"]).sort("Journal")

        all_out_path = os.path.join(OUTPUT_DIR, "all_biology.csv")
        all_df.write_csv(all_out_path, quote_char='"', quote_style="always")
        print(f"Wrote all biology entries to: {all_out_path}")


if __name__ == "__main__":
    main()
