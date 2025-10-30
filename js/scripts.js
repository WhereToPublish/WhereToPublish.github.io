function formatDomainName(domain) {
    // Capitalize the first letter of each word in the domain name
    return domain.replace(/_/g, ' ').split(' ').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
}

function parseCSV(csvText) {
    const lines = csvText.split('\n');
    const data = [];
    const domains = new Set();

    // Extract headers from the first line of the CSV
    // Line 0: "Journal","Field","Publisher","Publisher type","Business model","Institution","Institution type","Website","APC Euros","Scimago Rank","PCI partner"
    if (lines.length < 1) {
        console.error("CSV does not have header line.");
        return {data: [], domains: []};
    }

    const rawHeaders = lines[0].split(',').map(header => {
        // Remove quotes if present
        return header.replace(/^"|"$/g, '').trim();
    });

    // Define the columns we want to display
    const finalHeadersText = [
        "Journal",
        "Field", // This will be our domain column
        "Publisher",
        "Publisher type",
        "Business model",
        "APC (€)",
    ];

    const headerRow = $('#journalTable thead tr');
    headerRow.empty(); // Clear existing/placeholder headers
    finalHeadersText.forEach(headerText => {
        // Capitalize and replace underscores with spaces
        headerRow.append($('<th>').text(formatDomainName(headerText)));
    });

    // Find the indices of the columns we need
    const journalIndex = rawHeaders.findIndex(h => h.includes("Journal"));
    const fieldIndex = rawHeaders.findIndex(h => h.includes("Field"));
    const publisherIndex = rawHeaders.findIndex(h => h.includes("Publisher") && !h.includes("type"));
    const publisherTypeIndex = rawHeaders.findIndex(h => h.includes("Publisher type"));
    const businessModelIndex = rawHeaders.findIndex(h => h.includes("Business model"));
    const apcIndex = rawHeaders.findIndex(h => h.includes("APC"));
    const countryIndex = rawHeaders.findIndex(h => h.includes("Country"));
    const institutionIndex = rawHeaders.findIndex(h => h.includes("Institution") && !h.includes("type"));
    const institutionTypeIndex = rawHeaders.findIndex(h => h.includes("Institution type"));
    const websiteIndex = rawHeaders.findIndex(h => h.includes("Website"));
    const scimagoRankIndex = rawHeaders.findIndex(h => h.includes("Scimago"));
    const pciPartnerIndex = rawHeaders.findIndex(h => h.includes("PCI"));

    // Process data rows (starting from the 2nd line, index 1)
    for (let i = 1; i < lines.length; i++) {
        const line = lines[i].trim();

        // Skip empty lines
        if (line === "") {
            continue;
        }

        // Parse the CSV line
        const row = [];
        let currentField = '';
        let inQuotedField = false;

        for (let k = 0; k < line.length; k++) {
            const char = line[k];

            if (char === '"') {
                if (inQuotedField && k + 1 < line.length && line[k + 1] === '"') {
                    // Handle escaped quote "" inside a quoted field
                    currentField += '"';
                    k++; // Skip the second quote of the pair
                } else {
                    inQuotedField = !inQuotedField;
                }
            } else if (char === ',' && !inQuotedField) {
                row.push(currentField.trim());
                currentField = '';
            } else {
                currentField += char;
            }
        }
        row.push(currentField.trim()); // Add the last field

        // Clean up the row data by removing quotes
        const cleanRow = row.map(field => field.replace(/^"|"$/g, '').trim());

        // If we have a valid row with a journal name
        if (cleanRow.length > 0 && cleanRow[journalIndex] !== "") {
            // Extract the domain/field and add it to our set of domains
            if (cleanRow[fieldIndex]) {
                domains.add(cleanRow[fieldIndex]);
            }

            // Create a new row with the columns we want to display
            const newRow = [
                cleanRow[journalIndex] || "", // Journal
                cleanRow[fieldIndex] || "", // Field/Domain
                cleanRow[publisherIndex] || "", // Publisher
                cleanRow[publisherTypeIndex] || "", // Publisher type (status)
                cleanRow[businessModelIndex] || "", // Business model
                cleanRow[apcIndex] || "", // APC cost
                cleanRow[countryIndex] || "", // Country
                cleanRow[institutionIndex] || "", // Institution
                cleanRow[institutionTypeIndex] || "", // Institution type
                cleanRow[websiteIndex] || "", // Website
                cleanRow[scimagoRankIndex] || "", // Scimago Rank
                cleanRow[pciPartnerIndex] || "" // PCI partner
            ];

            data.push(newRow);
        }
    }

    return {
        data: data,
        domains: Array.from(domains).sort()
    };
}

$(document).ready(function () {
    let dataTable; // Variable to store the DataTable instance

    // Add click handler for expandable rows
    $('#journalTable').on('click', 'td.details-control', function () {
        var tr = $(this).closest('tr');
        var row = dataTable ? dataTable.row(tr) : $('#journalTable').DataTable().row(tr);

        if (row.child.isShown()) {
            // This row is already open - close it
            row.child.hide();
            tr.removeClass('shown');
        } else {
            // Open this row
            var content = tr.data('child-content');
            row.child(content).show();
            tr.addClass('shown');
        }
    });

    // Add event handlers for data source buttons
    $('#allJournals').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        loadTable('all_biology');
    });

    $('#generalist').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        loadTable('generalist');
    });

    $('#cancer').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        loadTable('cancer');
    });

    $('#development').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        loadTable('development');
    });

    $('#ecologyEvolution').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        loadTable('ecology_evolution');
    });

    $('#geneticsGenomics').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        loadTable('genetics_genomics');
    });

    $('#immunology').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        loadTable('immunology');
    });

    $('#molecularCellularBiology').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        loadTable('molecular_cellular_biology');
    });

    $('#neurosciences').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        loadTable('neurosciences');
    });

    $('#plants').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        loadTable('plants');
    });

    // Add event handlers for profit status filter buttons
    $('#allPublishers').on('click', function () {
        $('.profit-status-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            dataTable.column(3).search('').draw();

            // Update histogram based on filtered data
            const filteredData = dataTable.rows({search: 'applied'}).data().toArray();
            const distribution = calculateAPCDistribution(filteredData);
            renderHistogram(distribution);
        }
    });

    $('#forProfitPublishers').on('click', function () {
        $('.profit-status-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            dataTable.column(3).search('^For-profit$', true, false).draw();

            // Update histogram based on filtered data
            const filteredData = dataTable.rows({search: 'applied'}).data().toArray();
            const distribution = calculateAPCDistribution(filteredData);
            renderHistogram(distribution);
        }
    });

    $('#forProfitSocietyRunPublishers').on('click', function () {
        $('.profit-status-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            dataTable.column(3).search('^For-profit Society-Run$', true, false).draw();

            // Update histogram based on filtered data
            const filteredData = dataTable.rows({search: 'applied'}).data().toArray();
            const distribution = calculateAPCDistribution(filteredData);
            renderHistogram(distribution);
        }
    });


    $('#universityPressPublishers').on('click', function () {
        $('.profit-status-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            dataTable.column(3).search('^University Press$', true, false).draw();

            // Update histogram based on filtered data
            const filteredData = dataTable.rows({search: 'applied'}).data().toArray();
            const distribution = calculateAPCDistribution(filteredData);
            renderHistogram(distribution);
        }
    });

    $('#nonProfitPublishers').on('click', function () {
        $('.profit-status-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            dataTable.column(3).search('^Non-profit$', true, false).draw();

            // Update histogram based on filtered data
            const filteredData = dataTable.rows({search: 'applied'}).data().toArray();
            const distribution = calculateAPCDistribution(filteredData);
            renderHistogram(distribution);
        }
    });

    // Add event handlers for business model filter buttons
    $('#allBusinessModels').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            dataTable.column(4).search('').draw();

            // Update histogram based on filtered data
            const filteredData = dataTable.rows({search: 'applied'}).data().toArray();
            const distribution = calculateAPCDistribution(filteredData);
            renderHistogram(distribution);
        }
    });

    $('#diamondOABusinessModel').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            dataTable.column(4).search('Diamond OA', false, false).draw();

            // Update histogram based on filtered data
            const filteredData = dataTable.rows({search: 'applied'}).data().toArray();
            const distribution = calculateAPCDistribution(filteredData);
            renderHistogram(distribution);
        }
    });

    $('#goldOABusinessModel').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            dataTable.column(4).search('Gold OA', false, false).draw();

            // Update histogram based on filtered data
            const filteredData = dataTable.rows({search: 'applied'}).data().toArray();
            const distribution = calculateAPCDistribution(filteredData);
            renderHistogram(distribution);
        }
    });

    $('#oaBusinessModel').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            dataTable.column(4).search('^OA$', true, false).draw();

            // Update histogram based on filtered data
            const filteredData = dataTable.rows({search: 'applied'}).data().toArray();
            const distribution = calculateAPCDistribution(filteredData);
            renderHistogram(distribution);
        }
    });

    $('#hybridBusinessModel').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            dataTable.column(4).search('^Hybrid$', true, false).draw();

            // Update histogram based on filtered data
            const filteredData = dataTable.rows({search: 'applied'}).data().toArray();
            const distribution = calculateAPCDistribution(filteredData);
            renderHistogram(distribution);
        }
    });

    $('#subscriptionBusinessModel').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            dataTable.column(4).search('^Subscription$', true, false).draw();

            // Update histogram based on filtered data
            const filteredData = dataTable.rows({search: 'applied'}).data().toArray();
            const distribution = calculateAPCDistribution(filteredData);
            renderHistogram(distribution);
        }
    });

    // Function to calculate APC distribution
    function calculateAPCDistribution(data) {
        // Define bins for APC costs (0-1000, 1001-2000, etc.)
        const bins = [0, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000];
        const distribution = Array(bins.length - 1).fill(0);

        // Count journals in each bin
        data.forEach(row => {
            const apcValue = row[5].replace(/[^\d]/g, '');
            if (apcValue !== '') {
                const apc = parseInt(apcValue);
                for (let i = 0; i < bins.length - 1; i++) {
                    if (apc >= bins[i] && apc <= bins[i + 1]) {
                        distribution[i]++;
                        break;
                    }
                }
            }
        });

        return {bins, distribution};
    }

    // Function to render the histogram
    function renderHistogram(distribution, maxCount) {
        const histogramContainer = $('#apcHistogram');
        histogramContainer.empty();

        const {bins, distribution: counts} = distribution;
        const containerWidth = histogramContainer.width();
        const barWidth = containerWidth / (bins.length - 1);

        // Find the maximum count for scaling
        const maxValue = maxCount || Math.max(...counts, 1);

        // Create bars for each bin
        for (let i = 0; i < counts.length; i++) {
            const height = (counts[i] / maxValue) * 100;
            const bar = $('<div>')
                .css({
                    position: 'absolute',
                    left: (i * barWidth) + 'px',
                    bottom: '0',
                    width: (barWidth - 2) + 'px',
                    height: height + '%',
                    backgroundColor: '#3182ce',
                    borderRadius: '2px 2px 0 0',
                    opacity: '0.7'
                })
                .attr('title', counts[i] + ' journals with APC between ' + bins[i] + '€ and ' + bins[i + 1] + '€');

            // Add count label on top of the bar
            const label = $('<div>')
                .text(counts[i])
                .css({
                    position: 'absolute',
                    top: '-18px',
                    width: '100%',
                    textAlign: 'center',
                    fontSize: '10px',
                    color: '#4a5568'
                });

            if (counts[i] > 0) {
                bar.append(label);
            }

            histogramContainer.append(bar);
        }
    }

    // Add event handler for APC slider
    $('#apcSlider').on('input', function () {
        const maxAPC = $(this).val();
        $('#apcValue').text(maxAPC === '10000' ? 'All APC' : '≤ ' + maxAPC + ' €');

        if (dataTable) {
            // Custom filtering function for APC column
            $.fn.dataTable.ext.search.push(
                function (settings, data, dataIndex) {
                    if (maxAPC === '10000') return true; // Show all if slider is at max

                    const apcValue = data[5].replace(/[^\d]/g, ''); // Extract numeric value from APC column
                    if (apcValue === '') return true; // Show entries with no APC value

                    return parseInt(apcValue) <= parseInt(maxAPC);
                }
            );

            dataTable.draw();

            // Update histogram based on filtered data
            const filteredData = dataTable.rows({search: 'applied'}).data().toArray();
            const distribution = calculateAPCDistribution(filteredData);
            renderHistogram(distribution);

            // Remove the custom filter after drawing to avoid stacking multiple filters
            $.fn.dataTable.ext.search.pop();
        }
    });

    // Function to fetch CSV files based on the selected data source
    async function fetchCSVFiles(dataSource = 'all') {
        try {
            let csvFiles = [];

            // Determine which CSV files to load based on the data source
            if (dataSource === 'all_biology') {
                csvFiles = ['data/all_biology.csv']; // All journals
            } else if (dataSource === 'ecology_evolution') {
                csvFiles = ['data/ecology_evolution.csv']; // Ecology & Evolution
            } else if (dataSource === 'neurosciences') {
                csvFiles = ['data/neurosciences.csv']; // Neurosciences
            } else if (dataSource === 'cancer') {
                csvFiles = ['data/cancer.csv']; // Cancer
            } else if (dataSource === 'generalist') {
                csvFiles = ['data/generalist.csv']; // Generalist
            } else if (dataSource === 'development') {
                csvFiles = ['data/development.csv']; // Development
            } else if (dataSource === 'genetics_genomics') {
                csvFiles = ['data/genetics_genomics.csv']; // Genetics & Genomics
            } else if (dataSource === 'immunology') {
                csvFiles = ['data/immunology.csv']; // Immunology
            } else if (dataSource === 'molecular_cellular_biology') {
                csvFiles = ['data/molecular_cellular_biology.csv']; // Molecular & Cellular Biology
            } else if (dataSource === 'plants') {
                csvFiles = ['data/plants.csv']; // Plants
            }

            // Fetch and parse the selected CSV files
            const dataPromises = csvFiles.map(async (file) => {
                try {
                    const response = await fetch(file);
                    if (!response.ok) {
                        console.error(`Failed to fetch ${file}: ${response.statusText}`);
                        return {data: [], domains: []};
                    }
                    const csvText = await response.text();
                    return parseCSV(csvText);
                } catch (error) {
                    console.error(`Error processing ${file}:`, error);
                    return {data: [], domains: []};
                }
            });

            // Wait for all files to be fetched and parsed
            const allData = await Promise.all(dataPromises);

            // If only one file is loaded, return its data directly
            console.assert(csvFiles.length === 1)
            return allData[0];

        } catch (error) {
            console.error('Error fetching CSV files:', error);
            return {data: [], domains: []};
        }
    }

    // Function to load and initialize the table with data from the selected source
    async function loadTable(dataSource = 'all_biology') {
        try {
            // Clear existing table if it exists
            if (dataTable) {
                dataTable.destroy();
                $('#domainFilters').empty();
            }

            // Reset profit status filters
            $('.profit-status-button').removeClass('active');
            $('#allPublishers').addClass('active');

            // Reset business model filters
            $('.business-model-button').removeClass('active');
            $('#allBusinessModels').addClass('active');

            // Reset APC slider
            $('#apcSlider').val(10000);
            $('#apcValue').text('All APC');

            // Show loading indicator
            $('#journalTable').parent().append('<p id="loading-indicator">Loading data...</p>');

            // Fetch data from the selected source
            const {data: tableData, domains} = await fetchCSVFiles(dataSource);

            // Remove loading indicator
            $('#loading-indicator').remove();

            if (tableData && tableData.length > 0) {
                dataTable = $('#journalTable').DataTable({
                    data: tableData,
                    scrollX: false, // Disable horizontal scrolling to allow responsive wrapping
                    paging: false, // Disable pagination to show all items
                    searching: true,
                    ordering: true,
                    info: true,
                    dom: 'ift', // i=info, f=filtering, t=table (places info above table)
                    responsive: {
                        details: {
                            display: $.fn.dataTable.Responsive.display.childRow
                        },
                        breakpoints: [
                            {name: 'desktop', width: Infinity},
                            {name: 'tablet', width: 1024},
                            {name: 'phone', width: 480}
                        ]
                    },
                    columnDefs: [
                        // Format the publisher type column (3)
                        {
                            targets: [3],
                            render: function (data, type, row) {
                                if (type === 'display' || type === 'filter') {
                                    if (data === 'For-profit') return 'For-profit';
                                    if (data === 'Non-profit') return 'Non-profit';
                                    if (data === 'University Press') return 'University Press';
                                    return data;
                                }
                                return data;
                            }
                        },
                        // Make the first column (Journal) expandable to show details
                        {
                            targets: 0,
                            className: 'details-control'
                        }
                    ],
                    language: {
                        info: "Displaying all _TOTAL_ journals",
                        infoEmpty: "No journals available",
                        emptyTable: "No journal data available",
                        search: ""
                    },
                    initComplete: function () {
                        var table = this.api();
                        var domainFiltersContainer = $('#domainFilters');

                        // Add placeholder to search input
                        $('.dataTables_filter input').attr('placeholder', 'Search journals...');

                        // Add event handler for search box
                        $('.dataTables_filter input').on('keyup', function () {
                            // Update histogram based on filtered data
                            const filteredData = table.rows({search: 'applied'}).data().toArray();
                            const distribution = calculateAPCDistribution(filteredData);
                            renderHistogram(distribution);
                        });

                        // Initialize the APC histogram
                        const allData = table.rows().data().toArray();
                        const distribution = calculateAPCDistribution(allData);
                        renderHistogram(distribution);

                        // Count journals by publisher type and business model
                        const publisherTypeCounts = {
                            'For-profit': 0,
                            'Non-profit': 0,
                            'University Press': 0
                        };

                        const businessModelCounts = {
                            'Diamond OA': 0,
                            'Gold OA': 0,
                            'OA': 0,
                            'Hybrid': 0,
                            'Subscription': 0
                        };

                        allData.forEach(row => {
                            const publisherType = row[3];
                            const businessModel = row[4];

                            if (publisherType in publisherTypeCounts) {
                                publisherTypeCounts[publisherType]++;
                            }

                            if (businessModel in businessModelCounts) {
                                businessModelCounts[businessModel]++;
                            }
                        });

                        // Update publisher type buttons with counts
                        $('#allPublishers').text('All Publishers (' + allData.length + ')');
                        $('#forProfitPublishers').text('For-profit (' + publisherTypeCounts['For-profit'] + ')');
                        $('#nonProfitPublishers').text('Non-profit (' + publisherTypeCounts['Non-profit'] + ')');
                        $('#universityPressPublishers').text('University Press (' + publisherTypeCounts['University Press'] + ')');

                        // Update business model buttons with counts
                        $('#allBusinessModels').text('All Business Models (' + allData.length + ')');
                        $('#diamondOABusinessModel').text('Diamond OA (' + businessModelCounts['Diamond OA'] + ')');
                        $('#goldOABusinessModel').text('Gold OA (' + businessModelCounts['Gold OA'] + ')');
                        $('#oaBusinessModel').text('OA (' + businessModelCounts['OA'] + ')');
                        $('#hybridBusinessModel').text('Hybrid (' + businessModelCounts['Hybrid'] + ')');
                        $('#subscriptionBusinessModel').text('Subscription (' + businessModelCounts['Subscription'] + ')');

                        // Add "Show All" button
                        var showAllButton = $('<button class="domain-filter-button">SHOW ALL</button>')
                            .on('click', function () {
                                // Clear search for the Field column (1)
                                table.column(1).search('');
                                table.draw();
                                domainFiltersContainer.find('.domain-filter-button').removeClass('active');
                                $(this).addClass('active');

                                // Update histogram based on filtered data
                                const filteredData = table.rows({search: 'applied'}).data().toArray();
                                const distribution = calculateAPCDistribution(filteredData);
                                renderHistogram(distribution);
                            });
                        domainFiltersContainer.append(showAllButton);

                        // Add domain-specific filter buttons using the dynamically extracted domains
                        domains.forEach(function (domainName) {
                            var button = $('<button class="domain-filter-button">' + domainName + '</button>')
                                .on('click', function () {
                                    var isActive = $(this).hasClass('active');

                                    // Clear search for the Field column
                                    table.column(1).search('');
                                    domainFiltersContainer.find('.domain-filter-button').removeClass('active');

                                    if (isActive) {
                                        // If button was active, clicking again means show all
                                        showAllButton.addClass('active');
                                    } else {
                                        // If button was not active, make it active and apply its filter
                                        table.column(1).search('^' + domainName + '$', true, false); // Exact match for the domain
                                        $(this).addClass('active');
                                    }
                                    table.draw();

                                    // Update histogram based on filtered data
                                    const filteredData = table.rows({search: 'applied'}).data().toArray();
                                    const distribution = calculateAPCDistribution(filteredData);
                                    renderHistogram(distribution);
                                });
                            domainFiltersContainer.append(button);
                        });

                        // Set "Show All" as active by default
                        showAllButton.addClass('active');
                    },

                    // Add child row display functionality for journal details
                    rowCallback: function (row, data, index) {
                        // Apply row coloring based on publisher type (column 3)
                        var publisherType = data[3]; // Get the publisher type value
                        if (publisherType === 'For-profit') {
                            $(row).addClass('for-profit-row');
                        } else if (publisherType === 'For-profit Society-run') {
                            $(row).addClass('for-profit-society-run-row');
                        } else if (publisherType === 'University Press') {
                            $(row).addClass('university-press-row');
                        } else if (publisherType === 'Non-profit') {
                            $(row).addClass('non-profit-row');
                        }

                        // Create journal details HTML
                        var journalDetails = '<div class="domain-details"><ul>';

                        // Add institution
                        if (data[7]) {
                            journalDetails += '<li><span class="domain-name">Institution:</span> <span>' + data[7] + '</span></li>';
                        }

                        // Add institution type
                        if (data[8]) {
                            journalDetails += '<li><span class="domain-name">Institution type:</span> <span>' + data[8] + '</span></li>';
                        }

                        // Add website with link
                        if (data[9]) {
                            journalDetails += '<li><span class="domain-name">Website:</span> <a href="' + data[9] + '" target="_blank">' + data[9] + '</a></li>';
                        }

                        // Add country
                        if (data[6]) {
                            journalDetails += '<li><span class="domain-name">Country:</span> <span>' + data[6] + '</span></li>';
                        }

                        // Add Scimago Rank
                        if (data[10]) {
                            journalDetails += '<li><span class="domain-name">SCIMAGO rank:</span> <span>' + data[10] + '</span></li>';
                        }

                        // Add PCI partner
                        if (data[11]) {
                            journalDetails += '<li><span class="domain-name">PCI partner:</span> <span>' + data[11] + '</span></li>';
                        }

                        journalDetails += '</ul></div>';

                        // Store the journal details in the row's data
                        $(row).data('child-content', journalDetails);
                    }
                });
            } else if (tableData) { // tableData is an empty array
                $('#journalTable').parent().append('<p>No data found in CSV after parsing headers.</p>');
            }
        } catch (error) {
            console.error('Error loading or processing CSV files:', error);
            $('#journalTable').parent().append('<p style="color:red;">Could not load data. Please ensure CSV files exist in the data folder and check the browser console for errors.</p>');
        }
    }

    // Modal functionality
    const modal = $('#aboutModal');
    const modalContent = $('.modal-content');
    const closeModalButton = $('.close-modal');
    const modalTriggers = $('.modal-trigger');

    // Function to open the modal
    function openModal() {
        modal.addClass('show');
        // Prevent scrolling of the body when modal is open
        $('body').css('overflow', 'hidden');
    }

    // Function to close the modal
    function closeModal() {
        modal.removeClass('show');
        // Re-enable scrolling of the body
        $('body').css('overflow', '');
    }

    // Event listeners for opening the modal
    modalTriggers.on('click', function () {
        openModal();
    });

    // Event listeners for closing the modal
    closeModalButton.on('click', function () {
        closeModal();
    });

    // Close modal when clicking outside the modal content
    modal.on('click', function (event) {
        if ($(event.target).is(modal)) {
            closeModal();
        }
    });

    // Close modal when pressing Escape key
    $(document).on('keydown', function (event) {
        if (event.key === 'Escape' && modal.hasClass('show')) {
            closeModal();
        }
    });

    $('#copyBox').on('click', function () {
        // Get the text to copy
        const textToCopy = $('#copyContent').text();

        // Copy to clipboard
        navigator.clipboard.writeText(textToCopy)
            .then(() => {
                // Show tooltip
                $('#copyTooltip').css('opacity', '1');

                // Hide tooltip after 2 seconds
                setTimeout(() => {
                    $('#copyTooltip').css('opacity', '0');
                }, 2000);
            })
            .catch(err => {
                console.error('Failed to copy: ', err);
            });
    });
    // Load the table with all journals by default
    loadTable('generalist');
});
