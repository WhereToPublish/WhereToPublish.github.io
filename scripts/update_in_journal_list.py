import polars as pl

# Constants
INPUT_FILE = "data_legacy/WhereToPublish_database - SU journals to check.csv"
LIST_JOURNALS = "data_extraction/journals.txt"


def remove_unused_characters(name: str) -> str:
    """Remove unused characters from journal names for normalization."""
    if name is None:
        return ""
    return str(name).lower().replace("the ", "").replace("-", " ").replace("_", " ").strip()


def main():
    list_journals = set()
    with open(LIST_JOURNALS, "r") as f:
        for line in f:
            journal_name = line.strip()
            if journal_name:
                list_journals.add(remove_unused_characters(journal_name))

    # Load Scimago data
    input_df = pl.read_csv(INPUT_FILE, separator=',')

    def check_in_list(journal_name: str) -> bool:
        norm_name = remove_unused_characters(journal_name)
        return norm_name in list_journals

    output_df = input_df.with_columns(
        pl.col("Journal").map_elements(check_in_list, return_dtype=pl.Boolean).alias("In Journal List")
    )
    output_path = "data_legacy/WhereToPublish_database - SU journals to check UPDATED.csv"
    output_df.write_csv(output_path)
    print(f"Updated file written to: {output_path}")

if __name__ == "__main__":
    main()
