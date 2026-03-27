/**
 * APC Explorer - Article Processing Charges from 6 publishers (2019-2023)
 *
 * Based on WhereToPublish scripts.js, adapted for the APC Dataverse dataset.
 * Data source: Butler et al. (2024) - doi:10.7910/DVN/CR1MMV
 */

// Configuration
const APC_HISTOGRAM_BINS = 16;
const FIXEDHEADER_BREAKPOINT = 768;


function generateApcBins(numBins, maxApc = 5000) {
    const bins = [];
    const step = maxApc / numBins;
    for (let i = 0; i <= numBins; i++) {
        bins.push(Math.round(i * step));
    }
    return bins;
}

/**
 * Parse CSV text for APC data.
 * Per-publisher files have columns: Journal, Publisher, Business model, APC 2019 (€), ..., APC 2023 (€), APC (€)
 * APC_all.csv has columns: Journal, Publisher, Business model, APC (€)
 */
function parseCSV(csvText, isAllPublishers) {
    console.time('parseCSV');
    const lines = csvText.split('\n');
    const data = [];
    const apcBins = generateApcBins(APC_HISTOGRAM_BINS);

    if (!lines.length) return {data: []};

    // Parse header line to determine columns
    const headerLine = lines[0].trim();
    const csvHeaders = splitCSVLine(headerLine);

    // Identify year columns dynamically
    const yearCols = [];
    csvHeaders.forEach((h, i) => {
        if (h.match(/^APC \d{4} \(€\)$/)) {
            yearCols.push({index: i, header: h});
        }
    });

    // Find key column indices
    const journalIdx = csvHeaders.indexOf('Journal');
    const publisherIdx = csvHeaders.indexOf('Publisher');
    const businessModelIdx = csvHeaders.indexOf('Business model');
    const apcIdx = csvHeaders.indexOf('APC (€)');

    // Build header list for DataTables
    // Fixed columns: Journal (0), Publisher (1), Business model (2)
    // Then year columns (hidden by default), then APC (€) (last, visible)
    const allHeadersText = ['Journal', 'Publisher', 'Business model'];
    yearCols.forEach(yc => allHeadersText.push(yc.header));
    allHeadersText.push('APC (€)');

    const apcColIdx = allHeadersText.length - 1; // Index of APC (€) in our data array

    // Mandatory columns that cannot be hidden
    const mandatoryHeaders = new Set(['Journal', 'Business model', 'APC (€)']);

    // Default visible columns
    const defaultVisibleHeaders = new Set(['Journal', 'Publisher', 'Business model', 'APC (€)']);

    // Column tooltips
    const columnDefs = {
        0: 'Journal name from the publisher listing',
        1: 'Publishing company',
        2: 'OA status: OA (Gold Open Access) or Hybrid',
    };
    // Add tooltips for year columns
    yearCols.forEach((yc, i) => {
        const year = yc.header.match(/\d{4}/)[0];
        columnDefs[3 + i] = `Article Processing Charge in euros for year ${year}`;
    });
    columnDefs[apcColIdx] = 'Last recorded Article Processing Charge in euros';

    // Render table headers
    const headerRow = $('#journalTable thead tr');
    headerRow.empty();
    allHeadersText.forEach((headerText, index) => {
        const $th = $('<th>');
        if (columnDefs[index]) {
            const $icon = $('<span>')
                .attr('tabindex', '0')
                .text(headerText);
            $th.append($icon);
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
                aria: {content: 'describedby', expanded: false}
            });
        } else {
            $th.append($('<span>').text(headerText));
        }
        headerRow.append($th);
    });

    // Parse data rows
    for (let i = 1; i < lines.length; i++) {
        const raw = lines[i].trim();
        if (!raw) continue;

        const cols = splitCSVLine(raw);
        if (!cols.length || !cols[0]) continue;

        const row = [
            cols[journalIdx] || '',
            cols[publisherIdx] || '',
            cols[businessModelIdx] || '',
        ];

        // Add year columns
        yearCols.forEach(yc => {
            row.push(cols[yc.index] || '');
        });

        // Add last APC
        row.push(cols[apcIdx] || '');

        // Pre-compute APC bin for histogram (based on last APC)
        const apcValue = row[apcColIdx].replace(/[^\d]/g, '');
        if (apcValue !== '') {
            const apc = parseInt(apcValue);
            row.__apcBin = apcBins.length - 2;
            for (let j = 0; j < apcBins.length - 1; j++) {
                if (apc >= apcBins[j] && apc <= apcBins[j + 1]) {
                    row.__apcBin = j;
                    break;
                }
            }
        } else {
            row.__apcBin = -1;
        }

        data.push(row);
    }

    console.timeEnd('parseCSV');
    return {
        data,
        allHeadersText,
        defaultVisibleHeaders,
        mandatoryHeaders,
        apcBins,
        apcColIdx,
        yearColIndices: yearCols.map((_, i) => 3 + i),
    };
}

function splitCSVLine(line) {
    const result = [];
    let current = '';
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
        const ch = line[i];
        if (ch === '"') {
            if (inQuotes && i + 1 < line.length && line[i + 1] === '"') {
                current += '"';
                i++;
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
    return result.map(f => f.trim().replace(/^"|"$/g, ''));
}

$(document).ready(function () {
    const ALL_PUBLISHERS_SOURCE = 'data/APC_all.csv';
    const DEFAULT_DATA_SOURCE = 'data/APC_PLOS.csv';
    let dataTable;
    let currentDataSource = null;
    let currentDatasetLabel = '';
    let currentPublisher = 'all';
    let currentApcColIdx = 3; // Will be updated per dataset
    let isAllPublishersMode = true;

    localStorage.removeItem('apc_global_state_v1');

    DataTable.type('num', 'className', 'dt-body-right');
    DataTable.type('num-fmt', 'className', 'dt-body-right');

    let currentMinAPC = '0';
    let currentMaxAPC = '5000';
    let apcSearchRegistered = false;
    let currentBusinessModelFilter = 'all';
    let lastHistogramSnapshot = null;
    let cachedApcBins = generateApcBins(APC_HISTOGRAM_BINS);
    let searchDebounceTimer = null;
    let fixedHeaderResizeHandler = null;

    // Publisher button click handlers
    $('.publisher-button').on('click', function () {
        const publisher = $(this).data('publisher');
        $('.publisher-button').removeClass('active');
        $(this).addClass('active');
        currentPublisher = publisher;

        if (publisher === 'all') {
            currentDataSource = ALL_PUBLISHERS_SOURCE;
            currentDatasetLabel = 'All Publishers';
            isAllPublishersMode = true;
        } else {
            const safeName = publisher.replace(/ /g, '_');
            currentDataSource = `data/APC_${safeName}.csv`;
            currentDatasetLabel = publisher;
            isAllPublishersMode = false;
        }
        loadTable(currentDataSource);
    });

    // Business model (OA status) filter buttons
    $('#allBusinessModels').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            currentBusinessModelFilter = 'all';
            dataTable.column(2).search('').draw();
        }
    });
    $('#oaBusinessModel').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            currentBusinessModelFilter = 'OA';
            dataTable.column(2).search('OA', false, false).draw();
        }
    });
    $('#hybridBusinessModel').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            currentBusinessModelFilter = 'Hybrid';
            dataTable.column(2).search('Hybrid', false, false).draw();
        }
    });

    // APC distribution
    function calculateAPCDistribution(data) {
        const distribution = Array(cachedApcBins.length - 1).fill(0);
        data.forEach(row => {
            if (row.__apcBin !== undefined && row.__apcBin >= 0) {
                distribution[row.__apcBin]++;
            }
        });
        return {bins: cachedApcBins, distribution};
    }

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
                bar.append($('<div>').addClass('apc-histogram-label').text(counts[i]));
            }
            histogramContainer.append(bar);
        }
    }

    function refreshHistogramFromTable(tableApi) {
        const filteredData = tableApi.rows({search: 'applied'}).data().toArray();
        const distribution = calculateAPCDistribution(filteredData);
        renderHistogram(distribution);
    }

    function refreshCountsFromTable(tableApi) {
        // Temporarily clear business model filter to count all
        tableApi.column(2).search('');
        const allRows = tableApi.rows({search: 'applied'}).data().toArray();

        if (currentBusinessModelFilter !== 'all') {
            tableApi.column(2).search(currentBusinessModelFilter, false, false);
        }

        let businessConsidered = 0;
        const businessModelCounts = {'OA': 0, 'Hybrid': 0};

        allRows.forEach((row) => {
            if (!rowPassesApcFilter(row)) return;
            businessConsidered++;
            const bm = row && row[2] ? String(row[2]) : '';
            if (bm === 'OA') businessModelCounts['OA']++;
            else if (bm === 'Hybrid') businessModelCounts['Hybrid']++;
        });

        $('#allBusinessModels').text('All OA Status (' + businessConsidered + ')');
        $('#oaBusinessModel').text('OA (' + (businessModelCounts['OA'] || 0) + ')');
        $('#hybridBusinessModel').text('Hybrid (' + (businessModelCounts['Hybrid'] || 0) + ')');
    }

    function rowPassesApcFilter(row) {
        if (!row) return false;
        if (currentMinAPC !== '0' || currentMaxAPC !== '5000') {
            const apcRaw = row[currentApcColIdx] ? String(row[currentApcColIdx]) : '';
            const apcValue = apcRaw.replace(/[^\d]/g, '');
            if (apcValue === '') return false;
            const apc = parseInt(apcValue, 10);
            const minApc = parseInt(currentMinAPC, 10);
            const maxApc = parseInt(currentMaxAPC, 10);
            if (maxApc === 5000) {
                if (apc < minApc) return false;
            } else {
                if (apc < minApc || apc > maxApc) return false;
            }
        }
        return true;
    }

    function updateApcLabel() {
        if (currentMinAPC === '0' && currentMaxAPC === '5000') {
            $('#apcValue').text('All APCs');
        } else if (currentMinAPC === '0') {
            $('#apcValue').text('≤ ' + currentMaxAPC + ' €');
        } else if (currentMaxAPC === '5000') {
            $('#apcValue').text('≥ ' + currentMinAPC + ' €');
        } else {
            $('#apcValue').text(currentMinAPC + ' € - ' + currentMaxAPC + ' €');
        }
    }

    function updateRangeSliderBackground() {
        const min = parseInt(currentMinAPC);
        const max = parseInt(currentMaxAPC);
        const percentMin = (min / 5000) * 100;
        const percentMax = (max / 5000) * 100;
        const minSlider = $('#apcSliderMin')[0];
        if (minSlider) {
            minSlider.style.setProperty('--min-percent', percentMin + '%');
            minSlider.style.setProperty('--max-percent', percentMax + '%');
        }
    }

    // APC sliders
    $('#apcSliderMin').off('input').on('input', function () {
        let minVal = parseInt($(this).val());
        let maxVal = parseInt($('#apcSliderMax').val());
        if (minVal > maxVal) { minVal = maxVal; $(this).val(minVal); }
        currentMinAPC = String(minVal);
        updateApcLabel();
        updateRangeSliderBackground();
        if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
        searchDebounceTimer = setTimeout(function () { if (dataTable) dataTable.draw(); }, 20);
    });

    $('#apcSliderMax').off('input').on('input', function () {
        let maxVal = parseInt($(this).val());
        let minVal = parseInt($('#apcSliderMin').val());
        if (maxVal < minVal) { maxVal = minVal; $(this).val(maxVal); }
        currentMaxAPC = String(maxVal);
        updateApcLabel();
        updateRangeSliderBackground();
        if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
        searchDebounceTimer = setTimeout(function () { if (dataTable) dataTable.draw(); }, 20);
    });

    async function fetchCSVFile(csvFile) {
        try {
            const response = await fetch(csvFile);
            if (!response.ok) {
                console.error(`Failed to fetch ${csvFile}: ${response.statusText}`);
                return {data: []};
            }
            const csvText = await response.text();
            return parseCSV(csvText, csvFile === ALL_PUBLISHERS_SOURCE);
        } catch (error) {
            console.error('Error fetching CSV file:', error);
            return {data: []};
        }
    }

    async function loadTable(dataSource) {
        console.time('loadTable');
        try {
            let currentSearch = '';
            if (dataTable) {
                console.time('DataTable cleanup');
                currentSearch = dataTable.search();

                if ($('.dtcc-dropdown').length > 0) {
                    $(document).trigger('click');
                    await new Promise(resolve => {
                        const checkRemoved = setInterval(() => {
                            if ($('.dtcc-dropdown').length === 0) { clearInterval(checkRemoved); resolve(); }
                        }, 5);
                        setTimeout(() => { clearInterval(checkRemoved); resolve(); }, 200);
                    });
                }

                dataTable.off('column-visibility.dt');
                if (fixedHeaderResizeHandler) {
                    $(window).off('resize', fixedHeaderResizeHandler);
                    fixedHeaderResizeHandler = null;
                }

                try {
                    var fhInstance = dataTable.settings()[0]._fixedHeader;
                    if (fhInstance && typeof fhInstance.destroy === 'function') fhInstance.destroy();
                } catch (e) {}

                try {
                    $(window).off('resize.dtr orientationchange.dtr');
                    dataTable.off('.dtr');
                    $(dataTable.table().body()).off('.dtr');
                    $(dataTable.table().node()).removeClass('dtr-inline collapsed');
                } catch (e) {}

                dataTable.destroy(false);
                $('#journalTable tbody').empty();
                console.timeEnd('DataTable cleanup');
            }

            if (!apcSearchRegistered) {
                $.fn.dataTable.ext.search.push(function (settings, data) {
                    if (!settings.nTable || settings.nTable.id !== 'journalTable') return true;
                    if (currentMinAPC === '0' && currentMaxAPC === '5000') return true;
                    const apcRaw = data && data[currentApcColIdx] ? data[currentApcColIdx] : '';
                    const apcValue = apcRaw.replace(/[^\d]/g, '');
                    if (apcValue === '') return false;
                    const apc = parseInt(apcValue, 10);
                    const minApc = parseInt(currentMinAPC, 10);
                    const maxApc = parseInt(currentMaxAPC, 10);
                    if (maxApc === 5000) return apc >= minApc;
                    return apc >= minApc && apc <= maxApc;
                });
                apcSearchRegistered = true;
            }

            $('#journalTable').parent().append('<p id="loading-indicator">Loading data...</p>');

            console.time('fetchCSVFile');
            const parsed = await fetchCSVFile(dataSource);
            console.timeEnd('fetchCSVFile');
            const {data: tableData, allHeadersText, defaultVisibleHeaders, mandatoryHeaders, apcBins, apcColIdx, yearColIndices} = parsed;

            currentApcColIdx = apcColIdx;

            if (apcBins) cachedApcBins = apcBins;

            $('#loading-indicator').remove();

            if (tableData && tableData.length > 0) {
                console.time('DataTable initialization');
                const desiredVisible = allHeadersText.map(h => mandatoryHeaders.has(h) || defaultVisibleHeaders.has(h));
                const toHide = desiredVisible.map((v, i) => (v ? null : i)).filter(i => i !== null);
                let firstDrawCompleted = false;

                // Build buttons array: always include CSV download
                const buttonsConfig = [
                    {
                        extend: 'csvHtml5',
                        text: '<i class="fas fa-download"></i> Download CSV',
                        title: 'APC_Explorer',
                        exportOptions: {columns: ':visible'}
                    }
                ];

                // Only add show/hide columns button if not in "All Publishers" mode (which has no year columns)
                if (!isAllPublishersMode && yearColIndices && yearColIndices.length > 0) {
                    buttonsConfig.push({
                        extend: 'colvis',
                        text: '<i class="fas fa-columns"></i> Show/Hide year columns',
                        columns: ':not(.noVis)',
                        postfixButtons: [
                            {
                                text: 'Reset columns',
                                className: 'dt-button--reset',
                                action: function (e, dt) {
                                    try {
                                        allHeadersText.forEach(function (header, idx) {
                                            var mustShow = mandatoryHeaders.has(header) || defaultVisibleHeaders.has(header);
                                            dt.column(idx).visible(mustShow, false);
                                        });
                                        dt.columns.adjust().draw(false);
                                        if (dt.state && typeof dt.state.save === 'function') dt.state.save();
                                    } catch (err) {}
                                }
                            }
                        ]
                    });
                }

                dataTable = $('#journalTable').DataTable({
                    data: tableData,
                    scrollX: false,
                    scroller: true,
                    paging: false,
                    deferRender: true,
                    search: {
                        smart: true,
                        regex: false,
                        caseInsensitive: true,
                        search: currentSearch
                    },
                    columnControl: ['order', 'searchDropdown'],
                    ordering: {indicators: false, handler: false},
                    info: true,
                    dom: 'Bift',
                    stateSave: true,
                    stateDuration: -1,
                    stateSaveCallback: function (settings, data) {
                        try {
                            const stateToSave = {
                                time: data.time, start: data.start, length: data.length,
                                order: data.order, search: data.search, columns: data.columns, custom: data.custom
                            };
                            localStorage.setItem('apc_global_state_v1', JSON.stringify(stateToSave));
                        } catch (e) {}
                    },
                    stateLoadCallback: function () {
                        try {
                            const raw = localStorage.getItem('apc_global_state_v1');
                            return raw ? JSON.parse(raw) : null;
                        } catch (e) { return null; }
                    },
                    fixedHeader: window.innerWidth > FIXEDHEADER_BREAKPOINT,
                    buttons: buttonsConfig,
                    stateSaveParams: function (settings, data) {
                        data.custom = data.custom || {};
                        data.custom.apcMin = currentMinAPC;
                        data.custom.apcMax = currentMaxAPC;
                    },
                    stateLoadParams: function (settings, data) {
                        if (data && data.custom) {
                            if (data.custom.apcMin !== undefined) {
                                currentMinAPC = String(data.custom.apcMin);
                                $('#apcSliderMin').val(currentMinAPC);
                            }
                            if (data.custom.apcMax !== undefined) {
                                currentMaxAPC = String(data.custom.apcMax);
                                $('#apcSliderMax').val(currentMaxAPC);
                            }
                            updateApcLabel();
                            updateRangeSliderBackground();
                        }
                    },
                    autoWidth: true,
                    responsive: true,
                    columnDefs: [
                        {targets: [2, apcColIdx], columnControl: ['order']},
                        {targets: [1], columnControl: ['order', {
                            extend: 'dropdown', icon: 'search', className: 'searchList', content: ['searchList']
                        }]},
                        {targets: [0, 2, apcColIdx], className: 'noVis'},
                        {targets: 0, responsivePriority: 1},
                        {targets: 1, responsivePriority: 2},
                        {targets: apcColIdx, responsivePriority: 1000000},
                        ...(toHide.length ? [{targets: toHide, visible: false}] : [])
                    ],
                    language: {
                        info: "Displaying all _TOTAL_ journals",
                        infoEmpty: "No journals available",
                        emptyTable: "No journal data available",
                        search: "",
                        zeroRecords: 'No matching journals found.'
                    },
                    rowCallback: function (row, data) {
                        const publisher = data[1];
                        if (!publisher) return;
                        const $row = $(row);
                        // Remove all publisher classes
                        $row[0].className = $row[0].className.replace(/\bpublisher-\S+/g, '').trim();
                        // Add publisher class
                        const safePub = publisher.replace(/ /g, '_');
                        $row.addClass('publisher-' + safePub);
                    },
                    preDrawCallback: function () {
                        if (!firstDrawCompleted) {
                            var table = this.api();
                            table.columns().every(function (index) {
                                this.settings()[0].aoColumns[index].bSearchable = this.visible();
                            });
                            table.rows().invalidate();
                            firstDrawCompleted = true;
                        }
                    },
                    drawCallback: function () {
                        var table = this.api();
                        refreshHistogramFromTable(table);
                        refreshCountsFromTable(table);
                    },
                    initComplete: function () {
                        console.timeEnd('DataTable initialization');
                        var table = this.api();

                        $('.dt-input').attr('placeholder', 'Search journals...');

                        // Sync business model filter buttons
                        $('.business-model-button').removeClass('active');
                        const bmSearch = table.column(2).search();
                        if (!bmSearch) {
                            $('#allBusinessModels').addClass('active');
                            currentBusinessModelFilter = 'all';
                        } else if (bmSearch === 'OA') {
                            $('#oaBusinessModel').addClass('active');
                            currentBusinessModelFilter = 'OA';
                        } else if (bmSearch === 'Hybrid') {
                            $('#hybridBusinessModel').addClass('active');
                            currentBusinessModelFilter = 'Hybrid';
                        } else {
                            $('#allBusinessModels').addClass('active');
                            currentBusinessModelFilter = 'all';
                        }

                        table.on('column-visibility.dt', function (e, settings, column, state) {
                            settings.aoColumns[column].bSearchable = state;
                            table.rows().invalidate().draw();
                        });

                        updateRangeSliderBackground();

                        var fixedHeaderDebounceTimer = null;
                        fixedHeaderResizeHandler = function () {
                            clearTimeout(fixedHeaderDebounceTimer);
                            fixedHeaderDebounceTimer = setTimeout(function () {
                                if (window.innerWidth <= FIXEDHEADER_BREAKPOINT) {
                                    table.fixedHeader.disable();
                                } else {
                                    table.fixedHeader.enable();
                                }
                            }, 150);
                        };
                        $(window).on('resize', fixedHeaderResizeHandler);

                        table.columns.adjust().responsive.recalc();
                    }
                });
            } else if (tableData) {
                $('#journalTable').parent().append('<p>No data found in CSV after parsing headers.</p>');
            }
        } catch (error) {
            console.error('Error loading or processing CSV files:', error);
            $('#journalTable').parent().append('<p style="color:red;">Could not load data. Check that APC CSV files exist in the data folder.</p>');
        } finally {
            console.timeEnd('loadTable');
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

    modalTriggers.on('click', function () { openModal(aboutModal); });
    $('#aboutLink').on('click', function (event) { event.preventDefault(); openModal(aboutModal); });
    closeModalButton.on('click', function () { closeModal(); });
    $('.modal').on('click', function (event) { if ($(event.target).is('.modal')) closeModal(); });
    $(document).on('keydown', function (event) { if (event.key === 'Escape' && $('.modal.show').length) closeModal(); });

    // Load default table
    currentDataSource = DEFAULT_DATA_SOURCE;
    currentDatasetLabel = 'All Publishers';
    isAllPublishersMode = true;
    loadTable(DEFAULT_DATA_SOURCE);
});
