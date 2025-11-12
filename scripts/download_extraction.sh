# Download csv file from a given URL and save it to a specified directory
URL_PCI="https://docs.google.com/spreadsheets/d/1UF3z_brMq-cJt0nbVactbcNPm5U8YsC6vx1GdmzBfxU"
URL_SCIMAGO="https://www.scimagojr.com/journalrank.php"
URL_OPENAPC="https://github.com/OpenAPC/openapc-de/raw/refs/heads/master/data/apc_de.csv"
URL_DOAJ="https://doaj.org/csv"
mkdir -p ./data_extraction
wget -O ./data_extraction/PCI_friendly.csv "${URL_PCI}/export?format=csv"
wget -O ./data_extraction/scimagojr.csv "${URL_SCIMAGO}?out=xls"
wget -O ./data_extraction/openapc.csv "${URL_OPENAPC}"
wget -O ./data_extraction/DOAJ.csv "${URL_DOAJ}"