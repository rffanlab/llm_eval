"""订单对账纯函数实现（v1 + v2）与发布包导出。

reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None)
export_bundle(result) -> {"orders.csv", "customers.csv", "summary.json"}
仅依赖标准库 csv / io / json / decimal，不访问文件、网络或进程。

v1: 旧列契约，金额最多两位小数，无截止过滤。
v2: cutoff必填(YYYY-MM-DDTHH:MM:SSZ)；退款含status/created_at；
    只计 created_at<=cutoff 的paid订单，以及 created_at<=cutoff 且
    succeeded 的退款；金额允许多位小数，按ROUND_HALF_UP逐条取整到分。
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_ORDER_HEADER = ["order_id", "customer", "amount", "status", "created_at"]
_REFUND_HEADER_V1 = ["refund_id", "order_id", "amount"]
_REFUND_HEADER_V2 = ["refund_id", "order_id", "amount", "status", "created_at"]

_DIGITS = "0123456789"


def _valid_v1_amount_text(text):
    """v1金额：非负十进制，最多两位小数，无符号/指数。"""
    if not text:
        return False
    if not all("0" <= ch <= "9" or ch == "." for ch in text):
        return False
    parts = text.split(".")
    if len(parts) > 2:
        return False
    if len(parts) == 2 and len(parts[1]) > 2:
        return False
    if parts[0] == "" and (len(parts) < 2 or parts[1] == ""):
        return False
    return True


def _valid_v2_amount_text(text):
    """v2金额：非负十进制，任意位数小数，无符号/指数。"""
    if not text:
        return False
    if not all(ch in _DIGITS or ch == "." for ch in text):
        return False
    parts = text.split(".")
    if len(parts) > 2:
        return False
    if parts[0] == "" and (len(parts) < 2 or parts[1] == ""):
        return False
    return True


def _valid_timestamp(text):
    """严格校验 YYYY-MM-DDTHH:MM:SSZ（数字位置固定，字典序可比较）。"""
    if len(text) != 20 or text[19] != "Z" or text[10] != "T":
        return False
    if text[4] != "-" or text[7] != "-" or text[13] != ":" or text[16] != ":":
        return False
    positions = (0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18)
    return all(ch in _DIGITS for ch in (text[i] for i in positions))


def _to_cents(value):
    """Decimal元 -> 整数分，ROUND_HALF_UP。"""
    scaled = value.scaleb(2)
    return int(scaled.to_integral_value(rounding=ROUND_HALF_UP))


def _parse_amount_cents(raw, context, policy):
    """金额字符串转整数分；按policy校验格式，非法输入抛ValueError。"""
    if raw is None:
        raise ValueError("%s: missing amount" % context)
    text = raw.strip()
    valid = _valid_v1_amount_text(text) if policy == "v1" else _valid_v2_amount_text(text)
    if not valid:
        # 明确拒绝负数、NaN/Infinity、科学计数法；v1另拒超过两位小数
        raise ValueError("%s: invalid amount %r" % (context, raw))
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("%s: invalid amount %r" % (context, raw))
    if not value.is_finite() or value < 0:
        raise ValueError("%s: invalid amount %r" % (context, raw))
    return _to_cents(value)


def _read_rows(csv_text, expected_header, kind):
    """解析CSV字符串，校验表头，返回数据行列表（每行为字段值列表）。"""
    if csv_text is None:
        raise ValueError("%s csv is None" % kind)
    reader = csv.reader(csv_text.splitlines())
    rows = [row for row in reader if row and any(field.strip() != "" for field in row)]
    if not rows:
        return []
    header = [field.strip() for field in rows[0]]
    if header != expected_header:
        raise ValueError("%s: unexpected header %r" % (kind, rows[0]))
    data = []
    for row in rows[1:]:
        if len(row) != len(expected_header):
            raise ValueError("%s: bad row width %r" % (kind, row))
        data.append([field.strip() for field in row])
    return data


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy not in ("v1", "v2"):
        raise ValueError("unsupported policy %r" % (policy,))
    if policy == "v2":
        if not cutoff or not _valid_timestamp(cutoff):
            raise ValueError("v2 requires cutoff in YYYY-MM-DDTHH:MM:SSZ format")

    order_rows = _read_rows(orders_csv, _ORDER_HEADER, "orders")
    refund_header = _REFUND_HEADER_V1 if policy == "v1" else _REFUND_HEADER_V2
    refund_rows = _read_rows(refunds_csv, refund_header, "refunds")

    # ---- 订单：去重 + 校验 ----
    orders = {}  # order_id -> dict
    for row in order_rows:
        order_id, customer, amount_raw, status, created_at = row
        if not order_id:
            raise ValueError("orders: empty order_id")
        if status not in ("paid", "cancelled"):
            raise ValueError("orders: unknown status %r" % (status,))
        if policy == "v2" and not _valid_timestamp(created_at):
            raise ValueError("order %s: invalid created_at %r" % (order_id, created_at))
        paid_cents = _parse_amount_cents(amount_raw, "order %s" % order_id, policy)
        record = {
            "order_id": order_id,
            "customer": customer,
            "paid_cents": paid_cents,
            "status": status,
            "created_at": created_at,
        }
        existing = orders.get(order_id)
        if existing is None:
            orders[order_id] = record
        elif existing != record:
            raise ValueError(
                "orders: conflicting duplicate order_id %r" % (order_id,)
            )

    # ---- 退款：去重 + 校验 ----
    refunds = {}  # refund_id -> dict
    for row in refund_rows:
        if policy == "v1":
            refund_id, order_id, amount_raw = row
            status = "succeeded"
            created_at = None
        else:
            refund_id, order_id, amount_raw, status, created_at = row
            if status not in ("succeeded", "pending"):
                raise ValueError("refund %s: unknown status %r" % (refund_id, status))
            if not _valid_timestamp(created_at):
                raise ValueError("refund %s: invalid created_at %r" % (refund_id, created_at))
        if not refund_id:
            raise ValueError("refunds: empty refund_id")
        refund_cents = _parse_amount_cents(amount_raw, "refund %s" % refund_id, policy)
        record = {
            "refund_id": refund_id,
            "order_id": order_id,
            "refund_cents": refund_cents,
            "status": status,
            "created_at": created_at,
        }
        existing = refunds.get(refund_id)
        if existing is None:
            refunds[refund_id] = record
        elif existing != record:
            # 包含pending/截止后行的重复id冲突也必须拒绝
            raise ValueError(
                "refunds: conflicting duplicate refund_id %r" % (refund_id,)
            )

    # ---- 退款归属校验（v2只对“有效”退款：succeeded且未过期）----
    refund_by_order = {}
    for record in refunds.values():
        if policy == "v2" and (
            record["status"] != "succeeded" or record["created_at"] > cutoff
        ):
            continue  # pending或截止后退款不计
        order_id = record["order_id"]
        order = orders.get(order_id)
        if order is None:
            raise ValueError(
                "refund %s: unknown order %r" % (record["refund_id"], order_id)
            )
        if order["status"] != "paid":
            raise ValueError(
                "refund %s: order %s is not paid" % (record["refund_id"], order_id)
            )
        if policy == "v2" and order["created_at"] > cutoff:
            continue  # 订单存在但被截止时间排除：忽略该退款
        refund_by_order[order_id] = refund_by_order.get(order_id, 0) + record["refund_cents"]

    for order_id, total_refund in refund_by_order.items():
        order = orders[order_id]
        if total_refund > order["paid_cents"]:
            raise ValueError(
                "order %s: refunds %d exceed paid %d"
                % (order_id, total_refund, order["paid_cents"])
            )

    # ---- 汇总 ----
    order_results = []
    customer_net = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for order_id in sorted(orders):
        order = orders[order_id]
        if order["status"] != "paid":
            continue
        if policy == "v2" and order["created_at"] > cutoff:
            continue  # 截止后订单不计
        refund_cents = refund_by_order.get(order_id, 0)
        net_cents = order["paid_cents"] - refund_cents
        order_results.append(
            {
                "order_id": order_id,
                "customer": order["customer"],
                "paid_cents": order["paid_cents"],
                "refund_cents": refund_cents,
                "net_cents": net_cents,
            }
        )
        customer_net[order["customer"]] = customer_net.get(order["customer"], 0) + net_cents
        totals["paid_cents"] += order["paid_cents"]
        totals["refund_cents"] += refund_cents
        totals["net_cents"] += net_cents

    customers = [
        {"customer": name, "net_cents": customer_net[name]}
        for name in sorted(customer_net)
    ]

    return {
        "orders": order_results,
        "customers": customers,
        "totals": {
            "paid_cents": totals["paid_cents"],
            "refund_cents": totals["refund_cents"],
            "net_cents": totals["net_cents"],
        },
    }


def _csv_text(header, rows):
    """用标准csv.writer把表头+行序列写成CSV文本。"""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    """把reconcile结果导出为发布包：orders.csv / customers.csv / summary.json。"""
    orders_csv = _csv_text(
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
        [
            [
                order["order_id"],
                order["customer"],
                "%d" % order["paid_cents"],
                "%d" % order["refund_cents"],
                "%d" % order["net_cents"],
            ]
            for order in result["orders"]
        ],
    )
    customers_csv = _csv_text(
        ["customer", "net_cents"],
        [[cust["customer"], "%d" % cust["net_cents"]] for cust in result["customers"]],
    )
    summary_json = json.dumps(result["totals"], sort_keys=True)
    return {
        "orders.csv": orders_csv,
        "customers.csv": customers_csv,
        "summary.json": summary_json,
    }
