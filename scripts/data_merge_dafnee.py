import os
from glob import glob
import polars as pl
from libraries import load_csv, write_ordered, project_to_final_string_schema

# Directories
INPUT_DIR = "data_extracted"
OUTPUT_DIR = "data_merged"

os.makedirs(OUTPUT_DIR, exist_ok=True)


def normalize_field(name: str) -> str:
    """Normalize field values by stripping leading/trailing spaces."""
    if name is None:
        return ""
    if name.lower() == "general":
        return "Generalist"
    return str(name).strip()


def derive_publisher_type_from_publisher_and_institution(df: pl.DataFrame) -> pl.DataFrame:
    """Derive 'Publisher type' from 'Publisher' and 'Institution' columns.
    Institution can be "", "other", "Society", "Uni/Gov", "Museum", "Non-profit".
    When Institution is non-empty and not "other", Publisher type is
    "{Publisher} on behalf of a {Institution}". Otherwise, it's just Publisher.
    """

    def derive_type(publisher_type: str, institution_type: str) -> str:
        if publisher_type is None:
            return ""
        if publisher_type.lower() == "non-profit":
            return "Non-profit"
        if institution_type.lower() == "uni/gov":
            return f"{publisher_type} associated with a university or government institution"
        elif institution_type.lower() in ["non-profit", "society", "museum"]:
            return f"{publisher_type} associated with a {institution_type.lower()}"
        else:
            return publisher_type

    return df.with_columns(
        pl.struct(["Publisher type", "Institution type"])
        .map_elements(lambda row: derive_type(row["Publisher type"], row["Institution type"]), return_dtype=pl.Utf8)
        .alias("Publisher type")
    )


def main():
    # Detect if dafnee.csv exists and load/split for later merging
    dafnee_path = os.path.join(INPUT_DIR, "dafnee.csv.gz")
    dafnee_general = None
    dafnee_not_general = None
    if os.path.exists(dafnee_path):
        ddf = load_csv(dafnee_path)
        # Project to final string schema for safe concatenation later
        ddf = project_to_final_string_schema(ddf)
        # Normalize Publisher type for dafnee rows
        ddf = derive_publisher_type_from_publisher_and_institution(ddf)
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
            dafnee_not_general = dafnee_not_general.with_columns(
                pl.lit("Ecology and Evolution").alias("Journal's MAIN field"))

    # Process each CSV in input dir
    csv_paths = sorted(glob(os.path.join(INPUT_DIR, "*.csv*")))

    for path in csv_paths:
        fname = os.path.basename(path)
        if fname.startswith("dafnee.csv"):
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
        base_df = base_df.with_columns(
            pl.col("Field").map_elements(normalize_field, return_dtype=pl.Utf8).alias("Field"))

        # Finalize and write
        out_path = os.path.join(OUTPUT_DIR, fname)

        write_ordered(base_df, out_path)
        print(f"Wrote merged file: {out_path}")


if __name__ == "__main__":
    main()
