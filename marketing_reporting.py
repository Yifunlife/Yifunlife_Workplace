"""Shared advertising definition for operation and executive reporting."""

ADVERTISING_EXPENSE_TYPES = ('广告费', '展位费')


def advertising_records(db, start, end, project_id=None):
    """Calendar dates, active records only; currencies retain their original units."""
    rows = db.execute(
        "SELECT * FROM marketing_spends WHERE status='active' "
        "AND expense_type IN (?,?) AND record_date>=? AND record_date<=? "
        "ORDER BY record_date DESC,number",
        (*ADVERTISING_EXPENSE_TYPES, start, end),
    )
    return [dict(row) for row in rows
            if not project_id or row['project_id'] == project_id]
