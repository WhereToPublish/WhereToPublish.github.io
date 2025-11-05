import polars as pl

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


def clean_string(name: str) -> str:
    if "¬†" in name:
        name = name.replace("¬†", " ")
    if "√°√±" in name:
        name = name.replace("b√°√±", "an")
    if "√º" in name:
        name = name.replace("√º", "u")
    if "√ß" in name:
        name = name.replace("√ß", "ç")
    if "‚Äô" in name:
        name = name.replace("‚Äô", "'")
    return str(name).strip()


def normalize_publisher(name: str) -> str:
    """
    Normalize publisher names to standard forms.
    1. Map known variants to standard names.
    2. Remove " Inc." suffix.
    3. Handle specific known encoding issues.
    4. Trim leading/trailing spaces.
    5. Return empty string if name is None.
    """
    if name is None:
        return ""
    name_lower = name.lower()
    if "springer" in name_lower or "nature" == name_lower or "nature publishing group" in name_lower or "nature research" in name_lower or "nature portfolio" in name_lower:
        return "Springer Nature"
    if "wiley" in name_lower:
        return "John Wiley & Sons"
    if "taylor" in name_lower and "francis" in name_lower:
        return "Taylor & Francis Group"
    if "elsevier" in name_lower:
        return "Elsevier"
    if "frontiers" in name_lower:
        return "Frontiers Media SA"
    if "BMC" in name or "biomed central" in name_lower:
        return "Springer Nature (BioMed Central)"
    if "BMJ" in name:
        return "BMJ Group"
    if "Cell" == name or "cell press" in name_lower:
        return "Elsevier (Cell Press)"
    if "BioOne Complete" in name:
        return "BioOne"
    if "OUP" in name:
        return "Oxford University Press"
    if "APA" in name:
        return "American Psychological Association"
    if "AMA" in name:
        return "American Medical Association"
    if "AAAS" in name:
        return "American Association for the Advancement of Science"
    if "public library of science" in name_lower or "plos" in name_lower:
        return "Public Library of Science (PLoS)"
    if "PCI" in name:
        return "Peer Community In"
    if " Inc." in name:
        name = name.replace(" Inc.", "")
    name = clean_string(name)
    return str(name).strip()


def normalize_institution(name: str) -> str:
    """ Normalize institution names by stripping leading/trailing spaces.
    Return empty string if name is None.
    """
    if name is None:
        return ""
    name = clean_string(name)
    return str(name).strip()


def derive_country_from_publisher(df: pl.DataFrame) -> pl.DataFrame:
    """ Derive 'Country' from known 'Publisher' names when 'Country' is missing/empty.
    """
    country_map = {
        "Oxford University Press": "UK",
        "Cambridge University Press": "UK",
        "BMJ Group": "UK",
        "Springer Nature": "Germany/UK",
        "Frontiers Media SA": "Switzerland",
        "Peer Community In": "France",
        "Elsevier": "Netherlands",
        "Elsevier (Cell Press)": "USA",
        "John Wiley & Sons": "USA",
        "Taylor & Francis Group": "USA",
        "BioOne": "USA",
        "Sage Publishing": "USA",
        "Public Library of Science (PLoS)": "USA",
        "American Association for the Advancement of Science": "USA",
        "American Psychological Association": "USA",
        "American Medical Association": "USA",
    }
    return df.with_columns(
        pl.when(
            (pl.col("Country").is_null() | (pl.col("Country").cast(pl.Utf8).str.strip_chars() == ""))
            & pl.col("Publisher").is_not_null()
            & pl.col("Publisher").is_in(list(country_map.keys()))
        )
        .then(pl.col("Publisher").map_dict(country_map).alias("Country"))
        .otherwise(pl.col("Country"))
        .alias("Country")
    )


def normalize_publisher_type(name: str) -> str:
    """ Normalize publisher type values.
    """
    if name is None or str(name).strip() == "":
        return ""
    s = str(name).strip().lower()

    if "for-profit" in s and "society" in s:
        return "For-profit on behalf of a society"
    elif "for-profit" in s and "behalf" in s:
        return name.strip()
    elif "for-profit" in s:
        return "For-profit"
    elif "university press" in s and "society" in s:
        return "University Press on behalf of a society"
    elif "university press" in s and "behalf" in s:
        return name.strip()
    elif "university press" in s:
        return "University Press"
    elif s == "non-profit":
        return "Non-profit"
    else:
        print(f"Unknown publisher type: '{name}'")
        return s


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
        "gold oa": "Gold OA",
        "diamond_oa": "Diamond OA",
        "diamond oa": "Diamond OA",
        "hybrid": "Hybrid",
        "subscription": "Subscription",
    }
    if s in mapping:
        return mapping[s]
    else:
        return name.strip()


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


def write_ordered(df: pl.DataFrame, out_path: str) -> None:
    # Order columns and write CSV
    ordered = df.select([pl.col(c) for c in FINAL_COLUMNS])
    ordered.write_csv(out_path)


def load_csv(path: str) -> pl.DataFrame:
    return pl.read_csv(path, ignore_errors=True)
