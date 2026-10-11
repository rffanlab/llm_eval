```python
def invoice_total(lines):
    total = 0
    for line in lines:
        if not isinstance(line, dict):
            continue
        status = line.get("status")
        qty = line.get("qty")
        unit_cents = line.get("unit_cents")
        if status != "paid":
            continue
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 0:
            continue
        if isinstance(unit_cents, bool) or not isinstance(unit_cents, int) or unit_cents < 0:
            continue
        total += qty * unit_cents
    return total
```