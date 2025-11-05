function formatDomainName(domain) {
    // Capitalize the first letter of each word in the domain name
    return domain.replace(/_/g, ' ').split(' ').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
}

function parseCSV(csvText) {
    // We know the exact column order in the CSV:
    // 0: Journal, 1: Field, 2: Publisher, 3: Publisher type, 4: Business model,
    // 5: Institution, 6: Institution type, 7: Country, 8: Website, 9: APC Euros,
    // 10: Scimago Rank, 11: PCI partner
    const lines = csvText.split('\n');
    const data = [];
    const domains = new Set();

    if (!lines.length) return { data: [], domains: [] };

    // Render table headers (displayed columns only)
    const finalHeadersText = [
        'Journal',
        'Field',
        'Publisher',
        'Publisher type',
        'Business model',
        'APC (€)'
    ];
    const headerRow = $('#journalTable thead tr');
    headerRow.empty();
    finalHeadersText.forEach(headerText => headerRow.append($('<th>').text(formatDomainName(headerText))));

    // Helper to split a CSV line into fields, handling quotes and escaped quotes
    function splitCSVLine(line) {
        const result = [];
        let current = '';
        let inQuotes = false;
        for (let i = 0; i < line.length; i++) {
            const ch = line[i];
            if (ch === '"') {
                if (inQuotes && i + 1 < line.length && line[i + 1] === '"') {
                    current += '"';
                    i++; // skip escaped quote
                } else {
                    inQuotes = !inQuotes;
                }
            } else if (ch === ',' && !inQuotes) {
                result.push(current);
                current = '';
            } else {
                current += ch;
            }
        }
        result.push(current);
        // Trim and strip surrounding quotes
        return result.map(f => f.trim().replace(/^"|"$/g, ''));
    }

    // Skip header line (assumed present) and parse rows
    for (let i = 1; i < lines.length; i++) {
        const raw = lines[i].trim();
        if (!raw) continue; // skip empty lines

        const cols = splitCSVLine(raw);
        if (!cols.length || !cols[0]) continue; // need at least Journal

        // Collect Field values for domain filters
        if (cols[1]) domains.add(cols[1]);

        // Build the row in the display order for DataTables (6 visible + extras kept for details)
        const row = [
            cols[0] || '', // Journal
            cols[1] || '', // Field
            cols[2] || '', // Publisher
            cols[3] || '', // Publisher type
            cols[4] || '', // Business model
            cols[9] || '', // APC Euros -> displayed as APC (€)
            cols[7] || '', // Country
            cols[5] || '', // Institution
            cols[6] || '', // Institution type
            cols[8] || '', // Website
            cols[10] || '', // Scimago Rank
            cols[11] || ''  // PCI partner
        ];

        data.push(row);
    }

    return { data, domains: Array.from(domains).sort() };
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
        loadTable('data/all_biology.csv');
    });

    $('#generalist').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        loadTable('data/generalist.csv');
    });

    $('#cancer').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        loadTable('data/cancer.csv');
    });

    $('#development').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        loadTable('data/development.csv');
    });

    $('#ecologyEvolution').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        loadTable('data/ecology_evolution.csv');
    });

    $('#geneticsGenomics').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        loadTable('data/genetics_genomics.csv');
    });

    $('#immunology').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        loadTable('data/immunology.csv');
    });

    $('#molecularCellularBiology').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        loadTable('data/molecular_cellular_biology.csv');
    });

    $('#neurosciences').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        loadTable('data/neurosciences.csv');
    });

    $('#plants').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        loadTable('data/plants.csv');
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
            dataTable.column(3).search('For-profit', false, false).draw();

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
            dataTable.column(3).search('University Press', false, false).draw();

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
            dataTable.column(3).search('Non-profit', false, false).draw();

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

    // Function to fetch CSV file (single database file)
    async function fetchCSVFile(csvFile) {
        try {
            const response = await fetch(csvFile);
            if (!response.ok) {
                console.error(`Failed to fetch ${csvFile}: ${response.statusText}`);
                return { data: [], domains: [] };
            }
            const csvText = await response.text();
            return parseCSV(csvText);
        } catch (error) {
            console.error('Error fetching CSV file:', error);
            return { data: [], domains: [] };
        }
    }

    // Function to load and initialize the table with data from the selected source
    async function loadTable(dataSource = 'data/all_biology.csv') {
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

            // Fetch data from the selected source (single file)
            const {data: tableData, domains} = await fetchCSVFile(dataSource);

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
                            'For-profit on behalf of a society': 0,
                            'Non-profit': 0,
                            'University Press': 0,
                            'University Press on behalf of a society': 0
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
                        $('#forProfitPublishers').text('For-profit (' + (publisherTypeCounts['For-profit'] + publisherTypeCounts['For-profit on behalf of a society']) + ')');
                        $('#nonProfitPublishers').text('Non-profit (' + publisherTypeCounts['Non-profit'] + ')');
                        $('#universityPressPublishers').text('University Press (' + (publisherTypeCounts['University Press'] + publisherTypeCounts['University Press on behalf of a society']) + ')');

                        // Update business model buttons with counts
                        let d;
                        $('#allBusinessModels').text('All Business Models (' + allData.length + ')');
                        if (businessModelCounts['Diamond OA'] === 0) {
                            $('#diamondOABusinessModel').addClass('hidden');
                        } else {
                            d = $('#diamondOABusinessModel')
                            d.removeClass('hidden')
                            d.text('Diamond OA (' + businessModelCounts['Diamond OA'] + ')');
                        }
                        if (businessModelCounts['Gold OA'] === 0) {
                            $('#goldOABusinessModel').addClass('hidden');
                        } else {
                            d = $('#goldOABusinessModel')
                            d.removeClass('hidden')
                            d.text('Gold OA (' + businessModelCounts['Gold OA'] + ')');
                        }
                        if (businessModelCounts['OA'] === 0) {
                            $('#oaBusinessModel').addClass('hidden');
                        } else {
                            d = $('#oaBusinessModel')
                            d.removeClass('hidden')
                            d.text('OA (' + businessModelCounts['OA'] + ')');
                        }
                        if (businessModelCounts['Hybrid'] === 0) {
                            $('#hybridBusinessModel').addClass('hidden');
                        } else {
                            d = $('#hybridBusinessModel')
                            d.removeClass('hidden')
                            d.text('Hybrid (' + businessModelCounts['Hybrid'] + ')');
                        }
                        if (businessModelCounts['Subscription'] === 0) {
                            $('#subscriptionBusinessModel').addClass('hidden');
                        } else {
                            d = $('#subscriptionBusinessModel')
                            d.removeClass('hidden')
                            d.text('Subscription (' + businessModelCounts['Subscription'] + ')');
                        }

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
                        } else if (publisherType.includes('For-profit')) {
                            $(row).addClass('for-profit-society-run-row');
                        } else if (publisherType === 'University Press') {
                            $(row).addClass('university-press-row');
                        } else if (publisherType.includes('University Press')) {
                            $(row).addClass('university-press-society-run-row');
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
    loadTable('data/generalist.csv');
});
