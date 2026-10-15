"""订单对账纯函数实现（v1 + v2 契约 + 发布包导出）。

只使用 csv / io / json / decimal 等标准库；不访问文件、网络或进程。
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _parse_amount_to_cents(raw, context, policy):
    """把金额字符串解析为非负整数分。

    v1: 最多两位小数，超出报错。
    v2: 允许多位小数，Decimal ROUND_HALF_UP 取整到分。
    两者均拒绝负数 / NaN / Infinity / 非法字符串。
    """
    if raw is None:
        raise ValueError("%s: missing amount" % context)
    text = str(raw).strip()
    if text == "":
        raise ValueError("%s: empty amount" % context)
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError("%s: invalid amount %r" % (context, raw))
    if not value.is_finite():
        raise ValueError("%s: non-finite amount %r" % (context, raw))
    if value < 0:
        raise ValueError("%s: negative amount %r" % (context, raw))
    exponent = value.as_tuple().exponent
    if policy == "v1" and isinstance(exponent, int) and exponent < -2:
        raise ValueError("%s: more than two decimals %r" % (context, raw))
    cents = (value * Decimal(100)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(cents)


def _read_rows(csv_text, required_headers, kind):
    if not isinstance(csv_text, str):
        raise ValueError("%s csv must be a string" % kind)
    reader = csv.reader(csv_text.splitlines())
    try:
        header = next(reader)
    except StopIteration:
        raise ValueError("%s csv must have a header row" % kind)
    header = [h.strip() for h in header]
    for name in required_headers:
        if name not in header:
            raise ValueError("%s csv missing column %r" % (kind, name))
    rows = []
    for record in reader:
        if not record or all((cell or "").strip() == "" for cell in record):
            continue
        row = {}
        for idx, name in enumerate(header):
            row[name] = record[idx].strip() if idx < len(record) else ""
        rows.append(row)
    return rows


def _validate_cutoff(cutoff):
    """校验 cutoff 为 YYYY-MM-DDTHH:MM:SSZ 规范 UTC 字符串。"""
    if not isinstance(cutoff, str) or len(cutoff) != 20:
        raise ValueError(
            "v2 requires cutoff in YYYY-MM-DDTHH:MM:SSZ format, got %r" % (cutoff,))
    digits_ok = (
        cutoff[0:4].isdigit() and cutoff[5:7].isdigit() and cutoff[8:10].isdigit()
        and cutoff[11:13].isdigit() and cutoff[14:16].isdigit() and cutoff[17:19].isdigit()
    )
    if (not digits_ok
            or cutoff[4] != "-" or cutoff[7] != "-" or cutoff[10] != "T"
            or cutoff[13] != ":" or cutoff[16] != ":" or cutoff[19] != "Z"):
        raise ValueError(
            "v2 requires cutoff in YYYY-MM-DDTHH:MM:SSZ format, got %r" % (cutoff,))
    month, day = int(cutoff[5:7]), int(cutoff[8:10])
    hour, minute, second = int(cutoff[11:13]), int(cutoff[14:16]), int(cutoff[17:19])
    if not (1 <= month <= 12 and 1 <= day <= 31):
        raise ValueError("v2 cutoff has invalid date %r" % (cutoff,))
    if not (hour <= 23 and minute <= 59 and second <= 59):
        raise ValueError("v2 cutoff has invalid time %r" % (cutoff,))
    return cutoff


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """按 v1/v2 契约对账：返回 orders / customers / totals，金额均为整数分。

    v1（保持原行为）：
    - 只包含 paid 订单；cancelled 订单不入结果。
    - order_id / refund_id 去重：完全相同行只算一次，字段不同抛 ValueError。
    - 未知订单退款、cancelled 订单退款、单笔累计退款超已付均抛 ValueError。
    - 金额最多两位小数。

    v2（policy="v2"，cutoff 必填）：
    - 只计 created_at <= cutoff 的 paid 订单。
    - 只计 created_at <= cutoff 且 status=succeeded 的退款；
      pending / 截止后退款不计；对应订单存在但被截止时间排除时也忽略；
      真正不存在或 cancelled 订单的有效退款抛 ValueError。
    - 金额允许多位小数，逐条 ROUND_HALF_UP 到分后再汇总。
    - 重复 id 冲突（含 pending / 截止后行）仍抛 ValueError。

    输出结构与顺序与 v1 相同；非法 policy 或 v2 缺 cutoff 抛 ValueError。
    """
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy %r" % (policy,))
    if policy == "v2":
        if cutoff is None:
            raise ValueError("v2 requires cutoff")
        _validate_cutoff(cutoff)

    order_headers = ["order_id", "customer", "amount", "status"]
    refund_headers = ["refund_id", "order_id", "amount"]
    if policy == "v2":
        order_headers.append("created_at")
        refund_headers.extend(["status", "created_at"])

    order_rows = _read_rows(orders_csv, order_headers, "orders")
    refund_rows = _read_rows(refunds_csv, refund_headers, "refunds")

    # ---- 订单：解析 + 去重（去重覆盖全部行，含后续会被过滤的行）----
    orders = {}
    for row in order_rows:
        oid = row.get("order_id", "")
        if oid == "":
            raise ValueError("orders: empty order_id")
        status = row.get("status", "").lower()
        if status not in ("paid", "cancelled"):
            raise ValueError("orders: unknown status %r for %s" % (row.get("status"), oid))
        cents = _parse_amount_to_cents(row.get("amount"), "order %s" % oid, policy)
        created_at = row.get("created_at", "")
        if policy == "v2":
            if created_at == "":
                raise ValueError("orders: missing created_at for %s" % oid)
        record = (row.get("customer", ""), cents, status, created_at)
        if oid in orders:
            if orders[oid] == record:
                continue
            raise ValueError("orders: conflicting duplicate order_id %s" % oid)
        orders[oid] = record

    # ---- 退款：解析 + 去重（含 pending / 截止后行也必须查冲突）----
    seen_refunds = {}
    for row in refund_rows:
        rid = row.get("refund_id", "")
        if rid == "":
            raise ValueError("refunds: empty refund_id")
        cents = _parse_amount_to_cents(row.get("amount"), "refund %s" % rid, policy)
        status = row.get("status", "")
        created_at = row.get("created_at", "")
        if policy == "v2":
            if status not in ("succeeded", "pending"):
                raise ValueError("refunds: unknown status %r for %s" % (status, rid))
            if created_at == "":
                raise ValueError("refunds: missing created_at for %s" % rid)
            record = (row.get("order_id", ""), cents, status, created_at)
        else:
            record = (row.get("order_id", ""), cents)
        if rid in seen_refunds:
            if seen_refunds[rid] == record:
                continue
            raise ValueError("refunds: conflicting duplicate refund_id %s" % rid)
        seen_refunds[rid] = record

    # ---- 逐条退款应用 ----
    per_order_refunds = {oid: 0 for oid in orders}
    for rid in sorted(seen_refunds):
        record = seen_refunds[rid]
        oid = record[0]
        cents = record[1]

        if policy == "v2":
            status = record[2]
            created_at = record[3]
            if status != "succeeded" or created_at > cutoff:
                # pending 或截止后退款：完全忽略（即使订单未知也不报错）
                continue
            if oid not in orders:
                raise ValueError("refund %s references unknown order %s" % (rid, oid))
            ostatus = orders[oid][2]
            ocreated = orders[oid][3]
            if ostatus != "paid":
                raise ValueError("refund %s references cancelled order %s" % (rid, oid))
            if ocreated > cutoff:
                # 订单存在但被截止时间排除：忽略该退款
                continue
        else:
            if oid not in orders:
                raise ValueError("refund %s references unknown order %s" % (rid, oid))
            if orders[oid][2] != "paid":
                raise ValueError("refund %s references cancelled order %s" % (rid, oid))

        per_order_refunds[oid] += cents
        if per_order_refunds[oid] > orders[oid][1]:
            raise ValueError("refunds exceed paid amount for order %s" % oid)

    # ---- 汇总输出（结构与 v1 一致）----
    order_items = []
    customers = {}
    total_paid = 0
    total_refund = 0
    for oid in sorted(orders):
        customer, paid_cents, status = orders[oid][0], orders[oid][1], orders[oid][2]
        if status != "paid":
            continue
        if policy == "v2" and orders[oid][3] > cutoff:
            continue  # 截止后订单不计入
        refund_cents = per_order_refunds[oid]
        net_cents = paid_cents - refund_cents
        order_items.append({
            "order_id": oid,
            "customer": customer,
            "paid_cents": paid_cents,
            "refund_cents": refund_cents,
            "net_cents": net_cents,
        })
        customers[customer] = customers.get(customer, 0) + net_cents
        total_paid += paid_cents
        total_refund += refund_cents

    customer_items = [
        {"customer": name, "net_cents": customers[name]}
        for name in sorted(customers)
    ]

    return {
        "orders": order_items,
        "customers": customer_items,
        "totals": {
            "paid_cents": total_paid,
            "refund_cents": total_refund,
            "net_cents": total_paid - total_refund,
        },
    }


def _csv_text(rows):
    """用标准 csv writer 生成 CSV 文本（\\n 行结束，整数以文本写出）。"""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    """按发布契约导出恰好三个文件：orders.csv / customers.csv / summary.json。

    - orders.csv 表头 order_id,customer,paid_cents,refund_cents,net_cents；
    - customers.csv 表头 customer,net_cents；
    - 行顺序沿用 reconcile 的排序，金额为整数字符串；
    - summary.json 解析后恰好等于 result["totals"]。
    """
    if not isinstance(result, dict) or "orders" not in result \
            or "customers" not in result or "totals" not in result:
        raise ValueError("export_bundle: invalid result object")

    order_rows = [["order_id", "customer", "paid_cents", "refund_cents", "net_cents"]]
    for item in result["orders"]:
        order_rows.append([
            str(item["order_id"]),
            str(item["customer"]),
            str(int(item["paid_cents"])),
            str(int(item["refund_cents"])),
            str(int(item["net_cents"])),
        ])

    customer_rows = [["customer", "net_cents"]]
    for item in result["customers"]:
        customer_rows.append([str(item["customer"]), str(int(item["net_cents"]))])

    return {
        "orders.csv": _csv_text(order_rows),
        "customers.csv": _csv_text(customer_rows),
        "summary.json": json.dumps(result["totals"]),
    }
