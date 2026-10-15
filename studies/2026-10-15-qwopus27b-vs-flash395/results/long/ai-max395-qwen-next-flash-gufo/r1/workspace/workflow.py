"""订单对账纯函数实现（v1/v2契约）与发布包导出。

只使用标准库中的 csv/io/decimal/math 等；不访问文件、网络或进程。
金额使用十进制定点解析为整数分，绝不使用 float 乘 100。
"""

import csv
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import StringIO


def _validate_cutoff(cutoff):
    """校验cutoff为YYYY-MM-DDTHH:MM:SSZ且各字段在合法范围。"""
    bad = "cutoff必须为合法UTC时间 YYYY-MM-DDTHH:MM:SSZ: %r" % (cutoff,)
    if not isinstance(cutoff, str) or len(cutoff) != 20:
        raise ValueError(bad)
    digits_ok = all(
        cutoff[i].isdigit()
        for i in (0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18)
    )
    shape_ok = (
        cutoff[4] == "-" and cutoff[7] == "-" and cutoff[10] == "T"
        and cutoff[13] == ":" and cutoff[16] == ":" and cutoff[19] == "Z"
    )
    if not digits_ok or not shape_ok:
        raise ValueError(bad)
    year = int(cutoff[0:4])
    month = int(cutoff[5:7])
    day = int(cutoff[8:10])
    hour = int(cutoff[11:13])
    minute = int(cutoff[14:16])
    second = int(cutoff[17:19])
    if not (1 <= month <= 12 and 1 <= day <= 31 and hour <= 23
            and minute <= 59 and second <= 59 and year >= 1):
        raise ValueError(bad)


def _parse_cents(raw, context, allow_extra_decimals=False):
    """把金额字符串解析为非负整数分。

    v1(allow_extra_decimals=False): 最多两位小数，超出抛ValueError。
    v2(allow_extra_decimals=True):  任意位数小数按ROUND_HALF_UP取整到分。
    两者均拒绝: 空值、NaN、Infinity、负数、非法格式。
    """
    if raw is None:
        raise ValueError("%s: 金额缺失" % context)
    text = str(raw).strip()
    if text == "":
        raise ValueError("%s: 金额为空" % context)
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("%s: 非法金额 %r" % (context, raw))
    if not value.is_finite():
        raise ValueError("%s: 金额非有限数 %r" % (context, raw))
    if value < 0:
        raise ValueError("%s: 金额为负 %r" % (context, raw))
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int):
        raise ValueError("%s: 金额格式非法 %r" % (context, raw))
    if not allow_extra_decimals and exponent < -2:
        raise ValueError("%s: 金额超过两位小数 %r" % (context, raw))
    scaled = (value * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(scaled)


def _read_rows(csv_text, required_headers, kind):
    """解析CSV字符串为字典行列表，校验表头，不修改输入。"""
    if csv_text is None:
        raise ValueError("%s: 输入缺失" % kind)
    reader = csv.reader(StringIO(csv_text))
    try:
        header = next(reader)
    except StopIteration:
        raise ValueError("%s: 缺少表头" % kind)
    header = [h.strip() for h in header]
    for name in required_headers:
        if name not in header:
            raise ValueError("%s: 缺少列 %s" % (kind, name))
    rows = []
    for record in reader:
        if not record or all((cell is None or str(cell).strip() == "") for cell in record):
            continue
        row = {}
        for idx, name in enumerate(header):
            row[name] = record[idx].strip() if idx < len(record) else ""
        for name in required_headers:
            if row.get(name, "") == "":
                raise ValueError("%s: 行缺少必填字段 %s: %r" % (kind, name, record))
        rows.append(row)
    return rows


def _dedupe(rows, id_field, kind):
    """按id去重：完全相同的行只算一次；同id不同内容抛ValueError。

    冲突检查覆盖所有行（包括pending或截止后的行）。
    """
    seen = {}
    unique = []
    for row in rows:
        key = row[id_field]
        if key in seen:
            if seen[key] != row:
                raise ValueError("%s: id %s 重复但字段不同" % (kind, key))
            continue
        seen[key] = dict(row)
        unique.append(row)
    return unique


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """按v1/v2契约对账，返回纯数据字典。"""
    if policy not in ("v1", "v2"):
        raise ValueError("不支持的policy: %r" % (policy,))
    is_v2 = policy == "v2"
    if is_v2:
        if cutoff is None:
            raise ValueError("policy=v2时cutoff必填")
        _validate_cutoff(cutoff)

    order_headers = ["order_id", "customer", "amount", "status"]
    refund_headers = ["refund_id", "order_id", "amount"]
    if is_v2:
        order_headers.append("created_at")
        refund_headers.extend(["status", "created_at"])

    order_rows = _dedupe(_read_rows(orders_csv, order_headers, "orders"), "order_id", "orders")
    refund_rows = _dedupe(_read_rows(refunds_csv, refund_headers, "refunds"), "refund_id", "refunds")

    orders = {}
    order_status = {}
    for row in order_rows:
        oid = row["order_id"]
        status = row["status"].lower()
        if status not in ("paid", "cancelled"):
            raise ValueError("orders: 未知状态 %r" % row["status"])
        order_status[oid] = status
        if status != "paid":
            continue
        if is_v2 and row["created_at"] > cutoff:
            # 截止后订单不计入结果
            continue
        orders[oid] = {
            "order_id": oid,
            "customer": row["customer"],
            "paid_cents": _parse_cents(row["amount"], "orders[%s]" % oid, is_v2),
            "refund_cents": 0,
        }

    for row in refund_rows:
        oid = row["order_id"]
        rid = row["refund_id"]
        if is_v2:
            rstatus = row["status"].lower()
            if rstatus not in ("succeeded", "pending"):
                raise ValueError("refunds: 未知状态 %r" % row["status"])
            if rstatus != "succeeded":
                # pending退款不计
                continue
            if row["created_at"] > cutoff:
                # 截止后退款不计
                continue
            if oid not in order_status:
                raise ValueError("refunds: %s 引用未知订单 %s" % (rid, oid))
            if order_status[oid] == "cancelled":
                raise ValueError("refunds: %s 引用已取消订单 %s" % (rid, oid))
            if oid not in orders:
                # 订单存在但因截止时间被排除，忽略该退款
                continue
        else:
            if oid not in order_status:
                raise ValueError("refunds: %s 引用未知订单 %s" % (rid, oid))
            if order_status[oid] != "paid":
                raise ValueError("refunds: %s 引用已取消订单 %s" % (rid, oid))
        cents = _parse_cents(row["amount"], "refunds[%s]" % rid, is_v2)
        order = orders[oid]
        if order["refund_cents"] + cents > order["paid_cents"]:
            raise ValueError("refunds: 订单 %s 累计退款超过已付金额" % oid)
        order["refund_cents"] += cents

    result_orders = []
    customer_net = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for oid in sorted(orders):
        order = orders[oid]
        net = order["paid_cents"] - order["refund_cents"]
        result_orders.append({
            "order_id": oid,
            "customer": order["customer"],
            "paid_cents": order["paid_cents"],
            "refund_cents": order["refund_cents"],
            "net_cents": net,
        })
        customer_net[order["customer"]] = customer_net.get(order["customer"], 0) + net
        totals["paid_cents"] += order["paid_cents"]
        totals["refund_cents"] += order["refund_cents"]
        totals["net_cents"] += net

    result_customers = [
        {"customer": name, "net_cents": customer_net[name]}
        for name in sorted(customer_net)
    ]

    return {
        "orders": result_orders,
        "customers": result_customers,
        "totals": totals,
    }


def _csv_text(rows, header):
    """用标准csv writer把字典行序列化为CSV文本（\\r\\n行结束）。"""
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in rows:
        writer.writerow([row[name] for name in header])
    return buf.getvalue()


def export_bundle(result):
    """按发布契约导出恰好三个文件：orders.csv、customers.csv、summary.json。"""
    if not isinstance(result, dict) or "orders" not in result \
            or "customers" not in result or "totals" not in result:
        raise ValueError("result缺少orders/customers/totals字段")

    orders_header = ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"]
    customers_header = ["customer", "net_cents"]

    order_rows = []
    for order in result["orders"]:
        order_rows.append({
            "order_id": str(order["order_id"]),
            "customer": str(order["customer"]),
            "paid_cents": str(int(order["paid_cents"])),
            "refund_cents": str(int(order["refund_cents"])),
            "net_cents": str(int(order["net_cents"])),
        })
    customer_rows = []
    for customer in result["customers"]:
        customer_rows.append({
            "customer": str(customer["customer"]),
            "net_cents": str(int(customer["net_cents"])),
        })

    totals = result["totals"]
    summary = json.dumps({
        "paid_cents": int(totals["paid_cents"]),
        "refund_cents": int(totals["refund_cents"]),
        "net_cents": int(totals["net_cents"]),
    }, sort_keys=True)

    return {
        "orders.csv": _csv_text(order_rows, orders_header),
        "customers.csv": _csv_text(customer_rows, customers_header),
        "summary.json": summary,
    }
