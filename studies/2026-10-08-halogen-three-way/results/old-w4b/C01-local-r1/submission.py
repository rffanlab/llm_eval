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
        if type(qty) is not int or qty < 0:
            continue
        if type(unit_cents) is not int or unit_cents < 0:
            continue
        total += qty * unit_cents
    return total
```