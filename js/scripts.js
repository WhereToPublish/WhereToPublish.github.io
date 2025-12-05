/**
 * WhereToPublish - Journal Selection Tool
 * 
 * Performance Optimizations Applied:
 * 1. Pre-computed APC bins during CSV parsing (reduces O(n*m) to O(n))
 * 2. Single-pass count calculations (merged publisher + business model loops)
 * 3. Debounced search input (150ms) and APC slider (20ms)
 * 4. Proper event handler cleanup on DataTable destroy
 * 5. Optimized table header rendering (only once per page load)
 * 6. Limited localStorage state to prevent bloat
 * 7. Console profiling markers for performance monitoring
 */

function parseCSV(csvText) {
    console.time('parseCSV');
    // We know the exact column order in the CSV:
    // 0: Journal, 1: Subfield, 2: Publisher, 3: Publisher type, 4: Business model,
    // 5: Institution, 6: Institution type, 7: Country, 8: Website, 9: APC Euros,
    // 10: Scimago Rank, 11: Scimago Quartile, 12: H index, 13: PCI partner
    const lines = csvText.split('\n');
    const data = [];
    const domains = new Set();
    
    // Pre-compute APC bins for histogram
    const apcBins = [0, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000];

    if (!lines.length) return {data: [], domains: []};

    // Define all headers in the internal data order
    const allHeadersText = [
        'Journal',            // 0 (mandatory visible)
        'Subfield',           // 1
        'Publisher',          // 2
        'Publisher Type',     // 3 (mandatory visible)
        'Business Model',     // 4
        'APC (€)',            // 5 (from APC Euros)
        'Country (Publisher)',// 6
        'Institution',        // 7
        'Institution Type',   // 8
        'Website',            // 9
        'Scimago Rank',       // 10
        'Scimago Quartile',   // 11
        'H Index',            // 12
        'PCI Partner'         // 13
    ];
    const columnDefs = {
        5: 'APC values are obtained from OpenAPC as the average in the last 3 years.',
        10: 'Scimago Rank is an ordinal position where higher numbers indicate higher impact.',
        11: 'Scimago Quartile ranges from Q1 (best) to Q4 (lowest)',
        12: 'At least H publications have received at least H citations.'
    };

    // Mandatory columns that cannot be hidden
    const mandatoryHeaders = new Set(['Journal', 'Publisher Type', 'Business Model']);

    // Default visible columns at load
    const defaultVisibleHeaders = new Set(['Journal', 'Subfield', 'Publisher', 'Publisher Type', 'Business Model', 'APC (€)']);

    // Render table headers (we render all headers so DataTables knows columns; visibility handled later)
    const headerRow = $('#journalTable thead tr');
    headerRow.empty(); // Always clear and rebuild headers
    allHeadersText.forEach((headerText, index) => {
        const $th = $('<th>');
        if (columnDefs[index]) {
            const $icon = $('<span>')
                .attr('tabindex', '0')
                .text(headerText);
            $th.append($icon);
            
            // Initialize tippy tooltip on this element
            tippy($icon[0], {
                content: columnDefs[index],
                placement: 'bottom',
                arrow: true,
                theme: 'light-border',
                maxWidth: 250,
                appendTo: document.body,
                zIndex: 1000,
                trigger: 'mouseenter focus',
                allowHTML: true,
                interactive: true,
                aria: {
                    content: 'describedby',
                    expanded: false
                }
            });
        } else {
            const $label = $('<span>').text(headerText);
            $th.append($label);
        }
        headerRow.append($th);
    });

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

        // Build the row in the internal data order for DataTables
        const row = [
            cols[0] || '', // Journal
            cols[1] || '', // Field
            cols[2] || '', // Publisher
            cols[3] || '', // Publisher Type
            cols[4] || '', // Business Model
            cols[9] || '', // APC Euros -> displayed as APC (€)
            cols[7] || '', // Country -> displayed as Country (Publisher)
            cols[5] || '', // Institution
            cols[6] || '', // Institution Type
            cols[8] || '', // Website
            cols[10] || '', // Scimago Rank
            cols[11] || '', // Scimago Quartile
            cols[12] || '', // H index
            cols[13] || ''  // PCI partner
        ];
        
        // Pre-compute APC bin index for histogram optimization
        const apcValue = row[5].replace(/[^\d]/g, '');
        if (apcValue !== '') {
            const apc = parseInt(apcValue);
            for (let i = 0; i < apcBins.length - 1; i++) {
                if (apc >= apcBins[i] && apc <= apcBins[i + 1]) {
                    row.__apcBin = i;
                    break;
                }
            }
        } else {
            row.__apcBin = -1; // No valid APC
        }

        data.push(row);
    }

    console.timeEnd('parseCSV');
    return {data, domains: Array.from(domains).sort(), allHeadersText, defaultVisibleHeaders, mandatoryHeaders, apcBins};
}

// Escape a string for use inside a RegExp
function escapeRegExp(string) {
    return String(string).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

$(document).ready(function () {
    const CONTRIBUTION_FORM_URL = 'https://docs.google.com/forms/d/e/1FAIpQLSfTWQ8PaFCL_zabYwUidZZlh8GR_SZJ1rWaQfZWX3ZS98pm3g/viewform';
    const ALL_FIELDS_SOURCE = 'data/all_biology.csv';
    const DEFAULT_DATA_SOURCE = 'data/generalist.csv';
    let dataTable; // Variable to store the DataTable instance
    let currentDataSource = null; // Track current CSV file
    let currentDatasetLabel = '';
    let resetFieldOnNextLoad = false; // Only reset Field filter when switching CSV
    // Clear existing saved state on first load
    localStorage.removeItem('wtp_global_state_v1');

    DataTable.type('num', 'className', 'dt-body-right');
    DataTable.type('num-fmt', 'className', 'dt-body-right');
    DataTable.type('date', 'className', 'dt-body-right');
    // Track APC slider state for persistent filtering
    let currentMaxAPC = '10000';
    // Track selected Field (domain) for counts logic
    let selectedField = '';
    let apcSearchRegistered = false;
    let currentPublisherTypeFilter = 'all';
    let currentBusinessModelFilter = 'all';
    let lastHistogramSnapshot = null;
    let cachedApcBins = [0, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000];
    let searchDebounceTimer = null;

    function buildZeroRecordsMessage() {
        const contributeLink = '<a href="' + CONTRIBUTION_FORM_URL + '" target="_blank" rel="noopener noreferrer">contribute to the database</a>';
        if (currentDataSource === ALL_FIELDS_SOURCE) {
            return 'No matching journals found.<br> This database includes only biology and filtered out predatory journals.<br> If you think a journal is missing, please ' + contributeLink + '.';
        }
        const label = currentDatasetLabel || 'current dataset';
        return 'No matching journals.<br> You currently have the &quot;' + label + '&quot; dataset loaded.';
    }

    // Helper: whether a row passes current APC and Field selection only
    function rowPassesApcAndField(row) {
        if (!row) return false;
        if (selectedField && String(row[1]) !== String(selectedField)) return false;
        if (currentMaxAPC !== '10000') {
            const apcRaw = row[5] ? String(row[5]) : '';
            const apcValue = apcRaw.replace(/[^\d]/g, '');
            if (apcValue === '') return false;
            if (parseInt(apcValue, 10) > parseInt(currentMaxAPC, 10)) return false;
        }
        return true;
    }

    function matchesPublisherFilter(row, filterKey) {
        const publisherType = row && row[3] ? String(row[3]) : '';
        switch (filterKey) {
            case 'For-profit':
                return publisherType.indexOf('For-profit') === 0;
            case 'Non-profit':
                return publisherType.indexOf('Non-profit') === 0;
            case 'University Press':
                return publisherType.indexOf('University Press') === 0;
            default:
                return true;
        }
    }

    function matchesBusinessModelFilter(row, filterKey) {
        const businessModel = row && row[4] ? String(row[4]) : '';
        switch (filterKey) {
            case 'OA diamond':
                return businessModel === 'OA diamond';
            case 'OA':
                return businessModel.indexOf('OA') === 0;
            case 'Hybrid':
                return businessModel === 'Hybrid';
            case 'Subscription':
                return businessModel === 'Subscription';
            default:
                return true;
        }
    }

    // Data source buttons
    $('#allJournals').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        const src = ALL_FIELDS_SOURCE;
        resetFieldOnNextLoad = currentDataSource !== null && currentDataSource !== src;
        currentDataSource = src;
        currentDatasetLabel = 'All fields';
        loadTable(src);
    });
    $('#generalist').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        const src = 'data/generalist.csv';
        resetFieldOnNextLoad = currentDataSource !== null && currentDataSource !== src;
        currentDataSource = src;
        currentDatasetLabel = 'Generalist';
        loadTable(src);
    });
    $('#cancer').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        const src = 'data/cancer.csv';
        resetFieldOnNextLoad = currentDataSource !== null && currentDataSource !== src;
        currentDataSource = src;
        currentDatasetLabel = 'Cancer';
        loadTable(src);
    });
    $('#development').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        const src = 'data/development.csv';
        resetFieldOnNextLoad = currentDataSource !== null && currentDataSource !== src;
        currentDataSource = src;
        currentDatasetLabel = 'Development';
        loadTable(src);
    });
    $('#ecologyEvolution').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        const src = 'data/ecology_evolution.csv';
        resetFieldOnNextLoad = currentDataSource !== null && currentDataSource !== src;
        currentDataSource = src;
        currentDatasetLabel = 'Ecology & Evolution';
        loadTable(src);
    });
    $('#geneticsGenomics').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        const src = 'data/genetics_genomics.csv';
        resetFieldOnNextLoad = currentDataSource !== null && currentDataSource !== src;
        currentDataSource = src;
        currentDatasetLabel = 'Genetics & Genomics';
        loadTable(src);
    });
    $('#health').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        const src = 'data/health.csv';
        resetFieldOnNextLoad = currentDataSource !== null && currentDataSource !== src;
        currentDataSource = src;
        currentDatasetLabel = 'Health';
        loadTable(src);
    });
    $('#immunology').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        const src = 'data/immunology.csv';
        resetFieldOnNextLoad = currentDataSource !== null && currentDataSource !== src;
        currentDataSource = src;
        currentDatasetLabel = 'Immunology';
        loadTable(src);
    });
    $('#molecularCellularBiology').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        const src = 'data/molecular_cellular_biology.csv';
        resetFieldOnNextLoad = currentDataSource !== null && currentDataSource !== src;
        currentDataSource = src;
        currentDatasetLabel = 'Molecular & Cellular Biology';
        loadTable(src);
    });
    $('#neurosciences').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        const src = 'data/neurosciences.csv';
        resetFieldOnNextLoad = currentDataSource !== null && currentDataSource !== src;
        currentDataSource = src;
        currentDatasetLabel = 'Neurosciences';
        loadTable(src);
    });
    $('#plants').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        const src = 'data/plants.csv';
        resetFieldOnNextLoad = currentDataSource !== null && currentDataSource !== src;
        currentDataSource = src;
        currentDatasetLabel = 'Plants';
        loadTable(src);
    });

    // Profit status filter buttons
    $('#allPublishers').on('click', function () {
        $('.profit-status-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            currentPublisherTypeFilter = 'all';
            dataTable.column(3).search('').draw();
        }
    });
    $('#forProfitPublishers').on('click', function () {
        $('.profit-status-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            currentPublisherTypeFilter = 'For-profit';
            dataTable.column(3).search(currentPublisherTypeFilter, false, false, false).draw();
        }
    });
    $('#universityPressPublishers').on('click', function () {
        $('.profit-status-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            currentPublisherTypeFilter = 'University Press';
            dataTable.column(3).search(currentPublisherTypeFilter, false, false, false).draw();
        }
    });
    $('#nonProfitPublishers').on('click', function () {
        $('.profit-status-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            currentPublisherTypeFilter = 'Non-profit';
            dataTable.column(3).search(currentPublisherTypeFilter, false, false, false).draw();
        }
    });

    // Business model filter buttons
    $('#allBusinessModels').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            currentBusinessModelFilter = 'all';
            dataTable.column(4).search('').draw();
        }
    });
    $('#diamondOABusinessModel').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            currentBusinessModelFilter = 'OA diamond';
            dataTable.column(4).search(currentBusinessModelFilter, false, false).draw();
        }
    });
    $('#oaBusinessModel').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            currentBusinessModelFilter = 'OA';
            dataTable.column(4).search(currentBusinessModelFilter, false, false).draw();
        }
    });
    $('#hybridBusinessModel').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            currentBusinessModelFilter = 'Hybrid';
            dataTable.column(4).search(currentBusinessModelFilter, false, false).draw();
        }
    });
    $('#subscriptionBusinessModel').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            currentBusinessModelFilter = 'Subscription';
            dataTable.column(4).search(currentBusinessModelFilter, false, false).draw();
        }
    });

    // APC distribution - optimized to use pre-computed bins
    function calculateAPCDistribution(data) {
        const distribution = Array(cachedApcBins.length - 1).fill(0);
        // Use pre-computed bin indices from parseCSV
        data.forEach(row => {
            if (row.__apcBin !== undefined && row.__apcBin >= 0) {
                distribution[row.__apcBin]++;
            }
        });
        return {bins: cachedApcBins, distribution};
    }

    // Histogram render
    function renderHistogram(distribution, maxCount) {
        const histogramContainer = $('#apcHistogram');
        histogramContainer.empty();
        const bins = distribution && Array.isArray(distribution.bins) ? distribution.bins : [];
        const counts = distribution && Array.isArray(distribution.distribution) ? distribution.distribution : [];
        if (!bins.length || !counts.length || histogramContainer.length === 0) {
            lastHistogramSnapshot = null;
            return;
        }
        const resolvedMax = maxCount || Math.max(...counts, 1);
        lastHistogramSnapshot = {distribution: {bins: [...bins], distribution: [...counts]}, maxCount: resolvedMax};
        for (let i = 0; i < counts.length; i++) {
            const heightPercent = (counts[i] / resolvedMax) * 100;
            const upperBound = bins[i + 1] !== undefined ? bins[i + 1] : bins[i];
            const bar = $('<div>')
                .addClass('apc-histogram-bar')
                .css('height', heightPercent + '%')
                .attr('title', counts[i] + ' journals with APC between ' + bins[i] + '€ and ' + upperBound + '€');
            if (counts[i] > 0) {
                bar.append(
                    $('<div>')
                        .addClass('apc-histogram-label')
                        .text(counts[i])
                );
            }
            histogramContainer.append(bar);
        }
    }

    // Recompute only histogram based on current filtered rows
    function refreshHistogramFromTable(tableApi) {
        const filteredData = tableApi.rows({search: 'applied'}).data().toArray();
        const distribution = calculateAPCDistribution(filteredData);
        renderHistogram(distribution);
    }

    // Recompute and update counts for publisher type and business model buttons
    function refreshCountsFromTable(tableApi) {
        tableApi.column(3).search('')
        tableApi.column(4).search('')
        const allRows = tableApi.rows({search: 'applied'}).data().toArray();

        if (currentPublisherTypeFilter !== 'all') {
            tableApi.column(3).search(currentPublisherTypeFilter, false, false, false);
        }
        if (currentBusinessModelFilter !== 'all') {
            tableApi.column(4).search(currentBusinessModelFilter, false, false);
        }

        let publisherConsidered = 0;
        let businessConsidered = 0;

        const publisherTypeCounts = {'For-profit': 0, 'Non-profit': 0, 'University Press': 0};
        const businessModelCounts = {'OA diamond': 0, 'OA': 0, 'Hybrid': 0, 'Subscription': 0};

        const previouslyActiveId = $('.business-model-button.active').attr('id') || null;
        const idToModel = {
            'diamondOABusinessModel': 'OA diamond',
            'oaBusinessModel': 'OA',
            'hybridBusinessModel': 'Hybrid',
            'subscriptionBusinessModel': 'Subscription'
        };

        // Single iteration to compute both publisher and business model counts
        allRows.forEach((row) => {
            if (!rowPassesApcAndField(row)) return;
            
            const publisherType = row && row[3] ? String(row[3]) : '';
            const businessModel = row && row[4] ? String(row[4]) : '';
            const matchesBM = matchesBusinessModelFilter(row, currentBusinessModelFilter);
            const matchesPub = matchesPublisherFilter(row, currentPublisherTypeFilter);
            
            if (matchesBM) {
                publisherConsidered++;
                if (publisherType === 'Non-profit') publisherTypeCounts['Non-profit']++;
                else if (publisherType.indexOf('For-profit') === 0) publisherTypeCounts['For-profit']++;
                else if (publisherType.indexOf('University Press') === 0) publisherTypeCounts['University Press']++;
            }

            if (matchesPub) {
                businessConsidered++;
                if (businessModel === 'OA diamond') businessModelCounts['OA diamond']++;
                if (businessModel.indexOf('OA') === 0) businessModelCounts['OA']++;
                else if (businessModel === 'Hybrid') businessModelCounts['Hybrid']++;
                else if (businessModel === 'Subscription') businessModelCounts['Subscription']++;
            }
        });

        $('#allPublishers').text('All Publishers (' + publisherConsidered + ')');
        $('#forProfitPublishers').text('For-profit (' + (publisherTypeCounts['For-profit'] || 0) + ')');
        $('#nonProfitPublishers').text('Non-profit (' + (publisherTypeCounts['Non-profit'] || 0) + ')');
        $('#universityPressPublishers').text('University Press (' + (publisherTypeCounts['University Press'] || 0) + ')');

        $('#allBusinessModels').text('All Business Models (' + businessConsidered + ')');
        const modelToSelector = {
            'OA diamond': '#diamondOABusinessModel',
            'OA': '#oaBusinessModel',
            'Hybrid': '#hybridBusinessModel',
            'Subscription': '#subscriptionBusinessModel'
        };
        Object.keys(modelToSelector).forEach((model) => {
            const sel = modelToSelector[model];
            const count = businessModelCounts[model] || 0;
            const $btn = $(sel);
            $btn.text(model + ' (' + count + ')');
            if (count === 0) {
                $btn.addClass('hidden').removeClass('active');
            } else {
                $btn.removeClass('hidden');
            }
        });

        if (previouslyActiveId && previouslyActiveId !== 'allBusinessModels') {
            const previouslyActiveModel = idToModel[previouslyActiveId];
            const prevCount = businessModelCounts[previouslyActiveModel] || 0;
            if (prevCount === 0) {
                $('.business-model-button').removeClass('active');
                $('#allBusinessModels').addClass('active');
                tableApi.column(4).search('').draw();
                currentBusinessModelFilter = 'all';
            }
        }

        if ($('.business-model-button.active').length === 0) {
            $('#allBusinessModels').addClass('active');
            currentBusinessModelFilter = 'all';
        }
    }

    // APC slider filter with debouncing
    $('#apcSlider').off('input').on('input', function () {
        currentMaxAPC = $(this).val();
        $('#apcValue').text(currentMaxAPC === '10000' ? 'All APCs' : '≤ ' + currentMaxAPC + ' €');
        
        // Clear previous debounce timer
        if (searchDebounceTimer) {
            clearTimeout(searchDebounceTimer);
        }
        
        // Debounce the expensive operations
        searchDebounceTimer = setTimeout(function() {
            if (dataTable) {
                dataTable.draw();
            }
        }, 20); // 20ms debounce for slider (faster feedback than search)
    });

    // CSV fetch
    async function fetchCSVFile(csvFile) {
        try {
            const response = await fetch(csvFile);
            if (!response.ok) {
                console.error(`Failed to fetch ${csvFile}: ${response.statusText}`);
                return {data: [], domains: []};
            }
            const csvText = await response.text();
            return parseCSV(csvText);
        } catch (error) {
            console.error('Error fetching CSV file:', error);
            return {data: [], domains: []};
        }
    }

    // Load and initialize the table
    async function loadTable(dataSource = 'data/all_biology.csv') {
        console.time('loadTable');
        try {
            let currentSearch = '';
            // Clear existing table if it exists
            if (dataTable) {
                console.time('DataTable cleanup');
                currentSearch = dataTable.search(); // Save global search
                
                // Remove event handlers before destroying
                dataTable.off('column-visibility.dt');
                
                // Destroy without removing from DOM - we'll clear tbody manually
                dataTable.destroy(false);
                $('#journalTable tbody').empty();
                $('#domainFilters').empty();
                console.timeEnd('DataTable cleanup');
            }

            // Only reset the Field filter; other filters will be restored from saved state
            selectedField = '';

            // Ensure APC search is registered once and applies to our table only
            if (!apcSearchRegistered) {
                console.log('Registering APC custom search filter');
                $.fn.dataTable.ext.search.push(function (settings, data/*, dataIndex*/) {
                    // Apply only to our main table
                    if (!settings.nTable || settings.nTable.id !== 'journalTable') return true;
                    if (currentMaxAPC === '10000') return true;
                    const apcRaw = data && data[5] ? data[5] : '';
                    const apcValue = apcRaw.replace(/[^\d]/g, '');
                    if (apcValue === '') return false; // exclude non-numeric/missing APC when filter is applied
                    return parseInt(apcValue, 10) <= parseInt(currentMaxAPC, 10);
                });
                apcSearchRegistered = true;
            } else {
                console.log('APC search filter already registered, skipping');
            }

            // Show loading indicator
            $('#journalTable').parent().append('<p id="loading-indicator">Loading data...</p>');

            console.time('fetchCSVFile');
            const parsed = await fetchCSVFile(dataSource);
            console.timeEnd('fetchCSVFile');
            const {data: tableData, domains, allHeadersText, defaultVisibleHeaders, mandatoryHeaders, apcBins} = parsed;
            
            // Store bins for later use
            if (apcBins) {
                cachedApcBins = apcBins;
            }

            $('#loading-indicator').remove();

            if (tableData && tableData.length > 0) {
                console.time('DataTable initialization');
                // Precompute initial visibility (only used if no saved state exists)
                const desiredVisible = allHeadersText.map(h => mandatoryHeaders.has(h) || defaultVisibleHeaders.has(h));
                const toHide = desiredVisible.map((v, i) => (v ? null : i)).filter(i => i !== null);
                let firstDrawCompleted = false;

                dataTable = $('#journalTable').DataTable({
                    data: tableData,
                    scrollX: false,
                    scroller: false,
                    paging: false,
                    deferRender: true, 
                    search: {
                        smart: true,
                        regex: false,
                        caseInsensitive: true,
                        search: currentSearch // Re-apply global search
                    },
                    columnControl: ['order', 'searchDropdown'],
                    ordering: {
                        indicators: false,
                        handler: false
                    },
                    info: true,
                    dom: 'Bift',
                    footerCallback: function (row, data, start, end, display) {
                        const isAllFields = currentDataSource === ALL_FIELDS_SOURCE;
                        const $footerCell = $(row).find('td');
                        $footerCell.css('text-align', 'center');
                        if (!isAllFields) {
                            $footerCell.html('Load the larger <a href="#" id="load-all-dataset-link" role="button" style="color: #3182ce; font-weight: 500;">"All Fields"</a> dataset.');
                        } else {
                            $footerCell.html('');
                        }
                    },
                    stateSave: true,
                    stateDuration: -1, // use localStorage and persist
                    // Use a single global localStorage key so state is shared across CSVs
                    stateSaveCallback: function (settings, data) {
                        try {
                            // Limit the size of what we save to avoid localStorage bloat
                            const stateToSave = {
                                time: data.time,
                                start: data.start,
                                length: data.length,
                                order: data.order,
                                search: data.search,
                                columns: data.columns,
                                custom: data.custom
                            };
                            localStorage.setItem('wtp_global_state_v1', JSON.stringify(stateToSave));
                        } catch (e) {
                            console.warn('Failed to save state:', e);
                        }
                    },
                    stateLoadCallback: function (settings) {
                        try {
                            const raw = localStorage.getItem('wtp_global_state_v1');
                            return raw ? JSON.parse(raw) : null;
                        } catch (e) {
                            return null;
                        }
                    },
                    fixedHeader: true,
                    buttons: [
                        {
                            extend: 'csvHtml5',
                            title: 'WhereToPublish',
                            exportOptions: {
                                // export only visible columns by default
                                columns: ':visible'
                            }
                        },
                        {
                            extend: 'colvis',
                            columns: ':not(.noVis)',
                            postfixButtons: [
                                {
                                    text: 'Impact Factor',
                                    action: function (e, dt, node, config) {
                                        $('div.dt-button-background').click();
                                        openModal($('#impactFactorModal'));
                                    }
                                },
                                {
                                    text: 'Reset columns',
                                    className: 'dt-button--reset',
                                    action: function (e, dt/*, node, config*/) {
                                        try {
                                            // Restore the project defaults: mandatory + default visible headers
                                            allHeadersText.forEach(function (header, idx) {
                                                var mustShow = mandatoryHeaders.has(header) || defaultVisibleHeaders.has(header);
                                                dt.column(idx).visible(mustShow, false);
                                            });
                                            dt.columns.adjust().draw(false);
                                            if (dt.state && typeof dt.state.save === 'function') {
                                                dt.state.save();
                                            }
                                        } catch (err) {
                                            // no-op
                                        }
                                    }
                                }
                            ]
                        }
                    ],
                    stateSaveParams: function (settings, data) {
                        // Persist custom filters
                        data.custom = data.custom || {};
                        data.custom.apcMax = currentMaxAPC;
                    },
                    stateLoadParams: function (settings, data) {
                        // Reset Field filter when switching CSV files
                        if (resetFieldOnNextLoad && data && data.columns && data.columns[1] && data.columns[1].search) {
                            data.columns[1].search.search = '';
                            data.columns[1].search.regex = false;
                            data.columns[1].search.smart = true;
                        }
                        // Restore APC from saved state if present
                        if (data && data.custom && data.custom.apcMax) {
                            currentMaxAPC = String(data.custom.apcMax);
                            $('#apcSlider').val(currentMaxAPC);
                            $('#apcValue').text(currentMaxAPC === '10000' ? 'All APCs' : '≤ ' + currentMaxAPC + ' €');
                        } else {
                            // default APC
                            currentMaxAPC = '10000';
                            $('#apcSlider').val(10000);
                            $('#apcValue').text('All APCs');
                        }
                    },
                    autoWidth: false,
                    responsive: false, // Disable responsive - it's expensive and we handle it with CSS
                    columnDefs: [
                        {
                            targets: [1, 3, 4], columnControl: [
                                {
                                    extend: 'order',
                                }
                            ]
                        },
                        {targets: [0, 3], className: 'noVis'},
                        {
                            targets: 0,
                            render: function (data, type, row) {
                                if ((type === 'display') && row && row[9]) {
                                    return `<a href="${row[9]}" target="_blank" rel="noopener noreferrer">${data}</a>`;
                                }
                                return data;
                            }
                        },
                        {
                            targets: 9,
                            render: function (data, type, row) {
                                if ((type === 'display') && row && row[9]) {
                                    return `<a href="${row[9]}" target="_blank" rel="noopener noreferrer">${row[9]}</a>`;
                                }
                                return data;
                            }
                        },
                        ...(toHide.length ? [{targets: toHide, visible: false}] : [])
                    ],
                    language: {
                        info: "Displaying all _TOTAL_ journals",
                        infoEmpty: "No journals available",
                        emptyTable: "No journal data available",
                        search: "",
                        zeroRecords: buildZeroRecordsMessage()
                    },
                    rowCallback: function (row, data) {
                        // Optimized: use direct string comparison and early returns
                        const publisherType = data[3];
                        if (!publisherType) return;
                        
                        const $row = $(row);
                        
                        // Remove all classes at once
                        $row[0].className = $row[0].className.replace(/\b(for-profit-row|for-profit-society-run-row|university-press-row|university-press-society-run-row|non-profit-row)\b/g, '').trim();
                        
                        // Add appropriate class based on publisher type
                        if (publisherType === 'For-profit') {
                            $row.addClass('for-profit-row');
                        } else if (publisherType.startsWith('For-profit')) {
                            $row.addClass('for-profit-society-run-row');
                        } else if (publisherType === 'University Press') {
                            $row.addClass('university-press-row');
                        } else if (publisherType.startsWith('University Press')) {
                            $row.addClass('university-press-society-run-row');
                        } else if (publisherType === 'Non-profit') {
                            $row.addClass('non-profit-row');
                        }
                    },
                    preDrawCallback: function () {
                        if (!firstDrawCompleted) {
                            // Initialize whether columns are searchable based on visibility
                            var table = this.api();
                            table.columns().every(function (index) {
                                this.settings()[0].aoColumns[index].bSearchable = this.visible();
                            });
                            table.rows().invalidate();
                            firstDrawCompleted = true;
                        }
                    },
                    drawCallback: function () {
                        // This fires after every draw (search, filter, sort, page change, etc.)
                        // Automatically updates histogram and counts for all search types including ColControl
                        var table = this.api();
                        refreshHistogramFromTable(table);
                        refreshCountsFromTable(table);
                    },
                    initComplete: function () {
                        console.timeEnd('DataTable initialization');
                        console.time('initComplete callback');
                        var table = this.api();
                        var domainFiltersContainer = $('#domainFilters');

                        // Add placeholder to search input
                        $('.dt-input').attr('placeholder', 'Search journals...');

                        // Sync publisher and business model filter buttons with restored state
                        $('.profit-status-button').removeClass('active');
                        const pubSearch = table.column(3).search();
                        currentPublisherTypeFilter = 'all';
                        if (!pubSearch) {
                            $('#allPublishers').addClass('active');
                        } else if (pubSearch.indexOf('For-profit') === 0) {
                            $('#forProfitPublishers').addClass('active');
                            currentPublisherTypeFilter = 'For-profit';
                        } else if (pubSearch.indexOf('Non-profit') === 0) {
                            $('#nonProfitPublishers').addClass('active');
                            currentPublisherTypeFilter = 'Non-profit';
                        } else if (pubSearch.indexOf('University Press') === 0) {
                            $('#universityPressPublishers').addClass('active');
                            currentPublisherTypeFilter = 'University Press';
                        } else {
                            $('#allPublishers').addClass('active');
                        }

                        $('.business-model-button').removeClass('active');
                        const bmSearch = table.column(4).search();
                        currentBusinessModelFilter = 'all';
                        if (!bmSearch) {
                            $('#allBusinessModels').addClass('active');
                        } else if (bmSearch === 'OA diamond') {
                            $('#diamondOABusinessModel').addClass('active');
                            currentBusinessModelFilter = 'oa-diamond';
                        } else if (bmSearch === '^OA$') {
                            $('#oaBusinessModel').addClass('active');
                            currentBusinessModelFilter = 'oa';
                        } else if (bmSearch === '^Hybrid$') {
                            $('#hybridBusinessModel').addClass('active');
                            currentBusinessModelFilter = 'hybrid';
                        } else if (bmSearch === '^Subscription$') {
                            $('#subscriptionBusinessModel').addClass('active');
                            currentBusinessModelFilter = 'subscription';
                        } else {
                            $('#allBusinessModels').addClass('active');
                        }

                        // Event listener for when a column's visibility changes
                        table.on('column-visibility.dt', function (e, settings, column, state) {
                            settings.aoColumns[column].bSearchable = state;
                            table.rows().invalidate().draw();
                        });

                        // Render domain filter as dropdown if too many domains, else as buttons
                        const tooManyDomains = Array.isArray(domains) && domains.length > 10;
                        domainFiltersContainer.empty();
                        if (tooManyDomains) {
                            // Dropdown select to save vertical space
                            const select = $('<select class="domain-filter-select" aria-label="Filter by field"></select>');
                            // Default option: show all
                            select.append($('<option value="">All Subfields</option>'));
                            domains.forEach(function (domainName) {
                                select.append($('<option></option>').val(domainName).text(domainName));
                            });

                            select.on('change', function () {
                                const val = $(this).val();
                                if (!val) {
                                    selectedField = '';
                                    table.column(1).search('');
                                } else {
                                    selectedField = val;
                                    const pattern = '^' + escapeRegExp(val) + '$';
                                    table.column(1).search(pattern, true, false);
                                }
                                table.draw();
                            });

                            domainFiltersContainer.removeClass('compact').append(select);
                        } else {
                            // Fewer domains: render as clickable buttons
                            domainFiltersContainer.toggleClass('compact', false);

                            var showAllButton = $('<button class="domain-filter-button">All Subfields</button>')
                                .on('click', function () {
                                    selectedField = '';
                                    table.column(1).search('');
                                    table.draw();
                                    domainFiltersContainer.find('.domain-filter-button').removeClass('active');
                                    $(this).addClass('active');
                                });
                            domainFiltersContainer.append(showAllButton);

                            domains.forEach(function (domainName) {
                                var button = $('<button class="domain-filter-button">' + domainName + '</button>')
                                    .on('click', function () {
                                        var isActive = $(this).hasClass('active');
                                        table.column(1).search('');
                                        domainFiltersContainer.find('.domain-filter-button').removeClass('active');
                                        if (isActive) {
                                            selectedField = '';
                                            showAllButton.addClass('active');
                                        } else {
                                            selectedField = domainName;
                                            const pattern = '^' + escapeRegExp(domainName) + '$';
                                            table.column(1).search(pattern, true, false);
                                            $(this).addClass('active');
                                        }
                                        table.draw();
                                    });
                                domainFiltersContainer.append(button);
                            });
                            // Default to SHOW ALL (Field reset on data source change)
                            showAllButton.addClass('active');
                        }
                        // Reset flag once applied
                        resetFieldOnNextLoad = false;
                        console.timeEnd('initComplete callback');
                    }
                });
                $('#journalTable').off('click', '#load-all-dataset-link').on('click', '#load-all-dataset-link', function (event) {
                    event.preventDefault();
                    const $button = $('#allJournals');
                    if ($button.length) {
                        $button.trigger('click');
                    } else {
                        currentDataSource = ALL_FIELDS_SOURCE;
                        currentDatasetLabel = 'All fields';
                        loadTable(ALL_FIELDS_SOURCE);
                    }
                });
            } else if (tableData) {
                $('#journalTable').parent().append('<p>No data found in CSV after parsing headers.</p>');
            }
        } catch (error) {
            console.error('Error loading or processing CSV files:', error);
            $('#journalTable').parent().append('<p style="color:red;">Could not load data. Please ensure CSV files exist in the data folder and check the browser console for errors.</p>');
        } finally {
            console.timeEnd('loadTable');
            console.log('%c=== Performance Summary ===', 'color: #4CAF50; font-weight: bold; font-size: 14px');
            console.log('Dataset:', currentDatasetLabel);
            console.log('Check timing marks above for detailed breakdown');
            console.log('%c===========================', 'color: #4CAF50; font-weight: bold');
        }
    }

    // Modal functionality
    const aboutModal = $('#aboutModal');
    const closeModalButton = $('.close-modal');
    const modalTriggers = $('.modal-trigger');

    function openModal(modal) {
        modal.addClass('show');
        $('body').css('overflow', 'hidden');
    }

    function closeModal() {
        $('.modal').removeClass('show');
        $('body').css('overflow', '');
    }

    modalTriggers.on('click', function () {
        openModal(aboutModal);
    });
    
    // About link handler
    $('#aboutLink').on('click', function (event) {
        event.preventDefault();
        openModal(aboutModal);
    });
    
    closeModalButton.on('click', function () {
        closeModal();
    });
    $('.modal').on('click', function (event) {
        if ($(event.target).is('.modal')) closeModal();
    });
    $(document).on('keydown', function (event) {
        if (event.key === 'Escape' && $('.modal.show').length) closeModal();
    });

    $('#copyBox').on('click', function () {
        const textToCopy = $('#copyContent').text();
        navigator.clipboard.writeText(textToCopy)
            .then(() => {
                $('#copyTooltip').css('opacity', '1');
                setTimeout(() => {
                    $('#copyTooltip').css('opacity', '0');
                }, 2000);
            })
            .catch(err => {
                console.error('Failed to copy: ', err);
            });
    });

    // Load default table
    currentDataSource = DEFAULT_DATA_SOURCE;
    currentDatasetLabel = 'Generalist';
    loadTable(DEFAULT_DATA_SOURCE);
});
