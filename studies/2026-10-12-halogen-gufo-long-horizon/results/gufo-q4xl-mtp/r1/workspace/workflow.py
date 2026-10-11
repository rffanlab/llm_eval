"""订单对账 v1/v2。

reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None) -> dict
- v1契约见 spec-v1.md：整数分输出、十进制定点、去重与校验规则。
- v2变更见 spec-v2.md：cutoff必填、退款status/created_at、
  多位小数按 Decimal ROUND_HALF_UP 逐条取整到分。
发布契约见 release-spec.md：export_bundle 返回恰好三个文件
orders.csv、customers.csv、summary.json。
纯函数实现，仅使用标准库 csv/io/json/decimal，不访问文件/网络/进程。
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_ORDER_HEADER = ["order_id", "customer", "amount", "status", "created_at"]
_REFUND_HEADER_V1 = ["refund_id", "order_id", "amount"]
_REFUND_HEADER_V2 = ["refund_id", "order_id", "amount", "status", "created_at"]

_DIGITS = "0123456789"
_ONE = Decimal("1")


def _is_decimal_literal(text, max_frac=None):
    """非负十进制字面量（拒绝 NaN/Infinity/科学计数/负号）。

    max_frac=None 表示小数位数不限（v2），否则限制最多 max_frac 位（v1）。
    """
    if not text:
        return False
    if "." in text:
        parts = text.split(".")
        if len(parts) != 2:
            return False
        int_part, frac_part = parts
        if not int_part or any(c not in _DIGITS for c in int_part):
            return False
        if not frac_part or any(c not in _DIGITS for c in frac_part):
            return False
        if max_frac is not None and len(frac_part) > max_frac:
            return False
        return True
    return all(c in _DIGITS for c in text)


def _parse_amount_cents(raw, context, policy):
    """把金额字符串转成整数分；非法输入抛 ValueError。不使用 float。

    v1：最多两位小数（旧限制），直接精确转分。
    v2：允许多位小数，先乘100再按 ROUND_HALF_UP 逐条取整到分。
    """
    if raw is None:
        raise ValueError(f"{context}: missing amount")
    text = raw.strip()
    max_frac = 2 if policy == "v1" else None
    if not _is_decimal_literal(text, max_frac):
        raise ValueError(f"{context}: invalid amount {raw!r}")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:  # pragma: no cover - 校验已拦截
        raise ValueError(f"{context}: invalid amount {raw!r}") from exc
    if policy == "v2":
        return int((value * 100).quantize(_ONE, rounding=ROUND_HALF_UP))
    cents = value * 100
    if cents != cents.to_integral_value():  # pragma: no cover - 校验已拦截
        raise ValueError(f"{context}: amount not exact cents {raw!r}")
    return int(cents)


def _validate_cutoff(cutoff):
    """校验 YYYY-MM-DDTHH:MM:SSZ 格式（含基本范围）。"""
    if not isinstance(cutoff, str) or len(cutoff) != 20:
        raise ValueError(f"invalid cutoff {cutoff!r}")
    if (
        cutoff[4] != "-"
        or cutoff[7] != "-"
        or cutoff[10] != "T"
        or cutoff[13] != ":"
        or cutoff[16] != ":"
        or cutoff[19] != "Z"
    ):
        raise ValueError(f"invalid cutoff {cutoff!r}")
    year_text = cutoff[0:4]
    month_text = cutoff[5:7]
    day_text = cutoff[8:10]
    hour_text = cutoff[11:13]
    minute_text = cutoff[14:16]
    second_text = cutoff[17:19]
    for part in (year_text, month_text, day_text,
                 hour_text, minute_text, second_text):
        if any(c not in _DIGITS for c in part):
            raise ValueError(f"invalid cutoff {cutoff!r}")
    month, day = int(month_text), int(day_text)
    hour, minute, second = int(hour_text), int(minute_text), int(second_text)
    if int(year_text) < 1:
        raise ValueError(f"invalid cutoff {cutoff!r}")
    if not 1 <= month <= 12:
        raise ValueError(f"invalid cutoff {cutoff!r}")
    if not 1 <= day <= 31:
        raise ValueError(f"invalid cutoff {cutoff!r}")
    if hour > 23 or minute > 59 or second > 59:
        raise ValueError(f"invalid cutoff {cutoff!r}")
    return cutoff


def _read_rows(csv_text, header, kind):
    """解析CSV字符串为字典行列表，校验表头；不修改输入。"""
    if not isinstance(csv_text, str):
        raise ValueError(f"{kind}: input must be a string")
    reader = csv.reader(io.StringIO(csv_text))
    rows = [row for row in reader if row]
    if not rows:
        raise ValueError(f"{kind}: missing header")
    if rows[0] != header:
        raise ValueError(f"{kind}: unexpected header {rows[0]!r}")
    out = []
    for row in rows[1:]:
        if len(row) != len(header):
            raise ValueError(f"{kind}: malformed row {row!r}")
        out.append(dict(zip(header, row)))
    return out


def _dedupe(rows, id_field, kind):
    """相同id且完全相同的行只算一次；相同id不同内容（含pending/截止后行）抛 ValueError。"""
    seen = {}
    unique = []
    for row in rows:
        key = row[id_field]
        if key in seen:
            if seen[key] != row:
                raise ValueError(
                    f"{kind}: conflicting rows for {id_field}={key!r}"
                )
            continue  # 完全重复，忽略
        seen[key] = row
        unique.append(row)
    return unique


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    if policy not in ("v1", "v2"):
        raise ValueError(f"unsupported policy {policy!r}")
    if policy == "v2":
        if cutoff is None:
            raise ValueError("cutoff is required for policy v2")
        _validate_cutoff(cutoff)

    refund_header = _REFUND_HEADER_V1 if policy == "v1" else _REFUND_HEADER_V2
    order_rows = _dedupe(
        _read_rows(orders_csv, _ORDER_HEADER, "orders"), "order_id", "orders"
    )
    refund_rows = _dedupe(
        _read_rows(refunds_csv, refund_header, "refunds"), "refund_id", "refunds"
    )

    orders = {}
    for row in order_rows:
        status = row["status"]
        if status not in ("paid", "cancelled"):
            raise ValueError(f"orders: unknown status {status!r}")
        cents = _parse_amount_cents(
            row["amount"], f"orders {row['order_id']}", policy
        )
        orders[row["order_id"]] = {
            "order_id": row["order_id"],
            "customer": row["customer"],
            "status": status,
            "created_at": row["created_at"],
            "paid_cents": cents,
            "refund_cents": 0,
        }

    for row in refund_rows:
        order_id = row["order_id"]
        if policy == "v2":
            status = row["status"]
            if status not in ("succeeded", "pending"):
                raise ValueError(f"refunds: unknown status {status!r}")
            order = orders.get(order_id)
            if status == "succeeded":
                # 有效退款：真正不存在的订单 → ValueError
                if order is None:
                    raise ValueError(f"refunds: unknown order {order_id!r}")
                # cancelled 订单的有效退款 → ValueError
                if order["status"] != "paid":
                    raise ValueError(
                        f"refunds: order {order_id!r} is not paid"
                    )
                # 因截止时间被排除的订单：忽略该退款
                if order["created_at"] > cutoff:
                    continue
                # 截止后的退款：忽略
                if row["created_at"] > cutoff:
                    continue
            else:
                # pending 退款一律不计
                continue
        else:
            order = orders.get(order_id)
            if order is None:
                raise ValueError(f"refunds: unknown order {order_id!r}")
            if order["status"] != "paid":
                raise ValueError(
                    f"refunds: order {order_id!r} is not paid"
                )
        cents = _parse_amount_cents(
            row["amount"], f"refunds {row['refund_id']}", policy
        )
        order["refund_cents"] += cents
        if order["refund_cents"] > order["paid_cents"]:
            raise ValueError(
                f"refunds: order {order_id!r} refund exceeds paid amount"
            )

    result_orders = []
    customers = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for order in sorted(orders.values(), key=lambda o: o["order_id"]):
        if order["status"] != "paid":
            continue
        # v2：截止后创建的订单不计入结果
        if policy == "v2" and order["created_at"] > cutoff:
            continue
        net = order["paid_cents"] - order["refund_cents"]
        result_orders.append(
            {
                "order_id": order["order_id"],
                "customer": order["customer"],
                "paid_cents": order["paid_cents"],
                "refund_cents": order["refund_cents"],
                "net_cents": net,
            }
        )
        totals["paid_cents"] += order["paid_cents"]
        totals["refund_cents"] += order["refund_cents"]
        totals["net_cents"] += net
        customers[order["customer"]] = (
            customers.get(order["customer"], 0) + net
        )

    result_customers = [
        {"customer": name, "net_cents": customers[name]}
        for name in sorted(customers)
    ]
    return {
        "orders": result_orders,
        "customers": result_customers,
        "totals": totals,
    }


def _csv_text(header, rows):
    """用标准csv writer生成UTF-8 CSV文本（\\n行结束）。"""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    """按发布契约导出恰好三个文件：orders.csv、customers.csv、summary.json。

    - orders.csv 表头 order_id,customer,paid_cents,refund_cents,net_cents
    - customers.csv 表头 customer,net_cents
    - 行顺序沿用 reconcile 的排序；金额为整数字符串
    - summary.json 解析后恰好等于 result["totals"]
    """
    order_rows = [
        [
            o["order_id"],
            o["customer"],
            str(o["paid_cents"]),
            str(o["refund_cents"]),
            str(o["net_cents"]),
        ]
        for o in result["orders"]
    ]
    customer_rows = [
        [c["customer"], str(c["net_cents"])] for c in result["customers"]
    ]
    return {
        "orders.csv": _csv_text(
            ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
            order_rows,
        ),
        "customers.csv": _csv_text(
            ["customer", "net_cents"], customer_rows
        ),
        "summary.json": json.dumps(result["totals"], sort_keys=True),
    }
