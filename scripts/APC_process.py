"""Create website tables from the 2019-2025 Scholarly Communications Lab APC dataset."""

import re
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
from libraries import clean_string, load_csv, normalize_dataverse_publisher

DATAVERSE_FILE = Path("data_extraction") / "scholcommlab_apc_dataset_2019_2025-2.csv.gz"
OUTPUT_DIR = Path("data")
REQUIRED_COLUMNS = {"unique_id", "publisher", "journal", "oa_status", "apc_year", "apc_eur"}
BASE_COLUMNS = ["Journal", "Publisher", "Business model"]
APC_VALUE_COLUMNS = ["APC (€)", "APC year"]
ALL_PUBLISHER_COLUMNS = BASE_COLUMNS + APC_VALUE_COLUMNS


def clean_journal_name(name: str | None) -> str:
    """Normalize journal titles and remove control/formatting characters."""
    return clean_string(name)


def publisher_filename(publisher: str) -> str:
    """Return the filename-safe publisher name used by the website."""
    return re.sub(r"[^A-Za-z0-9]+", "_", publisher).strip("_")


def prepare_apc_table(source: pl.DataFrame) -> tuple[pl.DataFrame, list[int], list[str]]:
    """Validate the source and return the journal/publisher APC matrix."""
    missing_columns = REQUIRED_COLUMNS.difference(source.columns)
    assert not missing_columns, f"Missing APC dataset columns: {sorted(missing_columns)}"
    assert source.height > 0, "The APC dataset is empty"
    assert source["unique_id"].null_count() == 0, "APC dataset contains missing unique_id values"

    prepared = source.with_columns(
        pl.col("journal").map_elements(clean_journal_name, return_dtype=pl.Utf8).alias("Journal"),
        pl.col("publisher")
        .map_elements(normalize_dataverse_publisher, return_dtype=pl.Utf8)
        .alias("Publisher"),
        pl.when(pl.col("oa_status") == "Gold OA")
        .then(pl.lit("OA"))
        .when(pl.col("oa_status") == "Hybrid OA")
        .then(pl.lit("Hybrid"))
        .otherwise(pl.lit(""))
        .alias("Business model"),
        pl.col("apc_year").cast(pl.Int64, strict=True).alias("year"),
        pl.col("apc_eur").cast(pl.Float64, strict=False).alias("apc_eur_value"),
    )

    assert prepared.filter(pl.col("Journal").str.len_chars() == 0).height == 0, (
        "APC dataset contains an empty journal title after cleaning"
    )
    assert prepared.filter(pl.col("Publisher").str.len_chars() == 0).height == 0, (
        "APC dataset contains an empty publisher after normalization"
    )
    has_apc_text = pl.col("apc_eur").cast(pl.Utf8).str.strip_chars() != ""
    assert prepared.filter(
        pl.col("apc_eur").is_not_null() & has_apc_text & pl.col("apc_eur_value").is_null()
    ).height == 0, (
        "APC dataset contains non-numeric EUR values"
    )
    assert prepared.filter(pl.col("apc_eur_value") < 0).height == 0, (
        "APC dataset contains negative EUR values"
    )
    duplicate_years = prepared.group_by(["unique_id", "publisher", "year"]).len().filter(pl.col("len") > 1)
    assert duplicate_years.height == 0, (
        f"Expected one record per journal, publisher, and year; found {duplicate_years.height} duplicates"
    )

    years = sorted(prepared["year"].unique().to_list())
    assert years, "APC dataset contains no APC years"

    latest_metadata = (
        prepared.select(["unique_id", "Publisher", "Journal", "Business model", "year"])
        .sort("year")
        .unique(subset=["unique_id", "Publisher"], keep="last", maintain_order=True)
        .select(["unique_id", "Publisher", "Journal", "Business model"])
    )
    annual_apcs = (
        prepared.filter(pl.col("apc_eur_value").is_not_null())
        .with_columns(pl.col("apc_eur_value").round(0).cast(pl.Int64).alias("APC_EUR"))
        .group_by(["unique_id", "Publisher", "year"])
        .agg(pl.col("APC_EUR").mean().round(0).cast(pl.Int64))
        .pivot(on="year", index=["unique_id", "Publisher"], values="APC_EUR")
    )
    assert annual_apcs.height > 0, "APC dataset contains no numeric EUR APC values"

    year_columns_by_year = {year: str(year) for year in years if str(year) in annual_apcs.columns}
    annual_apcs = annual_apcs.rename(
        {column: f"APC {year} (€)" for year, column in year_columns_by_year.items()}
    )
    year_columns = [f"APC {year} (€)" for year in years if f"APC {year} (€)" in annual_apcs.columns]
    assert year_columns, "No annual APC columns were produced"

    apc_table = latest_metadata.join(annual_apcs, on=["unique_id", "Publisher"], how="inner")
    apc_table = apc_table.with_columns(
        pl.coalesce([pl.col(column) for column in reversed(year_columns)]).alias("APC (€)")
    )
    apc_table = apc_table.with_columns(
        pl.coalesce([
            pl.when(pl.col(column).is_not_null()).then(pl.lit(int(column[4:8])))
            for column in reversed(year_columns)
        ]).alias("APC year")
    )
    return apc_table.sort(["Journal", "Publisher"]), years, year_columns


def process_apc_data(
    input_file: str | Path = DATAVERSE_FILE,
    output_dir: str | Path = OUTPUT_DIR,
) -> None:
    """Write one table per publisher and a compact all-publishers table."""
    source_path = Path(input_file)
    assert source_path.is_file(), f"APC dataset does not exist: {source_path}"
    output_path = Path(output_dir)
    print(f"Loading {source_path}...")
    source = load_csv(str(source_path), infer_schema=False)
    print(f"  Raw rows: {source.height}")

    apc_table, years, year_columns = prepare_apc_table(source)
    publishers = sorted(apc_table["Publisher"].unique().to_list())
    assert publishers, "No publishers found in APC dataset"
    print(f"  Years available: {years}")
    print(f"  Publishers: {publishers}")
    output_path.mkdir(parents=True, exist_ok=True)

    for publisher in publishers:
        publisher_table = apc_table.filter(pl.col("Publisher") == publisher)
        available_year_columns = [
            column for column in year_columns
            if publisher_table[column].null_count() < publisher_table.height
        ]
        output_columns = BASE_COLUMNS + available_year_columns + APC_VALUE_COLUMNS
        publisher_table = publisher_table.select(output_columns).sort("Journal")
        assert publisher_table.height > 0, f"No APC values available for publisher {publisher}"
        file_path = output_path / f"APC_{publisher_filename(publisher)}.csv"
        publisher_table.write_csv(file_path)
        assert pl.read_csv(file_path).columns == output_columns
        print(f"  Wrote {file_path}: {publisher_table.height} journals")

    all_publishers = apc_table.select(ALL_PUBLISHER_COLUMNS).sort(["Journal", "Publisher"])
    file_path = output_path / "APC_all.csv"
    all_publishers.write_csv(file_path)
    assert pl.read_csv(file_path).columns == ALL_PUBLISHER_COLUMNS
    assert not any(column.startswith("APC 20") for column in all_publishers.columns)
    print(f"  Wrote {file_path}: {all_publishers.height} journals")
    print("Done.")


if __name__ == "__main__":
    process_apc_data()
