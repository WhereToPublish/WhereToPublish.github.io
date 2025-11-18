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

    // Mandatory columns that cannot be hidden
    const mandatoryHeaders = new Set(['Journal', 'Publisher type']);

    // Default visible columns at load
    const defaultVisibleHeaders = new Set(['Journal', 'Field', 'Publisher', 'Publisher type', 'Business model', 'APC (€)']);

    // Render table headers (we render all headers so DataTables knows columns; visibility handled later)
    const headerRow = $('#journalTable thead tr');
    headerRow.empty();
    allHeadersText.forEach(headerText => headerRow.append($('<th>').text(headerText)));

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

// Place the Columns control next to the DataTables search box
function placeColumnsControlNextToSearch() {
    const $wrapper = $('#journalTable').closest('.dataTables_wrapper');
    const $filter = $wrapper.find('.dataTables_filter');
    const $control = $('.table-controls .column-visibility');
    if ($filter.length && $control.length) {
        $filter.append($control);
    }
}

// Move the Columns control back to its original container (hidden) before destroying/reloading
function restoreColumnsControlToDock() {
    const $controlInWrapper = $('#journalTable').closest('.dataTables_wrapper').find('.column-visibility');
    if ($controlInWrapper.length) {
        $('.table-controls').append($controlInWrapper);
    }
}

$(document).ready(function () {
    let dataTable; // Variable to store the DataTable instance

    // Track APC slider state for persistent filtering
    let currentMaxAPC = '10000';
    // Track selected Field (domain) for counts logic
    let selectedField = '';
    let apcSearchRegistered = false;

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
        // Field check (row[1] is Field)
        if (selectedField && String(row[1]) !== String(selectedField)) return false;
        // APC check (row[5] is APC (€))
        if (currentMaxAPC !== '10000') {
            const apcRaw = (row && row[5]) ? String(row[5]) : '';
            const apcValue = apcRaw.replace(/[^\d]/g, '');
            if (apcValue === '') return false; // mimic table filter: exclude missing APC when filtering applied
            if (parseInt(apcValue, 10) > parseInt(currentMaxAPC, 10)) return false;
        }
        return true;
    }

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

    // Data source buttons
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

    // Profit status filter buttons
    $('#allPublishers').on('click', function () {
        $('.profit-status-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            dataTable.column(3).search('').draw();
            refreshHistogramFromTable(dataTable); // counts should NOT change here
        }
    });
    $('#forProfitPublishers').on('click', function () {
        $('.profit-status-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            dataTable.column(3).search('For-profit', false, false).draw();
            refreshHistogramFromTable(dataTable); // counts should NOT change here
        }
    });
    $('#universityPressPublishers').on('click', function () {
        $('.profit-status-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            dataTable.column(3).search('University Press', false, false).draw();
            refreshHistogramFromTable(dataTable); // counts should NOT change here
        }
    });
    $('#nonProfitPublishers').on('click', function () {
        $('.profit-status-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            dataTable.column(3).search('Non-profit', false, false).draw();
            refreshHistogramFromTable(dataTable); // counts should NOT change here
        }
    });

    // Business model filter buttons
    $('#allBusinessModels').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            dataTable.column(4).search('').draw();
            refreshHistogramFromTable(dataTable); // counts should NOT change here
        }
    });
    $('#diamondOABusinessModel').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            dataTable.column(4).search('OA diamond', false, false).draw();
            refreshHistogramFromTable(dataTable); // counts should NOT change here
        }
    });
    $('#oaBusinessModel').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            dataTable.column(4).search('^OA$', true, false).draw();
            refreshHistogramFromTable(dataTable); // counts should NOT change here
        }
    });
    $('#hybridBusinessModel').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            dataTable.column(4).search('^Hybrid$', true, false).draw();
            refreshHistogramFromTable(dataTable); // counts should NOT change here
        }
    });
    $('#subscriptionBusinessModel').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            dataTable.column(4).search('^Subscription$', true, false).draw();
            refreshHistogramFromTable(dataTable); // counts should NOT change here
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
                .attr('title', counts[i] + ' journals with APC between ' + bins[i] + '€ and ' + bins[i + 1] + '€');
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
        let consideredCount = 0;

        const publisherTypeCounts = { 'For-profit': 0, 'Non-profit': 0, 'University Press': 0 };
        const businessModelCounts = { 'OA diamond': 0, 'OA': 0, 'Hybrid': 0, 'Subscription': 0 };

        // Capture previously active business model button id (if any)
        const previouslyActiveId = $('.business-model-button.active').attr('id') || null;
        const idToModel = {
            'diamondOABusinessModel': 'OA diamond',
            'oaBusinessModel': 'OA',
            'hybridBusinessModel': 'Hybrid',
            'subscriptionBusinessModel': 'Subscription'
        };

        allRows.forEach((row) => {
            if (!rowPassesApcAndField(row)) return;
            consideredCount++;
            const publisherType = (row && row[3]) ? String(row[3]) : '';
            const businessModel = (row && row[4]) ? String(row[4]) : '';

            if (publisherType === 'Non-profit') publisherTypeCounts['Non-profit']++;
            else if (publisherType.indexOf('For-profit') === 0) publisherTypeCounts['For-profit']++;
            else if (publisherType.indexOf('University Press') === 0) publisherTypeCounts['University Press']++;

            if (Object.prototype.hasOwnProperty.call(businessModelCounts, businessModel)) {
                businessModelCounts[businessModel]++;
            }
        });

        // Update publisher buttons text using consideredCount
        $('#allPublishers').text('All Publishers (' + consideredCount + ')');
        $('#forProfitPublishers').text('For-profit (' + (publisherTypeCounts['For-profit'] || 0) + ')');
        $('#nonProfitPublishers').text('Non-profit (' + (publisherTypeCounts['Non-profit'] || 0) + ')');
        $('#universityPressPublishers').text('University Press (' + (publisherTypeCounts['University Press'] || 0) + ')');

        // Update business model buttons text + dynamic hide/show for zero-count
        $('#allBusinessModels').text('All Business Models (' + consideredCount + ')');
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

        // If the previously active business-model now has zero items, reset to All Business Models and clear the filter
        if (previouslyActiveId && previouslyActiveId !== 'allBusinessModels') {
            const previouslyActiveModel = idToModel[previouslyActiveId];
            const prevCount = businessModelCounts[previouslyActiveModel] || 0;
            if (prevCount === 0) {
                $('.business-model-button').removeClass('active');
                $('#allBusinessModels').addClass('active');
                tableApi.column(4).search('').draw();
                refreshHistogramFromTable(tableApi);
            }
        }

        // Ensure there's always an active business-model button
        if ($('.business-model-button.active').length === 0) {
            $('#allBusinessModels').addClass('active');
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

    // Column toggle menu
    function buildColumnToggleMenu(table, allHeadersText, defaultVisibleHeaders, mandatoryHeaders) {
        const menu = $('#columnToggleMenu');
        menu.empty();
        allHeadersText.forEach((header, index) => {
            const isMandatory = mandatoryHeaders.has(header);
            const isChecked = table.column(index).visible();
            const item = $('<label class="column-toggle-item"></label>');
            const checkbox = $('<input type="checkbox">')
                .prop('checked', isChecked)
                .prop('disabled', isMandatory)
                .on('change', function () {
                    if (isMandatory && !this.checked) {
                        this.checked = true;
                        return;
                    }
                    table.column(index).visible(this.checked, false);
                    scheduleAdjust(table);
                    saveVisibleColumns(table, allHeadersText, mandatoryHeaders);
                });
            item.append(checkbox).append($('<span>').text(header));
            menu.append(item);
        });
        const sep = $('<hr>').css({border: 'none', borderTop: '1px solid #e2e8f0', margin: '6px 0'});
        const resetBtn = $('<button type="button" class="column-toggle-button" style="width:100%;margin-top:4px;">Reset columns</button>')
            .on('click', function (e) {
                e.stopPropagation();
                try {
                    localStorage.removeItem(COLUMN_VIS_STATE_KEY);
                } catch (_) {
                }
                allHeadersText.forEach((header, idx) => {
                    const mustShow = defaultVisibleHeaders.has(header) || mandatoryHeaders.has(header);
                    table.column(idx).visible(mustShow, false);
                });
                scheduleAdjust(table);
                buildColumnToggleMenu(table, allHeadersText, defaultVisibleHeaders, mandatoryHeaders);
            });
        menu.append(sep).append(resetBtn);
    }

    // Column visibility persistence
    const COLUMN_VIS_STATE_KEY = 'wtp_visible_columns_v1';

    function saveVisibleColumns(table, allHeadersText, mandatoryHeaders) {
        const state = {};
        allHeadersText.forEach((header, idx) => {
            const visible = mandatoryHeaders.has(header) ? true : table.column(idx).visible();
            state[header] = !!visible;
        });
        try {
            localStorage.setItem(COLUMN_VIS_STATE_KEY, JSON.stringify(state));
        } catch (_) {
        }
    }

    function loadVisibleColumns() {
        try {
            const raw = localStorage.getItem(COLUMN_VIS_STATE_KEY);
            if (!raw) return null;
            return JSON.parse(raw);
        } catch (_) {
            return null;
        }
    }

    function computeDesiredVisibility(allHeadersText, defaultVisibleHeaders, mandatoryHeaders, saved) {
        return allHeadersText.map(header => {
            if (mandatoryHeaders.has(header)) return true;
            if (saved && Object.prototype.hasOwnProperty.call(saved, header)) return !!saved[header];
            return defaultVisibleHeaders.has(header);
        });
    }

    // Column toggle dropdown open/close
    $(document).on('click', '#columnToggleButton', function (e) {
        e.stopPropagation();
        const menu = $('#columnToggleMenu');
        const willOpen = !menu.hasClass('open');
        $('#columnToggleButton').attr('aria-expanded', willOpen ? 'true' : 'false');
        menu.toggleClass('open');
    });
    $(document).on('click', '#columnToggleMenu', function (e) {
        e.stopPropagation();
    });
    $(document).on('click', function () {
        $('#columnToggleMenu').removeClass('open');
        $('#columnToggleButton').attr('aria-expanded', 'false');
    });

    // Load and initialize the table
    async function loadTable(dataSource = 'data/all_biology.csv') {
        try {
            // Clear existing table if it exists
            if (dataTable) {
                // move Columns control back to the dock before destroying the wrapper
                restoreColumnsControlToDock();
                dataTable.destroy();
                $('#journalTable tbody').empty();
                $('#domainFilters').empty();
            }

            // Reset filters and slider
            $('.profit-status-button').removeClass('active');
            $('#allPublishers').addClass('active');
            $('.business-model-button').removeClass('active');
            $('#allBusinessModels').addClass('active');
            $('#apcSlider').val(10000);
            currentMaxAPC = '10000';
            selectedField = '';
            $('#apcValue').text('All APC');

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
                // Precompute initial visibility
                const savedVis = loadVisibleColumns();
                const desiredVisible = computeDesiredVisibility(allHeadersText, defaultVisibleHeaders, mandatoryHeaders, savedVis);
                const toHide = desiredVisible.map((v, i) => (v ? null : i)).filter(i => i !== null);

                dataTable = $('#journalTable').DataTable({
                    data: tableData,
                    scrollX: false,
                    paging: false,
                    searching: true,
                    ordering: true,
                    orderClasses: false,
                    info: true,
                    dom: 'ift',
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
                        { targets: 9, visible: false,  },
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
                        } else if (publisherType.indexOf('For-profit') !== -1) {
                            $row.addClass('for-profit-society-run-row');
                        } else if (publisherType === 'University Press') {
                            $row.addClass('university-press-row');
                        } else if (publisherType.indexOf('University Press') !== -1) {
                            $row.addClass('university-press-society-run-row');
                        } else if (publisherType === 'Non-profit') {
                            $row.addClass('non-profit-row');
                        }
                    },
                    initComplete: function () {
                        var table = this.api();
                        var domainFiltersContainer = $('#domainFilters');

                        // Add placeholder to search input
                        $('.dataTables_filter input').attr('placeholder', 'Search journals...');

                        // Build column toggle menu now that visibility is finalized
                        buildColumnToggleMenu(table, allHeadersText, defaultVisibleHeaders, mandatoryHeaders);

                        // Move Columns control next to search box
                        placeColumnsControlNextToSearch();

                        // Persist defaults if no saved preferences existed
                        if (!savedVis) {
                            saveVisibleColumns(table, allHeadersText, mandatoryHeaders);
                        }

                        // Search box updates only histogram
                        $('.dataTables_filter input').on('keyup', function () {
                            refreshHistogramFromTable(table);
                        });

                        // Initialize histogram
                        const allData = table.rows().data().toArray();
                        const distribution = calculateAPCDistribution(allData);
                        renderHistogram(distribution);

                        // Compute counts for buttons
                        const publisherTypeCounts = {
                            'For-profit': 0,
                            'Non-profit': 0,
                            'University Press': 0,
                        };
                        const businessModelCounts = {
                            'OA diamond': 0,
                            'OA': 0,
                            'Hybrid': 0,
                            'Subscription': 0
                        };
                        allData.forEach(row => {
                            const publisherType = row[3];
                            const businessModel = row[4];
                            if (publisherType === 'Non-profit') publisherTypeCounts["Non-profit"]++;
                            else if (publisherType.indexOf('For-profit') === 0) publisherTypeCounts["For-profit"]++;
                            else if (publisherType.indexOf('University Press') === 0) publisherTypeCounts["University Press"]++;
                            if (businessModel in businessModelCounts) businessModelCounts[businessModel]++;
                        });

                        // Update buttons with counts
                        $('#allPublishers').text('All Publishers (' + allData.length + ')');
                        $('#forProfitPublishers').text('For-profit (' + publisherTypeCounts['For-profit'] + ')');
                        $('#nonProfitPublishers').text('Non-profit (' + publisherTypeCounts['Non-profit'] + ')');
                        $('#universityPressPublishers').text('University Press (' + publisherTypeCounts['University Press'] + ')');

                        $('#allBusinessModels').text('All Business Models (' + allData.length + ')');
                        if (businessModelCounts['OA diamond'] === 0) {
                            $('#diamondOABusinessModel').addClass('hidden');
                        } else {
                            let d = $('#diamondOABusinessModel');
                            d.removeClass('hidden').text('OA diamond (' + businessModelCounts['OA diamond'] + ')');
                        }
                        if (businessModelCounts['OA'] === 0) {
                            $('#oaBusinessModel').addClass('hidden');
                        } else {
                            let d = $('#oaBusinessModel');
                            d.removeClass('hidden').text('OA (' + businessModelCounts['OA'] + ')');
                        }
                        if (businessModelCounts['Hybrid'] === 0) {
                            $('#hybridBusinessModel').addClass('hidden');
                        } else {
                            let d = $('#hybridBusinessModel');
                            d.removeClass('hidden').text('Hybrid (' + businessModelCounts['Hybrid'] + ')');
                        }
                        if (businessModelCounts['Subscription'] === 0) {
                            $('#subscriptionBusinessModel').addClass('hidden');
                        } else {
                            let d = $('#subscriptionBusinessModel');
                            d.removeClass('hidden').text('Subscription (' + businessModelCounts['Subscription'] + ')');
                        }

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
                                    refreshCountsFromTable(table); // counts should change with Field
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
                            showAllButton.addClass('active');
                        }
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
    const modal = $('#aboutModal');
    const closeModalButton = $('.close-modal');
    const modalTriggers = $('.modal-trigger');

    function openModal() {
        modal.addClass('show');
        $('body').css('overflow', 'hidden');
    }

    function closeModal() {
        modal.removeClass('show');
        $('body').css('overflow', '');
    }

    modalTriggers.on('click', function () {
        openModal();
    });
    closeModalButton.on('click', function () {
        closeModal();
    });
    modal.on('click', function (event) {
        if ($(event.target).is(modal)) closeModal();
    });
    $(document).on('keydown', function (event) {
        if (event.key === 'Escape' && modal.hasClass('show')) closeModal();
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
