"""
app/guardrails/masking.py - Sensitive column masking for privacy defense.
Masks columns like email and phone numbers in query outputs and samples.
Supports configuration control, table-qualified matching, and value pattern inspection.
"""

import re
from typing import Any, List, Dict, Optional


def mask_email(val: str) -> str:
    """Masks email: e.g. 'john.smith@example.com' -> 'j***@example.com'."""
    if not val or not isinstance(val, str) or "@" not in val:
        return val
    parts = val.split("@", 1)
    user = parts[0]
    domain = parts[1]
    masked_user = user[0] + "***" if len(user) > 0 else "***"
    return f"{masked_user}@{domain}"


def mask_phone(val: str) -> str:
    """Masks phone: preserves last 4 digits e.g. '+1-555-234-5678' -> '***-***-5678'."""
    if not val or not isinstance(val, str):
        return val
    digits = re.sub(r"\D", "", val)
    if len(digits) >= 4:
        last4 = digits[-4:]
        return f"***-***-{last4}"
    return "***-***-****"


def mask_value(column_name: str, val: Any) -> Any:
    """Applies specific column mask depending on column name or string pattern."""
    if val is None:
        return None
    val_str = str(val)
    col_lower = column_name.lower()
    if "email" in col_lower:
        return mask_email(val_str)
    if "phone" in col_lower:
        return mask_phone(val_str)
    return val


def mask_rows(
    columns: List[str],
    rows: List[List[Any]],
    sensitive_columns: Optional[List[str]] = None,
    enabled: bool = True,
) -> List[List[Any]]:
    """
    Applies masking to row data where column names match sensitive definitions,
    or where cell values match sensitive email patterns (handles aliased and joined projections).
    """
    if not enabled or not rows or not columns:
        return rows

    # Normalize sensitive column definitions (e.g. ['customers.email', 'customers.phone'] -> ['email', 'phone'])
    sens_list = sensitive_columns or ["email", "phone"]
    sens_names = set()
    for s in sens_list:
        clean = s.strip().lower()
        sens_names.add(clean)
        if "." in clean:
            sens_names.add(clean.split(".")[-1])

    # Find column indices that match configured sensitive column names
    mask_indices = {}
    for idx, col in enumerate(columns):
        col_clean = col.split(".")[-1].lower()
        if col_clean in sens_names or any(s in col_clean for s in ("email", "phone")):
            mask_indices[idx] = col_clean

    masked_rows = []
    for row in rows:
        new_row = list(row)
        for idx in range(len(new_row)):
            val = new_row[idx]
            if idx in mask_indices:
                new_row[idx] = mask_value(mask_indices[idx], val)
            elif isinstance(val, str) and "@" in val and re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", val.strip()):
                # Value-inspection fallback for aliased email columns (e.g. SELECT email AS contact_info)
                new_row[idx] = mask_email(val.strip())
        masked_rows.append(new_row)

    return masked_rows
