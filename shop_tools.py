# Магазин «Сулайман-Тоо» — Продано / не закуплено и полная выгрузка
# Версия: 1.0

import io
import streamlit as st
import pandas as pd
from datetime import datetime
from database import get_rows


def parse_day(value):
    try:
        text = str(value)[:10]
        if "." in text:
            return datetime.strptime(text, "%d.%m.%Y").date()
        return datetime.strptime(text, "%Y-%m-%d").date()
    except Exception:
        return None


def product_name(row):
    return str(row.get("pure_name") or row.get("name") or "").split("|")[0].strip().lower()


def show_archive_page():
    user_role = st.session_state.get("user", {}).get("role", "Кассир")
    if user_role != "Администратор":
        st.warning("Этот раздел только для администратора.")
        return

    st.header("Продано и не закуплено")
    st.caption("Слева что ушло со склада. Справа то, что продали и новую партию после этого не принимали.")

    sales = get_rows("sales")
    products = get_rows("products")
    clients = get_rows("clients")
    payments = get_rows("credit_payments")
    cash = get_rows("cash_operations")

    today = datetime.now().date()
    month_start = today.replace(day=1)
    period = st.date_input("Период продаж", value=(month_start, today), key="sold_period")
    if isinstance(period, tuple) and len(period) == 2:
        start, end = period
    else:
        start = end = today

    sold = {}
    for sale in sales:
        day = parse_day(sale.get("day") or sale.get("date"))
        if not day or day < start or day > end:
            continue
        name = product_name(sale)
        if not name:
            continue
        item = sold.setdefault(name, {"qty": 0, "sum": 0.0, "last": day})
        item["qty"] += int(sale.get("qty") or 0)
        item["sum"] += float(sale.get("total_sale") or 0)
        if day > item["last"]:
            item["last"] = day

    receipts = {}
    stock_now = {}
    for product in products:
        name = str(product.get("name") or "").strip().lower()
        if not name:
            continue
        day = parse_day(product.get("date"))
        qty = int(product.get("qty") or 0)
        stock_now[name] = stock_now.get(name, 0) + qty
        if day and (name not in receipts or day > receipts[name]):
            receipts[name] = day

    sold_rows = []
    missing_rows = []
    for name, item in sold.items():
        last_buy = receipts.get(name)
        left = stock_now.get(name, 0)
        bought_after = bool(last_buy and last_buy >= item["last"])
        sold_rows.append({
            "Товар": name.capitalize(),
            "Продано, шт": item["qty"],
            "Сумма продаж": int(item["sum"]),
            "Последняя продажа": item["last"].strftime("%d.%m.%Y"),
            "Сейчас на складе": left,
        })
        if not bought_after:
            missing_rows.append({
                "Товар": name.capitalize(),
                "Продано, шт": item["qty"],
                "Последняя продажа": item["last"].strftime("%d.%m.%Y"),
                "Последняя закупка": last_buy.strftime("%d.%m.%Y") if last_buy else "не было",
                "Сейчас на складе": left,
            })

    sold_df = pd.DataFrame(sold_rows)
    missing_df = pd.DataFrame(missing_rows)
    if not sold_df.empty:
        sold_df = sold_df.sort_values("Продано, шт", ascending=False)
    if not missing_df.empty:
        missing_df = missing_df.sort_values("Продано, шт", ascending=False)

    left, right = st.columns(2)
    left.subheader("Продано со склада")
    if sold_df.empty:
        left.info("За период продаж нет.")
    else:
        left.dataframe(sold_df, use_container_width=True, hide_index=True)
    right.subheader("Продано и обратно не закуплено")
    if missing_df.empty:
        right.info("Всё проданное после этого закупали снова, либо продаж нет.")
    else:
        right.dataframe(missing_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("Скачать всё")
    stock_rows = []
    for product in products:
        qty = int(product.get("qty") or 0)
        cost = float(product.get("cost") or 0)
        stock_rows.append({
            "Товар": str(product.get("name") or "").capitalize(),
            "Партия": str(product.get("date") or "")[:10],
            "Остаток": qty,
            "Закупка": int(cost),
            "Продажа": int(float(product.get("price") or 0)),
            "Сумма закупки": int(qty * cost),
        })
    sale_rows = []
    for sale in sales:
        sale_rows.append({
            "Дата": sale.get("date") or sale.get("day"),
            "Товар": sale.get("pure_name") or sale.get("name"),
            "Кол-во": sale.get("qty"),
            "Оплата": sale.get("payment"),
            "Сумма": sale.get("total_sale"),
            "Себестоимость": sale.get("total_cost"),
            "Прибыль": sale.get("profit"),
            "Взнос": sale.get("down_payment"),
            "Долг": sale.get("credit_balance"),
        })
    client_rows = [{
        "ФИО": c.get("fio"),
        "Телефон": c.get("phone"),
        "Адрес": c.get("address"),
        "Паспорт": c.get("passport"),
    } for c in clients]
    debt_rows = [{
        "Договор": p.get("sale_id"),
        "Дата": p.get("due_date"),
        "Надо": p.get("amount_expected"),
        "Оплачено": p.get("amount_paid"),
        "Статус": p.get("status"),
    } for p in payments]
    cash_rows = [{
        "Дата": op.get("date"),
        "Сумма": op.get("amount"),
        "Комментарий": op.get("comment"),
    } for op in cash]

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(stock_rows).to_excel(writer, index=False, sheet_name="Склад")
        pd.DataFrame(sale_rows).to_excel(writer, index=False, sheet_name="Продажи")
        pd.DataFrame(cash_rows).to_excel(writer, index=False, sheet_name="Касса")
        pd.DataFrame(client_rows).to_excel(writer, index=False, sheet_name="Клиенты")
        pd.DataFrame(debt_rows).to_excel(writer, index=False, sheet_name="Долги")
        sold_df.to_excel(writer, index=False, sheet_name="Продано")
        missing_df.to_excel(writer, index=False, sheet_name="Не закуплено")
    buffer.seek(0)
    st.download_button(
        "Скачать весь магазин в Excel",
        data=buffer.getvalue(),
        file_name=f"Sulaiman_vse_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
