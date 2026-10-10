```python
def invoice_total(lines):
    total = 0
    for line in lines:
        if not isinstance(line, dict):
            continue
        if line.get("status") != "paid":
            continue
        qty = line.get("qty")
        unit_cents = line.get("unit_cents")
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 0:
            continue
        if not isinstance(unit_cents, int) or isinstance(unit_cents, bool) or unit_cents < 0:
            continue
        total += qty * unit_cents
    return total
```