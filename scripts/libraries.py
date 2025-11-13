import polars as pl
import re
import unicodedata

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
    "Scimago Quartile",
    "H index",
    "PCI partner",
]


def load_csv(path: str) -> pl.DataFrame:
    return pl.read_csv(path, ignore_errors=True)


def ascii_fallbacks(s: str) -> str:
    """Handle characters that are not removed by unicode normalization.
    """
    # e.g. bad decoding of UTF-8 as Latin-1 or similar
    mojibake = [("¬†", " "), ("√°√±", "an"), ("√º", "u"), ("√§", "a"),
                ("√ß", "ç"), ("‚Äô", "'"), ("√©", "é"), ("√∫", "u"),
                ("√o", "u"), ("√≠", "i"), ("√†", "à")]
    for a, b in mojibake:
        if a in s:
            s = s.replace(a, b)
    # Normalize various dashes to ASCII hyphen
    s = s.replace("–", "-").replace("—", "-").replace("−", "-")
    return s


def clean_string(name: str) -> str:
    """General-purpose string cleaner for display/storage.
    - Return empty string for None
    - Unicode normalize to NFKC (compatibility decomposition + composition)
    - Remove control and formatting characters (categories Cc, Cf)
    - Replace non-breaking spaces with regular spaces
    - Apply ASCII fallbacks for special letters and mojibake
    - Collapse all whitespace runs to a single space and trim
    """
    if name is None:
        return ""
    s = str(name)
    # Normalize the text to handle compatibility characters
    s = unicodedata.normalize("NFKC", s)
    # Remove control and formatting characters (e.g., zero-width joiners)
    s = "".join(ch for ch in s if unicodedata.category(ch) not in {"Cc", "Cf"})
    # Normalize various space types
    s = s.replace("\u00A0", " ")  # non-breaking space to regular space
    # Apply ASCII fallbacks and dash normalization (also fixes mojibake)
    s = ascii_fallbacks(s)
    # Collapse whitespace and trim
    s = re.sub(r"\s+", " ", s).strip()
    return s


def strip_diacritics(text: str) -> str:
    """Remove diacritics from a unicode string using NFKD normalization."""
    if text is None:
        return ""
    norm = unicodedata.normalize("NFKD", str(text))
    return "".join(ch for ch in norm if not unicodedata.combining(ch))


def norm_name(text: str) -> str:
    """Normalize names for duplicate detection.
    - Lowercase
    - Remove diacritics
    - Replace any sequence of non-alphanumeric characters with a single space
    - Collapse multiple spaces, strip leading/trailing spaces
    """
    if text is None:
        return ""
    s = strip_diacritics(clean_string(text)).lower()
    if s.startswith("the "):
        s = s.replace("the ", "", 1)
    if " and " in s:
        s = s.replace(" and ", " ")
    if "&" in s:
        s = s.replace("&", " ")
    # Remove any non [a-z0-9]
    s = re.sub(r"[^a-z0-9]+", "", s)
    # Collapse spaces and trim
    s = re.sub(r"\s+", " ", s).strip()
    return s


def norm_url(url: str) -> str:
    """Normalize URLs for duplicate detection.
    - Lowercase
    - Strip scheme (http/https)
    - Strip leading www.
    - Remove query string and fragment
    - Remove trailing slash
    - Collapse whitespace and strip
    """
    if url is None:
        return ""
    s = str(url).strip().lower()
    # Remove scheme
    s = re.sub(r"^https?://", "", s)
    # Remove query and fragment
    s = s.split("?")[0].split("#")[0]
    # Remove leading www.
    s = re.sub(r"^www\.", "", s)
    # Remove trailing slash(es)
    s = s.rstrip("/")
    # Collapse whitespace just in case
    s = re.sub(r"\s+", " ", s).strip()
    return s


def format_url(url: str) -> str:
    """Format a single URL to normalized form."""
    # Add https:// if http/https scheme is missing
    if url is None:
        return ""
    s = str(url).strip()
    if not re.match(r"^https?://", s, re.IGNORECASE):
        s = "https://" + s
    # if http instead of https, convert to https
    if s.lower().startswith("http://"):
        s = "https://" + s[7:]
    return s


def format_urls(df: pl.DataFrame, col: str = "Website") -> pl.DataFrame:
    """Format the 'Website' column to normalized URLs."""
    return df.with_columns(
        pl.col(col)
        .map_elements(format_url, return_dtype=pl.Utf8)
        .alias(col)
    )


def format_APC_Euros(df: pl.DataFrame, col: str = "APC Euros") -> pl.DataFrame:
    """Format the 'APC Euros' column to be integer, extracting only the part before any comma or period, then removing non-digit characters."""
    return df.with_columns(
        pl.col(col)
        .cast(pl.Utf8)
        .str.replace_all(r"[,.].*", "")
        .str.replace_all(r"[^\d]", "")
        .cast(pl.Int64, strict=False)
        .alias(col)
    )


def format_Scimago_Rank(df: pl.DataFrame, col: str = "Scimago Rank") -> pl.DataFrame:
    """Format the 'Scimago Rank' column to be a float, removing non-numeric characters."""
    return df.with_columns(
        pl.col(col)
        .cast(pl.Utf8)
        .str.replace_all(",", ".")
        .str.replace_all(r"[^\d.]", "")
        .cast(pl.Float64, strict=False)
        .alias(col)
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
    elif "OUP" in name or "oxford university press" in name_lower:
        return "Oxford University Press (OUP)"
    elif "CUP" in name or "cambridge university press" in name_lower:
        return "Cambridge University Press (CUP)"
    elif "APA" in name or "american psychological association" in name_lower:
        return "American Psychological Association (APA)"
    elif "AMA" in name or "american medical association" in name_lower:
        return "American Medical Association (AMA)"
    elif "ASM" in name or "american society for microbiology" in name_lower:
        return "American Society for Microbiology (ASM)"
    elif "AAAS" in name or "american association for the advancement of science" in name_lower:
        return "American Association for the Advancement of Science (AAAS)"
    elif "public library of science" in name_lower or "plos" in name_lower:
        return "Public Library of Science (PLoS)"
    elif "PCI" in name or "peer community in" in name_lower:
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
        .then(pl.col("Publisher").replace(country_map).alias("Country"))
        .otherwise(pl.col("Country"))
        .alias("Country")
    )


def standardize_country_name(name: str) -> str:
    """Standardize country names to common abbreviations and names.
    Maps various country name variants to standard forms.
    """
    if name is None:
        return ""
    s = str(name).strip()
    if not s:
        return ""

    s_lower = s.lower()
    mapping = {
        "united states": "USA",
        "united states of america": "USA",
        "us": "USA",
        "usa": "USA",
        "united kingdom": "UK",
        "great britain": "UK",
        "uk": "UK",
        "england": "UK",
        "netherlands": "Netherlands",
        "the netherlands": "Netherlands",
        "holland": "Netherlands",
        "germany": "Germany",
        "deutschland": "Germany",
        "france": "France",
        "switzerland": "Switzerland",
        "swiss": "Switzerland",
        "spain": "Spain",
        "españa": "Spain",
        "italy": "Italy",
        "italia": "Italy",
        "canada": "Canada",
        "australia": "Australia",
        "china": "China",
        "japan": "Japan",
        "india": "India",
        "brazil": "Brazil",
        "brasil": "Brazil",
        "mexico": "Mexico",
        "méxico": "Mexico",
        "argentina": "Argentina",
        "russia": "Russia",
        "russian federation": "Russia",
        "south korea": "South Korea",
        "korea": "South Korea",
        "republic of korea": "South Korea",
        "new zealand": "New Zealand",
        "poland": "Poland",
        "portugal": "Portugal",
        "austria": "Austria",
        "belgium": "Belgium",
        "denmark": "Denmark",
        "finland": "Finland",
        "sweden": "Sweden",
        "norway": "Norway",
        "ireland": "Ireland",
        "czech republic": "Czech Republic",
        "czechia": "Czech Republic",
        "hungary": "Hungary",
        "romania": "Romania",
        "greece": "Greece",
        "turkey": "Turkey",
        "türkiye": "Turkey",
        "south africa": "South Africa",
        "egypt": "Egypt",
        "iran": "Iran",
        "islamic republic of iran": "Iran",
        "israel": "Israel",
        "saudi arabia": "Saudi Arabia",
    }

    if s_lower in mapping:
        return mapping[s_lower]
    # Return capitalized version if not in mapping
    return s


def normalize_business_model(name: str) -> str:
    """Normalize business model values.
    "oa" -> "OA"
    "gold_OA" -> "OA"
    "diamond_OA" -> "OA diamond"
    "hybrid" -> "Hybrid"
    "subscription" -> "Subscription"
    """
    if name is None:
        return ""
    s = str(name).strip().lower()
    mapping = {
        "oa": "OA",
        "gold_oa": "OA",
        "gold oa": "OA",
        "diamond_oa": "OA diamond",
        "diamond oa": "OA diamond",
        "oa diamond": "OA diamond",
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
    empty_pubtype = pl.col("Publisher type").is_null() | (
            pl.col("Publisher type").cast(pl.Utf8).str.strip_chars() == "")
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
        for row in changes.select(
                ["Journal", "Publisher type", "Institution", "Institution type", "new_publisher_type"]).to_dicts():
            print("\t[annotate_publisher_type_from_institution_type] Journal='{}'"
                  "\n\t\tprev_publisher_type='{}', institution='{}',\n\t\tinstitution_type='{}', new_publisher_type='{}'".format(
                row.get("Journal"), row.get("Publisher type"), row.get("Institution"), row.get("Institution type"),
                row.get("new_publisher_type")))
    df_temp = df_temp.with_columns(pl.col("new_publisher_type").alias("Publisher type")).drop("new_publisher_type")
    return df_temp


def format_table(df: pl.DataFrame) -> pl.DataFrame:
    # Format numeric columns and URLs
    df = format_APC_Euros(df)
    df = format_Scimago_Rank(df)
    df = format_urls(df)

    # Normalize text fields
    # Format names
    df = df.with_columns(
        pl.col("Journal").map_elements(clean_string, return_dtype=pl.Utf8).alias("Journal")
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
    df = df.with_columns(
        pl.col("Country").map_elements(standardize_country_name, return_dtype=pl.Utf8).alias("Country")
    )
    # Derive Country from Publisher when missing/empty
    df = derive_country_from_publisher(df)

    # Ensure required columns exist for inference
    df = ensure_columns(df)

    # Infer types and annotate the publisher type based on the institution type
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
