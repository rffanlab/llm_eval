"""订单对账交付模块。

reconcile: 纯函数，输入 UTF-8 CSV 字符串，输出整数分结果。
policy="v1": 原始契约（最多两位小数、旧列）。
policy="v2": cutoff 必填；订单按 created_at 截止；退款含 status/created_at，
只计 succeeded 且截止内的退款；金额多位小数按 Decimal ROUND_HALF_UP 逐条取整。
export_bundle: 按发布契约生成 orders.csv / customers.csv / summary.json。
不使用文件、网络、进程；仅使用 csv/io/datetime/decimal/json 标准库。
"""

import csv
import io
import json
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

_DIGITS = set("0123456789")


def _parse_amount_cents(raw, context, allow_many_decimals):
    """把金额字符串解析为非负整数分（Decimal 定点，ROUND_HALF_UP）。"""
    if raw is None:
        raise ValueError("%s: 金额缺失" % context)
    text = raw.strip()
    if not text:
        raise ValueError("%s: 金额为空" % context)
    # 手工校验：仅允许非负十进制；拒绝 NaN / Infinity / 负数 / 科学计数。
    if "." in text:
        int_part, _, frac_part = text.partition(".")
        if not int_part or not frac_part:
            raise ValueError("%s: 非法金额 %r" % (context, raw))
        if not set(frac_part) <= _DIGITS:
            raise ValueError("%s: 非法金额 %r" % (context, raw))
    else:
        int_part, frac_part = text, ""
    if not int_part or not set(int_part) <= _DIGITS:
        raise ValueError("%s: 非法金额 %r" % (context, raw))
    if not allow_many_decimals and len(frac_part) > 2:
        raise ValueError("%s: 金额超过两位小数 %r" % (context, raw))
    # 先精确乘 100，再按 ROUND_HALF_UP 取整到分
    cents = Decimal(text) * Decimal(100)
    return int(cents.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _validate_cutoff(cutoff):
    if not isinstance(cutoff, str) or not cutoff:
        raise ValueError("v2 必须提供 cutoff")
    try:
        datetime.strptime(cutoff, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValueError("cutoff 格式必须为 YYYY-MM-DDTHH:MM:SSZ")
    return cutoff


def _read_rows(csv_text, required_headers, kind):
    if csv_text is None:
        raise ValueError("%s CSV 为空" % kind)
    reader = csv.reader(io.StringIO(csv_text))
    try:
        header = next(reader)
    except StopIteration:
        raise ValueError("%s 缺少表头" % kind)
    header = [h.strip() for h in header]
    for col in required_headers:
        if col not in header:
            raise ValueError("%s 缺少列 %s" % (kind, col))
    rows = []
    for record in reader:
        if not record or all((cell is None or cell.strip() == "") for cell in record):
            continue
        if len(record) != len(header):
            raise ValueError("%s 行列数不匹配表头" % kind)
        rows.append(dict(zip(header, record)))
    return rows


def _row_key(row):
    return tuple(sorted((k, (v or "").strip()) for k, v in row.items()))


def _require_timestamp(value, context):
    text = (value or "").strip()
    if not text:
        raise ValueError("%s: created_at 缺失" % context)
    try:
        datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValueError("%s: created_at 非法 %r" % (context, value))
    return text


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """按 v1/v2 契约对账，返回 orders/customers/totals，金额均为整数分。"""
    if policy not in ("v1", "v2"):
        raise ValueError("不支持的 policy: %r" % (policy,))
    if policy == "v2":
        cutoff = _validate_cutoff(cutoff)
    allow_many = policy == "v2"

    order_headers = ["order_id", "customer", "amount", "status"]
    refund_headers = ["refund_id", "order_id", "amount"]
    if policy == "v2":
        order_headers.append("created_at")
        refund_headers += ["status", "created_at"]

    order_rows = _read_rows(orders_csv, order_headers, "orders")
    refund_rows = _read_rows(refunds_csv, refund_headers, "refunds")

    # ---- 订单：解析、去重（完全相同行合并，冲突报错） ----
    orders = {}          # order_id -> dict
    order_seen = {}      # order_id -> row key
    for row in order_rows:
        oid = (row.get("order_id") or "").strip()
        if not oid:
            raise ValueError("orders: order_id 为空")
        status = (row.get("status") or "").strip().lower()
        if status not in ("paid", "cancelled"):
            raise ValueError("orders: 未知状态 %r" % row.get("status"))
        cents = _parse_amount_cents(row.get("amount"), "orders %s" % oid, allow_many)
        created = ""
        if policy == "v2":
            created = _require_timestamp(row.get("created_at"), "orders %s" % oid)
        key = _row_key(row)
        if oid in order_seen:
            if order_seen[oid] == key:
                continue  # 完全相同重复行，只算一次
            raise ValueError("orders: order_id %s 重复且字段不一致" % oid)
        order_seen[oid] = key
        orders[oid] = {
            "order_id": oid,
            "customer": (row.get("customer") or "").strip(),
            "status": status,
            "paid_cents": cents,
            "refund_cents": 0,
            "created_at": created,
        }

    # ---- 退款：先去重（含 pending/截止后行），再过滤、校验归属与累计上限 ----
    refund_seen = {}
    unique_refunds = []
    for row in refund_rows:
        rid = (row.get("refund_id") or "").strip()
        if not rid:
            raise ValueError("refunds: refund_id 为空")
        key = _row_key(row)
        if rid in refund_seen:
            if refund_seen[rid] == key:
                continue
            raise ValueError("refunds: refund_id %s 重复且字段不一致" % rid)
        refund_seen[rid] = key
        unique_refunds.append(row)

    for row in unique_refunds:
        rid = (row.get("refund_id") or "").strip()
        status = "succeeded"
        if policy == "v2":
            status = (row.get("status") or "").strip().lower()
            if status not in ("succeeded", "pending"):
                raise ValueError("refunds: %s 未知状态 %r" % (rid, row.get("status")))
            created = _require_timestamp(row.get("created_at"), "refunds %s" % rid)
            # pending 或截止后的退款：不计，也不做归属校验
            if status != "succeeded" or created > cutoff:
                continue

        oid = (row.get("order_id") or "").strip()
        cents = _parse_amount_cents(row.get("amount"), "refunds %s" % rid, allow_many)
        order = orders.get(oid)
        if order is None:
            raise ValueError("refunds: %s 引用未知订单 %s" % (rid, oid))
        if order["status"] != "paid":
            raise ValueError("refunds: %s 引用非 paid 订单 %s" % (rid, oid))
        if policy == "v2" and order["created_at"] > cutoff:
            continue  # 订单因截止被排除，退款忽略
        if order["refund_cents"] + cents > order["paid_cents"]:
            raise ValueError("refunds: 订单 %s 累计退款超过已付" % oid)
        order["refund_cents"] += cents

    # ---- 汇总输出（结构与顺序保持 v1） ----
    paid_orders = [
        o for o in orders.values()
        if o["status"] == "paid"
        and (policy != "v2" or o["created_at"] <= cutoff)
    ]
    paid_orders.sort(key=lambda o: o["order_id"])

    out_orders = []
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    by_customer = {}
    for o in paid_orders:
        net = o["paid_cents"] - o["refund_cents"]
        out_orders.append({
            "order_id": o["order_id"],
            "customer": o["customer"],
            "paid_cents": o["paid_cents"],
            "refund_cents": o["refund_cents"],
            "net_cents": net,
        })
        totals["paid_cents"] += o["paid_cents"]
        totals["refund_cents"] += o["refund_cents"]
        totals["net_cents"] += net
        by_customer[o["customer"]] = by_customer.get(o["customer"], 0) + net

    customers = [
        {"customer": name, "net_cents": net}
        for name, net in sorted(by_customer.items())
    ]

    return {"orders": out_orders, "customers": customers, "totals": totals}


def _csv_text(rows, header):
    """用标准 csv writer 生成 CSV 文本；金额写为整数字符串。"""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([row[col] for col in header])
    return buf.getvalue()


def export_bundle(result):
    """按发布契约导出恰好三个文件：orders.csv / customers.csv / summary.json。"""
    if not isinstance(result, dict):
        raise ValueError("result 必须是 reconcile 返回的 dict")
    for key in ("orders", "customers", "totals"):
        if key not in result:
            raise ValueError("result 缺少 %s" % key)

    orders_csv = _csv_text(
        result["orders"],
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
    )
    customers_csv = _csv_text(result["customers"], ["customer", "net_cents"])
    summary_json = json.dumps(result["totals"], sort_keys=True)

    return {
        "orders.csv": orders_csv,
        "customers.csv": customers_csv,
        "summary.json": summary_json,
    }
