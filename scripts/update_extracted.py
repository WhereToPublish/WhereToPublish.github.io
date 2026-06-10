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

# Presence column values (ordered from best to worst match)
PRESENCE_VALUES = ["Yes", "With alternative journal name", "ISSN-L match",
                   "e-ISSN match", "p-ISSN match", "Ambiguous", "No"]

# Candidate join key cascade for each source.
# Each entry is (left_col_in_target, right_col_in_lookup, presence_label).
# Keys are tried in order; once a row gets a non-"No"/non-"Ambiguous" presence it stops.
CANDIDATE_KEYS: dict[str, list[tuple[str, str, str]]] = {
    "scimago": [
        ("norm_journal", "norm_journal_scimago", "Yes"),
        ("alt_journal_norm", "norm_journal_scimago", "With alternative journal name"),
        ("ISSN-L", "ISSN-L_scimago", "ISSN-L match"),
        ("e-ISSN", "e-ISSN_scimago", "e-ISSN match"),
        ("p-ISSN", "p-ISSN_scimago", "p-ISSN match"),
    ],
    "openapc": [
        ("norm_journal", "norm_journal_openapc", "Yes"),
        ("alt_journal_norm", "norm_journal_openapc", "With alternative journal name"),
        ("ISSN-L", "ISSN-L_openapc", "ISSN-L match"),
        ("e-ISSN", "e-ISSN_openapc", "e-ISSN match"),
        ("p-ISSN", "p-ISSN_openapc", "p-ISSN match"),
    ],
    "doaj": [
        ("norm_journal", "norm_journal_doaj", "Yes"),
        ("alt_journal_norm", "norm_journal_doaj", "With alternative journal name"),
        # DOAJ lookup has no ISSN-L column
        ("e-ISSN", "e-ISSN_doaj", "e-ISSN match"),
        ("p-ISSN", "p-ISSN_doaj", "p-ISSN match"),
    ],
    "dataverse": [
        ("norm_journal", "norm_journal_dataverse", "Yes"),
        ("alt_journal_norm", "norm_journal_dataverse", "With alternative journal name"),
        # Dataverse lookup has no ISSN columns
    ],
}


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
        "Journal_scimago",
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
    # Return all rows without deduplication (duplicates handled by compute_presence_and_keys)
    return scimago_df.select(selected_columns)


def load_openapc_lookup() -> pl.DataFrame:
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

    # For each journal, find the most recent year with data
    max_periods = openapc_df.group_by("Journal_openapc").agg(pl.col("period").max().alias("max_period"))

    # Join back to get max_period per row
    openapc_df = openapc_df.join(max_periods, on="Journal_openapc", how="left")

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
    openapc_df = openapc_df.group_by("Journal_openapc").agg(agg_expressions)
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
    # Normalize journal names first
    openapc_df = openapc_df.with_columns(
        pl.col("Journal_openapc").map_elements(norm_name, return_dtype=pl.Utf8).alias("norm_journal_openapc")
    )
    selected_columns = [
        "norm_journal_openapc",
        "Journal_openapc",
        "APC Euros_openapc",
        "Publisher_openapc",
        "Business model_openapc",
        "e-ISSN_openapc",
        "p-ISSN_openapc",
        "ISSN-L_openapc",
    ]
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
        "Journal_doaj",
        "Publisher_doaj",
        "Country_doaj",
        "Institution_doaj",
        "Website_doaj",
        "APC Euros_doaj",
        "e-ISSN_doaj",
        "p-ISSN_doaj",
    ]
    # Keep only necessary columns and remove duplicates (keep first occurrence)
    return doaj_df.select(selected_columns)


def load_scimago_issn_title_lookup() -> dict[str, list[str]]:
    """Return formatted ISSN -> Scimago title(s) using the canonical lookup loader."""
    return build_issn_title_lookup(
        load_scimago_lookup(), title_col="Journal_scimago",
        issn_cols=["e-ISSN_scimago", "p-ISSN_scimago", "ISSN-L_scimago"])


def load_doaj_issn_title_lookup() -> dict[str, list[str]]:
    """Return formatted ISSN -> DOAJ title(s) using the canonical lookup loader."""
    return build_issn_title_lookup(
        load_doaj_lookup(), title_col="Journal_doaj",
        issn_cols=["e-ISSN_doaj", "p-ISSN_doaj"])


def load_openapc_issn_title_lookup() -> dict[str, list[str]]:
    """Return formatted ISSN -> OpenAPC title(s) using the canonical lookup loader."""
    return build_issn_title_lookup(
        load_openapc_lookup(), title_col="Journal_openapc",
        issn_cols=["e-ISSN_openapc", "p-ISSN_openapc", "ISSN-L_openapc"])


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
    "url": pl.Utf8,
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
    non_null = [str(v).split("(", 1)[0].strip().lower() if isinstance(v, str) else v for v in non_null]
    if len(non_null) < 2:
        return False
    # For business model, if first (dataset) value is "Hybrid" and second (scimago) value is "OA", do not count as disagreement
    if col_name == "Business model" and vals[0] == "Hybrid" and vals[1] == "OA":
        return False
    if col_name == "APC Euros":
        as_ints = [int(v) for v in non_null if isinstance(v, (int, float))]
        if len(as_ints) < 2:
            return False
        return any(v == 0 for v in as_ints) and any(v != 0 for v in as_ints)
    return len(set(str(v) for v in non_null)) > 1


def compute_disagreements(enriched_df: pl.DataFrame) -> list[dict]:
    """Generate disagreement rows comparing enriched dataset values with source lookup values.

    Source columns (Publisher_scimago, APC Euros_openapc, etc.) are already present in
    enriched_df after the join_and_enrich calls and are used directly — no re-matching needed.
    Dataverse is excluded (enrichment only, not in disagreement report).

    Args:
        enriched_df: DataFrame after all join_and_enrich calls and format_table. Must contain
                     Journal, Website, Field, all dataset columns in DISAGREEMENT_COLS, and
                     all source columns referenced in DISAGREEMENT_COLS.

    Returns:
        List of dicts with keys matching REPORT_SCHEMA.
    """
    dataset_cols = [d for d, *_ in DISAGREEMENT_COLS]
    all_source_cols = [c for _, s, o, d in DISAGREEMENT_COLS for c in [s, o, d] if c is not None]
    needed_cols = ["Journal", "Website", "Field"] + dataset_cols + all_source_cols
    assert all(c in enriched_df.columns for c in needed_cols), (
        f"compute_disagreements: missing columns in enriched_df: "
        f"{[c for c in needed_cols if c not in enriched_df.columns]}"
    )

    disagreements: list[dict] = []
    for row in enriched_df.select(needed_cols).iter_rows(named=True):
        journal = str(row["Journal"] or "")
        url = str(row.get("Website") or "")
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
                "url": url,
                "field": field,
                "column": dataset_col,
                "dataset_value": str(dataset_val) if dataset_val is not None else "",
                "Scimago_value": str(scimago_val) if scimago_val is not None else "",
                "DOAJ_value": str(doaj_val) if doaj_val is not None else "",
                "OpenAPC_value": str(openapc_val) if openapc_val is not None else "",
            })

    return disagreements


def apply_candidate_key(target_df: pl.DataFrame, lookup_df: pl.DataFrame, left_col: str, right_col: str, label: str,
                        left_key_col: str, right_key_col: str,
                        presence_col: str) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Try to assign one candidate join key pair to unmatched / ambiguous rows.

    For rows in target_df where presence_col is "No" or "Ambiguous":
    - If left_col value appears exactly once in target_df AND exactly once in lookup_df
      (clean match) AND the matching lookup row has not yet been claimed:
        → set left_key_col = left_col value, presence_col = label
    - If left_col value appears more than once in either table, or the lookup row is
      already claimed by another match:
        → set presence_col = "Ambiguous" (only if currently "No")

    Also updates lookup_df: sets right_key_col = right_col value for newly-claimed rows.

    Args:
        target_df:    Left DataFrame being enriched (has left_key_col and presence_col).
        lookup_df:    Lookup DataFrame (has right_key_col).
        left_col:     Column in target_df supplying candidate key values.
        right_col:    Column in lookup_df supplying candidate key values.
        label:        Presence label to set on successful match (e.g. "Yes", "e-ISSN match").
        left_key_col: Column in target_df that stores the resolved join key.
        right_key_col: Column in lookup_df that stores the resolved join key.
        presence_col: Column in target_df tracking match status.

    Returns:
        Updated (target_df, lookup_df).
    """
    if left_col not in target_df.columns or right_col not in lookup_df.columns:
        return target_df, lookup_df

    is_nonempty_left = (pl.col(left_col).is_not_null() & (pl.col(left_col).cast(pl.Utf8).str.strip_chars() != ""))
    is_nonempty_right = (pl.col(right_col).is_not_null() & (pl.col(right_col).cast(pl.Utf8).str.strip_chars() != ""))

    # Count occurrences of candidate key values in each table
    left_counts = target_df.filter(is_nonempty_left).group_by(left_col).agg(pl.len().alias("_left_count"))
    right_counts = lookup_df.filter(is_nonempty_right).group_by(right_col).agg(pl.len().alias("_right_count"))

    # Values present in both tables
    matched = left_counts.join(right_counts, left_on=left_col, right_on=right_col, how="inner")
    if matched.height == 0:
        return target_df, lookup_df

    # Clean: unique on both sides; ambiguous: duplicated on either side
    clean_values = set(matched.filter((pl.col("_left_count") == 1) & (pl.col("_right_count") == 1))[left_col].to_list())
    ambiguous_values = set(
        matched.filter((pl.col("_left_count") > 1) | (pl.col("_right_count") > 1))[left_col].to_list())

    if not clean_values and not ambiguous_values:
        return target_df, lookup_df

    # Lookup rows already claimed by a previous key step
    claimed_right = set(
        lookup_df.filter(pl.col(right_key_col).is_not_null()).select(right_col).drop_nulls()[right_col].to_list()
    )

    available_clean = clean_values - claimed_right  # can be claimed now
    blocked_clean = clean_values & claimed_right  # clean but lookup row already taken
    all_ambiguous = ambiguous_values | blocked_clean  # flag as ambiguous

    needs_match = (pl.col(presence_col).is_in(["No", "Ambiguous"]) & is_nonempty_left)

    # Update target_df: assign key and presence in one pass
    update_exprs = []
    if available_clean:
        update_exprs.append(
            pl.when(needs_match & pl.col(left_col).is_in(list(available_clean)))
            .then(pl.col(left_col))
            .otherwise(pl.col(left_key_col))
            .alias(left_key_col)
        )
    if available_clean or all_ambiguous:
        presence_expr = (
            pl.when(needs_match & pl.col(left_col).is_in(list(available_clean)))
            .then(pl.lit(label))
        )
        if all_ambiguous:
            presence_expr = presence_expr.when(
                (pl.col(presence_col) == "No")
                & is_nonempty_left
                & pl.col(left_col).is_in(list(all_ambiguous))
            ).then(pl.lit("Ambiguous"))
        presence_expr = presence_expr.otherwise(pl.col(presence_col)).alias(presence_col)
        update_exprs.append(presence_expr)

    if update_exprs:
        target_df = target_df.with_columns(update_exprs)

    # Update lookup_df: claim rows for newly-available clean matches
    if available_clean:
        lookup_df = lookup_df.with_columns(
            pl.when(pl.col(right_key_col).is_null() & pl.col(right_col).is_in(list(available_clean)))
            .then(pl.col(right_col))
            .otherwise(pl.col(right_key_col))
            .alias(right_key_col)
        )
    return target_df, lookup_df


def compute_presence_and_keys(target_df: pl.DataFrame, lookup_df: pl.DataFrame, source: str,
                              presence_col: str | None) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Compute presence column and unique join keys for a source via the candidate key cascade.

    Tries candidate keys in priority order (norm_journal → alt_journal_norm → ISSN-L →
    e-ISSN → p-ISSN, as defined in CANDIDATE_KEYS). Each step only operates on rows
    still labelled "No" or "Ambiguous".

    Presence values (written to presence_col if provided, otherwise internal only):
        "Yes"                    — matched via normalized journal name
        "With alternative journal name" — matched via alternative journal name
        "ISSN-L match"           — matched via ISSN-L
        "e-ISSN match"           — matched via e-ISSN
        "p-ISSN match"           — matched via p-ISSN
        "Ambiguous"              — candidate key found in both tables but duplicated, or
                                   the only clean lookup row was already claimed
        "No"                     — no match found by any key

    Adds left_key_{source} to target_df and right_key_{source} to lookup_df.
    Both columns are null for rows/rows that could not be cleanly matched.

    Asserts that non-null left-key values are unique in target_df and non-null
    right-key values are unique in lookup_df (guarantees join produces no duplicates).

    Args:
        target_df:    Left DataFrame being enriched.
        lookup_df:    Lookup table for this source.
        source:       Source name ("scimago", "openapc", "doaj", "dataverse").
        presence_col: Column name to write presence info into target_df, or None to
                      skip writing the presence column (for sources like "dataverse").

    Returns:
        (target_df_with_left_key, lookup_df_with_right_key)
    """
    left_key_col = f"left_key_{source}"
    right_key_col = f"right_key_{source}"
    # Use a temporary internal name if no permanent presence column is needed
    presence_col_alias = presence_col if presence_col is not None else f"_presence_{source}"

    # Initialize: all rows start with no key and presence "No"
    target_df = target_df.with_columns([
        pl.lit(None).cast(pl.Utf8).alias(left_key_col),
        pl.lit("No").alias(presence_col_alias),
    ])
    lookup_df = lookup_df.with_columns(
        pl.lit(None).cast(pl.Utf8).alias(right_key_col)
    )

    # Walk through candidate keys in priority order
    for left_col, right_col, label in CANDIDATE_KEYS[source]:
        target_df, lookup_df = apply_candidate_key(
            target_df, lookup_df, left_col, right_col, label,
            left_key_col, right_key_col, presence_col_alias,
        )

    # Log presence distribution
    print(f"  [{source}] presence distribution:")
    for val in PRESENCE_VALUES:
        count = target_df.filter(pl.col(presence_col_alias) == val).height
        if count > 0:
            print(f"    - {val}: {count}")

    # Drop internal presence column if it was not requested
    if presence_col is None:
        target_df = target_df.drop(presence_col_alias)

    # Assert: non-null left_key values are unique in target_df (no duplicate join keys)
    non_null_left = target_df.filter(pl.col(left_key_col).is_not_null())
    assert non_null_left[left_key_col].n_unique() == non_null_left.height, (
        f"BUG: non-null {left_key_col} values are not unique in target_df for source '{source}'. "
        f"Rows={non_null_left.height}, unique={non_null_left[left_key_col].n_unique()}"
    )

    # Assert: non-null right_key values are unique in lookup_df (no duplicate join keys)
    non_null_right = lookup_df.filter(pl.col(right_key_col).is_not_null())
    assert non_null_right[right_key_col].n_unique() == non_null_right.height, (
        f"BUG: non-null {right_key_col} values are not unique in lookup_df for source '{source}'. "
        f"Rows={non_null_right.height}, unique={non_null_right[right_key_col].n_unique()}"
    )

    return target_df, lookup_df


def join_and_enrich(target_df: pl.DataFrame, lookup_df: pl.DataFrame, source: str, totals: dict) -> pl.DataFrame:
    """Perform a single left join using the pre-computed keys and enrich target columns.

    Joins target_df (left_key_{source}) to lookup_df (right_key_{source}).
    Applies FILE_COLS[source] enrichment rules (overwrite vs fill-null).
    Drops the two join-key columns after the join.
    Source data columns (e.g. Publisher_scimago) are kept in the result for
    downstream disagreement analysis; they are removed later by select(original_cols).

    Args:
        target_df:  DataFrame with left_key_{source} column added by compute_presence_and_keys.
        lookup_df:  Lookup DataFrame with right_key_{source} column added by compute_presence_and_keys.
        source:     Source name ("scimago", "openapc", "doaj", "dataverse").
        totals:     Dict accumulating per-column update counts (mutated in-place).

    Returns:
        Enriched target_df with join-key columns removed.
    """
    left_key_col = f"left_key_{source}"
    right_key_col = f"right_key_{source}"

    result = target_df.join(lookup_df, left_on=left_key_col, right_on=right_key_col, how="left", coalesce=False)

    matches = result.filter(pl.col(right_key_col).is_not_null()).height
    print(f"  [{source}] join matches: {matches} / {result.height}")

    for col, overwrite in FILE_COLS.get(source, []):
        source_col = f"{col}_{source}"
        if source_col not in result.columns:
            continue
        if overwrite:
            updates = result.filter(
                pl.col(source_col).is_not_null()
                & (pl.col(col).is_null() | (pl.col(col).cast(pl.Utf8) != pl.col(source_col).cast(pl.Utf8)))
            ).height
            result = result.with_columns(
                pl.when(pl.col(source_col).is_not_null())
                .then(pl.col(source_col))
                .otherwise(pl.col(col))
                .alias(col)
            )
        else:
            updates = result.filter(pl.col(col).is_null() & pl.col(source_col).is_not_null()).height
            result = result.with_columns(
                pl.when(pl.col(col).is_null())
                .then(pl.col(source_col))
                .otherwise(pl.col(col))
                .alias(col)
            )
        totals[col] += updates
        if updates > 0:
            action = "updated" if overwrite else "filled"
            print(f"\t- '{col}' {action} from {source}: {updates}")

    # Drop join-key columns; keep source data columns for disagreement analysis
    result = result.drop([left_key_col, right_key_col])
    return result


def process_csv_file(csv_path: str, scimago_lookup: pl.DataFrame, openapc_lookup: pl.DataFrame,
                     doaj_lookup: pl.DataFrame, dataverse_lookup: pl.DataFrame,
                     pci_friendly_set: set, totals: dict, disagreement_rows: list) -> None:
    """Process a single CSV file: enrich with external sources, then write back.

    For each source, compute_presence_and_keys assigns unique join keys via a key-cascade
    (norm_journal → alt_journal_norm → ISSN-L → e-ISSN → p-ISSN), then join_and_enrich
    does a single left join and applies enrichment rules. Disagreements between dataset
    and source values are detected from the joined source columns before cleanup.

    Args:
        csv_path: Path to the CSV file to process.
        scimago_lookup: Scimago lookup table (not pre-deduplicated).
        openapc_lookup: OpenAPC lookup table (already aggregated per journal).
        doaj_lookup: DOAJ lookup table (not pre-deduplicated).
        dataverse_lookup: APC Dataverse lookup table (already aggregated per journal).
        pci_friendly_set: Set of normalized PCI-friendly journal names.
        totals: Dict accumulating per-column update counts (mutated in-place).
        disagreement_rows: List accumulating disagreement report dicts (mutated in-place).
    """
    print(f"Processing file: {csv_path}")
    target_df = load_csv(csv_path, ignore_errors=True)

    # Ensure all FINAL_COLUMNS exist (adds missing columns as nulls, e.g. e-ISSN, p-ISSN, ISSN-L)
    target_df = ensure_columns(target_df)

    # Use the canonical FINAL_COLUMNS as the set of output columns
    original_cols = FINAL_COLUMNS

    # Normalize ISSN columns before key computation (format_issn is idempotent)
    target_df = target_df.with_columns([
        pl.col("e-ISSN").map_elements(format_issn, return_dtype=pl.Utf8).alias("e-ISSN"),
        pl.col("p-ISSN").map_elements(format_issn, return_dtype=pl.Utf8).alias("p-ISSN"),
        pl.col("ISSN-L").map_elements(format_issn, return_dtype=pl.Utf8).alias("ISSN-L"),
    ])

    # Add normalized journal names for key computation
    target_df = target_df.with_columns([
        pl.col("Journal").map_elements(norm_name, return_dtype=pl.Utf8).alias("norm_journal"),
        pl.when(pl.col("Alternative journal name").is_not_null())
        .then(pl.col("Alternative journal name").map_elements(norm_name, return_dtype=pl.Utf8))
        .otherwise(None)
        .alias("alt_journal_norm"),
    ])

    # For each source: compute presence + unique join keys, then do the enrichment join
    source_lookups = [
        ("scimago", scimago_lookup),
        ("openapc", openapc_lookup),
        ("doaj", doaj_lookup),
        ("dataverse", dataverse_lookup),
    ]
    updated_df = target_df
    for source, lookup_df in source_lookups:
        presence_col = SOURCE_PRESENCE_COL.get(source)
        updated_df, augmented_lookup = compute_presence_and_keys(updated_df, lookup_df, source, presence_col)
        updated_df = join_and_enrich(updated_df, augmented_lookup, source, totals)

    # Apply formatting and normalization (format_table also re-formats ISSNs idempotently)
    updated_df = format_table(updated_df)
    # Mark PCI friendly journals
    updated_df = mark_pci_friendly(updated_df, pci_friendly_set)

    # Compute disagreements from enriched values and the source columns still present
    new_rows = compute_disagreements(updated_df)
    if new_rows:
        print(f"  Disagreements found: {len(new_rows)}")
    disagreement_rows.extend(new_rows)

    # Select original columns only — drops all helper columns (norm_journal, left_key_*, source cols, etc.)
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
    assert report_df.columns == list(REPORT_SCHEMA.keys()), (
        f"Disagreement report columns mismatch: {report_df.columns}"
    )
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
