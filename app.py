import streamlit as st
import json
import os
import pandas as pd
from datetime import datetime
import io

DB_FILE = "sklad_data.json"

def load_data():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.setdefault("products", {})
                data.setdefault("sales", [])
                data.setdefault("cash_operations", [])
                data.setdefault("supplier_payments", [])
                # Защита от старой структуры
                if data.get("products") and not isinstance(next(iter(data["products"].values()), []), list):
                    data["products"] = {}
                return data
        except:
            pass
    return {"products": {}, "sales": [], "cash_operations": [], "supplier_payments": []}

def save_data(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

if "data" not in st.session_state:
    st.session_state.data = load_data()

data = st.session_state.data

st.set_page_config(page_title="Магазин Сулайман-Тоо", layout="wide", page_icon="🏬")
st.title("🏬 Магазин «Сулайман-Тоо» — Учет")

# ==================== БОКОВАЯ ПАНЕЛЬ ====================
menu = st.sidebar.radio("Разделы", [
    "📦 Склад / Поступление", 
    "💰 Касса / Продажи", 
    "💵 Баланс Кассы",
    "📊 Отчеты по дням",
    "🧾 Оплата контрагентам"
])

if st.sidebar.button("⚠️ Очистить всю базу", type="secondary"):
    if st.sidebar.checkbox("Я подтверждаю удаление всех данных"):
        st.session_state.data = {"products": {}, "sales": [], "cash_operations": [], "supplier_payments": []}
        save_data(st.session_state.data)
        st.success("База очищена!")
        st.rerun()

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def get_flat_stock():
    flat = []
    total_qty = total_cost = total_retail = 0.0
    for p_name, batches in data["products"].items():
        if isinstance(batches, list):
            for b in batches:
                if b.get("qty", 0) > 0:
                    qty = b["qty"]
                    cost = b.get("cost", 0)
                    price = b.get("price", 0)
                    flat.append({
                        "Товар": p_name.capitalize(),
                        "Дата поступления": b["date"],
                        "В наличии (шт)": qty,
                        "Закупка (сом)": cost,
                        "Продажа (сом)": price,
                        "Себестоимость партии": round(qty * cost, 2)
                    })
                    total_qty += qty
                    total_cost += qty * cost
                    total_retail += qty * price
    return pd.DataFrame(flat), total_qty, total_cost, total_retail

def save_product_smart(name, qty, cost, price, date_str):
    name = name.strip().lower()
    if not name:
        return False
    if name not in data["products"]:
        data["products"][name] = []
    for batch in data["products"][name]:
        if batch["date"] == date_str:
            batch["qty"] = qty
            batch["cost"] = cost
            batch["price"] = price
            return True
    data["products"][name].append({
        "date": date_str, "qty": qty, "cost": cost, "price": price
    })
    return True

# ==================== ВКЛАДКА 1: СКЛАД ====================
if menu == "📦 Склад / Поступление":
    st.header("Управление складом")

    df_stock, total_qty, total_cost, total_retail = get_flat_stock()

    c1, c2, c3 = st.columns(3)
    c1.metric("📦 Всего товаров", f"{int(total_qty)} шт.")
    c2.metric("💰 Сумма в закупке", f"{total_cost:,.2f} сом")
    c3.metric("📈 Розничная стоимость", f"{total_retail:,.2f} сом")

    print_mode = st.checkbox("🖨️ Режим для печати отчёта")

    if print_mode:
        st.subheader("📄 ОТЧЁТ ПО ОСТАТКАМ")
        if not df_stock.empty:
            st.dataframe(df_stock, use_container_width=True, hide_index=True)
        else:
            st.info("Склад пуст")
    else:
        # Импорт
        st.subheader("📥 Импорт из Excel / CSV")
        uploaded = st.file_uploader("Файл (Название | Кол-во | Закупка | Продажа)", type=["xlsx", "csv"])
        if uploaded:
            try:
                if uploaded.name.endswith(".xlsx"):
                    df = pd.read_excel(uploaded)
                else:
                    try:
                        df = pd.read_csv(uploaded, encoding="utf-8")
                    except:
                        uploaded.seek(0)
                        df = pd.read_csv(uploaded, sep=None, engine="python", encoding="cp1251")

                imported = 0
                today = datetime.now().strftime("%Y-%m-%d")
                for _, row in df.iterrows():
                    try:
                        name = str(row.iloc[0]).strip()
                        if not name or name.lower() == "nan": continue
                        qty = int(float(str(row.iloc[1]).replace(" ", "").replace(",", ".")))
                        cost = float(str(row.iloc[2]).replace(" ", "").replace(",", "."))
                        price = float(str(row.iloc[3]).replace(" ", "").replace(",", "."))
                        if save_product_smart(name, qty, cost, price, today):
                            imported += 1
                    except:
                        continue
                if imported > 0:
                    save_data(data)
                    st.success(f"Импортировано {imported} товаров")
                    st.rerun()
            except Exception as e:
                st.error(f"Ошибка: {e}")

        st.markdown("---")

        # Добавление вручную
        col_add, col_edit = st.columns(2)
        with col_add:
            st.subheader("➕ Добавить товар вручную")
            with st.form("add_form", clear_on_submit=True):
                name = st.text_input("Название товара").strip().lower()
                qty = st.number_input("Количество", min_value=1, value=1)
                cost = st.number_input("Закупка (сом)", min_value=0.0, step=10.0)
                price = st.number_input("Продажа (сом)", min_value=0.0, step=10.0)
                if st.form_submit_button("Сохранить"):
                    if name:
                        today = datetime.now().strftime("%Y-%m-%d")
                        save_product_smart(name, qty, cost, price, today)
                        save_data(data)
                        st.success("Сохранено!")
                        st.rerun()

        # Редактирование / Удаление партии
        with col_edit:
            st.subheader("✏️ Редактировать / Удалить партию")
            if not data["products"]:
                st.info("Товаров пока нет")
            else:
                options = {}
                for p_name, batches in data["products"].items():
                    if isinstance(batches, list):
                        for idx, b in enumerate(batches):
                            if b.get("qty", 0) > 0:
                                label = f"{p_name.capitalize()} | Приход: {b['date']} | Остаток: {b['qty']} шт."
                                options[label] = (p_name, idx)

                if options:
                    selected = st.selectbox("Выберите партию", list(options.keys()))
                    p_key, b_idx = options[selected]
                    current = data["products"][p_key][b_idx]

                    with st.form("edit_form"):
                        new_qty = st.number_input("Остаток (шт)", min_value=0, value=int(current["qty"]))
                        new_cost = st.number_input("Закупка (сом)", min_value=0.0, value=float(current["cost"]))
                        new_price = st.number_input("Продажа (сом)", min_value=0.0, value=float(current["price"]))

                        col1, col2 = st.columns(2)
                        if col1.form_submit_button("💾 Сохранить изменения"):
                            data["products"][p_key][b_idx] = {
                                "date": current["date"], "qty": new_qty, "cost": new_cost, "price": new_price
                            }
                            save_data(data)
                            st.success("Изменено!")
                            st.rerun()

                        if col2.form_submit_button("🗑️ Удалить партию", type="secondary"):
                            st.session_state.delete_batch = {"p_key": p_key, "b_idx": b_idx, "label": selected}

        # Диалог удаления партии
        if "delete_batch" in st.session_state and st.session_state.delete_batch:
            db = st.session_state.delete_batch
            with st.expander("⚠️ Подтверждение удаления", expanded=True):
                st.error(f"Удалить партию?\n{db['label']}")
                col_y, col_n = st.columns(2)
                if col_y.button("Да, удалить", type="primary"):
                    data["products"][db["p_key"]].pop(db["b_idx"])
                    if not data["products"][db["p_key"]]:
                        del data["products"][db["p_key"]]
                    save_data(data)
                    st.session_state.delete_batch = None
                    st.success("Партия удалена")
                    st.rerun()
                if col_n.button("Отмена"):
                    st.session_state.delete_batch = None
                    st.rerun()

        st.markdown("---")
        st.subheader("📋 Текущий остаток на складе")
        if not df_stock.empty:
            st.dataframe(df_stock, use_container_width=True, hide_index=True)
        else:
            st.info("Склад пуст")

# ==================== ВКЛАДКА 2: КАССА / ПРОДАЖИ ====================
elif menu == "💰 Касса / Продажи":
    st.header("Оформить продажу")

    if not data.get("products"):
        st.warning("Сначала добавьте товары на склад")
    else:
        available = [p.capitalize() for p, batches in data["products"].items() 
                     if isinstance(batches, list) and any(b.get("qty", 0) > 0 for b in batches)]

        if not available:
            st.error("Нет товаров в наличии")
        else:
            sel_name = st.selectbox("Товар", sorted(available))
            p_key = sel_name.lower()

            batch_opts = {}
            for idx, b in enumerate(data["products"][p_key]):
                if b.get("qty", 0) > 0:
                    batch_opts[f"{b['date']} (ост: {b['qty']} шт, цена: {b['price']})"] = idx

            sel_batch = st.selectbox("Партия (дата поступления)", list(batch_opts.keys()))
            b_idx = batch_opts[sel_batch]
            batch = data["products"][p_key][b_idx]

            qty = st.number_input("Количество", 1, int(batch["qty"]), 1)
            sale_price = st.number_input("Цена продажи за шт", 0.0, value=float(batch["price"]))
            pay_method = st.radio("Оплата", ["Наличные", "Рассрочка"], horizontal=True)

            if st.button("💵 Оформить продажу", type="primary"):
                st.session_state.pending_sale = {
                    "p_key": p_key, "b_idx": b_idx, "name": sel_name,
                    "batch_date": batch["date"], "qty": qty,
                    "price": sale_price, "total": qty * sale_price, "payment": pay_method
                }

            if "pending_sale" in st.session_state and st.session_state.pending_sale:
                conf = st.session_state.pending_sale
                with st.expander("Подтверждение продажи", expanded=True):
                    st.write(f"**{conf['name']}** | {conf['qty']} шт × {conf['price']:.2f} = **{conf['total']:.2f} сом**")
                    st.write(f"Оплата: **{conf['payment']}**")

                    col_y, col_n = st.columns(2)
                    if col_y.button("✅ Подтвердить", type="primary"):
                        data["products"][conf["p_key"]][conf["b_idx"]]["qty"] -= conf["qty"]
                        t_cost = conf["qty"] * data["products"][conf["p_key"]][conf["b_idx"]]["cost"]

                        data["sales"].append({
                            "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "day": datetime.now().strftime("%Y-%m-%d"),
                            "name": f"{conf['name']} (приход {conf['batch_date']})",
                            "pure_name": conf["p_key"],
                            "batch_date": conf["batch_date"],
                            "qty": conf["qty"],
                            "total_sale": conf["total"],
                            "total_cost": t_cost,
                            "profit": conf["total"] - t_cost,
                            "payment": conf["payment"]
                        })
                        save_data(data)
                        st.session_state.pending_sale = None
                        st.success("Продажа оформлена!")
                        st.rerun()
                    if col_n.button("Отмена"):
                        st.session_state.pending_sale = None
                        st.rerun()

# ==================== ВКЛАДКА 3: БАЛАНС КАССЫ ====================
elif menu == "💵 Баланс Кассы":
    st.header("Состояние кассы")

    cash_sales = sum(s["total_sale"] for s in data["sales"] if s.get("payment") == "Наличные")
    credit = sum(s["total_sale"] for s in data["sales"] if s.get("payment") == "Рассрочка")
    manual = sum(op.get("amount", 0) for op in data.get("cash_operations", []))
    current_cash = cash_sales + manual

    c1, c2, c3 = st.columns(3)
    c1.metric("💵 Наличные в кассе", f"{current_cash:,.2f} сом")
    c2.metric("📝 В рассрочке", f"{credit:,.2f} сом")
    c3.metric("📈 Общая прибыль", f"{sum(s['profit'] for s in data['sales']):,.2f} сом")

    st.markdown("---")
    st.subheader("Операции с кассой")

    with st.form("cash_op"):
        op_type = st.selectbox("Тип операции", ["Положить деньги", "Взять деньги"])
        amount = st.number_input("Сумма", min_value=1.0, value=100.0)
        comment = st.text_input("Комментарий")
        if st.form_submit_button("Выполнить"):
            actual = amount if "Положить" in op_type else -amount
            data["cash_operations"].append({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "amount": actual,
                "comment": comment or op_type
            })
            save_data(data)
            st.success("Операция записана!")
            st.rerun()

    if data.get("cash_operations"):
        st.subheader("История операций с кассой")
        st.dataframe(pd.DataFrame(data["cash_operations"][::-1]), use_container_width=True)

# ==================== ВКЛАДКА 4: ОТЧЁТЫ ====================
elif menu == "📊 Отчеты по дням":
    st.header("Отчёты по продажам")

    if not data["sales"]:
        st.info("Продаж ещё нет")
    else:
        df = pd.DataFrame(data["sales"])
        df["day"] = pd.to_datetime(df["day"]).dt.date

        date_range = st.date_input("Период", value=(df["day"].min(), df["day"].max()))
        if len(date_range) == 2:
            start, end = date_range
            filtered = df[(df["day"] >= start) & (df["day"] <= end)]
        else:
            filtered = df

        c1, c2 = st.columns(2)
        c1.metric("Выручка", f"{filtered['total_sale'].sum():,.2f} сом")
        c2.metric("Прибыль", f"{filtered['profit'].sum():,.2f} сом")

        # Экспорт
        if st.button("📥 Скачать в Excel"):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                filtered.to_excel(writer, index=False, sheet_name="Продажи")
            st.download_button("Скачать", data=output.getvalue(), 
                               file_name=f"report_{datetime.now().strftime('%Y%m%d')}.xlsx")

        st.markdown("---")
        st.subheader("Детализация продаж")

        tab_all, tab_cash, tab_credit = st.tabs(["Все продажи", "💵 Наличные", "📝 Рассрочка"])

        def show_sales_table(dataframe, tab_name):
            if dataframe.empty:
                st.info("Нет данных")
                return
            for idx, row in dataframe.iloc[::-1].iterrows():
                cols = st.columns([2.5, 3.5, 1, 1.8, 1.5, 1.5])
                cols[0].write(row["date"])
                cols[1].write(str(row["name"]))
                cols[2].write(f"{row['qty']} шт.")
                cols[3].write(f"{row['total_sale']:.2f} сом")
                cols[4].write(row.get("payment", "Наличные"))

                if cols[5].button("❌ Отменить", key=f"del_{tab_name}_{row.get('id', idx)}"):
                    st.session_state.delete_sale = {"idx": idx, "row": row}
                    st.rerun()

        with tab_all:
            show_sales_table(filtered, "all")
        with tab_cash:
            show_sales_table(filtered[filtered["payment"] == "Наличные"], "cash")
        with tab_credit:
            show_sales_table(filtered[filtered["payment"] == "Рассрочка"], "credit")

        # Диалог отмены продажи
        if "delete_sale" in st.session_state and st.session_state.delete_sale:
            ds = st.session_state.delete_sale
            with st.expander("⚠️ Отмена продажи", expanded=True):
                st.error(f"Отменить продажу?\n{ds['row']['name']}")
                col_y, col_n = st.columns(2)
                if col_y.button("Да, отменить", type="primary"):
                    sale = data["sales"][ds["idx"]]
                    p_key = sale.get("pure_name")
                    b_date = sale.get("batch_date")
                    if p_key and b_date and p_key in data["products"]:
                        found = False
                        for b in data["products"][p_key]:
                            if b["date"] == b_date:
                                b["qty"] += sale["qty"]
                                found = True
                                break
                        if not found:
                            data["products"][p_key].append({
                                "date": b_date,
                                "qty": sale["qty"],
                                "cost": sale["total_cost"] / sale["qty"],
                                "price": sale["total_sale"] / sale["qty"]
                            })
                    data["sales"].pop(ds["idx"])
                    save_data(data)
                    st.session_state.delete_sale = None
                    st.success("Продажа отменена, остаток восстановлен")
                    st.rerun()
                if col_n.button("Назад"):
                    st.session_state.delete_sale = None
                    st.rerun()

# ==================== ВКЛАДКА 5: ОПЛАТА КОНТРАГЕНТАМ ====================
elif menu == "🧾 Оплата контрагентам":
    st.header("Выплаты поставщикам и контрагентам")

    st.subheader("📤 Зафиксировать выплату")
    with st.form("supplier_payment"):
        supplier = st.text_input("Название контрагента / поставщика")
        amount = st.number_input("Сумма выплаты (сом)", min_value=1.0, value=1000.0)
        comment = st.text_input("Комментарий (за что)")
        if st.form_submit_button("Зафиксировать выплату"):
            if supplier:
                data["supplier_payments"].append({
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "supplier": supplier.strip(),
                    "amount": amount,
                    "comment": comment
                })
                save_data(data)
                st.success("Выплата зафиксирована!")
                st.rerun()

    st.markdown("---")
    st.subheader("📜 История выплат контрагентам")

    if not data.get("supplier_payments"):
        st.info("Выплат ещё не было")
    else:
        df_pay = pd.DataFrame(data["supplier_payments"][::-1])
        st.dataframe(df_pay, use_container_width=True, hide_index=True)
        total_paid = sum(p["amount"] for p in data["supplier_payments"])
        st.metric("Всего выплачено контрагентам", f"{total_paid:,.2f} сом")

st.sidebar.markdown("---")
st.sidebar.caption("Магазин Сулайман-Тоо • Учёт v3 (улучшенная версия)")
