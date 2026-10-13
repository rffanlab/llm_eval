"""订单对账工作流（v1 + v2 契约）与发布包导出。

纯函数实现：只依赖 csv / io / json / decimal 等标准库，
不访问文件、网络或进程，不修改传入的输入内容。
v1 行为完全保留；v2 增加截止时间、退款状态与三位小数四舍五入。
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MAX_DECIMALS = 2
_HUNDRED = Decimal(100)
_ONE = Decimal(1)

_ORDERS_FIELDS = ("order_id", "customer", "amount", "status", "created_at")
_REFUNDS_FIELDS = ("refund_id", "order_id", "amount")
_REFUNDS_FIELDS_V2 = ("refund_id", "order_id", "amount", "status", "created_at")

# policy -> CSV 列契约 / 金额精度 / 是否启用 cutoff 与退款状态
_POLICIES = {
    "v1": {
        "refund_fields": _REFUNDS_FIELDS,
        "max_decimals": MAX_DECIMALS,
        "rounding": None,
        "use_cutoff": False,
        "rounding_mode": "exact",
    },
    "v2": {
        "refund_fields": _REFUNDS_FIELDS_V2,
        "max_decimals": None,
        "rounding": ROUND_HALF_UP,
        "use_cutoff": True,
        "rounding_mode": "half_up",
    },
}

_PAID = "paid"
_SUCCEEDED = "succeeded"
_BOM = "\ufeff"
_TS_LEN = 20

_ORDERS_HEADER = ("order_id", "customer", "paid_cents", "refund_cents", "net_cents")
_CUSTOMERS_HEADER = ("customer", "net_cents")


# ---------------------------------------------------------------- helpers

def _text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _strip_bom(value):
    if value.startswith(_BOM):
        return value[1:]
    return value


def _is_digits(value):
    if value == "":
        return True
    for ch in value:
        if ch < "0" or ch > "9":
            return False
    return True


def _is_timestamp(value):
    """校验规范 UTC 时间戳 YYYY-MM-DDTHH:MM:SSZ（可直接按字典序比较）。"""
    if len(value) != _TS_LEN:
        return False
    if value[4] != "-" or value[7] != "-" or value[10] != "T":
        return False
    if value[13] != ":" or value[16] != ":" or value[19] != "Z":
        return False
    for start, end in ((0, 4), (5, 7), (8, 10), (11, 13), (14, 16), (17, 19)):
        if not _is_digits(value[start:end]):
            return False
    return True


def _require_timestamp(value, context):
    text = _text(value)
    if not _is_timestamp(text):
        raise ValueError("invalid timestamp " + text + " in " + context)
    return text


def _parse_amount(raw, context, config):
    """解析金额，返回 (整数分, 规范金额文本)。

    拒绝空值、非数字、NaN/Infinity、负数；v1 另外拒绝非零的超额小数位，
    v2 允许多位小数并按 ROUND_HALF_UP 逐条取整。
    """
    text = _text(raw)
    if text == "":
        raise ValueError("empty amount in " + context)
    body = text
    negative = False
    if body[0] == "+" or body[0] == "-":
        negative = body[0] == "-"
        body = body[1:]
    parts = body.split(".")
    if len(parts) > 2:
        raise ValueError("invalid amount " + text + " in " + context)
    int_part = parts[0]
    frac_part = parts[1] if len(parts) == 2 else ""
    if int_part == "" or not _is_digits(int_part):
        raise ValueError("invalid amount " + text + " in " + context)
    if not _is_digits(frac_part):
        raise ValueError("invalid amount " + text + " in " + context)
    max_decimals = config["max_decimals"]
    if max_decimals is not None and len(frac_part) > max_decimals:
        extra = frac_part[max_decimals:]
        if extra.strip("0") != "":
            raise ValueError("amount with more than two decimals " + text + " in " + context)
        frac_part = frac_part[:max_decimals]
    if negative:
        if int_part.strip("0") != "" or frac_part.strip("0") != "":
            raise ValueError("negative amount " + text + " in " + context)
        int_part = "0"
        frac_part = ""
    try:
        value = Decimal(int_part + "." + frac_part if frac_part else int_part)
    except InvalidOperation:
        raise ValueError("invalid amount " + text + " in " + context)
    if not value.is_finite():
        raise ValueError("non-finite amount " + text + " in " + context)
    scaled = value * _HUNDRED
    if config["rounding_mode"] == "exact":
        if scaled != scaled.to_integral_value():
            raise ValueError("amount with more than two decimals " + text + " in " + context)
        cents = int(scaled)
    else:
        cents = int(scaled.quantize(_ONE, rounding=config["rounding"]))
    return cents, str(value.normalize())


def _read_records(raw_text, required_fields, context):
    """解析 CSV 文本为字典列表；只读取，不修改输入。"""
    if raw_text is None:
        raw_text = ""
    if isinstance(raw_text, str):
        data = raw_text
    else:
        data = str(raw_text)
    data = _strip_bom(data)
    if _text(data) == "":
        return []
    reader = csv.reader(io.StringIO(data, newline=""))
    rows = [row for row in reader]
    rows = [row for row in rows if not (len(row) == 0 or all(_text(cell) == "" for cell in row))]
    if not rows:
        return []
    header = [_text(cell).lower() for cell in rows[0]]
    positions = {}
    for name in required_fields:
        if name not in header:
            raise ValueError("missing column " + name + " in " + context)
        positions[name] = header.index(name)
    records = []
    for row in rows[1:]:
        if len(row) != len(rows[0]):
            raise ValueError("malformed row in " + context)
        record = {}
        for name in required_fields:
            record[name] = _text(row[positions[name]])
        records.append(record)
    return records


def _index_orders(records, config):
    """按 order_id 去重；同 id 不同内容 -> ValueError（截止前后行都参与校验）。"""
    orders = {}
    for record in records:
        order_id = record["order_id"]
        if order_id == "":
            raise ValueError("empty order_id in orders_csv")
        customer = record["customer"]
        cents, amount_text = _parse_amount(record["amount"], "order " + order_id, config)
        status = record["status"].lower()
        created_at = record["created_at"]
        if config["use_cutoff"]:
            created_at = _require_timestamp(created_at, "order " + order_id)
        key = (order_id, customer, amount_text, status, created_at)
        if order_id in orders:
            if orders[order_id]["key"] != key:
                raise ValueError("conflicting duplicate order_id " + order_id)
            continue
        orders[order_id] = {
            "key": key,
            "customer": customer,
            "amount": cents,
            "status": status,
            "created_at": created_at,
        }
    return orders


def _index_refunds(records, config):
    """按 refund_id 去重；同 id 不同内容 -> ValueError（pending/截止后行同样参与）。"""
    seen = {}
    items = []
    for record in records:
        refund_id = record["refund_id"]
        if refund_id == "":
            raise ValueError("empty refund_id in refunds_csv")
        order_id = record["order_id"]
        cents, amount_text = _parse_amount(record["amount"], "refund " + refund_id, config)
        if config["use_cutoff"]:
            status = record["status"].lower()
            created_at = _require_timestamp(record["created_at"], "refund " + refund_id)
            key = (refund_id, order_id, amount_text, status, created_at)
        else:
            status = _SUCCEEDED
            created_at = ""
            key = (refund_id, order_id, amount_text)
        if refund_id in seen:
            if seen[refund_id] != key:
                raise ValueError("conflicting duplicate refund_id " + refund_id)
            continue
        seen[refund_id] = key
        items.append({
            "refund_id": refund_id,
            "order_id": order_id,
            "amount": cents,
            "status": status,
            "created_at": created_at,
        })
    return items


def _is_counted_order(order, cutoff, use_cutoff):
    if order["status"] != _PAID:
        return False
    if use_cutoff and order["created_at"] > cutoff:
        return False
    return True


def _is_counted_refund(refund, cutoff, use_cutoff):
    """有效退款：v1 全部有效；v2 需 succeeded 且 created_at <= cutoff。"""
    if not use_cutoff:
        return True
    if refund["status"] != _SUCCEEDED:
        return False
    if refund["created_at"] > cutoff:
        return False
    return True


# ---------------------------------------------------------------- contract

def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    policy_name = _text(policy) or "v1"
    if policy_name not in _POLICIES:
        raise ValueError("unsupported policy: " + policy_name)
    config = _POLICIES[policy_name]
    use_cutoff = config["use_cutoff"]
    if use_cutoff:
        cutoff_text = _text(cutoff)
        if cutoff_text == "":
            raise ValueError("cutoff is required for policy " + policy_name)
        if not _is_timestamp(cutoff_text):
            raise ValueError("invalid cutoff " + cutoff_text + "; expected YYYY-MM-DDTHH:MM:SSZ")
    else:
        cutoff_text = None

    order_records = _read_records(orders_csv, _ORDERS_FIELDS, "orders_csv")
    refund_records = _read_records(refunds_csv, config["refund_fields"], "refunds_csv")
    orders = _index_orders(order_records, config)
    refunds = _index_refunds(refund_records, config)

    # 先按退款有效性过滤，再校验归属与超额，最后按订单累加
    refund_by_order = {}
    for refund in refunds:
        if not _is_counted_refund(refund, cutoff_text, use_cutoff):
            continue  # pending 或截止后退款：不计、不校验
        refund_id = refund["refund_id"]
        order_id = refund["order_id"]
        if order_id not in orders:
            raise ValueError("refund " + refund_id + " references unknown order " + order_id)
        order = orders[order_id]
        if order["status"] != _PAID:
            raise ValueError("refund " + refund_id + " references non-paid order " + order_id)
        if use_cutoff and order["created_at"] > cutoff_text:
            continue  # 订单存在但被截止时间排除，其退款忽略
        accumulated = refund_by_order.get(order_id, 0) + refund["amount"]
        if accumulated > order["amount"]:
            raise ValueError("refunds exceed paid amount for order " + order_id)
        refund_by_order[order_id] = accumulated

    order_rows = []
    customer_net = {}
    paid_total = 0
    refund_total = 0
    for order_id in sorted(orders.keys()):
        order = orders[order_id]
        if not _is_counted_order(order, cutoff_text, use_cutoff):
            continue
        paid = order["amount"]
        refunded = refund_by_order.get(order_id, 0)
        net = paid - refunded
        order_rows.append({
            "order_id": order_id,
            "customer": order["customer"],
            "paid_cents": paid,
            "refund_cents": refunded,
            "net_cents": net,
        })
        customer = order["customer"]
        customer_net[customer] = customer_net.get(customer, 0) + net
        paid_total += paid
        refund_total += refunded

    customer_rows = []
    for customer in sorted(customer_net.keys()):
        customer_rows.append({"customer": customer, "net_cents": customer_net[customer]})

    return {
        "orders": order_rows,
        "customers": customer_rows,
        "totals": {
            "paid_cents": paid_total,
            "refund_cents": refund_total,
            "net_cents": paid_total - refund_total,
        },
    }


# ---------------------------------------------------------------- release

def _csv_text(header, rows):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(list(header))
    for row in rows:
        writer.writerow(list(row))
    return buffer.getvalue()


def export_bundle(result):
    """导出发布包：恰好 orders.csv / customers.csv / summary.json 三个文本文件。"""
    if not isinstance(result, dict):
        raise ValueError("result must be a dict from reconcile()")
    order_rows = result.get("orders")
    customer_rows = result.get("customers")
    totals = result.get("totals")
    if order_rows is None or customer_rows is None or not isinstance(totals, dict):
        raise ValueError("result must contain orders, customers and totals")

    orders_body = []
    for row in order_rows:
        orders_body.append([
            row["order_id"],
            row["customer"],
            str(int(row["paid_cents"])),
            str(int(row["refund_cents"])),
            str(int(row["net_cents"])),
        ])
    customers_body = []
    for row in customer_rows:
        customers_body.append([row["customer"], str(int(row["net_cents"]))])

    totals_body = {
        "paid_cents": int(totals["paid_cents"]),
        "refund_cents": int(totals["refund_cents"]),
        "net_cents": int(totals["net_cents"]),
    }
    return {
        "orders.csv": _csv_text(_ORDERS_HEADER, orders_body),
        "customers.csv": _csv_text(_CUSTOMERS_HEADER, customers_body),
        "summary.json": json.dumps(totals_body, sort_keys=True, ensure_ascii=False),
    }