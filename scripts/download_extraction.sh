# Download csv file from a given URL and save it to a specified directory
URL_PCI="https://docs.google.com/spreadsheets/d/1UF3z_brMq-cJt0nbVactbcNPm5U8YsC6vx1GdmzBfxU"
URL_OPENAPC="https://github.com/OpenAPC/openapc-de/raw/refs/heads/master/data/apc_de.csv"
URL_DOAJ="https://doaj.org/csv"
URL_SCIMAGO="https://www.scimagojr.com/journalrank.php"

mkdir -p ./data_extraction

rm -rf ./data_extraction/PCI_friendly.csv.gz
rm -rf ./data_extraction/openapc.csv.gz
rm -rf ./data_extraction/DOAJ.csv.gz
rm -rf ./data_extraction/Scimago.csv.gz

wget -O ./data_extraction/PCI_friendly.csv "${URL_PCI}/export?format=csv"
gzip ./data_extraction/PCI_friendly.csv

wget -O ./data_extraction/openapc.csv "${URL_OPENAPC}"
gzip ./data_extraction/openapc.csv

wget -O ./data_extraction/DOAJ.csv "${URL_DOAJ}"
gzip ./data_extraction/DOAJ.csv

echo "Downloading Scimago data is not possible due to the need to interact with the website."
echo "Please download the data manually from ${URL_SCIMAGO} as a csv file and save it to ./data_extraction/Scimago.csv"
echo "After downloading the Scimago data, please gzip it using the command:"
echo "gzip ./data_extraction/Scimago.csv"