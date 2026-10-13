def invoice_total(lines):
    total = 0
    for record in lines:
        if not isinstance(record, dict):
            continue
        if record.get("status") != "paid":
            continue
        qty = record.get("qty")
        unit_cents = record.get("unit_cents")
        if (
            isinstance(qty, int)
            and not isinstance(qty, bool)
            and qty >= 0
            and isinstance(unit_cents, int)
            and not isinstance(unit_cents, bool)
            and unit_cents >= 0
        ):
            total += qty * unit_cents
    return total