import json
import polars as pl
import re
import unicodedata
import gzip
from pathlib import Path

# Expected columns and their final order
FINAL_COLUMNS: list[str] = [
    "Journal's MAIN field",
    "Field",
    "Journal",
    "Website",
    "Publisher type",
    "Publisher",
    "Institution",
    "Institution type",
    "Country",
    "Business model",
    "APC Euros",
    "Alternative journal name",
    "Present in Scimago",
    "Present in DOAJ",
    "Present in openAPC",
    "Scimago Rank",
    "Scimago Quartile",
    "H index",
    "PCI partner",
    "e-ISSN",
    "p-ISSN",
    "ISSN-L",
]

COUNTRY_FORMATTING_PATH = Path("config/country_formatting.json")

NUMERIC_COLUMNS = [
    "APC Euros",
    "Scimago Rank",
    "H index",
]


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


def load_csv(file_path, **kwargs):
    """
    Load a CSV file, handling both compressed (.gz) and uncompressed files.
    By default, all columns are read as Utf8 to avoid type inference issues.
    """
    if file_path.endswith(".gz"):
        with gzip.open(file_path, "rb") as f:
            return pl.read_csv(f, **kwargs)
    else:
        return pl.read_csv(file_path, **kwargs)


def ascii_fallbacks(s: str) -> str:
    """Handle characters that are not removed by unicode normalization.
    """
    # e.g. bad decoding of UTF-8 as Latin-1 or similar
    mojibake = [("¬†", " "), ("√°√±", "an"), ("√º", "u"), ("√§", "a"),
                ("√ß", "ç"), ("‚Äô", "'"), ("√©", "é"), ("√∫", "u"),
                ("√o", "u"), ("√≠", "i"), ("√†", "à"), ("Äö", "")]
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
    if s.startswith("la "):
        s = s.replace("la ", "", 1)
    if s.startswith("le "):
        s = s.replace("le ", "", 1)
    if s.startswith("les "):
        s = s.replace("les ", "", 1)
    if s.startswith("el "):
        s = s.replace("el ", "", 1)
    if s.startswith("los "):
        s = s.replace("los ", "", 1)
    if s.startswith("las "):
        s = s.replace("las ", "", 1)
    if s.startswith("a "):
        s = s.replace("a ", "", 1)
    if s.startswith("l'"):
        s = s.replace("l'", "", 1)
    if " an " in s:
        s = s.replace(" an ", " ")
    if " of " in s:
        s = s.replace(" of ", " ")
    if " l'" in s:
        s = s.replace(" l'", " ")
    if " and " in s:
        s = s.replace(" and ", " ")
    if "&" in s:
        s = s.replace("&", " ")
    # Remove anything between parentheses
    s = re.sub(r"\(.*?\)", "", s)
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


def format_issn(issn: str) -> str | None:
    """Normalize an ISSN string to standard XXXX-XXXX format.
    - Strips whitespace and non-alphanumeric characters except dashes
    - If 8 consecutive digits (no dash), inserts dash at position 4
    - Returns None if the result is not a valid-looking ISSN (not 9 chars XXXX-XXXX)
    """
    if issn is None:
        return None
    s = str(issn).strip()
    if not s or s.upper() == "NA":
        return None
    # Remove all non-alphanumeric chars except dash
    s = re.sub(r"[^0-9Xx]", "", s)
    if len(s) == 8:
        s = s[:4] + "-" + s[4:]
    elif len(s) == 9 and s[4] == "-":
        pass  # already formatted
    else:
        return None
    # Validate: XXXX-XXXX where X is digit or 'X'
    if not re.match(r"^[0-9]{4}-[0-9]{3}[0-9Xx]$", s):
        return None
    return s.upper()


def format_APC(apc: str) -> str:
    """Format a single APC value to extract the integer part before any comma or period, removing non-digit characters."""
    if apc is None:
        return ""
    s = str(apc)
    # Their can be ";" as separator for multiple values, take the one that contains EUR
    if ";" in s:
        parts = s.split(";")
        eur_parts = [p for p in parts if "eur" in p.lower()]
        if eur_parts:
            s = eur_parts[0]
        else:
            s = parts[0]
    # Extract part before comma or period
    s = re.split(r"[,.]", s)[0]
    # Remove non-digit characters
    s = re.sub(r"[^\d]", "", s)
    return s


def format_APC_Euros(df: pl.DataFrame, col: str = "APC Euros") -> pl.DataFrame:
    """Format the 'APC Euros' column to be integer, extracting only the part before any comma or period, then removing non-digit characters."""
    df = df.with_columns(
        pl.col(col).map_elements(format_APC, return_dtype=pl.Utf8).cast(pl.Int64, strict=True)
        .alias(col)
    )
    # assert there is no APC < 0 and APC > 20000
    filter_invalid = df.filter((pl.col(col).is_not_null()) & ((pl.col(col) < 0) | (pl.col(col) > 20000)))
    if filter_invalid.height > 0:
        print("Invalid APC Euros values found:")
        print(filter_invalid)
    return df


def format_Scimago_Rank(df: pl.DataFrame, col: str = "Scimago Rank") -> pl.DataFrame:
    """Format the 'Scimago Rank' column to be a float, removing non-numeric characters."""
    return df.with_columns(
        pl.col(col)
        .cast(pl.Utf8)
        .str.replace_all(",", ".")
        .str.replace_all(r"[^\d.]", "")
        .cast(pl.Float64, strict=True)
        .alias(col)
    )


def load_pci_friendly_set() -> set[str]:
    """Load the set of normalized (lowercase, trimmed) journal names that are PCI-friendly."""
    PCI_FRIENDLY_PATH = "data_extraction/PCI_friendly.csv.gz"
    df = load_csv(PCI_FRIENDLY_PATH)
    journals = [clean_string(j) for j in df["Journal"].to_list()]
    return {str(j).lower().strip() for j in journals if j is not None}


def normalize_pci_friendly(entry: str) -> str:
    """Normalize a journal name for PCI-friendly comparison: lowercase and trim."""
    if entry is None:
        return "No"
    name = str(entry).strip().lower()
    if name == "none":
        return "No"
    elif name == "pci friendly":
        return "PCI friendly"
    elif name == "pci":
        return "PCI"
    else:
        return "No"


def mark_pci_friendly(df: pl.DataFrame, friendly_set: set[str]) -> pl.DataFrame:
    """Set 'PCI partner' to 'PCI friendly' when journal is in friendly_set."""
    df = df.with_columns(
        pl.col("PCI partner").map_elements(normalize_pci_friendly, return_dtype=pl.Utf8, skip_nulls=False).alias(
            "PCI partner")
    )
    return df.with_columns(
        pl.when(
            pl.col("Journal").cast(pl.Utf8).str.to_lowercase().str.strip_chars().is_in(list(friendly_set))
        )
        .then(pl.lit("PCI friendly"))
        .otherwise(pl.col("PCI partner"))
        .alias("PCI partner")
    )


def normalize_field(name: str) -> str:
    """Normalize field values by stripping leading/trailing spaces."""
    if name is None:
        return "Generalist"
    if name.lower() == "general":
        return "Generalist"
    name = str(name).replace("_", " ").strip()
    return name[0].upper() + name[1:]


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
    elif "de gruyter" in name_lower or "brill" in name_lower:
        return "De Gruyter Brill"
    elif "karger" in name_lower:
        return "Karger Publishers"
    elif "inderscience" in name_lower:
        return "Inderscience Publishers"
    elif ("taylor" in name_lower) and ("francis" in name_lower) and ("(" not in name_lower):
        return "Taylor & Francis Group"
    elif ("taylor" in name_lower) and ("francis" in name_lower):
        return "Taylor & Francis Group (" + name.split("(", 1)[1]
    elif "PeerJ" in name:
        return "Taylor & Francis Group (PeerJ)"
    elif ("sage" in name_lower) and ("(" not in name_lower):
        return "Sage Publishing"
    elif "sage publishing" in name_lower:
        return "Sage Publishing (" + name.split("(", 1)[1]
    elif "Cell" == name or "cell press" in name_lower:
        return "Elsevier (Cell Press)"
    elif "academic press" in name_lower:
        return "Elsevier (Academic Press)"
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
    elif "AAAS" in name or "american association for the advancement of science" in name_lower:
        return "American Association for the Advancement of Science (AAAS)"
    elif "AACR" in name or "american association for cancer research" in name_lower:
        return "American Association for Cancer Research (AACR)"
    elif "ACS" in name or "american chemical society" in name_lower:
        return "American Chemical Society (ACS)"
    elif "AMA" in name or "american medical association" in name_lower:
        return "American Medical Association (AMA)"
    elif "APA" in name or "american psychological association" in name_lower:
        return "American Psychological Association (APA)"
    elif "APS" in name or "american physiological society" in name_lower:
        return "American Physiological Society (APS)"
    elif "ASM" in name or "american society for microbiology" in name_lower:
        return "American Society for Microbiology (ASM)"
    elif "ERS" in name or "european respiratory society" in name_lower:
        return "European Respiratory Society (ERS)"
    elif "public library of science" in name_lower or "plos" in name_lower:
        return "Public Library of Science (PLoS)"
    elif "PCI" in name or "peer community in" in name_lower:
        return "Peer Community In"
    elif "annual reviews" in name_lower:
        return "Annual Reviews"
    elif "lippincott" in name_lower and "williams" in name_lower and "wilkins" in name_lower:
        return "Wolters Kluwer (Lippincott)"
    elif "ovid technologies" in name_lower:
        return "Wolters Kluwer (Ovid Technologies)"
    elif "wolters kluwer" in name_lower and "(" not in name_lower and ")" not in name_lower:
        return "Wolters Kluwer"
    elif "bioscientifica" in name_lower:
        return "Bioscientifica Ltd"
    elif "mary ann liebert" in name_lower:
        return "Sage Publishing (Mary Ann Liebert)"
    elif "pensoft publishers" in name_lower or "pensoft" in name_lower:
        return "Pensoft Publishers"
    elif "CSIRO" in name or "commonwealth scientific and industrial research organisation" in name_lower:
        return "CSIRO Publishing"
    elif "MIT" in name and "mit press" in name_lower:
        return "MIT Press"
    elif "john libbey" in name_lower or "JLE" in name:
        return "John Libbey Eurotext"
    elif "national" in name_lower and "histoire" in name_lower and "naturelle" in name_lower:
        return "Muséum national d'Histoire naturelle (MNHN)"
    elif "korean society for microbiology and biotechnology" in name_lower or "KSBMB" in name:
        return "Korean Society for Microbiology and Biotechnology (KSBMB)"
    elif "cold spring harbor" in name_lower:
        return "Cold Spring Harbor (CSH) Laboratory Press"
    elif "pagepress" in name_lower or "page press publications" in name_lower:
        return "PAGEPress Publications"
    elif "PUF" in name or "presses universitaires de france" in name_lower:
        return "Presses Universitaires de France (PUF)"
    elif "company of biologists" in name_lower:
        return "The Company of Biologists"
    elif "royal society publishing" in name_lower or "the royal society" in name_lower:
        return "The Royal Society"
    elif "EDP Sciences" in name or "china science publishing & media" in name_lower:
        return "China Science Publishing & Media (EDP Sciences)"
    return str(clean_string(name))


def load_country_formatting() -> dict[str, dict[str, str]]:
    """Load publisher→country mappings from config/country_formatting.json.

    Returns a nested dict with keys 'for_profit', 'university_press', 'non_profit',
    each mapping publisher name → country string.
    """
    with open(COUNTRY_FORMATTING_PATH, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict) and "for_profit" in data and "non_profit" in data and "university_press" in data, (
        "Expected keys 'for_profit', 'university_press', and 'non_profit' in country formatting data"
    )
    assert isinstance(data["for_profit"], dict) and isinstance(data["non_profit"], dict) and isinstance(
        data["university_press"], dict), (
        "Expected 'for_profit', 'university_press', and 'non_profit' to be dicts in country formatting data"
    )
    assert len(data["for_profit"]) > 0, (
        f"'for_profit' dict is empty in {COUNTRY_FORMATTING_PATH}"
    )
    return data


def derive_country_from_publisher(df: pl.DataFrame) -> pl.DataFrame:
    """Derive 'Country' from known 'Publisher' names when 'Country' is missing/empty.
    Publisher→country mapping is loaded from config/country_formatting.json (all 3 groups).
    """
    formatting = load_country_formatting()
    country_map = {
        **formatting["for_profit"],
        **formatting.get("university_press", {}),
        **formatting.get("non_profit", {}),
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
        "uk / germany": "Germany / UK",
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
        "south korea": "Republic of Korea (South Korea)",
        "republic of Korea (south korea)": "Republic of Korea (South Korea)",
        "korea": "Republic of Korea (South Korea)",
        "republic of korea": "Republic of Korea (South Korea)",
        "(republic of) korea": "Republic of Korea (South Korea)",
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
def normalize_institution_type(name: str) -> str:
    """ Normalize institution type values.
    """
    if name is None or str(name).strip() == "":
        return ""
    s = str(name).strip().lower()

    if "society" in s or "association" in s:
        return "Society/Association"
    elif "non-profit" in s or "non profit" in s or "nonprofit" in s:
        return "Non-profit"
    elif "university" in s or "government" in s or "université" in s or "universidad" in s or "università" in s or "universidade" in s:
        return "University/Government"
    else:
        print(f"Unknown institution type: '{name}'")
        return s


def infer_institution_type(df: pl.DataFrame) -> pl.DataFrame:
    """Infer 'Institution type' as 'Society' when Institution name suggests a society and Institution type is empty/null."""
    pattern_assoc = r"\b(society|société|societe|sociedad|società|sociedade|gesellschaft|association|associación|associação|vereniging|genootschap)\b"
    df = df.with_columns(inst_lower=pl.col("Institution").cast(pl.Utf8).str.to_lowercase())
    df = df.with_columns(
        pl.when(
            (pl.col("Institution type").is_null() | (pl.col("Institution type").cast(pl.Utf8).str.strip_chars() == ""))
            & pl.col("inst_lower").str.contains(pattern_assoc)
        )
        .then(pl.lit("Society/Association"))
        .otherwise(pl.col("Institution type"))
        .alias("Institution type")
    ).drop("inst_lower")
    return df


def infer_publisher_type_from_publisher(df: pl.DataFrame) -> pl.DataFrame:
    """Infer 'Publisher type' from known publisher names when Publisher type is empty/null.

    Publisher name sets are loaded from config/country_formatting.json:
      - 'for_profit' keys  → 'For-profit'
      - 'university_press' keys → 'University Press'
      - 'non_profit' keys  → 'Non-profit'

    A catch-all fallback assigns 'University Press' to any publisher whose name
    contains the substring 'University Press' (covers unlisted publishers).
    """
    formatting = load_country_formatting()
    for_profit_pubs = set(formatting["for_profit"].keys())
    university_press_pubs = set(formatting.get("university_press", {}).keys())
    non_profit_pubs = set(formatting.get("non_profit", {}).keys())

    pub = pl.col("Publisher").cast(pl.Utf8)
    empty_pubtype = pl.col("Publisher type").is_null() | (
            pl.col("Publisher type").cast(pl.Utf8).str.strip_chars() == ""
    )

    df = df.with_columns(
        pl.when(empty_pubtype & pub.is_in(for_profit_pubs))
        .then(pl.lit("For-profit"))
        .when(empty_pubtype & pub.is_in(university_press_pubs))
        .then(pl.lit("University Press"))
        .when(empty_pubtype & pub.is_in(non_profit_pubs))
        .then(pl.lit("Non-profit"))
        .when(empty_pubtype & pub.str.contains(r"University Press"))
        .then(pl.lit("University Press"))
        .otherwise(pl.col("Publisher type"))
        .alias("Publisher type")
    )
    return df


def annotate_publisher_type_from_institution_type(df: pl.DataFrame) -> pl.DataFrame:
    """Annotate 'Publisher type' with Society-Run based on 'Institution type'.
    Rules:
    - If Publisher type is 'For-profit' and Institution type is 'Society' => 'For-profit Society-Run'
    - If Publisher type is 'University Press' and Institution type is 'Society' => 'University Press Society-Run'
    Log each change with journal, previous publisher type, institution, institution type, and new publisher type.
    """
    new_type_expr = (
        pl.when((pl.col("Publisher type") == "For-profit") & (pl.col("Institution type") == "Society/Association"))
        .then(pl.lit("For-profit Society-Run"))
        .otherwise(
            pl.when((pl.col("Publisher type") == "University Press") & (
                    pl.col("Institution type") == "Society/Association"))
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


def derive_business_model_from_APC(df: pl.DataFrame) -> pl.DataFrame:
    """ Derive 'Business model' from 'APC Euros'.
    - If APC Euros is > 0 and business model is empty or 'Subscription', set Business model to 'Hybrid'.
    """
    df = df.with_columns(
        pl.when(
            (pl.col("APC Euros").is_not_null())
            & (pl.col("APC Euros") > 0)
            & (
                    pl.col("Business model").is_null()
                    | (pl.col("Business model").cast(pl.Utf8).str.strip_chars() == "")
                    | (pl.col("Business model").cast(pl.Utf8) == "Subscription")
            )
        )
        .then(pl.lit("Hybrid"))
        .otherwise(pl.col("Business model"))
        .alias("Business model")
    )
    return df


def derive_APC_from_business_model(df: pl.DataFrame) -> pl.DataFrame:
    """ Derive 'APC Euros' from 'Business model'.
    - If Business model is 'OA diamond', set 'APC Euros' to 0.
    - If Business model is 'Subscription', set 'APC Euros' to None.
    """
    df = df.with_columns(
        pl.when(pl.col("Business model") == "OA diamond")
        .then(pl.lit(0))
        .when(pl.col("Business model") == "Subscription")
        .then(pl.lit(None))
        .otherwise(pl.col("APC Euros"))
        .alias("APC Euros")
    )
    return df


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
    # Force Business model to 'OA diamond' for all "Peer Community In" journals
    df = df.with_columns(
        pl.when(pl.col("Journal").cast(pl.Utf8).str.starts_with("Peer Community In"))
        .then(pl.lit("OA diamond"))
        .otherwise(pl.col("Business model"))
        .alias("Business model")
    )
    df = df.with_columns(
        pl.col("Business model").map_elements(normalize_business_model, return_dtype=pl.Utf8).alias("Business model"))
    df = df.with_columns(
        pl.col("Country").map_elements(standardize_country_name, return_dtype=pl.Utf8).alias("Country")
    )
    df = df.with_columns(
        pl.col("Institution").map_elements(normalize_institution, return_dtype=pl.Utf8).alias("Institution")
    )
    # Infer types and annotate the publisher type based on the institution type
    df = df.with_columns(
        pl.col("Institution type").map_elements(normalize_institution_type, return_dtype=pl.Utf8).alias(
            "Institution type")
    )
    # Derive Country from Publisher when missing/empty
    df = derive_country_from_publisher(df)

    # Ensure required columns exist for inference
    df = ensure_columns(df)

    # Format ISSNs to standard XXXX-XXXX (ensures consistency with external source lookups)
    df = df.with_columns([
        pl.col("e-ISSN").map_elements(format_issn, return_dtype=pl.Utf8).alias("e-ISSN"),
        pl.col("p-ISSN").map_elements(format_issn, return_dtype=pl.Utf8).alias("p-ISSN"),
        pl.col("ISSN-L").map_elements(format_issn, return_dtype=pl.Utf8).alias("ISSN-L"),
    ])

    # Infer types and annotate the publisher type based on the institution type
    df = infer_institution_type(df)
    df = infer_publisher_type_from_publisher(df)
    df = annotate_publisher_type_from_institution_type(df)

    # Infer Business model from APC first (Subscription + APC > 0 → Hybrid)
    df = derive_business_model_from_APC(df)
    # Then derive APC from Business model (OA diamond → 0, Subscription → None)
    df = derive_APC_from_business_model(df)
    return df


def normalize_publisher_type(name: str) -> str:
    """ Normalize publisher type values.
    """
    if name is None or str(name).strip() == "":
        return ""
    s = str(name).strip().lower()

    if "for-profit" in s and "society" in s:
        return "For-profit associated with a society"
    elif "for-profit" in s and "associated" in s:
        return name.strip()
    elif "for-profit" in s:
        return "For-profit"
    elif "university press" in s and "society" in s:
        return "University Press associated with a society"
    elif "university press" in s and "associated" in s:
        return name.strip()
    elif "university press" in s:
        return "University Press"
    elif s == "non-profit":
        return "Non-profit"
    else:
        print(f"Unknown publisher type: '{name}'")
        return s


def write_ordered(df: pl.DataFrame, out_path: str) -> None:
    # Order columns and write CSV
    ordered = df.select([pl.col(c) for c in FINAL_COLUMNS])
    ordered.write_csv(out_path)


def check_consistency(df: pl.DataFrame) -> None:
    """Check for consistency in key columns and log any issues found."""
    # Assert that no OA diamond journal has APC > 0.
    filter_diamond = df.filter(
        (pl.col("Business model") == "OA diamond") &
        (pl.col("APC Euros").is_not_null()) &
        (pl.col("APC Euros").cast(pl.Utf8).str.strip_chars() != "") &
        (pl.col("APC Euros").cast(pl.Utf8).str.strip_chars() != "0")
    )
    assert filter_diamond.height == 0, (
        f"Found {filter_diamond.height} rows with Business model 'OA diamond' but APC Euros not 0."
    )
    # Assert that no Subscription journal has APC > 0.
    filter_sub = df.filter(
        (pl.col("Business model") == "Subscription") &
        (pl.col("APC Euros").is_not_null()) &
        (pl.col("APC Euros").cast(pl.Utf8).str.strip_chars() != "") &
        (pl.col("APC Euros").cast(pl.Utf8).str.strip_chars() != "0")
    )
    assert filter_sub.height == 0, (
        f"Found {filter_sub.height} rows with Business model 'Subscription' but APC Euros not null/0."
    )
