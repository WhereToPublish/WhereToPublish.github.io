# From the list of .csv files in the 'data_merged' directory, process each file to have it formatted with specific columns and write them to a new directory 'data'.
# Create one more csv file in the 'data' directory: all_biology.csv containing all entries (deduplicated if necessary).
import os
from glob import glob
import polars as pl
from libraries import load_pci_friendly_set, mark_pci_friendly, format_table, normalize_publisher_type, norm_name, \
    norm_url

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
    "Country",
    "Website",
    "APC Euros",
    "Scimago Rank",
    "Scimago Quartile",
    "H index",
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


def dedupe_by_journal_and_website(df: pl.DataFrame, source_name: str) -> pl.DataFrame:
    """Deduplicate entries using OR logic in a simple single pass.
    Rules:
    - Normalize Journal with norm_name and Website with norm_url.
    - Keep the first row in original order.
    - A row is a duplicate if (normalized website is non-empty AND already seen) OR (normalized journal already seen).
    - Prefer URL reason if both match; otherwise Name.

    Logging:
    - Print one line per removed row: reason (URL/Name), normalized key, kept row (Journal/Website), removed row (Journal/Website).
    - Print a summary with URL and Name counts (sum equals total removed by construction).
    """
    df_norm = (
        df.with_columns(
            norm_journal=pl.col("Journal").map_elements(norm_name, return_dtype=pl.Utf8),
            norm_website=pl.col("Website").map_elements(norm_url, return_dtype=pl.Utf8),
        )
        .with_row_index("row_idx")
    )

    seen_names: set[str] = set()
    seen_urls: set[str] = set()
    kept_by_name: dict[str, tuple[str, str]] = {}
    kept_by_url: dict[str, tuple[str, str]] = {}

    removed_row_idxs: list[int] = []
    url_removed_count = 0
    name_removed_count = 0

    # Iterate in current order (row_idx reflects original order at this point)
    for row in df_norm.select(["row_idx", "norm_journal", "norm_website", "Journal", "Website"]).iter_rows(named=True):
        idx = row["row_idx"]
        nj = row["norm_journal"] or ""
        nw = row["norm_website"] or ""
        j = row["Journal"] or ""
        w = row["Website"] or ""

        # URL duplicate has priority when website is non-empty and already seen
        if nw and nw in seen_urls:
            kept_j, kept_w = kept_by_url.get(nw, ("", ""))
            print(
                f"\t[dedupe:{source_name}] Remove (URL) norm_website='{nw}'"
                f"\n\t\tkept=[Journal='{kept_j}', Website='{kept_w}']\n\t\tremoved=[Journal='{j}', Website='{w}']"
            )
            removed_row_idxs.append(idx)
            url_removed_count += 1
            continue

        # Name duplicate fallback
        if nj in seen_names:
            kept_j, kept_w = kept_by_name.get(nj, ("", ""))
            print(
                f"\t[dedupe:{source_name}] Remove (Name) norm_journal='{nj}'"
                f"\n\t\tkept=[Journal='{kept_j}', Website='{kept_w}']\n\t\tremoved=[Journal='{j}', Website='{w}']"
            )
            removed_row_idxs.append(idx)
            name_removed_count += 1
            continue

        # Keep this row; register as seen and record kept mappings
        seen_names.add(nj)
        kept_by_name.setdefault(nj, (j, w))
        if nw:
            seen_urls.add(nw)
            kept_by_url.setdefault(nw, (j, w))

    total_removed = url_removed_count + name_removed_count
    if total_removed > 0:
        print(f"\t[dedupe:{source_name}] Summary: removed {total_removed} row(s): "
              f"\n\t{url_removed_count} by URL, {name_removed_count} by Name.")

    if not removed_row_idxs:
        return df

    # Build the result by filtering out removed row indices
    removed_set = set(removed_row_idxs)
    result = (
        df_norm
        .filter(~pl.col("row_idx").is_in(list(removed_set)))
        .drop([c for c in ("norm_journal", "norm_website", "row_idx") if c in df_norm.columns])
    )
    return result


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

    # Load PCI-friendly journals once
    pci_friendly_set = load_pci_friendly_set()

    # Process each CSV in the input directory
    for csv_path in sorted(glob(os.path.join(INPUT_DIR, "*.csv"))):
        print(f"Processing file: {csv_path}")
        df = pl.read_csv(csv_path)
        # Drop rows with empty/null Journal
        df = drop_empty_journals(df, os.path.basename(csv_path))

        # Backfill Field from "Journal's MAIN field" when empty/missing
        df = normalize_field(fill_field_from_main_field(df))

        # Format table:
        df = format_table(df)
        df = df.with_columns(
            pl.col("Publisher type").map_elements(normalize_publisher_type, return_dtype=pl.Utf8)
            .alias("Publisher type")
        )

        # Update PCI partner using PCI_friendly.csv list
        df = mark_pci_friendly(df, pci_friendly_set)

        # Deduplicate by Journal (case-insensitive, trimmed)
        df = dedupe_by_journal_and_website(df, os.path.basename(csv_path))

        # Sort alphabetically by Journal
        df = df.sort(by=["Journal"], descending=[False])

        # Ensure expected columns and order
        df = ensure_columns_and_order(df)

        # Write to output directory using same filename
        out_path = os.path.join(OUTPUT_DIR, os.path.basename(csv_path))
        # Write using "" surrounding for all fields to ensure proper CSV formatting
        df.write_csv(out_path, quote_char='"', quote_style="always")
        print(f"Wrote formatted data to: {out_path}")

        processed_frames.append(df)

    # Create all_biology.csv as the concatenation of all processed frames, deduplicated by Journal
    if processed_frames:
        all_df = pl.concat(processed_frames, how="vertical_relaxed")
        # Deduplicate using OR logic (same normalized journal OR same normalized website)
        all_df = dedupe_by_journal_and_website(all_df, "all_biology.csv").sort("Journal")

        all_out_path = os.path.join(OUTPUT_DIR, "all_biology.csv")
        all_df.write_csv(all_out_path, quote_char='"', quote_style="always")
        print(f"Wrote all biology entries to: {all_out_path}")


if __name__ == "__main__":
    main()
