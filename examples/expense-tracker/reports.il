// reports.il — Reporting and export
domain reports:

@level: mid
feature Summary:
  route GET /reports/summary:
    input: from_date, to_date, group_by? (day|week|month, default month)
    action: aggregate Expenses by period and category for current user
    returns: { period, total, by_category: { category, amount, count }[] }[]

  route GET /reports/trends:
    input: months? (default 6)
    action: compute month-over-month spend trend per category
    algorithm: simple moving average over rolling window
    returns: { category, trend: { month, amount }[], avg, change_pct }[]

feature Export:
  route GET /reports/export:
    input: from_date, to_date, format (csv|json, default csv)
    action: stream all Expenses in date range for current user
    returns: file download (Content-Disposition: attachment)

  @level: low
  config StreamExport:
    strategy: cursor-based pagination, stream rows directly to response
    chunk_size: 500
    reason: avoid loading all rows into memory for large exports
