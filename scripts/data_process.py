# From the list of .csv files in the 'data_merged' directory, process each file to have it formatted with specific columns and write them to a new directory 'data'.
# Create one more csv file in the 'data' directory: all_biology.csv containing all entries (deduplicated if necessary).
import os
from glob import glob
from libraries import *

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


def is_valid_value(val) -> bool:
    """Check if a value is valid (not None, not empty, not 'nan')."""
    return val is not None and str(val).strip() != "" and str(val).lower() != "nan"


def collect_valid_values(entries: list[dict], field: str) -> list:
    """Collect all valid values for a field from entries."""
    return [entry.get(field) for entry in entries if is_valid_value(entry.get(field))]


def merge_numeric_field(values: list, field: str) -> tuple[any, str | None]:
    """Merge numeric field by keeping highest value. Returns (best_value, conflict_msg or None)."""
    numeric_values = []
    for v in values:
        try:
            numeric_values.append((float(v), v))
        except (ValueError, TypeError):
            pass

    if not numeric_values:
        return values[0], None

    numeric_values.sort(key=lambda x: x[0], reverse=True)
    best_val = numeric_values[0][1]

    # Check for conflicts
    unique_nums = set(nv[0] for nv in numeric_values)
    conflict = None
    if len(unique_nums) > 1:
        conflict = f"{field}: kept={best_val} from options={[nv[1] for nv in numeric_values]}"

    return best_val, conflict


def merge_text_field(values: list, field: str) -> tuple[str, str | None]:
    """Merge text field by keeping longest value. Returns (best_value, conflict_msg or None)."""
    str_values = [(len(str(v)), str(v)) for v in values]
    str_values.sort(key=lambda x: x[0], reverse=True)
    best_val = str_values[0][1]

    # Check for conflicts
    unique_vals = set(sv[1] for sv in str_values if sv[1])
    conflict = None
    if len(unique_vals) > 1:
        conflict = f"{field}: kept='{best_val}' from options={list(unique_vals)}"

    return best_val, conflict


def merge_duplicates(entries: list[dict]) -> dict:
    """Merge duplicate entries by keeping the best information from all duplicates.
    Args:
        entries: List of dictionaries representing duplicate rows
    Returns:
        Merged dictionary with the best values from all entries
    """
    if not entries:
        return {}

    if len(entries) == 1:
        return entries[0]

    numeric_max_fields = {"APC Euros", "H index", "Scimago Rank"}
    merged = {}
    conflicts = []

    # Process each field across all entries
    for field in EXPECTED_COLUMNS:
        values = collect_valid_values(entries, field)

        if not values:
            merged[field] = None
        elif len(values) == 1:
            merged[field] = values[0]
        elif field in numeric_max_fields:
            best_val, conflict = merge_numeric_field(values, field)
            merged[field] = best_val
            if conflict:
                conflicts.append(conflict)
        else:
            best_val, conflict = merge_text_field(values, field)
            merged[field] = best_val
            if conflict:
                conflicts.append(conflict)

    # Log conflicts if any
    if conflicts:
        journal_name = merged.get("Journal", "Unknown")
        print(f"\t[merge_duplicates] WARNING: Conflicts for Journal='{journal_name}':")
        for conflict in conflicts:
            print(f"\t\t{conflict}")

    return merged


def identify_duplicate_groups(df_norm: pl.DataFrame, source_name: str) -> tuple[dict, dict, int, int]:
    """Identify duplicate groups by URL and Name. Returns (url_groups, name_groups, url_count, name_count)."""
    duplicate_groups_by_url = {}
    duplicate_groups_by_name = {}
    seen_names = set()
    seen_urls = set()
    url_removed_count = 0
    name_removed_count = 0

    for row in df_norm.select(["row_idx", "norm_journal", "norm_website", "Journal", "Website"]).iter_rows(named=True):
        idx = row["row_idx"]
        nj = row["norm_journal"] or ""
        nw = row["norm_website"] or ""

        # URL duplicate has priority when website is non-empty and already seen
        if nw and nw in seen_urls:
            duplicate_groups_by_url.setdefault(nw, []).append(idx)
            url_removed_count += 1
            print(f"\t[dedupe:{source_name}] Duplicate (URL) norm_website='{nw}'"
                  f"\n\t\tJournal='{row['Journal']}', Website='{row['Website']}'")
            continue

        # Name duplicate fallback
        if nj in seen_names:
            duplicate_groups_by_name.setdefault(nj, []).append(idx)
            name_removed_count += 1
            print(f"\t[dedupe:{source_name}] Duplicate (Name) norm_journal='{nj}'"
                  f"\n\t\tJournal='{row['Journal']}', Website='{row['Website']}'")
            continue

        # Keep this row; register as seen and record as first in its group
        seen_names.add(nj)
        duplicate_groups_by_name.setdefault(nj, []).append(idx)
        if nw:
            seen_urls.add(nw)
            duplicate_groups_by_url.setdefault(nw, []).append(idx)

    return duplicate_groups_by_url, duplicate_groups_by_name, url_removed_count, name_removed_count


def dedupe_by_journal_and_website(df: pl.DataFrame, source_name: str) -> pl.DataFrame:
    """Deduplicate entries using OR logic and merge duplicate information.
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

    # Identify duplicate groups
    url_groups, name_groups, url_count, name_count = identify_duplicate_groups(df_norm, source_name)

    total_removed = url_count + name_count
    if total_removed > 0:
        print(f"\t[dedupe:{source_name}] Summary: found {total_removed} duplicate(s): "
              f"\n\t{url_count} by URL, {name_count} by Name.")
    else:
        # No duplicates found, return early
        return df_norm.drop([c for c in ("norm_journal", "norm_website", "row_idx") if c in df_norm.columns])

    # Convert dataframe to list of dicts for easier manipulation
    all_rows = df_norm.drop([c for c in ("norm_journal", "norm_website", "row_idx") if c in df_norm.columns]).to_dicts()

    # Merge duplicate groups and track which indices to keep
    processed_indices = set()
    kept_indices = []

    # Process URL groups first (higher priority), then Name groups
    for groups in [url_groups, name_groups]:
        for indices in groups.values():
            if len(indices) > 1 and not any(idx in processed_indices for idx in indices):
                entries = [all_rows[idx] for idx in indices]
                merged = merge_duplicates(entries)
                first_idx = min(indices)
                all_rows[first_idx] = merged
                kept_indices.append(first_idx)
                processed_indices.update(indices)

    # Keep non-duplicate rows as-is
    for idx in range(len(all_rows)):
        if idx not in processed_indices:
            kept_indices.append(idx)

    # Build result by selecting kept rows in order
    kept_indices.sort()
    result_rows = [all_rows[idx] for idx in kept_indices]

    # Convert back to DataFrame
    return pl.DataFrame(result_rows, schema_overrides={col: pl.Utf8 for col in EXPECTED_COLUMNS})


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
        df = load_csv(csv_path)
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
