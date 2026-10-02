// Backend CSV contract; consumes export_actual_journal, never calculates metrics.
export const VERSION = "actual-journal-export-v1";
export const COLUMNS = Object.freeze([
  "contract_version", "mode", "data_mode", "trade_id", "revision", "ticker", "status",
  "primary_strategy", "signal_id", "exit_policy_snapshot", "planned_rr", "initial_stop",
  "current_stop", "initial_risk_idr", "provisional_risk_idr", "open_quantity",
  "remaining_cost_idr", "realized_pnl_idr", "realized_r", "fee_total_idr", "fee_quality",
  "entry_finalized_at", "closed_at", "exit_session", "tags", "notes",
]);
const decimals = new Set(["planned_rr", "initial_stop", "current_stop", "initial_risk_idr",
  "provisional_risk_idr", "open_quantity", "remaining_cost_idr", "realized_pnl_idr",
  "realized_r", "fee_total_idr"]);
const structured = new Set(["exit_policy_snapshot", "tags", "notes"]);

function cell(value, key) {
  let text = value == null ? "" : structured.has(key) ? JSON.stringify(value) : String(value);
  if (decimals.has(key) && value != null) {
    if (typeof value !== "string" || !/^-?\d+(\.\d+)?$/.test(value)) {
      throw new Error("export_decimal_string_required:" + key);
    }
  } else if (/^[\s\u0000-\u001f\u007f]*[=+\-@]/u.test(text) || /^[\t\r\n]/.test(text)) {
    text = "'" + text;
  }
  return '"' + text.replaceAll('"', '""') + '"';
}

// Call per page, header=true only for the first page. Do not silently truncate
// when has_more=true. Multi-page exports require a quiescent journal (see docs).
export function actualJournalCsv(page, { header = true } = {}) {
  if (page.contract_version !== VERSION || page.mode !== "actual" ||
      !["fixture", "live"].includes(page.data_mode) || !Array.isArray(page.rows)) {
    throw new Error("invalid_actual_export_envelope");
  }
  const lines = header ? [COLUMNS.map(key => cell(key, "header")).join(",")] : [];
  for (const row of page.rows) {
    if (row.contract_version !== VERSION || row.mode !== "actual" ||
        row.data_mode !== page.data_mode || COLUMNS.some(key => !(key in row))) {
      throw new Error("invalid_actual_export_row");
    }
    lines.push(COLUMNS.map(key => cell(row[key], key)).join(","));
  }
  return lines.length ? lines.join("\r\n") + "\r\n" : "";
}
