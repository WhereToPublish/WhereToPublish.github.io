function parseCSV(csvText) {
    // We know the exact column order in the CSV:
    // 0: Journal, 1: Field, 2: Publisher, 3: Publisher type, 4: Business model,
    // 5: Institution, 6: Institution type, 7: Country, 8: Website, 9: APC Euros,
    // 10: Scimago Rank, 11: PCI partner
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
        'PCI partner'         // 11
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
            cols[11] || ''  // PCI partner
        ];

        data.push(row);
    }

    return {data, domains: Array.from(domains).sort(), allHeadersText, defaultVisibleHeaders, mandatoryHeaders};
}

$(document).ready(function () {
    let dataTable; // Variable to store the DataTable instance

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
            const filteredData = dataTable.rows({search: 'applied'}).data().toArray();
            const distribution = calculateAPCDistribution(filteredData);
            renderHistogram(distribution);
        }
    });

    // Business model filter buttons
    $('#allBusinessModels').on('click', function () {
        $('.business-model-button').removeClass('active');
        $(this).addClass('active');
        if (dataTable) {
            dataTable.column(4).search('').draw();
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
            const filteredData = dataTable.rows({search: 'applied'}).data().toArray();
            const distribution = calculateAPCDistribution(filteredData);
            renderHistogram(distribution);
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

    // APC slider filter
    $('#apcSlider').on('input', function () {
        const maxAPC = $(this).val();
        $('#apcValue').text(maxAPC === '10000' ? 'All APC' : '≤ ' + maxAPC + ' €');
        if (dataTable) {
            $.fn.dataTable.ext.search.push(
                function (settings, data/*, dataIndex*/) {
                    if (maxAPC === '10000') return true;
                    const apcValue = data[5].replace(/[^\d]/g, '');
                    if (apcValue === '') return true;
                    return parseInt(apcValue) <= parseInt(maxAPC);
                }
            );
            dataTable.draw();
            const filteredData = dataTable.rows({search: 'applied'}).data().toArray();
            const distribution = calculateAPCDistribution(filteredData);
            renderHistogram(distribution);
            $.fn.dataTable.ext.search.pop();
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
            $('#apcValue').text('All APC');

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
                            targets: 9,
                            render: function (data, type) {
                                if ((type === 'display' || type === 'filter') && data) {
                                    const url = data.startsWith('http') ? data : `https://${data}`;
                                    return `<a href="${url}" target="_blank" rel="noopener">${data}</a>`;
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

                        // Persist defaults if no saved preferences existed
                        if (!savedVis) {
                            saveVisibleColumns(table, allHeadersText, mandatoryHeaders);
                        }

                        // Search box updates histogram
                        $('.dataTables_filter input').on('keyup', function () {
                            const filteredData = table.rows({search: 'applied'}).data().toArray();
                            const distribution = calculateAPCDistribution(filteredData);
                            renderHistogram(distribution);
                        });

                        // Initialize histogram
                        const allData = table.rows().data().toArray();
                        const distribution = calculateAPCDistribution(allData);
                        renderHistogram(distribution);

                        // Compute counts for buttons
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
                            if (publisherType in publisherTypeCounts) publisherTypeCounts[publisherType]++;
                            if (businessModel in businessModelCounts) businessModelCounts[businessModel]++;
                        });

                        // Update buttons with counts
                        $('#allPublishers').text('All Publishers (' + allData.length + ')');
                        $('#forProfitPublishers').text('For-profit (' + (publisherTypeCounts['For-profit'] + publisherTypeCounts['For-profit on behalf of a society']) + ')');
                        $('#nonProfitPublishers').text('Non-profit (' + publisherTypeCounts['Non-profit'] + ')');
                        $('#universityPressPublishers').text('University Press (' + (publisherTypeCounts['University Press'] + publisherTypeCounts['University Press on behalf of a society']) + ')');

                        $('#allBusinessModels').text('All Business Models (' + allData.length + ')');
                        if (businessModelCounts['Diamond OA'] === 0) {
                            $('#diamondOABusinessModel').addClass('hidden');
                        } else {
                            let d = $('#diamondOABusinessModel');
                            d.removeClass('hidden').text('Diamond OA (' + businessModelCounts['Diamond OA'] + ')');
                        }
                        if (businessModelCounts['Gold OA'] === 0) {
                            $('#goldOABusinessModel').addClass('hidden');
                        } else {
                            let d = $('#goldOABusinessModel');
                            d.removeClass('hidden').text('Gold OA (' + businessModelCounts['Gold OA'] + ')');
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

                        // Show all button
                        var showAllButton = $('<button class="domain-filter-button">SHOW ALL</button>')
                            .on('click', function () {
                                table.column(1).search('');
                                table.draw();
                                domainFiltersContainer.find('.domain-filter-button').removeClass('active');
                                $(this).addClass('active');
                                const filteredData = table.rows({search: 'applied'}).data().toArray();
                                const distribution = calculateAPCDistribution(filteredData);
                                renderHistogram(distribution);
                            });
                        domainFiltersContainer.append(showAllButton);

                        // Domain filter buttons
                        domains.forEach(function (domainName) {
                            var button = $('<button class="domain-filter-button">' + domainName + '</button>')
                                .on('click', function () {
                                    var isActive = $(this).hasClass('active');
                                    table.column(1).search('');
                                    domainFiltersContainer.find('.domain-filter-button').removeClass('active');
                                    if (isActive) {
                                        showAllButton.addClass('active');
                                    } else {
                                        table.column(1).search('^' + domainName + '$', true, false);
                                        $(this).addClass('active');
                                    }
                                    table.draw();
                                    const filteredData = table.rows({search: 'applied'}).data().toArray();
                                    const distribution = calculateAPCDistribution(filteredData);
                                    renderHistogram(distribution);
                                });
                            domainFiltersContainer.append(button);
                        });
                        showAllButton.addClass('active');
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
