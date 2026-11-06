// ApplyReviewedChanges.gs — WhereToPublish unified review workflow.
//
// Processes reviewed rows of the two review tabs (Agent_suggestions, Disagreements):
//   "approve" → verifies the recorded target cell in the data tab and writes the
//               suggested value into that single cell, then archives the row
//   "reject"  → archives the row without any data change
//   "pending" → left untouched
//
// Each review row carries the exact cell to change (data_tab, target_row,
// target_col) plus the verification values (journal, field, current_value),
// so approvals never scan whole data tabs: the script checks that the target
// row still belongs to the journal, that the column header still matches, and
// that the cell still holds the recorded current value (or the already-applied
// suggested value — an approvals re-run is idempotent) before writing.
//
// Processed rows are archived in <tab>_processed and deleted from the review
// tab (descending, so row indices stay valid). Approvals whose verification
// fails (moved rows, changed values, missing target) stay in the review tab
// and are reported, and applied rows are re-verified idempotently, so the run
// can be safely repeated after any interruption.
//
// Install: Extensions → Apps Script → paste this file → save. Run onOpen once
// to register the menu. Run via: WhereToPublish → Apply Reviewed Changes.

const REVIEW_TABS = ["Agent_suggestions", "Disagreements"];
const ARCHIVE_SUFFIX = "_processed";
const STATUS_COLUMN = "Status";
const DISAGREEMENTS_TAB = "Disagreements";
const AGENT_SUGGESTIONS_TAB = "Agent_suggestions";

// Columns required in every review tab (shared apply-row schema, see
// scripts/review_common.py of the WhereToPublish repo).
const REQUIRED_COLUMNS = [
  "journal", "field", "current_value", "suggested_value",
  "suggestion_type", "data_tab", "target_row", "target_col",
];

const FLAGGED_FOR_REMOVAL = "FLAGGED_FOR_REMOVAL";

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("Review")
    .addItem("Review Disagreements", "reviewDisagreements")
    .addItem("Review Agent suggestions", "reviewAgentSuggestions")
    .addSeparator()
    .addItem("Apply Reviewed Changes", "applyReviewedChanges")
    .addToUi();
}

// Menu shortcuts opening the review tabs.
function reviewDisagreements() {
  activateReviewTab_(DISAGREEMENTS_TAB);
}

function reviewAgentSuggestions() {
  activateReviewTab_(AGENT_SUGGESTIONS_TAB);
}

function activateReviewTab_(tabName) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const tab = ss.getSheetByName(tabName);
  if (!tab) {
    SpreadsheetApp.getUi().alert("Tab '" + tabName + "' not found — run the upload step first.");
    return;
  }
  tab.setActiveRange(tab.getRange(1, 1));
  if (typeof tab.activate === "function") tab.activate();
}

// Backwards-compatible alias for menus created with the previous script.
function applyReviewedSuggestions() {
  applyReviewedChanges();
}

function applyReviewedChanges() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const parts = [];
  let hadIssues = false;
  for (const tabName of REVIEW_TABS) {
    const summary = processReviewTab_(ss, tabName);
    if (summary) {
      parts.push(summary.title);
      if (summary.issues.length) hadIssues = true;
    }
  }
  const text = parts.length ? parts.join("\n\n") : "Nothing to process.";
  SpreadsheetApp.getUi().alert(text + (hadIssues ? "\n\nSee per-tab issue lists above." : ""));
}

// Processes one review tab; returns null when the tab does not exist or has no
// reviewed (approve/reject) rows.
function processReviewTab_(ss, tabName) {
  const reviewTab = ss.getSheetByName(tabName);
  if (!reviewTab || reviewTab.getLastRow() < 1) return null;

  const data = reviewTab.getDataRange().getValues();
  const headers = data[0];
  const col = buildColumnIndex_(headers);

  const required = [STATUS_COLUMN].concat(REQUIRED_COLUMNS);
  const missing = required.filter(function (name) { return col[name] === undefined; });
  if (missing.length) {
    return {
      title: "'" + tabName + "': missing required columns " + missing.join(", ") +
        " — re-upload the tab with the shared review-row schema.",
      issues: [],
    };
  }

  // Collect reviewed rows ((approve|reject) and not entirely empty).
  const rowIndexes = [];
  const statuses = [];
  const rowsToArchive = [];
  for (let i = 1; i < data.length; i++) {
    const row = data[i];
    if (isEmptyRow_(row)) continue;
    const status = normalize_(row[col[STATUS_COLUMN]]);
    if (status !== "approve" && status !== "reject") continue;
    rowIndexes.push(i);
    statuses.push(status);
    rowsToArchive.push(row);
  }
  if (!rowIndexes.length) return null;

  const procTab = getOrCreateArchiveTab_(ss, tabName + ARCHIVE_SUFFIX, headers);

  const cache = {};  // data_tab -> {sheet, header, journalCol}
  const errors = [];
  let applied = 0;
  let rejected = 0;
  // Only rows fully processed (applied or rejected) are archived and deleted;
  // approvals whose verification failed stay in the review tab for the human.
  const processedIndexes = [];

  for (let i = 0; i < rowIndexes.length; i++) {
    const status = statuses[i];
    const row = rowsToArchive[i];
    if (status === "reject") {
      rejected++;
      processedIndexes.push(i);
      continue;
    }
    try {
      if (!applyTargetedChange_(ss, cache, col, row)) continue;  // should not happen
      applied++;
      processedIndexes.push(i);
    } catch (e) {
      errors.push("Row " + (rowIndexes[i] + 1) + ": " + e.message);
    }
  }

  // Archive processed rows in one write, then delete them from the review
  // tab in descending order (higher rows first — indices stay valid).
  const archivedRows = processedIndexes.map(function (i) { return rowsToArchive[i]; });
  appendRows_(procTab, archivedRows);
  for (let k = processedIndexes.length - 1; k >= 0; k--) {
    const i = processedIndexes[k];
    reviewTab.deleteRow(rowIndexes[i] + 1);
  }

  const status =
    "Applied: " + applied + " | Rejected: " + rejected + " | Archived: " + archivedRows.length +
    " | Left for review: " + (rowIndexes.length - processedIndexes.length) +
    (errors.length ? "\nIssues:\n" + errors.join("\n") : "");
  return { title: "'" + tabName + "'\n" + status, issues: errors };
}

// Verifies the target cell recorded in the review row and writes the new value.
// Throws on any verification failure; returns true when the value was written
// (or was already in place — idempotent re-runs).
function applyTargetedChange_(ss, cache, col, row) {
  const journal = row[col["journal"]];
  const field = row[col["field"]];
  const tabName = String(row[col["data_tab"]] || "").trim();
  const rowNum = parseInt(String(row[col["target_row"]]).trim(), 10);
  const colNum = parseInt(String(row[col["target_col"]]).trim(), 10);
  const suggestionType = normalize_(row[col["suggestion_type"]]);

  if (!tabName || !rowNum || !colNum) {
    throw new Error(
      "no target cell recorded (data_tab/target_row/target_col) for journal '" +
      journal + "' — resolve manually.");
  }

  const ctx = getDataTabContext_(ss, cache, tabName, field);
  const headerName = colNum - 1 < ctx.header.length ? ctx.header[colNum - 1] : "";
  if (normalize_(String(headerName)) !== normalize_(String(field))) {
    throw new Error(
      "column header at " + tabName + "!" + a1_(rowNum, colNum) + " is '" + headerName +
      "' but the row expects '" + field + "' — the tab layout changed; resolve manually.");
  }

  const journalInCell = String(
    ctx.sheet.getRange(rowNum, ctx.journalCol + 1).getValue());
  if (normalize_(journalInCell) !== normalize_(String(journal))) {
    throw new Error(
      "row " + tabName + "!" + a1_(rowNum, ctx.journalCol + 1) + " holds journal '" + journalInCell +
      "' instead of '" + journal + "' — rows moved; resolve manually.");
  }

  const cell = ctx.sheet.getRange(rowNum, colNum);
  const currentValue = normalize_(String(cell.getValue()));
  // Journal removal is flagged on the Journal column (the data pipeline performs
  // the actual removal); every other type writes the suggested value verbatim.
  const newValue = suggestionType === "remove" ? FLAGGED_FOR_REMOVAL : String(row[col["suggested_value"]]);
  if (!normalize_(newValue)) {
    throw new Error(
      "empty suggested_value for journal '" + journal + "' (" + field +
      ") — fill in the value to apply before approving.");
  }
  const recordedCurrent = normalize_(String(row[col["current_value"]]));
  if (normalize_(newValue) === currentValue) return true;  // already applied — idempotent re-run
  if (currentValue !== recordedCurrent) {
    throw new Error(
      tabName + "!" + a1_(rowNum, colNum) + " holds '" + cell.getValue() +
      "' but the row recorded current_value '" + row[col["current_value"]] +
      "' — the cell changed since the report was generated; resolve manually.");
  }
  cell.setValue(newValue);
  return true;
}

// Cached per-data-tab context: sheet handle, header row, Journal column index.
// One header read per tab per run instead of one full-tab scan per edit.
function getDataTabContext_(ss, cache, tabName, field) {
  const key = String(tabName);
  if (key in cache) {
    const cached = cache[key];
    if (cached === null) throw new Error("data tab not found: '" + tabName + "'");
    return cached;
  }
  const sheet = ss.getSheetByName(tabName);
  if (!sheet || sheet.getLastRow() < 1) {
    cache[key] = null;
    throw new Error("data tab not found: '" + tabName + "'");
  }
  const headerRow = sheet.getRange(1, 1, 1, Math.max(sheet.getLastColumn(), 1)).getValues()[0];
  const journalCol = headerRow.findIndex(function (name) {
    return normalize_(String(name)) === "journal";
  });
  if (journalCol === -1) {
    cache[key] = null;
    throw new Error("data tab '" + tabName + "' has no 'Journal' header column.");
  }
  const ctx = { sheet: sheet, header: headerRow, journalCol: journalCol };
  cache[key] = ctx;
  return ctx;
}

function getOrCreateArchiveTab_(ss, tabName, headers) {
  let tab = ss.getSheetByName(tabName);
  if (!tab) {
    tab = ss.insertSheet(tabName);
    tab.appendRow(headers);
    return tab;
  }
  if (tab.getLastRow() === 0 || tab.getLastColumn() === 0) {
    tab.appendRow(headers);
    return tab;
  }
  // Extend the header row when the schema gained trailing columns (same
  // leading order), so archived rows stay aligned with their headers.
  const width = Math.max(tab.getLastColumn(), headers.length);
  if (width > tab.getMaxColumns()) tab.insertColumnsAfter(tab.getMaxColumns(), width - tab.getMaxColumns());
  const existing = tab.getLastColumn() > 0
    ? tab.getRange(1, 1, 1, tab.getLastColumn()).getValues()[0] : [];
  for (let c = existing.length; c < headers.length; c++) {
    tab.getRange(1, c + 1).setValue(headers[c]);
  }
  return tab;
}

// Batch-append rows to the archive tab (one write instead of one per row).
function appendRows_(tab, rows) {
  if (!rows.length) return;
  const width = Math.max.apply(null, rows.map(function (r) { return r.length; }));
  while (tab.getMaxColumns() < width) {
    tab.insertColumnsAfter(tab.getMaxColumns(), width - tab.getMaxColumns());
  }
  const start = tab.getLastRow() + 1;
  tab.getRange(start, 1, rows.length, width).setValues(rows);
}

function buildColumnIndex_(headers) {
  const col = {};
  headers.forEach(function (h, i) {
    if (String(h).trim() !== "") col[String(h).trim()] = i;
  });
  return col;
}

function normalize_(value) {
  return String(value === null || value === undefined ? "" : value).trim().toLowerCase();
}

function isEmptyRow_(row) {
  return row.every(function (cell) { return normalize_(cell) === ""; });
}

function a1_(row, col) {
  let n = col;
  let label = "";
  while (n > 0) {
    const rem = (n - 1) % 26;
    label = String.fromCharCode(65 + rem) + label;
    n = Math.floor((n - rem - 1) / 26);
  }
  return label + row;
}
