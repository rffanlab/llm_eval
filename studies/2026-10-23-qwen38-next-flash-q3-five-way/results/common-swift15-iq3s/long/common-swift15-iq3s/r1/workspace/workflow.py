"""订单对账纯函数实现（v1 + v2契约 + 发布包导出）。

只使用标准库：csv, io, json, decimal, collections, datetime, math。
输入为UTF-8 CSV字符串，输出金额一律为整数分。
"""

import csv
import io
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _parse_amount_cents(raw, what, allow_multi_decimal):
    """解析金额字符串为非负整数分。

    拒绝NaN/Infinity/负数。
    v1: 最多两位小数；v2: 允许多位小数，Decimal ROUND_HALF_UP 到整数分。
    """
    if raw is None:
        raise ValueError(f"{what}: 金额缺失")
    s = raw.strip()
    if s == "":
        raise ValueError(f"{what}: 金额为空")
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{what}: 非法金额 {raw!r}")
    if d.is_nan() or d.is_infinite():
        raise ValueError(f"{what}: 金额非有限数值 {raw!r}")
    if d < 0:
        raise ValueError(f"{what}: 金额为负数 {raw!r}")
    if not allow_multi_decimal:
        exp = d.as_tuple().exponent
        if isinstance(exp, int) and exp < -2:
            raise ValueError(f"{what}: 金额超过两位小数 {raw!r}")
        cents = d * Decimal(100)
        if cents != cents.to_integral_value(rounding=ROUND_HALF_UP):
            raise ValueError(f"{what}: 金额无法精确转为整数分 {raw!r}")
        return int(cents.to_integral_value(rounding=ROUND_HALF_UP))
    cents = (d * Decimal(100)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(cents)


def _validate_datetime(s, what):
    """校验规范UTC字符串 YYYY-MM-DDTHH:MM:SSZ。"""
    ok = (len(s) == 20
          and s[4] == "-" and s[7] == "-" and s[10] == "T"
          and s[13] == ":" and s[16] == ":" and s[19] == "Z"
          and s[0:4].isdigit() and s[5:7].isdigit() and s[8:10].isdigit()
          and s[11:13].isdigit() and s[14:16].isdigit() and s[17:19].isdigit())
    if not ok:
        raise ValueError(f"{what}: 非法时间格式 {s!r}")
    month = int(s[5:7]); day = int(s[8:10])
    hh = int(s[11:13]); mm = int(s[14:16]); ss = int(s[17:19])
    if not (1 <= month <= 12 and 1 <= day <= 31
            and 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59):
        raise ValueError(f"{what}: 时间超出范围 {s!r}")
    return s


def _read_rows(csv_text, required_headers, kind):
    """解析CSV文本为dict行列表，校验表头。"""
    if csv_text is None:
        raise ValueError(f"{kind}: 输入为空")
    # 不修改输入；仅在内存中解析
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    if not rows:
        raise ValueError(f"{kind}: 缺少表头")
    header = rows[0]
    missing = [h for h in required_headers if h not in header]
    if missing:
        raise ValueError(f"{kind}: 缺少表头列 {missing}")
    out = []
    for line in rows[1:]:
        if not line or (len(line) == 1 and line[0].strip() == ""):
            continue  # 跳过空行
        if len(line) != len(header):
            raise ValueError(f"{kind}: 行列数与表头不一致: {line!r}")
        out.append({h: line[i] for i, h in enumerate(header)})
    return out


def reconcile(orders_csv, refunds_csv, policy="v1", cutoff=None):
    """按契约对账。policy="v1"保持v1行为；policy="v2"启用截止/退款状态/多位小数。

    输出结构与顺序与v1一致。
    """
    if policy not in ("v1", "v2"):
        raise ValueError(f"不支持的policy: {policy!r}")
    allow_multi = policy == "v2"
    if policy == "v2":
        if not cutoff or not isinstance(cutoff, str):
            raise ValueError("v2需要cutoff (YYYY-MM-DDTHH:MM:SSZ)")
        cutoff = _validate_datetime(cutoff, "cutoff")

    order_headers = ["order_id", "customer", "amount", "status"]
    refund_headers = ["refund_id", "order_id", "amount"]
    if policy == "v2":
        order_headers.append("created_at")
        refund_headers += ["status", "created_at"]

    order_rows = _read_rows(orders_csv, order_headers, "orders")
    refund_rows = _read_rows(refunds_csv, refund_headers, "refunds")

    # 订单去重：完全相同行只算一次；同id任何字段不同 -> ValueError
    orders = {}              # order_id -> dict
    order_signatures = {}
    for row in order_rows:
        oid = (row["order_id"] or "").strip()
        if oid == "":
            raise ValueError("orders: order_id为空")
        customer = (row["customer"] or "").strip()
        status = (row["status"] or "").strip().lower()
        if status not in ("paid", "cancelled"):
            raise ValueError(f"orders[{oid}]: 未知状态 {row['status']!r}")
        paid_cents = _parse_amount_cents(row["amount"], f"orders[{oid}]", allow_multi)
        created_at = ""
        if policy == "v2":
            created_at = (row.get("created_at") or "").strip()
            _validate_datetime(created_at, f"orders[{oid}].created_at")
        sig = (customer, str(paid_cents), status, created_at)
        if oid in order_signatures:
            if order_signatures[oid] != sig:
                raise ValueError(f"orders: 重复order_id {oid} 且字段不一致")
            continue
        order_signatures[oid] = sig
        orders[oid] = {"order_id": oid, "customer": customer,
                       "paid_cents": paid_cents, "status": status,
                       "created_at": created_at}

    # 退款去重（包含pending/截止后行也必须检查冲突）
    refunds = {}
    refund_signatures = {}
    for row in refund_rows:
        rid = (row["refund_id"] or "").strip()
        if rid == "":
            raise ValueError("refunds: refund_id为空")
        oid = (row["order_id"] or "").strip()
        refund_cents = _parse_amount_cents(row["amount"], f"refunds[{rid}]", allow_multi)
        status = "succeeded"
        created_at = ""
        if policy == "v2":
            status = (row.get("status") or "").strip().lower()
            if status not in ("succeeded", "pending"):
                raise ValueError(f"refunds[{rid}]: 未知状态 {row.get('status')!r}")
            created_at = (row.get("created_at") or "").strip()
            _validate_datetime(created_at, f"refunds[{rid}].created_at")
        sig = (oid, str(refund_cents), status, created_at)
        if rid in refund_signatures:
            if refund_signatures[rid] != sig:
                raise ValueError(f"refunds: 重复refund_id {rid} 且字段不一致")
            continue
        refund_signatures[rid] = sig
        refunds[rid] = {"refund_id": rid, "order_id": oid,
                        "refund_cents": refund_cents,
                        "status": status, "created_at": created_at}

    # 纳入范围：v1全部；v2只计 created_at<=cutoff 的订单/退款，且退款须succeeded
    def order_included(o):
        if policy == "v1":
            return True
        return o["created_at"] <= cutoff

    def refund_included(r):
        if policy == "v1":
            return True
        return r["status"] == "succeeded" and r["created_at"] <= cutoff

    # 校验有效（计入范围）的退款
    refund_by_order = {}
    for r in refunds.values():
        if not refund_included(r):
            continue
        oid = r["order_id"]
        order = orders.get(oid)
        if order is None:
            raise ValueError(f"refunds[{r['refund_id']}]: 未知订单 {oid}")
        if order["status"] != "paid":
            raise ValueError(f"refunds[{r['refund_id']}]: 订单 {oid} 非paid状态，不允许退款")
        if not order_included(order):
            # 订单存在但因截止时间排除 -> 忽略该退款
            continue
        refund_by_order.setdefault(oid, 0)
        refund_by_order[oid] += r["refund_cents"]
    for oid, total in refund_by_order.items():
        if total > orders[oid]["paid_cents"]:
            raise ValueError(f"orders[{oid}]: 累计退款超过已付金额")

    # 组装结果（结构与顺序保持v1）
    order_results = []
    customer_net = {}
    totals = {"paid_cents": 0, "refund_cents": 0, "net_cents": 0}
    for oid in sorted(orders):
        o = orders[oid]
        if o["status"] != "paid":
            continue
        if not order_included(o):
            continue
        refund_cents = refund_by_order.get(oid, 0)
        net_cents = o["paid_cents"] - refund_cents
        order_results.append({
            "order_id": oid,
            "customer": o["customer"],
            "paid_cents": o["paid_cents"],
            "refund_cents": refund_cents,
            "net_cents": net_cents,
        })
        customer_net[o["customer"]] = customer_net.get(o["customer"], 0) + net_cents
        totals["paid_cents"] += o["paid_cents"]
        totals["refund_cents"] += refund_cents
        totals["net_cents"] += net_cents

    customers = [{"customer": c, "net_cents": customer_net[c]}
                 for c in sorted(customer_net)]

    return {"orders": order_results, "customers": customers, "totals": totals}


def _csv_text(header, rows):
    """用标准csv writer生成CSV文本。"""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_bundle(result):
    """按发布契约导出恰好三个文件：orders.csv、customers.csv、summary.json。

    行顺序遵守reconcile排序；金额文本为整数；summary.json为totals的JSON。
    """
    if not isinstance(result, dict):
        raise ValueError("export_bundle: result必须是dict")
    for key in ("orders", "customers", "totals"):
        if key not in result:
            raise ValueError(f"export_bundle: 缺少字段 {key}")

    order_rows = []
    for o in result["orders"]:
        order_rows.append([
            str(o["order_id"]),
            str(o["customer"]),
            str(int(o["paid_cents"])),
            str(int(o["refund_cents"])),
            str(int(o["net_cents"])),
        ])
    orders_csv = _csv_text(
        ["order_id", "customer", "paid_cents", "refund_cents", "net_cents"],
        order_rows)

    customer_rows = []
    for c in result["customers"]:
        customer_rows.append([str(c["customer"]), str(int(c["net_cents"]))])
    customers_csv = _csv_text(["customer", "net_cents"], customer_rows)

    totals = result["totals"]
    summary = json.dumps({
        "paid_cents": int(totals["paid_cents"]),
        "refund_cents": int(totals["refund_cents"]),
        "net_cents": int(totals["net_cents"]),
    })

    return {"orders.csv": orders_csv,
            "customers.csv": customers_csv,
            "summary.json": summary}
