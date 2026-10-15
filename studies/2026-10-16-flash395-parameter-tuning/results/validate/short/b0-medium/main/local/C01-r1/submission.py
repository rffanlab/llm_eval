```python
def invoice_total(lines):
    total = 0
    for record in lines:
        if not isinstance(record, dict):
            continue
        if record.get("status") != "paid":
            continue
        qty = record.get("qty")
        unit_cents = record.get("unit_cents")
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 0:
            continue
        if isinstance(unit_cents, bool) or not isinstance(unit_cents, int) or unit_cents < 0:
            continue
        total += qty * unit_cents
    return total
```