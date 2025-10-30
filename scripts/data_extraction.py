import os
import re
from glob import glob
import polars as pl
from libraries import load_csv, write_ordered, project_to_final_string_schema

# Directories
INPUT_DIR = "data_raw"
INPUT_EXTRACTION_PATH = "data_extraction/extraction.tsv"
OUTPUT_DIR = "data_extracted"

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
os.makedirs(OUTPUT_DIR, exist_ok=True)


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


def normalize_publisher_type(name: str) -> str:
    """ Normalize publisher type values.
    "for-profit" -> "For-profit"
    "university press" -> "University press"
    "non-profit" -> "Non-profit"
    """
    if name is None:
        return ""
    s = str(name).strip().lower()
    mapping = {
        "for-profit": "For-profit",
        "university press": "University Press",
        "non-profit": "Non-profit",
        "for-profit society-run": "For-profit Society-run"
    }
    return mapping.get(s, name)


def normalize_business_model(name: str) -> str:
    """Normalize business model values.
    "oa" -> "OA"
    "gold_OA" -> "Gold OA"
    "diamond_OA" -> "Diamond OA"
    "hybrid" -> "Hybrid"
    "subscription" -> "Subscription"
    """
    if name is None:
        return ""
    s = str(name).strip().lower()
    mapping = {
        "oa": "OA",
        "gold_oa": "Gold OA",
        "diamond_oa": "Diamond OA",
        "hybrid": "Hybrid",
        "subscription": "Subscription",
    }
    return mapping.get(s, name)

def normalize_field(name: str) -> str:
    """Normalize field values by stripping leading/trailing spaces."""
    if name is None:
        return ""
    if name.lower() == "general":
        return "Generalist"
    return str(name).strip()

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
    # for-profit list
    fp_list = ["springer", "elsevier", "wiley", "mdpi", "taylor", "francis", "hindawi", "frontiers", "informa",
               "sciendo", "nature"]
    for kw in fp_list:
        if kw in p:
            return "For-profit"
    return None


def coalesce_from_extraction(base_df: pl.DataFrame, ext_df: pl.DataFrame) -> pl.DataFrame:
    # Join on normalized journal key
    left = base_df.join(ext_df, on="__norm_journal__", how="left", suffix="_ext", coalesce=True)

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
    left = left.with_columns(pl.col("Business model").map_elements(normalize_business_model, return_dtype=pl.Utf8).alias("Business model"))
    left = left.with_columns(pl.col("Publisher type").map_elements(normalize_publisher_type, return_dtype=pl.Utf8).alias("Publisher type"))
    left = left.with_columns(pl.col("Field").map_elements(normalize_field, return_dtype=pl.Utf8).alias("Field"))
    return left


def prepare_base_df(df: pl.DataFrame) -> pl.DataFrame:
    # Ensure columns, cast to Utf8, then build normalized key for joining
    df = project_to_final_string_schema(df)
    df = df.with_columns(
        pl.col("Journal").map_elements(normalize_journal_name, return_dtype=pl.Utf8).alias("__norm_journal__")
    )
    return df


def main():
    # Load and prepare extraction data
    extraction_df = load_and_prepare_extraction(INPUT_EXTRACTION_PATH)

    # Process each CSV in input dir
    csv_paths = sorted(glob(os.path.join(INPUT_DIR, "*.csv")))

    for path in csv_paths:
        fname = os.path.basename(path)

        base_df = load_csv(path)
        # Project to final string schema to align with dafnee frames if appended
        base_df = project_to_final_string_schema(base_df)

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
