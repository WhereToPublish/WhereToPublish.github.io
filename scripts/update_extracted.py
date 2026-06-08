import datetime
import os
from glob import glob
from libraries import *
import re

# Current year used for openAPC recency check
CURRENT_YEAR = datetime.datetime.now().year

# Constants
DATA_EXTRACTED_DIR = "data_extracted"
SCIMAGO_FILE = os.path.join("data_extraction", "scimagojr.csv.gz")
ISSN_TYPE_FILE = os.path.join("config", "ISSN_type.csv")
OPENAPC_FILE = os.path.join("data_extraction", "openapc.csv.gz")
DOAJ_FILE = os.path.join("data_extraction", "DOAJ.csv.gz")
DATAVERSE_FILE = os.path.join("data_extraction", "APC_dataverse.txt.gz")
FILES_TO_SKIP = []

# Columns that should be updated from each data source
FILE_COLS = {"scimago": [("Scimago Rank", True),
                         ("Publisher", False),
                         ("Business model", False),
                         ("Scimago Quartile", True),
                         ("H index", True),
                         ("e-ISSN", False),
                         ("p-ISSN", False),
                         ("ISSN-L", False)],
             "openapc": [("APC Euros", True),
                         ("Publisher", False),
                         ("Business model", False),
                         ("e-ISSN", False),
                         ("p-ISSN", False),
                         ("ISSN-L", False)],
             "doaj": [("Publisher", False),
                      ("Country", False),
                      ("Website", False),
                      ("Institution", False),
                      ("APC Euros", False),
                      ("e-ISSN", False),
                      ("p-ISSN", False)],
             "dataverse": [("APC Euros", False),
                           ("Publisher", False),
                           ("Business model", False)]}

COLUMNS_TO_UPDATE = set([col for cols in FILE_COLS.values() for col, _ in cols])
print(f"Columns to update: {COLUMNS_TO_UPDATE}")

# Maps source name -> presence column written in data_extracted CSVs
# (Dataverse intentionally omitted — no presence column was requested for it)
SOURCE_PRESENCE_COL = {
    "scimago": "Present in Scimago",
    "doaj": "Present in DOAJ",
    "openapc": "Present in openAPC",
}


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


def load_issn_type_lookup() -> dict[str, str]:
    """Load config/ISSN_type.csv and return a dict mapping ISSN → combined type string.

    The type string is a semicolon-joined set of type codes sorted by TYPE_ORDER,
    e.g. "p;l", "e;l", "e", "p".
    """
    df = pl.read_csv(ISSN_TYPE_FILE)
    assert list(df.columns) == ["ISSN", "Type"], (
        f"Unexpected columns in {ISSN_TYPE_FILE}: {df.columns}"
    )
    assert df["ISSN"].n_unique() == df.height, (
        f"{ISSN_TYPE_FILE} has duplicate ISSNs: {df.height} rows, {df['ISSN'].n_unique()} unique"
    )
    assert df.filter(pl.col("ISSN").is_null() | pl.col("Type").is_null()).height == 0, (
        f"{ISSN_TYPE_FILE} has null ISSN or Type values"
    )
    return dict(zip(df["ISSN"].to_list(), df["Type"].to_list()))


def classify_scimago_issns(issns_str: str | None, issn_type_lookup: dict[str, str]
                           ) -> tuple[str | None, str | None, str | None]:
    """Classify ISSNs from a Scimago 'Issn' cell into e-ISSN, p-ISSN, and ISSN-L.

    The Scimago Issn cell contains comma-separated ISSNs, e.g. "1234-5678, 8765-4321".
    Each ISSN is looked up in issn_type_lookup; the type string (e.g. "p;l") is split
    on ";" to determine which categories (e, p, l) the ISSN belongs to.
    Returns the first ISSN found for each category (e_issn, p_issn, issn_l).
    """
    if issns_str is None:
        return None, None, None

    e_issn = None
    p_issn = None
    issn_l = None

    for part in str(issns_str).split(","):
        formatted = format_issn(part.strip())
        if formatted is None:
            continue
        type_str = issn_type_lookup.get(formatted)
        if type_str is None:
            continue
        codes = set(type_str.split(";"))
        if "e" in codes and e_issn is None:
            e_issn = formatted
        if "p" in codes and p_issn is None:
            p_issn = formatted
        if "l" in codes and issn_l is None:
            issn_l = formatted

    return e_issn, p_issn, issn_l


def build_issn_title_lookup(lookup_df: pl.DataFrame, title_col: str, issn_cols: list[str]) -> dict[str, list[str]]:
    """Return a mapping of formatted ISSN -> ordered unique source titles."""
    lookup: dict[str, list[str]] = {}

    for row in lookup_df.select([title_col] + issn_cols).iter_rows(named=True):
        title = clean_string(row.get(title_col))
        if not title:
            continue

        for issn_col in issn_cols:
            formatted_issn = format_issn(row.get(issn_col))
            if formatted_issn is None:
                continue
            values = lookup.setdefault(formatted_issn, [])
            if title not in values:
                values.append(title)

    return lookup


def load_scimago_lookup(include_titles: bool = False) -> pl.DataFrame:
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
        "Issn": "Issn_scimago",
    })

    scimago_df = scimago_df.with_columns([
        pl.col("Journal_scimago").map_elements(norm_name, return_dtype=pl.Utf8).alias("norm_journal_scimago"),
        pl.col("Scimago Quartile_scimago").alias("Best Quartile_scimago"),
        pl.when(pl.col("Open Access Diamond_scimago") == "Yes")
        .then(pl.lit("OA diamond"))
        .when(pl.col("Open Access_scimago") == "Yes")
        .then(pl.lit("OA"))
        .otherwise(None)
        .alias("Business model_scimago"),
    ])
    # Normalize publisher names for consistent enrichment and disagreement comparison
    scimago_df = scimago_df.with_columns(
        pl.col("Publisher_scimago").map_elements(normalize_publisher, return_dtype=pl.Utf8).alias("Publisher_scimago")
    )

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

    # Classify ISSNs into e-ISSN, p-ISSN, ISSN-L using the ISSN type lookup
    issn_type_lookup = load_issn_type_lookup()
    scimago_df = scimago_df.with_columns(
        pl.col("Issn_scimago").map_elements(
            lambda issns: classify_scimago_issns(issns, issn_type_lookup)[0],
            return_dtype=pl.Utf8,
        ).alias("e-ISSN_scimago"),
        pl.col("Issn_scimago").map_elements(
            lambda issns: classify_scimago_issns(issns, issn_type_lookup)[1],
            return_dtype=pl.Utf8,
        ).alias("p-ISSN_scimago"),
        pl.col("Issn_scimago").map_elements(
            lambda issns: classify_scimago_issns(issns, issn_type_lookup)[2],
            return_dtype=pl.Utf8,
        ).alias("ISSN-L_scimago"),
    )

    selected_columns = [
        "norm_journal_scimago",
        "Scimago Rank_scimago",
        "Publisher_scimago",
        "Business model_scimago",
        "Scimago Quartile_scimago",
        "H index_scimago",
        "Country_scimago",
        "e-ISSN_scimago",
        "p-ISSN_scimago",
        "ISSN-L_scimago",
    ]
    if include_titles:
        selected_columns.insert(0, "Journal_scimago")

    # Keep only necessary columns and remove duplicates
    return scimago_df.select(selected_columns).unique(subset=["norm_journal_scimago"], keep="first")


def load_openapc_lookup(include_titles: bool = False) -> pl.DataFrame:
    """Load and process OpenAPC data into a lookup table.

    Uses only the most recent year's records per journal.
    Journals whose most recent record is older than 3 years are excluded entirely
    (their APC data is considered stale).

    Returns:
        pl.DataFrame: Processed OpenAPC lookup table with normalized journal names.
    """
    openapc_df = load_csv(OPENAPC_FILE)
    openapc_df = openapc_df.rename(
        {"journal_full_title": "Journal_openapc",
         "euro": "APC Euros_openapc",
         "publisher": "Publisher_openapc",
         "issn_electronic": "e-ISSN_openapc",
         "issn_l": "ISSN-L_openapc"}
    )

    # Treat "NA" as null for print ISSN
    openapc_df = openapc_df.with_columns(
        pl.when(pl.col("issn_print").cast(pl.Utf8).str.to_uppercase() == "NA")
        .then(None)
        .otherwise(pl.col("issn_print"))
        .alias("p-ISSN_openapc")
    )

    # Normalize journal names first
    openapc_df = openapc_df.with_columns(
        pl.col("Journal_openapc").map_elements(norm_name, return_dtype=pl.Utf8).alias("norm_journal_openapc")
    )

    # For each journal, find the most recent year with data
    max_periods = openapc_df.group_by("norm_journal_openapc").agg(
        pl.col("period").max().alias("max_period")
    )

    # Join back to get max_period per row
    openapc_df = openapc_df.join(max_periods, on="norm_journal_openapc", how="left")

    # Keep only records from the most recent year per journal
    openapc_df = openapc_df.filter(pl.col("period") == pl.col("max_period"))

    # Exclude journals whose most recent data is older than 3 years
    openapc_df = openapc_df.filter(pl.col("max_period") >= (CURRENT_YEAR - 3))

    assert openapc_df.filter(pl.col("max_period") < (CURRENT_YEAR - 3)).height == 0, \
        "BUG: stale openAPC records still present after filtering"

    # Group by normalized journal name and aggregate:
    # - Mean APC Euros from records in the most recent year
    # - Most frequent publisher from the most recent year
    # - Majority vote for is_hybrid (if more than 50% are hybrid, mark as Hybrid)
    # - First ISSN values (consistent within a journal)
    agg_expressions = [
        pl.col("Journal_openapc").mode().first().alias("Journal_openapc"),
        pl.col("APC Euros_openapc").mean().alias("APC Euros_openapc"),
        pl.col("Publisher_openapc").mode().first().alias("Publisher_openapc"),
        pl.when(pl.col("is_hybrid").mean() > 0.5)
        .then(pl.lit("Hybrid"))
        .otherwise(None)
        .alias("Business model_openapc"),
        pl.col("e-ISSN_openapc").drop_nulls().first().alias("e-ISSN_openapc"),
        pl.col("p-ISSN_openapc").drop_nulls().first().alias("p-ISSN_openapc"),
        pl.col("ISSN-L_openapc").drop_nulls().first().alias("ISSN-L_openapc"),
    ]
    openapc_df = openapc_df.group_by("norm_journal_openapc").agg(agg_expressions)
    # Normalize publisher names for consistent enrichment and disagreement comparison
    openapc_df = openapc_df.with_columns(
        pl.col("Publisher_openapc").map_elements(normalize_publisher, return_dtype=pl.Utf8).alias("Publisher_openapc")
    )

    # Format ISSNs to standard XXXX-XXXX
    openapc_df = openapc_df.with_columns([
        pl.col("e-ISSN_openapc").map_elements(format_issn, return_dtype=pl.Utf8).alias("e-ISSN_openapc"),
        pl.col("p-ISSN_openapc").map_elements(format_issn, return_dtype=pl.Utf8).alias("p-ISSN_openapc"),
        pl.col("ISSN-L_openapc").map_elements(format_issn, return_dtype=pl.Utf8).alias("ISSN-L_openapc"),
    ])

    openapc_df = format_APC_Euros(openapc_df, "APC Euros_openapc")
    selected_columns = [
        "norm_journal_openapc",
        "APC Euros_openapc",
        "Publisher_openapc",
        "Business model_openapc",
        "e-ISSN_openapc",
        "p-ISSN_openapc",
        "ISSN-L_openapc",
    ]
    if include_titles:
        selected_columns.insert(1, "Journal_openapc")
    return openapc_df.select(selected_columns)


def load_dataverse_lookup() -> pl.DataFrame:
    """Load and process APC Dataverse data into a lookup table.

    Returns:
        pl.DataFrame: Processed Dataverse lookup table with normalized journal names and aggregated data from last 5 years.
    """
    dataverse_df = load_csv(DATAVERSE_FILE, separator='\t', encoding="utf8-lossy")

    # Only keep rows where APC was actually provided
    dataverse_df = dataverse_df.filter(pl.col("APC_provided") == "yes")

    # Rename columns to our convention
    dataverse_df = dataverse_df.rename({
        "Journal": "Journal_dataverse",
        "Publisher": "Publisher_dataverse",
        "APC_EUR": "APC Euros_dataverse",
        "APC_year": "period_dataverse",
    })

    # Normalize journal names
    dataverse_df = dataverse_df.with_columns(
        pl.col("Journal_dataverse").map_elements(norm_name, return_dtype=pl.Utf8).alias("norm_journal_dataverse")
    )

    # Map OA_status to Business model
    dataverse_df = dataverse_df.with_columns(
        pl.when(pl.col("OA_status") == "Gold")
        .then(pl.lit("OA"))
        .when(pl.col("OA_status") == "Hybrid")
        .then(pl.lit("Hybrid"))
        .otherwise(None)
        .alias("Business model_dataverse")
    )

    # For each journal, keep only last 5 years of data
    max_periods = dataverse_df.group_by("norm_journal_dataverse").agg(
        pl.col("period_dataverse").max().alias("max_period")
    )
    dataverse_df = dataverse_df.join(max_periods, on="norm_journal_dataverse", how="left")
    dataverse_df = dataverse_df.filter(
        pl.col("period_dataverse") > (pl.col("max_period") - 5)
    )

    # Aggregate per journal: mean APC, mode publisher and business model
    dataverse_df = dataverse_df.group_by("norm_journal_dataverse").agg([
        pl.col("APC Euros_dataverse").mean().alias("APC Euros_dataverse"),
        pl.col("Publisher_dataverse").mode().first().alias("Publisher_dataverse"),
        pl.col("Business model_dataverse").mode().first().alias("Business model_dataverse"),
    ])

    # Normalize publisher names
    dataverse_df = dataverse_df.with_columns(
        pl.col("Publisher_dataverse").map_elements(normalize_publisher, return_dtype=pl.Utf8).alias(
            "Publisher_dataverse")
    )

    return format_APC_Euros(dataverse_df, "APC Euros_dataverse")


def load_doaj_lookup(include_titles: bool = False) -> pl.DataFrame:
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
        "Journal ISSN (print version)": "p-ISSN_doaj",
        "Journal EISSN (online version)": "e-ISSN_doaj",
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

    # Format ISSNs to standard XXXX-XXXX
    doaj_df = doaj_df.with_columns([
        pl.col("e-ISSN_doaj").map_elements(format_issn, return_dtype=pl.Utf8).alias("e-ISSN_doaj"),
        pl.col("p-ISSN_doaj").map_elements(format_issn, return_dtype=pl.Utf8).alias("p-ISSN_doaj"),
    ])

    # Format APC Euros (extract numeric value)
    doaj_df = format_APC_Euros(doaj_df, "APC Euros_doaj")
    doaj_df = format_urls(doaj_df, "Website_doaj")

    selected_columns = [
        "norm_journal_doaj",
        "Publisher_doaj",
        "Country_doaj",
        "Institution_doaj",
        "Website_doaj",
        "APC Euros_doaj",
        "e-ISSN_doaj",
        "p-ISSN_doaj",
    ]
    if include_titles:
        selected_columns.insert(0, "Journal_doaj")

    # Keep only necessary columns and remove duplicates (keep first occurrence)
    return doaj_df.select(selected_columns).unique(subset=["norm_journal_doaj"], keep="first")


def load_scimago_issn_title_lookup() -> dict[str, list[str]]:
    """Return formatted ISSN -> Scimago title(s) using the canonical lookup loader."""
    return build_issn_title_lookup(
        load_scimago_lookup(include_titles=True),
        title_col="Journal_scimago",
        issn_cols=["e-ISSN_scimago", "p-ISSN_scimago", "ISSN-L_scimago"],
    )


def load_doaj_issn_title_lookup() -> dict[str, list[str]]:
    """Return formatted ISSN -> DOAJ title(s) using the canonical lookup loader."""
    return build_issn_title_lookup(
        load_doaj_lookup(include_titles=True),
        title_col="Journal_doaj",
        issn_cols=["e-ISSN_doaj", "p-ISSN_doaj"],
    )


def load_openapc_issn_title_lookup() -> dict[str, list[str]]:
    """Return formatted ISSN -> OpenAPC title(s) using the canonical lookup loader."""
    return build_issn_title_lookup(
        load_openapc_lookup(include_titles=True),
        title_col="Journal_openapc",
        issn_cols=["e-ISSN_openapc", "p-ISSN_openapc", "ISSN-L_openapc"],
    )


# ---------------------------------------------------------------------------
# Disagreement report helpers
# ---------------------------------------------------------------------------

# Defines what to compare for the disagreement report.
# Each entry: (dataset_col, scimago_col_or_None, openapc_col_or_None, doaj_col_or_None)
# None means the source does not provide that column.
# Dataverse is excluded — it is used for enrichment only, not for the disagreement report.
DISAGREEMENT_COLS: list[tuple[str, str | None, str | None, str | None]] = [
    ("Publisher", "Publisher_scimago", "Publisher_openapc", "Publisher_doaj"),
    ("Business model", "Business model_scimago", "Business model_openapc", None),
    ("e-ISSN", "e-ISSN_scimago", "e-ISSN_openapc", "e-ISSN_doaj"),
    ("p-ISSN", "p-ISSN_scimago", "p-ISSN_openapc", "p-ISSN_doaj"),
    ("APC Euros", None, "APC Euros_openapc", "APC Euros_doaj"),
]

REPORT_SCHEMA = {
    "journal": pl.Utf8,
    "field": pl.Utf8,
    "column": pl.Utf8,
    "dataset_value": pl.Utf8,
    "Scimago_value": pl.Utf8,
    "DOAJ_value": pl.Utf8,
    "OpenAPC_value": pl.Utf8,
}


def has_disagreement(vals: list, col_name: str) -> bool:
    """Return True if the non-null values disagree.

    For APC Euros: flags only when one value is 0 and another is non-zero.
    For all other columns: flags when at least two distinct non-null values exist.
    Both dataset and lookup values are expected to be pre-normalized (post format_table).
    """
    non_null = [v for v in vals if v is not None and str(v).strip() != ""]
    # If contains "(", remove it and everything after to ignore details
    non_null = [str(v).split("(", 1)[0].strip() if isinstance(v, str) else v for v in non_null]
    if len(non_null) < 2:
        return False
    if col_name == "APC Euros":
        as_ints = [int(v) for v in non_null if isinstance(v, (int, float))]
        if len(as_ints) < 2:
            return False
        return any(v == 0 for v in as_ints) and any(v != 0 for v in as_ints)
    return len(set(str(v) for v in non_null)) > 1


def fetch_source_values(df: pl.DataFrame, lookup_df: pl.DataFrame, right_on: str, cols_to_fetch: list[str],
                        left_on: str = "norm_journal", fallback_col: str = "alt_journal_norm", ) -> pl.DataFrame:
    """Fetch source column values via a two-pass left join (primary on left_on, fallback on fallback_col).

    Returns df with the requested cols_to_fetch appended. Does not modify existing df columns.
    For cols in cols_to_fetch not present in lookup_df, appends null string columns.
    """
    available = [c for c in cols_to_fetch if c in lookup_df.columns]
    unavailable = [c for c in cols_to_fetch if c not in lookup_df.columns]

    if not available:
        return df.with_columns([pl.lit(None).cast(pl.Utf8).alias(c) for c in unavailable])

    lookup_subset = lookup_df.select([right_on] + available)
    has_alt = (pl.col(fallback_col).is_not_null() & (pl.col(fallback_col).cast(pl.Utf8).str.strip_chars() != ""))
    # Primary join — coalesce=False so we can detect unmatched rows via right_on being null
    result = df.join(lookup_subset, left_on=left_on, right_on=right_on, how="left", coalesce=False)

    unmatched_mask = pl.col(right_on).is_null() & has_alt
    if result.filter(unmatched_mask).height > 0:
        rest = result.filter(~unmatched_mask).drop(right_on)
        unmatched = result.filter(unmatched_mask).drop([right_on] + available)
        fallback = unmatched.join(lookup_subset, left_on=fallback_col, right_on=right_on, how="left",
                                  coalesce=False).drop(right_on)
        result = pl.concat([rest, fallback], how="diagonal_relaxed")
    else:
        result = result.drop(right_on)

    for c in unavailable:
        result = result.with_columns(pl.lit(None).cast(pl.Utf8).alias(c))

    return result


def compute_disagreements(enriched_df: pl.DataFrame, scimago_lookup: pl.DataFrame,
                          openapc_lookup: pl.DataFrame, doaj_lookup: pl.DataFrame, ) -> list[dict]:
    """Generate disagreement rows by comparing enriched dataset values with external source values.

    Both the dataset (enriched_df, post format_table) and the lookup tables have fully
    normalized values (publisher names, business models, ISSNs, APC as integer), so
    comparison is direct — no additional normalization is applied here.
    Dataverse is excluded from this report (used for enrichment only).

    Args:
        enriched_df: Dataset after enrichment and format_table. Must contain norm_journal,
                     alt_journal_norm, Journal, Field, and all columns in _DISAGREEMENT_COLS.
    Returns:
        List of dicts with keys matching _REPORT_SCHEMA.
    """
    dataset_cols = [d for d, *_ in DISAGREEMENT_COLS]
    needed_cols = ["Journal", "Field", "norm_journal", "alt_journal_norm"] + dataset_cols
    assert all(c in enriched_df.columns for c in needed_cols), (
        f"compute_disagreements: missing columns in enriched_df: "
        f"{[c for c in needed_cols if c not in enriched_df.columns]}"
    )

    scimago_cols = [c for _, c, _, _ in DISAGREEMENT_COLS if c is not None]
    openapc_cols = [c for _, _, c, _ in DISAGREEMENT_COLS if c is not None]
    doaj_cols = [c for _, _, _, c in DISAGREEMENT_COLS if c is not None]

    comp_df = enriched_df.select(needed_cols)
    n_rows = comp_df.height

    comp_df = fetch_source_values(comp_df, scimago_lookup, "norm_journal_scimago", scimago_cols)
    comp_df = fetch_source_values(comp_df, openapc_lookup, "norm_journal_openapc", openapc_cols)
    comp_df = fetch_source_values(comp_df, doaj_lookup, "norm_journal_doaj", doaj_cols)

    assert comp_df.height == n_rows, (
        f"BUG: compute_disagreements lost rows: {n_rows} → {comp_df.height}"
    )

    disagreements: list[dict] = []
    for row in comp_df.iter_rows(named=True):
        journal = str(row["Journal"] or "")
        field = str(row["Field"] or "")

        for dataset_col, scimago_col, openapc_col, doaj_col in DISAGREEMENT_COLS:
            dataset_val = row.get(dataset_col)
            scimago_val = row.get(scimago_col) if scimago_col else None
            openapc_val = row.get(openapc_col) if openapc_col else None
            doaj_val = row.get(doaj_col) if doaj_col else None

            if not has_disagreement([dataset_val, scimago_val, openapc_val, doaj_val], dataset_col):
                continue

            disagreements.append({
                "journal": journal,
                "field": field,
                "column": dataset_col,
                "dataset_value": str(dataset_val) if dataset_val is not None else "",
                "Scimago_value": str(scimago_val) if scimago_val is not None else "",
                "DOAJ_value": str(doaj_val) if doaj_val is not None else "",
                "OpenAPC_value": str(openapc_val) if openapc_val is not None else "",
            })

    return disagreements


def join_and_update(df: pl.DataFrame, lookup_df: pl.DataFrame, left_on: str, right_on: str,
                    source: str, totals: dict, only_fill_nulls: bool = False, label: str = "") -> pl.DataFrame:
    """Join a lookup table, update target columns from it, then drop lookup columns.

    Args:
        df: Target DataFrame.
        lookup_df: Lookup DataFrame (columns suffixed with _<source>).
        left_on: Join key in df.
        right_on: Join key in lookup_df.
        source: Data source name ("scimago", "openapc", "doaj").
        totals: Dict accumulating update counts per column.
        only_fill_nulls: If True, never overwrite existing values (for fallback joins).
        label: Label for log messages (e.g. "1st pass", "2nd pass").

    Returns:
        Updated DataFrame with lookup columns removed.
    """
    result = df.join(lookup_df, left_on=left_on, right_on=right_on, how="left", coalesce=False)
    matches = result.filter(pl.col(right_on).is_not_null()).height
    print(f"    - {label} matches: {matches}")

    for col, overwrite in FILE_COLS.get(source, []):
        source_col = f"{col}_{source}"
        do_overwrite = overwrite and not only_fill_nulls
        if do_overwrite:
            updates = result.filter(pl.col(source_col).is_not_null() &
                                    (pl.col(col).is_null() |
                                     (pl.col(col).cast(pl.Utf8) != pl.col(source_col).cast(pl.Utf8)))).height
            result = result.with_columns(
                pl.when(pl.col(source_col).is_not_null()).then(pl.col(source_col)).otherwise(pl.col(col)).alias(col)
            )
        else:
            updates = result.filter(pl.col(col).is_null() & pl.col(source_col).is_not_null()).height
            result = result.with_columns(
                pl.when(pl.col(col).is_null()).then(pl.col(source_col)).otherwise(pl.col(col)).alias(col)
            )
        totals[col] += updates
        if updates > 0:
            print(f"\t- '{col}' {'updates' if do_overwrite else 'empty filled'} from {source}: {updates}")

    # Drop lookup columns to keep DataFrame clean for subsequent joins
    return result.drop([c for c in lookup_df.columns if c in result.columns])


def compute_presence(target_df: pl.DataFrame, lookup_df: pl.DataFrame, right_on: str,
                     left_on: str, fallback_col: str, presence_col: str) -> pl.DataFrame:
    """Compute a presence column for a data source before any join takes place.

    The column is set to:
    - "Yes"                         — primary name (norm_journal) matched in the lookup
    - "With alternative journal name" — primary did NOT match, but alt name matched
    - "No"                          — neither name matched

    Args:
        target_df:    Left DataFrame being enriched.
        lookup_df:    Lookup table for this source.
        right_on:     Join key column name in lookup_df.
        left_on:      Primary join key column name in target_df (norm_journal).
        fallback_col: Fallback join key column name in target_df (alt_journal_norm).
        presence_col: Name to give the new presence column.

    Returns:
        target_df with the presence_col column added/overwritten.
    """
    lookup_keys = set(lookup_df[right_on].drop_nulls().to_list())
    lookup_keys_list = list(lookup_keys)

    has_alt = (
            pl.col(fallback_col).is_not_null()
            & (pl.col(fallback_col).cast(pl.Utf8).str.strip_chars() != "")
    )
    primary_matched = pl.col(left_on).is_in(lookup_keys_list)
    alt_matched = has_alt & pl.col(fallback_col).is_in(lookup_keys_list)

    result = target_df.with_columns(
        pl.when(primary_matched)
        .then(pl.lit("Yes"))
        .when(alt_matched)
        .then(pl.lit("With alternative journal name"))
        .otherwise(pl.lit("No"))
        .alias(presence_col)
    )

    yes_count = result.filter(pl.col(presence_col) == "Yes").height
    alt_count = result.filter(pl.col(presence_col) == "With alternative journal name").height
    no_count = result.filter(pl.col(presence_col) == "No").height
    print(f"    - Presence '{presence_col}': Yes={yes_count}, With alternative journal name={alt_count}, No={no_count}")
    assert yes_count + alt_count + no_count == result.height, \
        f"BUG: presence counts don't sum to total rows for {presence_col}"
    assert result.filter(pl.col(presence_col).is_null()).height == 0, \
        f"BUG: null values in presence column '{presence_col}'"
    return result


def two_pass_join(target_df: pl.DataFrame, lookup_df: pl.DataFrame, right_on: str, totals: dict, source: str,
                  left_on: str = "norm_journal", fallback_col: str = "alt_journal_norm") -> pl.DataFrame:
    """Join on primary key, then on fallback key for unmatched rows.

    The fallback (2nd pass) only fills null values and never overwrites
    values already set by the primary match.
    If the source has a presence column defined in SOURCE_PRESENCE_COL, it is
    computed before the joins and preserved in the result.
    """
    print(f"  Performing two-pass join for {source}...")
    has_fallback = pl.col(fallback_col).is_not_null() & (pl.col(fallback_col).cast(pl.Utf8).str.strip_chars() != "")
    print(f"    - Total rows: {target_df.height}, {target_df.filter(has_fallback).height} with fallback.")

    # Compute presence column (before any join, so it reflects name-match status)
    presence_col = SOURCE_PRESENCE_COL.get(source)
    if presence_col is not None:
        target_df = compute_presence(target_df, lookup_df, right_on, left_on, fallback_col, presence_col)

    # First pass: join on primary key
    result_df = join_and_update(target_df, lookup_df, left_on, right_on, source, totals, label="1st pass")

    # Second pass: join unmatched rows on fallback key
    matched_keys = set(lookup_df[right_on].to_list())
    nbr_fallback = result_df.filter(has_fallback & ~pl.col(left_on).is_in(list(matched_keys))).height
    if nbr_fallback > 0:
        print(f"    - 2nd pass on '{fallback_col}' for {nbr_fallback} unmatched rows...")
        result_df = join_and_update(result_df, lookup_df, fallback_col, right_on, source, totals,
                                    only_fill_nulls=True, label="2nd pass")
    else:
        print(f"    - No rows for 2nd pass (all matched in 1st pass).")
    print(f"  Two-pass join for {source} completed.")
    return result_df


def process_csv_file(csv_path: str, scimago_lookup: pl.DataFrame, openapc_lookup: pl.DataFrame,
                     doaj_lookup: pl.DataFrame, dataverse_lookup: pl.DataFrame,
                     pci_friendly_set: set, totals: dict, disagreement_rows: list) -> None:
    """Process a single CSV file with Scimago, OpenAPC, DOAJ, and Dataverse data using two-pass joins.

    Args:
        csv_path: Path to the CSV file to process
        scimago_lookup: Scimago lookup table
        openapc_lookup: OpenAPC lookup table
        doaj_lookup: DOAJ lookup table
        dataverse_lookup: APC Dataverse lookup table
        pci_friendly_set: Set of PCI-friendly journal names
        totals: Dictionary to accumulate update counts
        disagreement_rows: List to accumulate disagreement report rows (mutated in-place)
    """
    print(f"Processing file: {csv_path}")
    target_df = load_csv(csv_path, ignore_errors=True)

    # Migrate legacy column name "Scimago Journal Title" -> "Alternative journal name"
    if "Scimago Journal Title" in target_df.columns and "Alternative journal name" not in target_df.columns:
        print(f"  [migrate] Renaming 'Scimago Journal Title' -> 'Alternative journal name' in {csv_path}")
        target_df = target_df.rename({"Scimago Journal Title": "Alternative journal name"})

    # Ensure all FINAL_COLUMNS exist (adds missing columns as nulls, e.g. e-ISSN, p-ISSN, ISSN-L)
    target_df = ensure_columns(target_df)

    # Use the canonical FINAL_COLUMNS as the set of output columns
    original_cols = FINAL_COLUMNS

    # Add normalized journal names for joining
    target_df = target_df.with_columns([
        pl.col("Journal").map_elements(norm_name, return_dtype=pl.Utf8).alias("norm_journal"),
        pl.when(pl.col("Alternative journal name").is_not_null())
        .then(pl.col("Alternative journal name").map_elements(norm_name, return_dtype=pl.Utf8))
        .otherwise(None)
        .alias("alt_journal_norm")
    ])

    # Get the set of keys that will be used for joining
    left_keys = set(target_df["norm_journal"].unique().to_list())
    left_keys = left_keys.union(set(target_df["alt_journal_norm"].unique().to_list()))

    validate_no_duplicates_for_join(scimago_lookup, "norm_journal_scimago", left_keys, "Scimago")
    updated_df = two_pass_join(target_df, scimago_lookup, right_on="norm_journal_scimago", source="scimago",
                               totals=totals)

    validate_no_duplicates_for_join(openapc_lookup, "norm_journal_openapc", left_keys, "OpenAPC")
    updated_df = two_pass_join(updated_df, openapc_lookup, right_on="norm_journal_openapc", source="openapc",
                               totals=totals)

    validate_no_duplicates_for_join(doaj_lookup, "norm_journal_doaj", left_keys, "DOAJ")
    updated_df = two_pass_join(updated_df, doaj_lookup, right_on="norm_journal_doaj", source="doaj", totals=totals)

    validate_no_duplicates_for_join(dataverse_lookup, "norm_journal_dataverse", left_keys, "Dataverse")
    updated_df = two_pass_join(updated_df, dataverse_lookup, right_on="norm_journal_dataverse", source="dataverse",
                               totals=totals)

    # Apply formatting and normalization
    updated_df = format_table(updated_df)
    # Mark PCI friendly journals
    updated_df = mark_pci_friendly(updated_df, pci_friendly_set)

    # Compute disagreements from enriched, normalized values (both dataset and lookup tables are fully formatted at this point)
    new_rows = compute_disagreements(updated_df, scimago_lookup, openapc_lookup, doaj_lookup)
    if new_rows:
        print(f"  Disagreements found: {len(new_rows)}")
    disagreement_rows.extend(new_rows)

    # Select original columns only (avoid helper/join columns)
    final_df = updated_df.select(original_cols)
    check_consistency(final_df)
    final_df.write_csv(csv_path)
    print(f"Successfully updated and saved {csv_path}\n")


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

    dataverse_lookup = load_dataverse_lookup()
    print(f"Successfully loaded and processed Dataverse data from {DATAVERSE_FILE}")

    # Initialize totals for tracking updates
    totals = {col: 0 for col in COLUMNS_TO_UPDATE}
    disagreement_rows: list[dict] = []

    # Process each CSV file in the data_extracted directory
    for csv_path in sorted(glob(os.path.join(DATA_EXTRACTED_DIR, "*.csv"))):
        filename = os.path.basename(csv_path)
        if filename in FILES_TO_SKIP:
            print(f"Skipping file: {filename}")
            continue

        process_csv_file(csv_path, scimago_lookup, openapc_lookup, doaj_lookup, dataverse_lookup,
                         pci_friendly_set, totals, disagreement_rows)

    # Write disagreement report
    os.makedirs("logs", exist_ok=True)
    report_path = os.path.join("logs", "disagreements.csv")
    if disagreement_rows:
        report_df = pl.DataFrame(disagreement_rows, schema=REPORT_SCHEMA)
    else:
        report_df = pl.DataFrame(schema=REPORT_SCHEMA)
    report_df.write_csv(report_path)
    print(f"\nDisagreement report written to {report_path} ({len(disagreement_rows)} rows).")

    # Print summary
    print("\nScript finished.")
    if sum(totals.values()) == 0:
        print("\t- No updates were made.")
    for col, total in totals.items():
        if total > 0:
            print(f"\t- Total {col} updates: {total}")


if __name__ == "__main__":
    main()
