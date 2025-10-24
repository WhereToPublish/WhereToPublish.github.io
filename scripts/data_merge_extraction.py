import os
from glob import glob
import re
import polars as pl

# Directories
INPUT_DIR = "data_raw"
INPUT_EXTRACTION_PATH = "data_extracted/extraction.tsv"
OUTPUT_DIR = "data_merged"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Expected columns and their final order
FINAL_COLUMNS = [
    "Journal",
    "Website",
    "Journal's MAIN field",
    "Field",
    "Publisher type",
    "Publisher",
    "Institution",
    "Institution type",
    "Country",
    "Business model",
    "APC Euros",
    "Scimago Rank",
    "PCI partner",
]

# Mapping from extraction.tsv columns to our target columns
EXTRACTION_TO_TARGET = {
    "journal": "Journal",
    "APC_euros": "APC Euros",
    "PCI_partnership": "PCI partner",
    "SJR": "Scimago Rank",
    "business_model": "Business model",
    "publisher": "Publisher",
    "website": "Website",
}


def normalize_journal_name(name: str) -> str:
    """Normalize journal names for matching:
    - lowercase
    - strip leading/trailing spaces
    - remove anything in parentheses
    - replace non-alphanumeric with space
    - collapse multiple spaces
    """
    if name is None:
        return ""
    # Remove parentheses and their content
    name = re.sub(r"\([^)]*\)", " ", str(name))
    # Lowercase
    name = name.lower()
    # Replace non-alphanumeric with space
    name = re.sub(r"[^a-z0-9]", " ", name)
    # Collapse spaces
    name = re.sub(r"\s+", " ", name).strip()
    return name


def first_source_value(val: str) -> str | None:
    """Take the first source entry (split by '|'), return the value after the first ':'; strip source labels."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    first = s.split("|")[0]
    # Some entries might not contain ':'; return the whole string in that case
    if ":" in first:
        return first.split(":", 1)[1].strip() or None
    return first.strip() or None


def infer_publisher_type(publisher: str | None) -> str | None:
    """Infer Publisher type from publisher name when missing.
    - contains 'university press' -> 'University Press'
    - contains springer, elsevier, wiley, taylor, francis, frontiers, informa, sciendo, nature -> 'for-profit'
    - contains mdpi or hindawi -> 'predatory'
    """
    if not publisher:
        return None
    p = publisher.lower()
    if "university press" in p:
        return "University Press"
    # predatory first for clarity on overlaps
    if "mdpi" in p or "hindawi" in p:
        return "predatory"
    # for-profit list
    for kw in [
        "springer",
        "elsevier",
        "wiley",
        "taylor",
        " francis",
        "frontiers",
        "informa",
        "sciendo",
        "nature",
    ]:
        if kw in p:
            return "for-profit"
    return None


def load_and_prepare_extraction(path: str) -> pl.DataFrame:
    df = pl.read_csv(path, separator="\t")
    # Keep only mapped columns and rename to target names
    keep_cols = [c for c in df.columns if c in EXTRACTION_TO_TARGET]
    df = df.select([pl.col(c).alias(EXTRACTION_TO_TARGET[c]) for c in keep_cols])

    # Apply first_source_value to all non-Journal columns
    value_cols = [c for c in df.columns if c != "Journal"]
    for c in value_cols:
        df = df.with_columns(pl.col(c).map_elements(first_source_value, return_dtype=pl.Utf8).alias(c))

    # Create normalized key for joining
    df = df.with_columns(
        pl.col("Journal").map_elements(normalize_journal_name, return_dtype=pl.Utf8).alias("__norm_journal__")
    )
    # Deduplicate on normalized journal, keeping the first occurrence
    df = df.unique(subset=["__norm_journal__"], keep="first")
    return df


def ensure_columns(df: pl.DataFrame) -> pl.DataFrame:
    # Ensure all FINAL_COLUMNS exist; add missing as nulls
    for c in FINAL_COLUMNS:
        if c not in df.columns:
            df = df.with_columns(pl.lit(None).alias(c))
    return df


def project_to_final_string_schema(df: pl.DataFrame) -> pl.DataFrame:
    """Ensure all final columns are present and cast them to Utf8 for safe concatenation/merging."""
    df = ensure_columns(df)
    return df.select([pl.col(c).cast(pl.Utf8).alias(c) for c in FINAL_COLUMNS])


def coalesce_from_extraction(base_df: pl.DataFrame, ext_df: pl.DataFrame) -> pl.DataFrame:
    # Join on normalized journal key
    left = base_df.join(ext_df, on="__norm_journal__", how="left", suffix="_ext")

    # For each mapped column from extraction, fill into base only when base is missing/empty
    mapped_targets = [
        "Website",
        "APC Euros",
        "PCI partner",
        "Scimago Rank",
        "Business model",
        "Publisher",
        # Journal is used only for joining; do not overwrite
    ]
    for col in mapped_targets:
        col_ext = f"{col}_ext"
        if col not in left.columns or col_ext not in left.columns:
            continue
        # treat empty strings as missing
        presence = (
            pl.col(col).is_not_null()
            & (pl.col(col).cast(pl.Utf8).str.strip_chars().str.len_chars() > 0)
        )
        left = left.with_columns(
            pl.when(presence).then(pl.col(col)).otherwise(pl.col(col_ext)).alias(col)
        )

    # Infer Publisher type if missing
    if "Publisher type" in left.columns:
        presence_pubtype = (
            pl.col("Publisher type").is_not_null()
            & (pl.col("Publisher type").cast(pl.Utf8).str.strip_chars().str.len_chars() > 0)
        )
        left = left.with_columns(
            pl.when(presence_pubtype)
            .then(pl.col("Publisher type"))
            .otherwise(pl.col("Publisher").map_elements(infer_publisher_type, return_dtype=pl.Utf8))
            .alias("Publisher type")
        )
    else:
        left = left.with_columns(
            pl.col("Publisher").map_elements(infer_publisher_type, return_dtype=pl.Utf8).alias("Publisher type")
        )

    # Clean up temporary extraction columns
    drop_cols = [c for c in left.columns if c.endswith("_ext")]
    left = left.drop(drop_cols)

    return left


def prepare_base_df(df: pl.DataFrame) -> pl.DataFrame:
    # Ensure columns, cast to Utf8, then build normalized key for joining
    df = project_to_final_string_schema(df)
    df = df.with_columns(
        pl.col("Journal").map_elements(normalize_journal_name, return_dtype=pl.Utf8).alias("__norm_journal__")
    )
    return df


def write_ordered(df: pl.DataFrame, out_path: str) -> None:
    # Order columns and write CSV
    ordered = df.select([pl.col(c) for c in FINAL_COLUMNS])
    ordered.write_csv(out_path)


def load_csv(path: str) -> pl.DataFrame:
    return pl.read_csv(path, ignore_errors=True)


def main():
    # Load and prepare extraction data
    extraction_df = load_and_prepare_extraction(INPUT_EXTRACTION_PATH)

    # Detect if dafnee.csv exists and load/split for later merging
    dafnee_path = os.path.join(INPUT_DIR, "dafnee.csv")
    dafnee_general = None
    dafnee_not_general = None
    if os.path.exists(dafnee_path):
        ddf = load_csv(dafnee_path)
        # Project to final string schema for safe concatenation later
        ddf = project_to_final_string_schema(ddf)
        # Split by Field == 'general' (case-insensitive, strip)
        field_norm = (
            pl.col("Field")
            .cast(pl.Utf8)
            .str.to_lowercase()
            .str.strip_chars()
        )
        ddf = ddf.with_columns(field_norm.alias("__field_norm__"))
        dafnee_general = ddf.filter(pl.col("__field_norm__") == "general").drop("__field_norm__")
        dafnee_not_general = ddf.filter(pl.col("__field_norm__") != "general").drop("__field_norm__")
        # Do NOT add normalized key yet; we'll compute it after concatenation into targets
        # Set Journal's MAIN field for dafnee-derived rows according to destination
        if dafnee_general.height > 0:
            dafnee_general = dafnee_general.with_columns(pl.lit("Generalist").alias("Journal's MAIN field"))
        if dafnee_not_general.height > 0:
            dafnee_not_general = dafnee_not_general.with_columns(pl.lit("Ecology and Evolution").alias("Journal's MAIN field"))

    # Process each CSV in input dir
    csv_paths = sorted(glob(os.path.join(INPUT_DIR, "*.csv")))

    for path in csv_paths:
        fname = os.path.basename(path)
        if fname == "dafnee.csv":
            # Do not write dafnee.csv output
            continue

        base_df = load_csv(path)
        # Project to final string schema to align with dafnee frames if appended
        base_df = project_to_final_string_schema(base_df)

        # Special handling: append dafnee rows to target files
        if fname == "ecology_evolution.csv" and dafnee_not_general is not None and dafnee_not_general.height > 0:
            base_df = pl.concat([base_df, dafnee_not_general], how="vertical", rechunk=True)
        if fname == "generalist.csv" and dafnee_general is not None and dafnee_general.height > 0:
            base_df = pl.concat([base_df, dafnee_general], how="vertical", rechunk=True)

        # Prepare for join (adds normalized key)
        base_df = prepare_base_df(base_df)

        # Merge from extraction while preserving existing non-empty values
        merged = coalesce_from_extraction(base_df, extraction_df)

        # Finalize and write
        out_path = os.path.join(OUTPUT_DIR, fname)
        write_ordered(merged, out_path)
        print(f"Wrote merged file: {out_path}")


if __name__ == "__main__":
    main()
