"""订单对账工作流（v1 + v2 契约 + 发布包导出）。

纯函数实现：只依赖标准库 csv / io / json / decimal，
不访问文件、网络或进程，不使用双下划线属性，不修改入参。
金额定点化全部使用 decimal.Decimal 的数字元组做精确整数运算，不用 float。
"""

import csv
import io
import json
import decimal

PAID = "paid"
CANCELLED = "cancelled"
SUCCEEDED = "succeeded"

V1 = "v1"
V2 = "v2"

ORDER_COLUMNS_V1 = ("order_id", "customer", "amount", "status")
ORDER_COLUMNS_V2 = ("order_id", "customer", "amount", "status", "created_at")
REFUND_COLUMNS_V1 = ("refund_id", "order_id", "amount")
REFUND_COLUMNS_V2 = ("refund_id", "order_id", "amount", "status", "created_at")

ORDER_BUNDLE_COLUMNS = ("order_id", "customer", "paid_cents", "refund_cents",
                        "net_cents")
CUSTOMER_BUNDLE_COLUMNS = ("customer", "net_cents")

ZERO_TOTALS = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}

BOM = "\ufeff"
_DATE_DIGITS = (0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18)
_MONTH_LENGTHS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _fail(message):
    raise ValueError(message)


def empty_result():
    return {"orders": [], "customers": [], "totals": dict(ZERO_TOTALS)}


def _round_half_up_to_cents(sign, digits, exponent):
    """把十进制数字元组精确换算为整数分（四舍五入 ROUND_HALF_UP），不使用 float。"""
    magnitude = 0
    for digit in digits:
        magnitude = magnitude * 10 + digit
    if exponent >= 0:
        scaled = magnitude * (10 ** exponent) * 100
    else:
        numerator = magnitude * 100
        denominator = 10 ** (-exponent)
        scaled = numerator // denominator
        remainder = numerator - scaled * denominator
        if remainder * 2 >= denominator:
            scaled += 1
    return -scaled if sign else scaled


def _to_cents(raw, field, row_no, policy):
    """金额转整数分。v1 最多两位小数；v2 允许多位小数并逐条按 ROUND_HALF_UP 取整。"""
    if raw is None:
        _fail("row %d: missing field %s" % (row_no, field))
    text = raw.strip()
    if text == "":
        _fail("row %d: empty amount for %s" % (row_no, field))
    try:
        value = decimal.Decimal(text)
    except (ValueError, ArithmeticError):
        _fail("row %d: invalid amount %r for %s" % (row_no, text, field))
    if not value.is_finite():
        _fail("row %d: non-finite amount %r for %s" % (row_no, text, field))
    if value < 0:
        _fail("row %d: negative amount %r for %s" % (row_no, text, field))
    parts = value.as_tuple()
    exponent = parts.exponent
    if not isinstance(exponent, int):
        _fail("row %d: non-finite amount %r for %s" % (row_no, text, field))
    if policy == V1 and exponent < -2:
        _fail("row %d: more than two decimals %r for %s" % (row_no, text, field))
    return _round_half_up_to_cents(parts.sign, parts.digits, exponent)


def _is_leap_year(year):
    return (year % 4 == 0 and year % 100 != 0) or year % 400 == 0


def _parse_instant(raw, field, row_no):
    """校验规范 UTC 时间戳 YYYY-MM-DDTHH:MM:SSZ；字符串比较即可按时间排序。"""
    if raw is None:
        _fail("row %d: missing field %s" % (row_no, field))
    text = raw.strip()
    shaped = (len(text) == 20 and text.endswith("Z") and text[4] == "-"
              and text[7] == "-" and text[10] == "T" and text[13] == ":"
              and text[16] == ":"
              and all(text[i].isdigit() for i in _DATE_DIGITS))
    if not shaped:
        _fail("row %d: invalid timestamp %r for %s" % (row_no, text, field))
    year = int(text[0:4])
    month = int(text[5:7])
    day = int(text[8:10])
    hour = int(text[11:13])
    minute = int(text[14:16])
    second = int(text[17:19])
    if month < 1 or month > 12 or hour > 23 or minute > 59 or second > 59:
        _fail("row %d: invalid timestamp %r for %s" % (row_no, text, field))
    length = _MONTH_LENGTHS[month - 1]
    if month == 2 and _is_leap_year(year):
        length = 29
    if day < 1 or day > length:
        _fail("row %d: invalid timestamp %r for %s" % (row_no, text, field))
    return text


def _parse_cutoff(cutoff):
    if cutoff is None:
        _fail("policy v2 requires cutoff")
    if not isinstance(cutoff, str):
        _fail("cutoff must be a string YYYY-MM-DDTHH:MM:SSZ")
    return _parse_instant(cutoff, "cutoff", 0)


def _read_rows(text, required, kind):
    """解析 CSV 字符串为 [(行号, 字段字典, 原始行元组)]；输入字符串不被修改。"""
    if text is None:
        _fail("%s csv must be a string" % kind)
    if not isinstance(text, str):
        _fail("%s csv must be a string" % kind)
    body = text
    if body.startswith(BOM):
        body = body[1:]
    try:
        parsed = [row for row in csv.reader(io.StringIO(body, newline=""))]
    except csv.Error as exc:
        _fail("%s csv is not parseable: %s" % (kind, exc))
    parsed = [row for row in parsed if any(field.strip() for field in row)]
    if not parsed:
        return []

    header = [field.strip().lower() for field in parsed[0]]
    if len(set(header)) != len(header):
        _fail("%s csv has duplicated header columns" % kind)
    missing = [name for name in required if name not in header]
    if missing:
        _fail("%s csv missing columns: %s" % (kind, ", ".join(missing)))

    records = []
    for offset, raw_row in enumerate(parsed[1:], start=2):
        if len(raw_row) != len(header):
            _fail("%s csv row %d has %d fields, expected %d"
                  % (kind, offset, len(raw_row), len(header)))
        records.append((offset, dict(zip(header, raw_row)), tuple(raw_row)))
    return records


def _collect(records, id_field, kind, build):
    """按 id 去重：完全相同的行只算一次；相同 id 但任何字段不同必须 ValueError。"""
    values = {}
    raws = {}
    order = []
    for row_no, fields, raw_row in records:
        key = fields[id_field].strip()
        if key == "":
            _fail("%s row %d: empty %s" % (kind, row_no, id_field))
        if key in raws:
            if raws[key] != raw_row:
                _fail("%s row %d: duplicate %s %r with conflicting fields"
                      % (kind, row_no, id_field, key))
            continue
        values[key] = build(row_no, fields)
        raws[key] = raw_row
        order.append(key)
    return values, order


def _assemble(orders, refund_by_order):
    """把已付订单与生效退款汇总为 v1/v2 共用的输出结构。"""
    order_rows = []
    customer_net = {}
    total_paid = 0
    total_refund = 0
    for order_id in sorted(orders):
        order = orders[order_id]
        if order["status"] != PAID:
            continue
        refund_cents = refund_by_order.get(order_id, 0)
        if refund_cents > order["paid_cents"]:
            _fail("order %r refunds %d exceed paid %d"
                  % (order_id, refund_cents, order["paid_cents"]))
        net_cents = order["paid_cents"] - refund_cents
        order_rows.append({
            "order_id": order_id,
            "customer": order["customer"],
            "paid_cents": order["paid_cents"],
            "refund_cents": refund_cents,
            "net_cents": net_cents,
        })
        customer = order["customer"]
        customer_net[customer] = customer_net.get(customer, 0) + net_cents
        total_paid += order["paid_cents"]
        total_refund += refund_cents

    customer_rows = [{"customer": name, "net_cents": customer_net[name]}
                     for name in sorted(customer_net)]
    return {
        "orders": order_rows,
        "customers": customer_rows,
        "totals": {
            "paid_cents": total_paid,
            "refund_cents": total_refund,
            "net_cents": total_paid - total_refund,
        },
    }


def _reconcile_v1(orders_csv, refunds_csv):
    order_records = _read_rows(orders_csv, ORDER_COLUMNS_V1, "orders")
    refund_records = _read_rows(refunds_csv, REFUND_COLUMNS_V1, "refunds")

    orders, _ = _collect(order_records, "order_id", "orders",
                         lambda row_no, fields: {
                             "order_id": fields["order_id"].strip(),
                             "customer": fields["customer"].strip(),
                             "status": fields["status"].strip().lower(),
                             "paid_cents": _to_cents(fields["amount"], "amount",
                                                     row_no, V1),
                         })
    refunds, refund_ids = _collect(refund_records, "refund_id", "refunds",
                                   lambda row_no, fields: {
                                       "refund_id": fields["refund_id"].strip(),
                                       "order_id": fields["order_id"].strip(),
                                       "refund_cents": _to_cents(fields["amount"],
                                                                  "amount",
                                                                  row_no, V1),
                                   })

    refund_by_order = {}
    for refund_id in refund_ids:
        refund = refunds[refund_id]
        order = orders.get(refund["order_id"])
        if order is None:
            _fail("refund %r references unknown order %r"
                  % (refund["refund_id"], refund["order_id"]))
        if order["status"] != PAID:
            _fail("refund %r references order %r with status %s"
                  % (refund["refund_id"], refund["order_id"], order["status"]))
        refund_by_order[refund["order_id"]] = (
            refund_by_order.get(refund["order_id"], 0) + refund["refund_cents"])

    return _assemble(orders, refund_by_order)


def _reconcile_v2(orders_csv, refunds_csv, cutoff):
    limit = _parse_cutoff(cutoff)
    order_records = _read_rows(orders_csv, ORDER_COLUMNS_V2, "orders")
    refund_records = _read_rows(refunds_csv, REFUND_COLUMNS_V2, "refunds")

    orders, _ = _collect(order_records, "order_id", "orders",
                         lambda row_no, fields: {
                             "order_id": fields["order_id"].strip(),
                             "customer": fields["customer"].strip(),
                             "status": fields["status"].strip().lower(),
                             "created_at": _parse_instant(fields["created_at"],
                                                           "created_at", row_no),
                             "paid_cents": _to_cents(fields["amount"], "amount",
                                                     row_no, V2),
                         })
    refunds, refund_ids = _collect(refund_records, "refund_id", "refunds",
                                   lambda row_no, fields: {
                                       "refund_id": fields["refund_id"].strip(),
                                       "order_id": fields["order_id"].strip(),
                                       "status": fields["status"].strip().lower(),
                                       "created_at": _parse_instant(
                                           fields["created_at"], "created_at", row_no),
                                       "refund_cents": _to_cents(fields["amount"],
                                                                  "amount",
                                                                  row_no, V2),
                                   })

    # 只有 succeeded 且不晚于 cutoff 的退款才生效；pending 与截止后退款一律忽略。
    refund_by_order = {}
    for refund_id in refund_ids:
        refund = refunds[refund_id]
        if refund["status"] != SUCCEEDED or refund["created_at"] > limit:
            continue
        order = orders.get(refund["order_id"])
        if order is None:
            _fail("refund %r references unknown order %r"
                  % (refund["refund_id"], refund["order_id"]))
        if order["status"] == CANCELLED:
            _fail("refund %r references cancelled order %r"
                  % (refund["refund_id"], refund["order_id"]))
        # 订单存在但因截止时间或非 paid 被排除时忽略该退款。
        if order["status"] != PAID or order["created_at"] > limit:
            continue
        refund_by_order[refund["order_id"]] = (
            refund_by_order.get(refund["order_id"], 0) + refund["refund_cents"])

    return _assemble(orders, refund_by_order)


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """按 v1（默认）或 v2 契约对账。v1 忽略 cutoff；v2 必须提供 cutoff。"""
    if policy == V1:
        return _reconcile_v1(orders_csv, refunds_csv)
    if policy == V2:
        return _reconcile_v2(orders_csv, refunds_csv, cutoff)
    _fail("unsupported policy: %r" % (policy,))


def _csv_text(header, rows):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def export_bundle(result):
    """导出发布包：恰好 orders.csv / customers.csv / summary.json 三个文件。"""
    if not isinstance(result, dict):
        _fail("result must be a dict")
    orders = result.get("orders") or []
    customers = result.get("customers") or []
    totals = result.get("totals") or ZERO_TOTALS

    orders_csv = _csv_text(
        ORDER_BUNDLE_COLUMNS,
        [[row["order_id"], row["customer"], row["paid_cents"],
          row["refund_cents"], row["net_cents"]] for row in orders])
    customers_csv = _csv_text(
        CUSTOMER_BUNDLE_COLUMNS,
        [[row["customer"], row["net_cents"]] for row in customers])
    summary_json = json.dumps(
        {
            "paid_cents": int(totals.get("paid_cents", 0)),
            "refund_cents": int(totals.get("refund_cents", 0)),
            "net_cents": int(totals.get("net_cents", 0)),
        },
        ensure_ascii=False, sort_keys=True, indent=2) + "\n"

    return {
        "orders.csv": orders_csv,
        "customers.csv": customers_csv,
        "summary.json": summary_json,
    }