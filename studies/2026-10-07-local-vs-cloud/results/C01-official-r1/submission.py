def invoice_total(lines):
    total = 0
    for line in lines:
        if not isinstance(line, dict):
            continue
        if line.get("status") != "paid":
            continue

        qty = line.get("qty")
        unit_cents = line.get("unit_cents")

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