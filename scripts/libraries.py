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


def load_csv(path: str) -> pl.DataFrame:
    return pl.read_csv(path, ignore_errors=True)


def clean_string(name: str) -> str:
    if "¬†" in name:
        name = name.replace("¬†", " ")
    if "√°√±" in name:
        name = name.replace("√°√±", "an")
    if "√º" in name:
        name = name.replace("√º", "u")
    if "√§" in name:
        name = name.replace("√§", "a")
    if "√ß" in name:
        name = name.replace("√ß", "ç")
    if "‚Äô" in name:
        name = name.replace("‚Äô", "'")
    return str(name).strip()


def format_APC_Euros(df: pl.DataFrame) -> pl.DataFrame:
    """Format the 'APC Euros' column to be integer, extracting only the part before any comma or period, then removing non-digit characters."""
    return df.with_columns(
        pl.col("APC Euros")
        .cast(pl.Utf8)
        .str.replace_all(r"[,.].*", "")
        .str.replace_all(r"[^\d]", "")
        .cast(pl.Int64, strict=False)
        .alias("APC Euros")
    )


def format_Scimago_Rank(df: pl.DataFrame) -> pl.DataFrame:
    """Format the 'Scimago Rank' column to be a float, removing non-numeric characters."""
    return df.with_columns(
        pl.col("Scimago Rank")
        .cast(pl.Utf8)
        .str.replace_all(",", ".")
        .str.replace_all(r"[^\d.]", "")
        .cast(pl.Float64, strict=False)
        .alias("Scimago Rank")
    )


def load_pci_friendly_set() -> set[str]:
    """Load the set of normalized (lowercase, trimmed) journal names that are PCI-friendly."""
    PCI_FRIENDLY_PATH = "data_extraction/PCI_friendly.csv"
    df = pl.read_csv(PCI_FRIENDLY_PATH)
    journals = [clean_string(j) for j in df["Journal"].to_list()]
    return {str(j).lower().strip() for j in journals if j is not None}


def normalize_pci_friendly(entry: str) -> str:
    """Normalize a journal name for PCI-friendly comparison: lowercase and trim."""
    if entry is None:
        return ""
    name = str(entry).strip().lower()
    if name == "none":
        return ""
    elif name == "pci friendly":
        return "PCI friendly"
    elif name == "pci":
        return "PCI"
    else:
        return ""


def mark_pci_friendly(df: pl.DataFrame, friendly_set: set[str]) -> pl.DataFrame:
    """Set 'PCI partner' to 'PCI friendly' when journal is in friendly_set."""
    df = df.with_columns(
        pl.col("PCI partner").map_elements(normalize_pci_friendly, return_dtype=pl.Utf8).alias(
            "PCI partner"
        )
    )
    return df.with_columns(
        pl.when(
            pl.col("Journal").cast(pl.Utf8).str.to_lowercase().str.strip_chars().is_in(list(friendly_set))
        )
        .then(pl.lit("PCI friendly"))
        .otherwise(pl.col("PCI partner"))
        .alias("PCI partner")
    )


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
    if "BMC" in name or "biomed central" in name_lower:
        return "Springer Nature (BioMed Central)"
    elif "springer" in name_lower or "nature" == name_lower or "nature publishing group" in name_lower or "nature research" in name_lower or "nature portfolio" in name_lower:
        return "Springer Nature"
    elif "wiley" in name_lower:
        return "John Wiley & Sons"
    elif "taylor" in name_lower and "francis" in name_lower:
        return "Taylor & Francis Group"
    elif "Cell" == name or "cell press" in name_lower:
        return "Elsevier (Cell Press)"
    elif "elsevier" in name_lower:
        return "Elsevier"
    elif "frontiers" in name_lower:
        return "Frontiers Media SA"
    elif "BMJ" in name:
        return "BMJ Group"
    elif "BioOne Complete" in name:
        return "BioOne"
    elif "OUP" in name:
        return "Oxford University Press"
    elif "APA" in name:
        return "American Psychological Association"
    elif "AMA" in name:
        return "American Medical Association"
    elif "AAAS" in name:
        return "American Association for the Advancement of Science"
    elif "public library of science" in name_lower or "plos" in name_lower:
        return "Public Library of Science (PLoS)"
    elif "PCI" in name:
        return "Peer Community In"
    return str(clean_string(name))


def derive_country_from_publisher(df: pl.DataFrame) -> pl.DataFrame:
    """ Derive 'Country' from known 'Publisher' names when 'Country' is missing/empty.
    """
    country_map = {
        "Oxford University Press": "UK",
        "Cambridge University Press": "UK",
        "BMJ Group": "UK",
        "Springer Nature": "Germany/UK",
        "The Royal Society": "UK",
        "MDPI": "Switzerland",
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


def normalize_institution(name: str) -> str:
    """ Normalize institution names by stripping leading/trailing spaces.
    Return empty string if name is None.
    """
    if name is None:
        return ""
    return str(clean_string(name))


# New inference and annotation helpers

def infer_institution_type(df: pl.DataFrame) -> pl.DataFrame:
    """Infer 'Institution type' as 'Society' when Institution name suggests a society and Institution type is empty/null."""
    pattern = r"\b(society|société|societe|sociedad|società|sociedade|gesellschaft|association|associación|associação|vereniging|genootschap)\b"
    df = df.with_columns(inst_lower=pl.col("Institution").cast(pl.Utf8).str.to_lowercase())
    df = df.with_columns(
        pl.when(
            (pl.col("Institution type").is_null() | (pl.col("Institution type").cast(pl.Utf8).str.strip_chars() == ""))
            & pl.col("inst_lower").str.contains(pattern)
        )
        .then(pl.lit("Society"))
        .otherwise(pl.col("Institution type"))
        .alias("Institution type")
    ).drop("inst_lower")
    return df


def infer_publisher_type_from_publisher(df: pl.DataFrame) -> pl.DataFrame:
    """Infer 'Publisher type' from known publisher names when Publisher type is empty/null.
    - Recognized for-profit: set to 'For-profit'.
    - Recognized university presses: set to 'University Press'.
    """
    for_profit = {
        "Elsevier",
        "Elsevier (Cell Press)",
        "Taylor & Francis Group",
        "Springer Nature",
        "John Wiley & Sons",
        "Sage Publishing",
        "Frontiers Media SA",
        "MDPI",
    }
    df = df.with_columns(pub_lower=pl.col("Publisher").cast(pl.Utf8))
    empty_pubtype = pl.col("Publisher type").is_null() | (pl.col("Publisher type").cast(pl.Utf8).str.strip_chars() == "")
    is_forprofit = pl.col("pub_lower").is_in(list(for_profit))
    is_unipress = pl.col("pub_lower").cast(pl.Utf8).str.contains(r"University Press")

    df = df.with_columns(
        pl.when(empty_pubtype & is_forprofit)
        .then(pl.lit("For-profit"))
        .otherwise(
            pl.when(empty_pubtype & is_unipress)
            .then(pl.lit("University Press"))
            .otherwise(pl.col("Publisher type"))
        )
        .alias("Publisher type")
    ).drop("pub_lower")
    return df


def annotate_publisher_type_from_institution_type(df: pl.DataFrame) -> pl.DataFrame:
    """Annotate 'Publisher type' with Society-Run based on 'Institution type'.
    Rules:
    - If Publisher type is 'For-profit' and Institution type is 'Society' => 'For-profit Society-Run'
    - If Publisher type is 'University Press' and Institution type is 'Society' => 'University Press Society-Run'
    Log each change with journal, previous publisher type, institution, institution type, and new publisher type.
    """
    new_type_expr = (
        pl.when((pl.col("Publisher type") == "For-profit") & (pl.col("Institution type") == "Society"))
        .then(pl.lit("For-profit Society-Run"))
        .otherwise(
            pl.when((pl.col("Publisher type") == "University Press") & (pl.col("Institution type") == "Society"))
            .then(pl.lit("University Press Society-Run"))
            .otherwise(pl.col("Publisher type"))
        )
    )

    df_temp = df.with_columns(new_publisher_type=new_type_expr)
    changes = df_temp.filter(pl.col("new_publisher_type") != pl.col("Publisher type"))
    if changes.height > 0:
        for row in changes.select(["Journal", "Publisher type", "Institution", "Institution type", "new_publisher_type"]).to_dicts():
            print(
                "[annotate_publisher_type_from_institution_type] Journal='{}', prev_publisher_type='{}', institution='{}', institution_type='{}', new_publisher_type='{}'".format(
                    row.get("Journal"), row.get("Publisher type"), row.get("Institution"), row.get("Institution type"), row.get("new_publisher_type")
                )
            )
    df_temp = df_temp.with_columns(pl.col("new_publisher_type").alias("Publisher type")).drop("new_publisher_type")
    return df_temp


def format_table(df: pl.DataFrame) -> pl.DataFrame:
    # Format numeric columns
    df = format_APC_Euros(df)
    df = format_Scimago_Rank(df)

    # Normalize text fields
    # Format names
    df = df.with_columns(
        pl.col("Journal").map_elements(clean_string, return_dtype=pl.Utf8)
        .alias("Journal")
    )
    df = df.with_columns(
        pl.col("Publisher").map_elements(normalize_publisher, return_dtype=pl.Utf8).alias("Publisher")
    )
    df = df.with_columns(
        pl.col("Business model").map_elements(normalize_business_model, return_dtype=pl.Utf8).alias("Business model")
    )
    df = df.with_columns(
        pl.col("Institution").map_elements(normalize_institution, return_dtype=pl.Utf8).alias("Institution")
    )

    # Derive Country from Publisher when missing/empty
    df = derive_country_from_publisher(df)

    # Ensure required columns exist for inference
    df = ensure_columns(df)

    # Infer types and annotate publisher type based on institution type
    df = infer_institution_type(df)
    df = infer_publisher_type_from_publisher(df)
    df = annotate_publisher_type_from_institution_type(df)
    return df


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
