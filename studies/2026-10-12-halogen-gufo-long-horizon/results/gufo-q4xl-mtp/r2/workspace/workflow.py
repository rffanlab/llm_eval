"""订单对账 v1/v2。

reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None) -> dict
- v1 契约见 spec-v1.md：整数分输出、十进制定点、去重与校验规则。
- v2 变更见 spec-v2.md：cutoff 必填、退款带 status/created_at、
  金额多位小数按 Decimal ROUND_HALF_UP 逐条取整到分。

export_bundle(result) -> dict[str, str]
- 见 release-spec.md：恰好 orders.csv / customers.csv / summary.json 三个文件。

纯函数实现，仅使用标准库 csv/io/json/decimal，不访问文件/网络/进程。
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_ORDER_HEADER = ["order_id", "customer", "amount", "status", "created_at"]
_REFUND_HEADER_V1 = ["refund_id", "order_id", "amount"]
_REFUND_HEADER_V2 = ["refund_id", "order_id", "amount", "status", "created_at"]


def _is_valid_decimal(text):
    """非负十进制字面量（任意位小数）；拒绝 NaN/Infinity/科学计数/负号/空。"""
    if not text:
        return False
    parts = text.split(".")
    if len(parts) > 2:
        return False
    if not parts[0].isdigit():
        return False
    if len(parts) == 2 and not parts[1].isdigit():
        return False
    return True


def _is_valid_cutoff(text):
    """严格校验 YYYY-MM-DDTHH:MM:SSZ。"""
    if not isinstance(text, str) or len(text) != 20 or text[-1] != "Z":
        return False
    if text[4] != "-" or text[7] != "-" or text[10] != "T":
        return False
    if text[13] != ":" or text[16] != ":":
        return False
    digit_positions = (0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18)
    if not all(text[i] in "0123456789" for i in digit_positions):
        return False
    year, month, day = int(text[0:4]), int(text[5:7]), int(text[8:10])
    hour, minute, second = int(text[11:13]), int(text[14:16]), int(text[17:19])
    if not 1 <= month <= 12:
        return False
    if hour > 23 or minute > 59 or second > 59:
        return False
    days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    leap = (year % 4 == 0 and year % 100 != 0) or year % 400 == 0
    if leap:
        days_in_month[1] = 29
    return 1 <= day <= days_in_month[month - 1]


def _parse_amount_cents(raw, context, max_two_decimals):
    """金额字符串 -> 整数分。v1最多两位小数；v2任意位按ROUND_HALF_UP逐条取整。"""
    if raw is None:
        raise ValueError(f"{context}: missing amount")
    text = raw.strip()
    if not _is_valid_decimal(text):
        raise ValueError(f"{context}: invalid amount {raw!r}")
    if max_two_decimals and "." in text and len(text.split(".")[1]) > 2:
        raise ValueError(f"{context}: amount has more than two decimals {raw!r}")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:  # pragma: no cover - 校验已拦截
        raise ValueError(f"{context}: invalid amount {raw!r}") from exc
    cents = value.scaleb(2).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(cents)


def _read_rows(csv_text, expected_header, kind):
    """解析CSV字符串为字典行，校验表头；不修改输入。"""
    if not isinstance(csv_text, str):
        raise ValueError(f"{kind}: input must be a string")
    reader = csv.reader(io.StringIO(csv_text))
    rows = [row for row in reader if row]
    if not rows:
        raise ValueError(f"{kind}: missing header")
    header = rows[0]
    if header != expected_header:
        raise ValueError(f"{kind}: bad header {header!r}, expected {expected_header!r}")
    out = []
    for row in rows[1:]:
        if len(row) != len(expected_header):
            raise ValueError(f"{kind}: bad row width {row!r}")
        out.append(dict(zip(expected_header, row)))
    return out


def _dedupe(rows, id_field, kind):
    """按id去重：完全相同的行只算一次；同id不同内容抛 ValueError。

    对全部行（包括 pending / 截止后的行）做冲突检查。
    """
    seen = {}
    unique = []
    for row in rows:
        key = row[id_field]
        if key in seen:
            if seen[key] != row:
                raise ValueError(
                    f"{kind}: duplicate {id_field}={key!r} with conflicting fields"
                )
            continue
        seen[key] = row
        unique.append(row)
    return unique


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy not in ("v1", "v2"):
        raise ValueError(f"unsupported policy {policy!r}")
    max_two_decimals = policy == "v1"
    if policy == "v2":
        if cutoff is None:
            raise ValueError("v2 requires cutoff")
        if not _is_valid_cutoff(cutoff):
            raise ValueError(f"invalid cutoff {cutoff!r}")

    order_rows = _read_rows(orders_csv, _ORDER_HEADER, "orders")
    refund_header = _REFUND_HEADER_V2 if policy == "v2" else _REFUND_HEADER_V1
    refund_rows = _read_rows(refunds_csv, refund_header, "refunds")

    # 去重与冲突检查先于任何过滤（pending/截止后行同样参与冲突检查）。
    order_rows = _dedupe(order_rows, "order_id", "orders")
    refund_rows = _dedupe(refund_rows, "refund_id", "refunds")

    orders = {}
    orders_in_scope = {}
    for row in order_rows:
        status = row["status"]
        if status not in ("paid", "cancelled"):
            raise ValueError(f"orders: unknown status {status!r}")
        cents = _parse_amount_cents(
            row["amount"], f"orders {row['order_id']}", max_two_decimals
        )
        order = {
            "order_id": row["order_id"],
            "customer": row["customer"],
            "status": status,
            "paid_cents": cents,
            "refund_cents": 0,
        }
        orders[row["order_id"]] = order
        in_scope = status == "paid" and (
            policy == "v1" or row["created_at"] <= cutoff
        )
        if in_scope:
            orders_in_scope[row["order_id"]] = order

    for row in refund_rows:
        order_id = row["order_id"]
        status = row["status"] if policy == "v2" else "succeeded"
        if policy == "v2" and status not in ("succeeded", "pending"):
            raise ValueError(f"refunds: unknown status {status!r}")

        order = orders.get(order_id)
        if order is None:
            # 真正不存在的订单：任何退款行都非法。
            raise ValueError(f"refunds: unknown order {order_id!r}")
        if order["status"] != "paid":
            # cancelled 订单的退款始终非法。
            raise ValueError(f"refunds: order {order_id!r} is not paid")

        if policy == "v2":
            if status == "pending":
                continue  # pending 退款不计
            if row["created_at"] > cutoff:
                continue  # 截止后退款不计
            if order_id not in orders_in_scope:
                continue  # 订单因截止时间被排除：忽略该退款

        refund_cents = _parse_amount_cents(
            row["amount"], f"refunds {row['refund_id']}", max_two_decimals
        )
        if order["refund_cents"] + refund_cents > order["paid_cents"]:
            raise ValueError(
                f"refunds: order {order_id!r} refund exceeds paid amount"
            )
        order["refund_cents"] += refund_cents

    paid_orders = sorted(orders_in_scope.values(), key=lambda o: o["order_id"])

    orders_out = []
    customers_net = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for o in paid_orders:
        net = o["paid_cents"] - o["refund_cents"]
        orders_out.append(
            {
                "order_id": o["order_id"],
                "customer": o["customer"],
                "paid_cents": o["paid_cents"],
                "refund_cents": o["refund_cents"],
                "net_cents": net,
            }
        )
        customers_net[o["customer"]] = customers_net.get(o["customer"], 0) + net
        totals["paid_cents"] += o["paid_cents"]
        totals["refund_cents"] += o["refund_cents"]
        totals["net_cents"] += net

    customers_out = [
        {"customer": name, "net_cents": customers_net[name]}
        for name in sorted(customers_net)
    ]

    return {"orders": orders_out, "customers": customers_out, "totals": totals}


def _csv_text(header, rows):
    """用标准csv writer生成LF结尾的CSV文本。"""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    """按 release-spec.md 导出恰好三个文件的发布包 dict[str, str]。"""
    orders_csv = _csv_text(
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
        [
            [
                o["order_id"],
                o["customer"],
                str(o["paid_cents"]),
                str(o["refund_cents"]),
                str(o["net_cents"]),
            ]
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
