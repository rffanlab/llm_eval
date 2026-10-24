"""订单对账：v1/v2 纯函数实现，仅使用标准库（csv/io/decimal 等）。"""
import csv
import io
import json
import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


ORDER_HEADERS = ["order_id", "customer", "amount", "status", "created_at"]
REFUND_HEADERS_V1 = ["refund_id", "order_id", "amount"]
REFUND_HEADERS_V2 = ["refund_id", "order_id", "amount", "status", "created_at"]


def _parse_amount_v1(raw):
    """v1：最多两位小数，拒绝 NaN/Infinity/负数/超过两位小数。返回整数分。"""
    value = _decimal_from(raw)
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -2:
        raise ValueError("more than two decimals: %s" % value)
    cents = value.scaleb(2)
    if cents != cents.to_integral_value():
        raise ValueError("fractional cents: %s" % value)
    return int(cents)


def _parse_amount_v2(raw):
    """v2：允许多位小数，Decimal ROUND_HALF_UP 到整数分。"""
    value = _decimal_from(raw)
    cents = value.scaleb(2).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(cents)


def _decimal_from(raw):
    if raw is None:
        raise ValueError("missing amount")
    text = str(raw).strip()
    if text == "":
        raise ValueError("missing amount")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("invalid amount: %s" % text)
    if not value.is_finite():
        raise ValueError("non-finite amount: %s" % text)
    # 负数检测（同时捕获 -0）
    if value.copy_sign(Decimal(1)).compare(value) != 0:
        raise ValueError("negative amount: %s" % text)
    return value


def _validate_cutoff(cutoff):
    """校验 YYYY-MM-DDTHH:MM:SSZ 格式（不使用 re）。"""
    if not isinstance(cutoff, str) or len(cutoff) != 20:
        raise ValueError("cutoff must be YYYY-MM-DDTHH:MM:SSZ")
    digits_ok = lambda s: all(ch.isdigit() for ch in s)
    if not (digits_ok(cutoff[0:4]) and cutoff[4] == "-"
            and digits_ok(cutoff[5:7]) and cutoff[7] == "-"
            and digits_ok(cutoff[8:10]) and cutoff[10] == "T"
            and digits_ok(cutoff[11:13]) and cutoff[13] == ":"
            and digits_ok(cutoff[14:16]) and cutoff[16] == ":"
            and digits_ok(cutoff[17:19]) and cutoff[19] == "Z"):
        raise ValueError("cutoff must be YYYY-MM-DDTHH:MM:SSZ")
    try:
        datetime.datetime.strptime(cutoff, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValueError("invalid cutoff datetime: %s" % cutoff)
    return cutoff


def _read_rows(csv_string, required_headers):
    reader = csv.DictReader(io.StringIO(csv_string))
    header = reader.fieldnames
    if header is None:
        raise ValueError("missing CSV header")
    for name in required_headers:
        if name not in header:
            raise ValueError("missing column: %s" % name)
    return list(reader)


def _canonical(row, headers):
    return tuple((row.get(h) or "").strip() for h in headers)


def _dedupe(rows, headers, kind):
    """按 id 去重：完全相同行只计一次；同 id 字段不同抛 ValueError。保持首次出现顺序。"""
    seen = {}
    ordered = []
    for row in rows:
        canon = _canonical(row, headers)
        item_id = canon[0]
        if item_id == "":
            raise ValueError("empty %s id" % kind)
        if item_id in seen:
            if seen[item_id] == canon:
                continue
            raise ValueError("conflicting duplicate %s: %s" % (kind, item_id))
        seen[item_id] = canon
        ordered.append((item_id, canon))
    return ordered


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """按 v1/v2 契约对账。v1 忽略 cutoff；v2 必须提供合法 cutoff。"""
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy: %s" % policy)
    amount_parser = _parse_amount_v1 if policy == "v1" else _parse_amount_v2
    refund_headers = REFUND_HEADERS_V1 if policy == "v1" else REFUND_HEADERS_V2
    if policy == "v2":
        if cutoff is None:
            raise ValueError("cutoff is required for policy v2")
        cutoff = _validate_cutoff(cutoff)

    orders = dict(_dedupe(_read_rows(orders_csv, ORDER_HEADERS), ORDER_HEADERS, "order"))
    refunds = dict(_dedupe(_read_rows(refunds_csv, refund_headers), refund_headers, "refund"))

    def in_cutoff(created_at):
        # 规范 UTC 字符串，字典序比较即可
        return created_at <= cutoff

    # 校验退款引用（对全部退款行，包括 pending/截止后），再筛选计入的退款
    refund_by_order = {}
    for refund_id in sorted(refunds):
        if policy == "v1":
            _, order_id, amount_text = refunds[refund_id]
            status, created_at = "succeeded", None
        else:
            _, order_id, amount_text, status, created_at = refunds[refund_id]
            if status not in ("succeeded", "pending"):
                raise ValueError("refund %s has invalid status: %s" % (refund_id, status))

        if order_id not in orders:
            raise ValueError("refund %s references unknown order %s" % (refund_id, order_id))
        order_status = orders[order_id][3]
        if order_status != "paid":
            raise ValueError("refund %s references non-paid order %s" % (refund_id, order_id))

        if policy == "v2":
            order_created_at = orders[order_id][4]
            # 订单存在但被截止时间排除 -> 忽略该退款
            if not in_cutoff(order_created_at):
                continue
            # pending 或截止后退款不计
            if status != "succeeded" or not in_cutoff(created_at):
                continue

        cents = amount_parser(amount_text)
        refund_by_order[order_id] = refund_by_order.get(order_id, 0) + cents

    order_rows = []
    customer_net = {}
    total_paid = 0
    total_refund = 0
    for order_id in sorted(orders):
        _, customer, amount_text, status, created_at = orders[order_id]
        if status != "paid":
            continue  # cancelled 等非 paid 订单不入结果
        if policy == "v2" and not in_cutoff(created_at):
            continue  # 截止后订单不计
        paid = amount_parser(amount_text)
        refund = refund_by_order.get(order_id, 0)
        if refund > paid:
            raise ValueError(
                "refunds (%d) exceed paid (%d) for order %s" % (refund, paid, order_id)
            )
        net = paid - refund
        order_rows.append({
            "order_id": order_id,
            "customer": customer,
            "paid_cents": paid,
            "refund_cents": refund,
            "net_cents": net,
        })
        customer_net[customer] = customer_net.get(customer, 0) + net
        total_paid += paid
        total_refund += refund

    customers = [
        {"customer": name, "net_cents": customer_net[name]}
        for name in sorted(customer_net)
    ]
    return {
        "orders": order_rows,
        "customers": customers,
        "totals": {
            "paid_cents": total_paid,
            "refund_cents": total_refund,
            "net_cents": total_paid - total_refund,
        },
    }


def _csv_text(header, rows):
    """用标准 csv writer 写出 CSV 文本（\\n 行结束，与输入风格一致）。"""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    """按发布契约导出恰好三个文件：orders.csv、customers.csv、summary.json。"""
    orders_csv = _csv_text(
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
        [
            [o["order_id"], o["customer"], str(o["paid_cents"]),
             str(o["refund_cents"]), str(o["net_cents"])]
            for o in result["orders"]
        ],
    )
    customers_csv = _csv_text(
        ["customer", "net_cents"],
        [[c["customer"], str(c["net_cents"])] for c in result["customers"]],
    )
    summary_json = json.dumps(result["totals"], sort_keys=True)
    return {
        "orders.csv": orders_csv,
        "customers.csv": customers_csv,
        "summary.json": summary_json,
    }
