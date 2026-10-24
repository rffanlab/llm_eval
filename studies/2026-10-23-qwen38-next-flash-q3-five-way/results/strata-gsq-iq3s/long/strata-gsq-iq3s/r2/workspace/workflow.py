"""订单对账 v1/v2 实现。

契约见 spec-v1.md、spec-v2.md 与 release-spec.md：输入为 UTF-8 CSV 字符串，
输出使用整数分（Decimal 定点，不用 float）。v1 保留旧金额限制与旧 CSV 列契约；
v2 增加 created_at 截止、退款 status，以及多位小数 ROUND_HALF_UP 取整。
export_bundle 按发布契约产出恰好三个文件：orders.csv、customers.csv、summary.json。
"""

import csv
import io
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_V1_ORDERS_REQUIRED = ("order_id", "customer", "amount", "status")
_V1_REFUNDS_REQUIRED = ("refund_id", "order_id", "amount")
_V2_ORDERS_REQUIRED = ("order_id", "customer", "amount", "status", "created_at")
_V2_REFUNDS_REQUIRED = ("refund_id", "order_id", "amount", "status", "created_at")

_PAID = "paid"
_CANCELLED = "cancelled"
_EXCLUDED = "excluded"
_SUCCEEDED = "succeeded"
_PENDING = "pending"
_CUTOFF_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _amount_to_cents(raw, context, policy):
    """把金额字符串转成整数分；拒绝 NaN/Infinity/负数。

    v1: 最多两位小数（超出即报错）。
    v2: 允许多位小数，按 ROUND_HALF_UP 逐条取到整数分。
    """
    if raw is None:
        raise ValueError("%s: 缺少金额字段" % context)
    text = raw.strip()
    if text == "":
        raise ValueError("%s: 金额为空" % context)
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError("%s: 金额无法解析: %r" % (context, raw))
    if not value.is_finite():
        raise ValueError("%s: 金额必须是有限数: %r" % (context, raw))
    if value < 0:
        raise ValueError("%s: 金额不能为负: %r" % (context, raw))
    if policy == "v1":
        exponent = value.as_tuple().exponent
        if not isinstance(exponent, int) or exponent < -2:
            raise ValueError("%s: 金额最多两位小数: %r" % (context, raw))
        return int(value.scaleb(2).to_integral_value())
    quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(quantized.scaleb(2).to_integral_value())


def _read_rows(csv_text, required, kind):
    """读取 CSV 字符串，返回 (header, rows)；不修改输入内容。"""
    if csv_text is None:
        raise ValueError("%s: 输入必须是字符串" % kind)
    if not isinstance(csv_text, str):
        raise ValueError("%s: 输入必须是字符串" % kind)
    reader = csv.DictReader(io.StringIO(csv_text))
    header = reader.fieldnames
    if header is None:
        return [], []
    missing = [name for name in required if name not in header]
    if missing:
        raise ValueError("%s: 缺少列 %s" % (kind, ",".join(missing)))
    rows = []
    for index, row in enumerate(reader, start=2):
        if row.get(None) is not None:
            raise ValueError("%s 第%d行: 字段过多" % (kind, index))
        values = {}
        for name in header:
            if name is None:
                continue
            value = row.get(name)
            if value is None:
                raise ValueError("%s 第%d行: 缺少列 %s" % (kind, index, name))
            values[name] = value.strip()
        if all(value == "" for value in values.values()):
            continue
        rows.append(values)
    return header, rows


def _index_unique(rows, id_field, kind):
    """按 id 去重：完全相同的行只算一次；同 id 但任何字段不同抛 ValueError。

    pending / 截止后行虽不计入汇总，但重复 id 冲突仍必须拒绝。
    """
    seen = {}
    unique = []
    for row in rows:
        key = row.get(id_field, "")
        if key == "":
            raise ValueError("%s: %s 不能为空" % (kind, id_field))
        signature = tuple(row.get(name, "") for name in sorted(row))
        if key in seen:
            if seen[key] != signature:
                raise ValueError("%s %s 重复但字段不一致" % (kind, id_field))
            continue
        seen[key] = signature
        unique.append(row)
    return unique


def _validate_timestamp(text, context):
    """校验规范 UTC 字符串 YYYY-MM-DDTHH:MM:SSZ。"""
    if text == "":
        raise ValueError("%s: 缺少 created_at" % context)
    try:
        datetime.strptime(text, _CUTOFF_FORMAT)
    except ValueError:
        raise ValueError("%s: 非法时间 %r" % (context, text))
    return text


def _validate_cutoff(cutoff):
    if cutoff is None:
        raise ValueError("policy=v2 时 cutoff 必填")
    if not isinstance(cutoff, str):
        raise ValueError("cutoff 必须是字符串")
    return _validate_timestamp(cutoff.strip(), "cutoff")


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """按 v1/v2 契约对账，返回 orders / customers / totals。"""
    if policy not in ("v1", "v2"):
        raise ValueError("未知 policy: %r" % (policy,))
    if policy == "v2":
        cutoff = _validate_cutoff(cutoff)

    if policy == "v2":
        orders_required, refunds_required = (
            _V2_ORDERS_REQUIRED,
            _V2_REFUNDS_REQUIRED,
        )
    else:
        orders_required, refunds_required = _V1_ORDERS_REQUIRED, _V1_REFUNDS_REQUIRED

    _, order_rows = _read_rows(orders_csv, orders_required, "orders")
    _, refund_rows = _read_rows(refunds_csv, refunds_required, "refunds")

    order_rows = _index_unique(order_rows, "order_id", "orders")
    refund_rows = _index_unique(refund_rows, "refund_id", "refunds")

    orders = {}
    for row in order_rows:
        order_id = row["order_id"]
        customer = row["customer"]
        status = row["status"]
        if customer == "":
            raise ValueError("orders: customer 不能为空")
        if status not in (_PAID, _CANCELLED):
            raise ValueError("orders: 未知 status %r" % (status,))
        paid_cents = _amount_to_cents(row["amount"], "orders %s" % order_id, policy)
        if policy == "v2":
            created_at = _validate_timestamp(
                row.get("created_at", ""), "orders %s" % order_id
            )
            if status == _PAID and created_at > cutoff:
                # 截止后订单：保留记录用于退款校验，但不计入结果。
                status = _EXCLUDED
        orders[order_id] = {
            "order_id": order_id,
            "customer": customer,
            "status": status,
            "paid_cents": paid_cents,
        }

    refund_by_order = {}
    for row in refund_rows:
        refund_id = row["refund_id"]
        order_id = row["order_id"]
        amount_cents = _amount_to_cents(
            row["amount"], "refunds %s" % refund_id, policy
        )
        if policy == "v2":
            status = row["status"]
            if status not in (_SUCCEEDED, _PENDING):
                raise ValueError("refunds: 未知 status %r" % (status,))
            created_at = _validate_timestamp(
                row.get("created_at", ""), "refunds %s" % refund_id
            )
            effective = status == _SUCCEEDED and created_at <= cutoff
        else:
            effective = True
        if not effective:
            # pending 或截止后退款不计入汇总。
            continue
        order = orders.get(order_id)
        if order is None:
            raise ValueError("refunds %s: 未知订单 %s" % (refund_id, order_id))
        if order["status"] == _CANCELLED:
            raise ValueError(
                "refunds %s: 订单 %s 不是 paid 状态" % (refund_id, order_id)
            )
        if order["status"] == _EXCLUDED:
            # 订单存在但被截止时间排除：忽略该退款。
            continue
        refund_by_order[order_id] = refund_by_order.get(order_id, 0) + amount_cents

    for order_id, order in orders.items():
        if order["status"] != _PAID:
            continue
        refunded = refund_by_order.get(order_id, 0)
        if refunded > order["paid_cents"]:
            raise ValueError(
                "订单 %s 累计退款 %d 超过已付 %d"
                % (order_id, refunded, order["paid_cents"])
            )

    result_orders = []
    customer_totals = {}
    total_paid = 0
    total_refund = 0
    for order_id in sorted(orders):
        order = orders[order_id]
        if order["status"] != _PAID:
            continue
        paid_cents = order["paid_cents"]
        refund_cents = refund_by_order.get(order_id, 0)
        net_cents = paid_cents - refund_cents
        result_orders.append({
            "order_id": order_id,
            "customer": order["customer"],
            "paid_cents": paid_cents,
            "refund_cents": refund_cents,
            "net_cents": net_cents,
        })
        customer_totals[order["customer"]] = (
            customer_totals.get(order["customer"], 0) + net_cents
        )
        total_paid += paid_cents
        total_refund += refund_cents

    customers = [
        {"customer": name, "net_cents": customer_totals[name]}
        for name in sorted(customer_totals)
    ]
    return {
        "orders": result_orders,
        "customers": customers,
        "totals": {
            "paid_cents": total_paid,
            "refund_cents": total_refund,
            "net_cents": total_paid - total_refund,
        },
    }


def _rows_to_csv(header, rows):
    """用标准 csv writer 生成 CSV 文本（\\r\\n 行结束，金额已是整数）。"""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def export_bundle(result):
    """按 release-spec.md 导出恰好三个文件：orders.csv、customers.csv、summary.json。"""
    orders_rows = [
        [
            order["order_id"],
            order["customer"],
            str(order["paid_cents"]),
            str(order["refund_cents"]),
            str(order["net_cents"]),
        ]
        for order in result["orders"]
    ]
    customers_rows = [
        [customer["customer"], str(customer["net_cents"])]
        for customer in result["customers"]
    ]
    return {
        "orders.csv": _rows_to_csv(
            ("order_id", "customer", "paid_cents", "refund_cents", "net_cents"),
            orders_rows,
        ),
        "customers.csv": _rows_to_csv(("customer", "net_cents"), customers_rows),
        "summary.json": json.dumps(
            result["totals"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ),
    }
