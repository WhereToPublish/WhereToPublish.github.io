function parseCSV(csvText) {
    // We know the exact column order in the CSV:
    // 0: Journal, 1: Field, 2: Publisher, 3: Publisher type, 4: Business model,
    // 5: Institution, 6: Institution type, 7: Country, 8: Website, 9: APC Euros,
    // 10: Scimago Rank, 11: Scimago Quartile, 12: H index, 13: PCI partner
    const lines = csvText.split('\n');
    const data = [];
    const domains = new Set();

    if (!lines.length) return {data: [], domains: []};

    // Define all headers in the internal data order
    const allHeadersText = [
        'Journal',            // 0 (mandatory visible)
        'Field',              // 1
        'Publisher',          // 2
        'Publisher type',     // 3 (mandatory visible)
        'Business model',     // 4
        'APC (€)',            // 5 (from APC Euros)
        'Country (Publisher)',// 6
        'Institution',        // 7
        'Institution type',   // 8
        'Website',            // 9
        'Scimago Rank',       // 10
        'Scimago Quartile',   // 11
        'H index',            // 12
        'PCI partner'         // 13
    ];
    const columnDefs = {
        5: 'APC values are obtained from OpenAPC as the average in the last 3 years.',
        10: 'Scimago Rank is an ordinal position where higher numbers indicate higher impact.',
        11: 'Scimago Quartile ranges from Q1 (best) to Q4 (lowest)',
        12: 'At least H publications have received at least H citations.'
    };

    // Mandatory columns that cannot be hidden
    const mandatoryHeaders = new Set(['Journal', 'Publisher type']);

    // Default visible columns at load
    const defaultVisibleHeaders = new Set(['Journal', 'Field', 'Publisher', 'Publisher type', 'Business model', 'APC (€)']);

    // Render table headers (we render all headers so DataTables knows columns; visibility handled later)
    const headerRow = $('#journalTable thead tr');
    headerRow.empty();
    allHeadersText.forEach((headerText, index) => {
        const $th = $('<th>');
        if (columnDefs[index]) {
            const $icon = $('<span>')
                .addClass('hint--bottom hint--medium hint--rounded')
                .attr('aria-label', columnDefs[index])
                .attr('tabindex', '0')
                .text(headerText);
            $th.append($icon);
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
            cols[3] || '', // Publisher type
            cols[4] || '', // Business model
            cols[9] || '', // APC Euros -> displayed as APC (€)
            cols[7] || '', // Country -> displayed as Country (Publisher)
            cols[5] || '', // Institution
            cols[6] || '', // Institution type
            cols[8] || '', // Website
            cols[10] || '', // Scimago Rank
            cols[11] || '', // Scimago Quartile
            cols[12] || '', // H index
            cols[13] || ''  // PCI partner
        ];

        data.push(row);
    }

    return {data, domains: Array.from(domains).sort(), allHeadersText, defaultVisibleHeaders, mandatoryHeaders};
}

// Escape a string for use inside a RegExp
function escapeRegExp(string) {
    return String(string).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

$(document).ready(function () {
    let dataTable; // Variable to store the DataTable instance
    let currentDataSource = null; // Track current CSV file
    let resetFieldOnNextLoad = false; // Only reset Field filter when switching CSV

    // Track APC slider state for persistent filtering
    let currentMaxAPC = '10000';
    // Track selected Field (domain) for counts logic
    let selectedField = '';
    let apcSearchRegistered = false;
    let currentPublisherTypeFilter = 'all';
    let currentBusinessModelFilter = 'all';

    // Batch expensive adjust/recalc to the next animation frame
    let adjustScheduled = false;

    function scheduleAdjust(table) {
        if (adjustScheduled) return;
        adjustScheduled = true;
        requestAnimationFrame(() => {
            try {
                table.columns.adjust().responsive.recalc();
            } finally {
                adjustScheduled = false;
            }
        });
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
            case 'for-profit':
                return publisherType.indexOf('For-profit') === 0;
            case 'non-profit':
                return publisherType.indexOf('Non-profit') === 0;
            case 'university-press':
                return publisherType.indexOf('University Press') === 0;
            default:
                return true;
        }
    }

    function matchesBusinessModelFilter(row, filterKey) {
        const businessModel = row && row[4] ? String(row[4]) : '';
        switch (filterKey) {
            case 'oa-diamond':
                return businessModel === 'OA diamond';
            case 'oa':
                return businessModel === 'OA';
            case 'hybrid':
                return businessModel === 'Hybrid';
            case 'subscription':
                return businessModel === 'Subscription';
            default:
                return true;
        }
    }

    function rowMatchesGlobalSearch(row, tableApi) {
        if (!tableApi || typeof tableApi.search !== 'function') return true;
        const term = String(tableApi.search() || '').trim();
        if (!term) return true;
        const haystack = row
            .map(cell => (cell === null || cell === undefined) ? '' : String(cell))
            .join(' ')
            .toLowerCase();
        const tokens = term.toLowerCase().split(/\s+/).filter(Boolean);
        return tokens.every(token => haystack.indexOf(token) !== -1);
    }

    // Data source buttons
    $('#allJournals').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        const src = 'data/all_biology.csv';
        resetFieldOnNextLoad = currentDataSource !== null && currentDataSource !== src;
        currentDataSource = src;
        loadTable(src);
    });
    $('#generalist').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        const src = 'data/generalist.csv';
        resetFieldOnNextLoad = currentDataSource !== null && currentDataSource !== src;
        currentDataSource = src;
        loadTable(src);
    });
    $('#cancer').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        const src = 'data/cancer.csv';
        resetFieldOnNextLoad = currentDataSource !== null && currentDataSource !== src;
        currentDataSource = src;
        loadTable(src);
    });
    $('#development').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        const src = 'data/development.csv';
        resetFieldOnNextLoad = currentDataSource !== null && currentDataSource !== src;
        currentDataSource = src;
        loadTable(src);
    });
    $('#ecologyEvolution').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        const src = 'data/ecology_evolution.csv';
        resetFieldOnNextLoad = currentDataSource !== null && currentDataSource !== src;
        currentDataSource = src;
        loadTable(src);
    });
    $('#geneticsGenomics').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        const src = 'data/genetics_genomics.csv';
        resetFieldOnNextLoad = currentDataSource !== null && currentDataSource !== src;
        currentDataSource = src;
        loadTable(src);
    });
    $('#immunology').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        const src = 'data/immunology.csv';
        resetFieldOnNextLoad = currentDataSource !== null && currentDataSource !== src;
        currentDataSource = src;
        loadTable(src);
    });
    $('#molecularCellularBiology').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        const src = 'data/molecular_cellular_biology.csv';
        resetFieldOnNextLoad = currentDataSource !== null && currentDataSource !== src;
        currentDataSource = src;
        loadTable(src);
    });
    $('#neurosciences').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        const src = 'data/neurosciences.csv';
        resetFieldOnNextLoad = currentDataSource !== null && currentDataSource !== src;
        currentDataSource = src;
        loadTable(src);
    });
    $('#plants').on('click', function () {
        $('.data-source-button').removeClass('active');
        $(this).addClass('active');
        const src = 'data/plants.csv';
        resetFieldOnNextLoad = currentDataSource !== null && currentDataSource !== src;
        currentDataSource = src;
        loadTable(src);
    });

    // Profit status filter buttons
    $('#allPublishers').on('click', function () {
        $('.profit-status-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            currentPublisherTypeFilter = 'all';
            dataTable.column(3).search('').draw();
            refreshHistogramFromTable(dataTable);
            refreshCountsFromTable(dataTable);
        }
    });
    $('#forProfitPublishers').on('click', function () {
        $('.profit-status-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            currentPublisherTypeFilter = 'for-profit';
            dataTable.column(3).search('For-profit', regex = false, smart = false, caseInsenstive = false).draw();
            refreshHistogramFromTable(dataTable);
            refreshCountsFromTable(dataTable);
        }
    });
    $('#universityPressPublishers').on('click', function () {
        $('.profit-status-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            currentPublisherTypeFilter = 'university-press';
            dataTable.column(3).search('University Press', regex = false, smart = false, caseInsenstive = false).draw();
            refreshHistogramFromTable(dataTable);
            refreshCountsFromTable(dataTable);
        }
    });
    $('#nonProfitPublishers').on('click', function () {
        $('.profit-status-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            currentPublisherTypeFilter = 'non-profit';
            dataTable.column(3).search('Non-profit', regex = false, smart = false, caseInsenstive = false).draw();
            refreshHistogramFromTable(dataTable);
            refreshCountsFromTable(dataTable);
        }
    });

    // Business model filter buttons
    $('#allBusinessModels').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            currentBusinessModelFilter = 'all';
            dataTable.column(4).search('').draw();
            refreshHistogramFromTable(dataTable);
            refreshCountsFromTable(dataTable);
        }
    });
    $('#diamondOABusinessModel').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            currentBusinessModelFilter = 'oa-diamond';
            dataTable.column(4).search('OA diamond', false, false).draw();
            refreshHistogramFromTable(dataTable);
            refreshCountsFromTable(dataTable);
        }
    });
    $('#oaBusinessModel').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            currentBusinessModelFilter = 'oa';
            dataTable.column(4).search('^OA$', true, false).draw();
            refreshHistogramFromTable(dataTable);
            refreshCountsFromTable(dataTable);
        }
    });
    $('#hybridBusinessModel').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            currentBusinessModelFilter = 'hybrid';
            dataTable.column(4).search('^Hybrid$', true, false).draw();
            refreshHistogramFromTable(dataTable);
            refreshCountsFromTable(dataTable);
        }
    });
    $('#subscriptionBusinessModel').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            currentBusinessModelFilter = 'subscription';
            dataTable.column(4).search('^Subscription$', true, false).draw();
            refreshHistogramFromTable(dataTable);
            refreshCountsFromTable(dataTable);
        }
    });

    // APC distribution
    function calculateAPCDistribution(data) {
        const bins = [0, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000];
        const distribution = Array(bins.length - 1).fill(0);
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

    // Histogram render
    function renderHistogram(distribution, maxCount) {
        const histogramContainer = $('#apcHistogram');
        histogramContainer.empty();
        const {bins, distribution: counts} = distribution;
        const containerWidth = histogramContainer.width();
        const barWidth = containerWidth / (bins.length - 1);
        const maxValue = maxCount || Math.max(...counts, 1);
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
                .attr('title', counts[i] + ' journals with APC between ' + bins[i] + '€ and ' + bins[i] + '€');
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
            if (counts[i] > 0) bar.append(label);
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
        const allRows = tableApi.rows().data().toArray();
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

        allRows.forEach((row) => {
            if (!rowPassesApcAndField(row) || !rowMatchesGlobalSearch(row, tableApi)) return;

            if (matchesBusinessModelFilter(row, currentBusinessModelFilter)) {
                publisherConsidered++;
                const publisherType = row && row[3] ? String(row[3]) : '';
                if (publisherType === 'Non-profit') publisherTypeCounts['Non-profit']++;
                else if (publisherType.indexOf('For-profit') === 0) publisherTypeCounts['For-profit']++;
                else if (publisherType.indexOf('University Press') === 0) publisherTypeCounts['University Press']++;
            }

            if (matchesPublisherFilter(row, currentPublisherTypeFilter)) {
                businessConsidered++;
                const businessModel = row && row[4] ? String(row[4]) : '';
                if (Object.prototype.hasOwnProperty.call(businessModelCounts, businessModel)) {
                    businessModelCounts[businessModel]++;
                }
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
                refreshHistogramFromTable(tableApi);
                currentBusinessModelFilter = 'all';
            }
        }

        if ($('.business-model-button.active').length === 0) {
            $('#allBusinessModels').addClass('active');
            currentBusinessModelFilter = 'all';
        }
    }

    // APC slider filter
    $('#apcSlider').on('input', function () {
        currentMaxAPC = $(this).val();
        $('#apcValue').text(currentMaxAPC === '10000' ? 'All APC' : '≤ ' + currentMaxAPC + ' €');
        if (dataTable) {
            dataTable.draw();
            refreshHistogramFromTable(dataTable);
            refreshCountsFromTable(dataTable); // counts should change with APC
        }
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

    // Column visibility menu removed in favor of DataTables Buttons 'colvis'

    // Load and initialize the table
    async function loadTable(dataSource = 'data/all_biology.csv') {
        try {
            // Clear existing table if it exists
            if (dataTable) {
                dataTable.destroy();
                $('#journalTable tbody').empty();
                $('#domainFilters').empty();
            }

            // Only reset the Field filter; other filters will be restored from saved state
            selectedField = '';

            // Ensure APC search is registered once and applies to our table only
            if (!apcSearchRegistered) {
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
            }

            // Show loading indicator
            $('#journalTable').parent().append('<p id="loading-indicator">Loading data...</p>');

            const parsed = await fetchCSVFile(dataSource);
            const {data: tableData, domains, allHeadersText, defaultVisibleHeaders, mandatoryHeaders} = parsed;

            $('#loading-indicator').remove();

            if (tableData && tableData.length > 0) {
                // Precompute initial visibility (only used if no saved state exists)
                const desiredVisible = allHeadersText.map(h => mandatoryHeaders.has(h) || defaultVisibleHeaders.has(h));
                const toHide = desiredVisible.map((v, i) => (v ? null : i)).filter(i => i !== null);

                dataTable = $('#journalTable').DataTable({
                    data: tableData,
                    scrollX: false,
                    paging: false,
                    searching: true,
                    ordering: true,
                    orderClasses: false,
                    info: true,
                    dom: 'Bift',
                    stateSave: true,
                    stateDuration: -1, // use localStorage and persist
                    // Use a single global localStorage key so state is shared across CSVs
                    stateSaveCallback: function (settings, data) {
                        try {
                            localStorage.setItem('wtp_global_state_v1', JSON.stringify(data));
                        } catch (e) {
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
                            $('#apcValue').text(currentMaxAPC === '10000' ? 'All APC' : '≤ ' + currentMaxAPC + ' €');
                        } else {
                            // default APC
                            currentMaxAPC = '10000';
                            $('#apcSlider').val(10000);
                            $('#apcValue').text('All APC');
                        }
                    },
                    deferRender: true,
                    autoWidth: false,
                    responsive: {
                        details: {display: $.fn.dataTable.Responsive.display.childRow},
                        breakpoints: [
                            {name: 'desktop', width: Infinity},
                            {name: 'tablet', width: 1024},
                            {name: 'phone', width: 480}
                        ]
                    },
                    columnDefs: [
                        {targets: [0, 3], className: 'noVis'},
                        {
                            targets: 0,
                            render: function (data, type, row) {
                                if ((type === 'display' || type === 'filter') && row && row[9]) {
                                    return `<a href="${row[9]}" target="_blank" rel="noopener noreferrer">${data}</a>`;
                                }
                                return data;
                            }
                        },
                        {
                            targets: 9,
                            render: function (data, type, row) {
                                if ((type === 'display' || type === 'filter') && row && row[9]) {
                                    return `<a href="${row[9]}" target="_blank" rel="noopener noreferrer">${row[9]}</a>`;
                                }
                                return data;
                            },
                            searchable: false
                        },
                        ...(toHide.length ? [{targets: toHide, visible: false}] : [])
                    ],
                    language: {
                        info: "Displaying all _TOTAL_ journals",
                        infoEmpty: "No journals available",
                        emptyTable: "No journal data available",
                        search: ""
                    },
                    rowCallback: function (row, data) {
                        var publisherType = (data && data[3]) ? String(data[3]) : '';
                        var $row = $(row);
                        $row.removeClass('for-profit-row for-profit-society-run-row university-press-row university-press-society-run-row non-profit-row');
                        if (publisherType === 'For-profit') {
                            $row.addClass('for-profit-row');
                        } else if (publisherType.indexOf('For-profit') === 0) {
                            $row.addClass('for-profit-society-run-row');
                        } else if (publisherType === 'University Press') {
                            $row.addClass('university-press-row');
                        } else if (publisherType.indexOf('University Press') === 0) {
                            $row.addClass('university-press-society-run-row');
                        } else if (publisherType === 'Non-profit') {
                            $row.addClass('non-profit-row');
                        }
                    },
                    initComplete: function () {
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
                            currentPublisherTypeFilter = 'for-profit';
                        } else if (pubSearch.indexOf('Non-profit') === 0) {
                            $('#nonProfitPublishers').addClass('active');
                            currentPublisherTypeFilter = 'non-profit';
                        } else if (pubSearch.indexOf('University Press') === 0) {
                            $('#universityPressPublishers').addClass('active');
                            currentPublisherTypeFilter = 'university-press';
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

                        // Search box updates only histogram
                        $('.dt-input').on('keyup', function () {
                            refreshHistogramFromTable(table);
                            refreshCountsFromTable(table);
                        });

                        // Initialize histogram
                        const allData = table.rows().data().toArray();
                        const distribution = calculateAPCDistribution(allData);
                        renderHistogram(distribution);
                        refreshCountsFromTable(table);


                        // Render domain filter as dropdown if too many domains, else as buttons
                        const tooManyDomains = Array.isArray(domains) && domains.length > 10;
                        domainFiltersContainer.empty();
                        if (tooManyDomains) {
                            // Dropdown select to save vertical space
                            const select = $('<select class="domain-filter-select" aria-label="Filter by field"></select>');
                            // Default option: show all
                            select.append($('<option value="">Show all fields</option>'));
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
                                refreshHistogramFromTable(table);
                                refreshCountsFromTable(table); // counts should change with Field
                            });

                            domainFiltersContainer.removeClass('compact').append(select);
                        } else {
                            // Fewer domains: render as clickable buttons
                            domainFiltersContainer.toggleClass('compact', false);

                            var showAllButton = $('<button class="domain-filter-button">SHOW ALL</button>')
                                .on('click', function () {
                                    selectedField = '';
                                    table.column(1).search('');
                                    table.draw();
                                    domainFiltersContainer.find('.domain-filter-button').removeClass('active');
                                    $(this).addClass('active');
                                    refreshHistogramFromTable(table);
                                    refreshCountsFromTable(table);
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
                                        refreshHistogramFromTable(table);
                                        refreshCountsFromTable(table); // counts should change with Field
                                    });
                                domainFiltersContainer.append(button);
                            });
                            // Default to SHOW ALL (Field reset on data source change)
                            showAllButton.addClass('active');
                        }
                        // Reset flag once applied
                        resetFieldOnNextLoad = false;
                    }
                });
            } else if (tableData) {
                $('#journalTable').parent().append('<p>No data found in CSV after parsing headers.</p>');
            }
        } catch (error) {
            console.error('Error loading or processing CSV files:', error);
            $('#journalTable').parent().append('<p style="color:red;">Could not load data. Please ensure CSV files exist in the data folder and check the browser console for errors.</p>');
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
    loadTable('data/generalist.csv');
});
