import streamlit as st
import json
import os
import pandas as pd
from datetime import datetime

# ─────────────────────────────────────────────
# КОНСТАНТЫ
# ─────────────────────────────────────────────
DB_FILE = "sklad_data.json"
CURRENCY = "сом"
EMPTY_DB = {"products": {}, "sales": [], "cash_operations": []}


# ─────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ─────────────────────────────────────────────
def fmt(amount: float) -> str:
    """Форматирует число как денежную сумму."""
    return f"{amount:,.2f} {CURRENCY}"


def load_data() -> dict:
    """Загружает базу данных из файла. При ошибке возвращает пустую БД."""
    if not os.path.exists(DB_FILE):
        return EMPTY_DB.copy()
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        # Миграция: старый формат хранил продукты как dict, а не list
        products = loaded.get("products", {})
        if products:
            first = next(iter(products.values()))
            if not isinstance(first, list):
                st.warning("⚠️ Обнаружен устаревший формат базы данных. Данные сброшены.")
                return EMPTY_DB.copy()
        # Добавляем недостающие поля для обратной совместимости
        loaded.setdefault("cash_operations", [])
        loaded.setdefault("sales", [])
        return loaded
    except (json.JSONDecodeError, Exception) as e:
        st.error(f"Ошибка при чтении базы данных: {e}. Создана новая база.")
        return EMPTY_DB.copy()


def save_data(data: dict):
    """Сохраняет данные в файл."""
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def upsert_product_batch(data: dict, name: str, qty: int, cost: float, price: float, date_str: str):
    """
    Добавляет или обновляет партию товара по дате.
    Если партия с такой датой уже есть — обновляет её, иначе создаёт новую.
    """
    if name not in data["products"]:
        data["products"][name] = []
    for batch in data["products"][name]:
        if batch["date"] == date_str:
            batch.update({"qty": qty, "cost": cost, "price": price})
            return
    data["products"][name].append({"date": date_str, "qty": qty, "cost": cost, "price": price})


def get_stock_table(data: dict) -> list[dict]:
    """Возвращает плоский список всех партий с ненулевым остатком."""
    rows = []
    for p_name, batches in data["products"].items():
        if not isinstance(batches, list):
            continue
        for b in batches:
            if b["qty"] > 0:
                rows.append({
                    "Товар": p_name.capitalize(),
                    "Дата поступления": b["date"],
                    "В наличии (шт)": b["qty"],
                    "Закупка (1 шт)": b["cost"],
                    "Продажа (1 шт)": b["price"],
                    "Итого стоимость закупки": b["qty"] * b["cost"],
                })
    return rows


# ─────────────────────────────────────────────
# ИНИЦИАЛИЗАЦИЯ
# ─────────────────────────────────────────────
st.set_page_config(page_title="Магазин Сулайман-Тоо", layout="wide", page_icon="🏬")

if "data" not in st.session_state:
    st.session_state.data = load_data()

# Удобный псевдоним — но всегда читаем/пишем через session_state
data = st.session_state.data


# ─────────────────────────────────────────────
# ШАПКА И НАВИГАЦИЯ
# ─────────────────────────────────────────────
st.title("🏬 Магазин «Сулайман-Тоо» — Учет")

menu = st.sidebar.radio("Разделы", [
    "📦 Склад / Поступление",
    "💰 Касса / Продажи",
    "💵 Баланс Кассы",
    "📊 Отчеты по дням",
])

st.sidebar.markdown("---")
st.sidebar.subheader("Настройки системы")
if st.sidebar.button("⚠️ Перезагрузить базу (Очистить)", type="secondary"):
    st.session_state.data = EMPTY_DB.copy()
    data = st.session_state.data
    save_data(data)
    st.sidebar.success("База данных успешно очищена!")
    st.rerun()


# ─────────────────────────────────────────────
# ВКЛАДКА 1: СКЛАД
# ─────────────────────────────────────────────
if menu == "📦 Склад / Поступление":
    st.header("Управление товарами")

    flat_stock = get_stock_table(data)

    total_qty = sum(r["В наличии (шт)"] for r in flat_stock)
    total_cost_sum = sum(r["Итого стоимость закупки"] for r in flat_stock)
    total_price_sum = sum(r["В наличии (шт)"] * r["Продажа (1 шт)"] for r in flat_stock)

    st.subheader("📊 Общие итоги по складу")
    m1, m2, m3 = st.columns(3)
    m1.metric("📦 Всего товаров в наличии", f"{total_qty} шт.")
    m2.metric("💰 Общая сумма в закупке", fmt(total_cost_sum))
    m3.metric("📈 Потенциальная розничная стоимость", fmt(total_price_sum))

    st.markdown("---")
    print_mode = st.checkbox("🖨️ Режим для печати отчета остатков")

    if print_mode:
        st.subheader("📄 ОТЧЕТ ПО ОСТАТКАМ ТОВАРОВ НА СКЛАДЕ")
        st.write(f"Дата формирования: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        if flat_stock:
            df_print = pd.DataFrame(flat_stock).sort_values(by=["Товар", "Дата поступления"])
            for col in ["Закупка (1 шт)", "Продажа (1 шт)", "Итого стоимость закупки"]:
                df_print[col] = df_print[col].map(fmt)
            st.table(df_print)
            st.markdown(f"**Итого на складе:** {total_qty} шт. на сумму закупки **{fmt(total_cost_sum)}**")
            st.info("💡 Нажмите Ctrl+P (Cmd+P на Mac) чтобы распечатать или сохранить в PDF.")
        else:
            st.write("Склад пуст.")

    else:
        # --- Загрузка из файла ---
        st.subheader("📥 Загрузка/Обновление товаров из Excel (.xlsx или .csv)")
        uploaded_file = st.file_uploader("Выберите файл таблицы", type=["csv", "xlsx"])
        if uploaded_file is not None:
            try:
                if uploaded_file.name.endswith(".xlsx"):
                    df = pd.read_excel(uploaded_file)
                else:
                    # Пробуем cp1251, затем utf-8
                    for enc in ("cp1251", "utf-8"):
                        try:
                            uploaded_file.seek(0)
                            df = pd.read_csv(uploaded_file, sep=None, engine="python", encoding=enc)
                            break
                        except UnicodeDecodeError:
                            continue

                if df.shape[1] < 4:
                    st.error("Файл должен содержать минимум 4 столбца: Товар, Количество, Закупка, Продажа.")
                else:
                    imported_count = 0
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    errors = []
                    for i, row in df.iterrows():
                        try:
                            p_name = str(row.iloc[0]).strip().lower()
                            if not p_name or p_name == "nan":
                                continue
                            p_qty = int(float(str(row.iloc[1]).replace(" ", "").replace(",", ".")))
                            p_cost = float(str(row.iloc[2]).replace(" ", "").replace(",", "."))
                            p_price = float(str(row.iloc[3]).replace(" ", "").replace(",", "."))
                            upsert_product_batch(data, p_name, p_qty, p_cost, p_price, today_str)
                            imported_count += 1
                        except (ValueError, IndexError) as e:
                            errors.append(f"Строка {i+2}: {e}")

                    if imported_count > 0:
                        save_data(data)
                        st.success(f"🚀 Обработано товаров: {imported_count}")
                        if errors:
                            st.warning(f"Пропущено строк с ошибками: {len(errors)}\n" + "\n".join(errors[:5]))
                        st.rerun()
                    else:
                        st.error("Не удалось импортировать ни одного товара. Проверьте формат файла.")
            except Exception as e:
                st.error(f"Не удалось прочитать файл: {e}")

        st.markdown("---")

        col_add, col_edit = st.columns(2)

        with col_add:
            st.subheader("➕ Добавить товар вручную")
            with st.form("add_form", clear_on_submit=True):
                name = st.text_input("Название товара").strip().lower()
                qty = st.number_input("Количество (шт)", min_value=1, value=1)
                cost = st.number_input("Закупка (себестоимость), сом", min_value=0.0, step=10.0)
                price = st.number_input("Цена продажи, сом", min_value=0.0, step=10.0)

                if st.form_submit_button("Сохранить в БД"):
                    if not name:
                        st.error("Введите название товара.")
                    elif price < cost:
                        st.warning("⚠️ Цена продажи ниже закупки — вы продадите в убыток. Проверьте цены.")
                    else:
                        today_str = datetime.now().strftime("%Y-%m-%d")
                        upsert_product_batch(data, name, qty, cost, price, today_str)
                        save_data(data)
                        st.success(f"✅ Товар «{name.capitalize()}» успешно сохранён!")
                        st.rerun()

        with col_edit:
            st.subheader("✏️ Редактировать / Удалить партию")
            if not data["products"]:
                st.write("На складе еще нет товаров.")
            else:
                all_batches_options = {}
                for p_name, batches in data["products"].items():
                    if isinstance(batches, list):
                        for b_idx, b in enumerate(batches):
                            if b["qty"] > 0:
                                label = f"{p_name.capitalize()} (Приход: {b['date']}) — Остаток: {b['qty']} шт."
                                all_batches_options[label] = (p_name, b_idx)

                if not all_batches_options:
                    st.write("Нет активных товаров для изменения.")
                else:
                    selected_label = st.selectbox("Выберите запись", list(all_batches_options.keys()))
                    p_key, b_index = all_batches_options[selected_label]
                    cb = data["products"][p_key][b_index]

                    with st.form("edit_form"):
                        new_qty = st.number_input("Остаток (шт)", min_value=0, value=int(cb["qty"]))
                        new_cost = st.number_input("Цена закупки, сом", min_value=0.0, value=float(cb["cost"]), step=10.0)
                        new_price = st.number_input("Цена продажи, сом", min_value=0.0, value=float(cb["price"]), step=10.0)

                        c1, c2 = st.columns(2)
                        save_btn = c1.form_submit_button("💾 Сохранить")
                        delete_btn = c2.form_submit_button("🗑️ Удалить", type="secondary")

                        if save_btn:
                            if new_price < new_cost:
                                st.warning("⚠️ Цена продажи ниже закупки!")
                            data["products"][p_key][b_index] = {
                                "date": cb["date"], "qty": new_qty, "cost": new_cost, "price": new_price
                            }
                            save_data(data)
                            st.success("Изменения сохранены!")
                            st.rerun()

                        if delete_btn:
                            st.session_state.show_batch_delete = {
                                "key": p_key, "index": b_index, "label": selected_label
                            }

                    if st.session_state.get("show_batch_delete"):
                        b_del = st.session_state.show_batch_delete

                        @st.dialog("⚠️ Подтверждение удаления")
                        def delete_batch_dialog():
                            st.error(f"Удалить партию?\n**{b_del['label']}**")
                            cy, cn = st.columns(2)
                            if cy.button("🗑️ Да, удалить", type="primary", use_container_width=True):
                                products = data["products"]
                                if b_del["key"] in products:
                                    batches = products[b_del["key"]]
                                    idx = b_del["index"]
                                    if 0 <= idx < len(batches):
                                        batches.pop(idx)
                                    if not batches:
                                        del products[b_del["key"]]
                                save_data(data)
                                st.session_state.show_batch_delete = None
                                st.success("Удалено!")
                                st.rerun()
                            if cn.button("Отмена", type="secondary", use_container_width=True):
                                st.session_state.show_batch_delete = None
                                st.rerun()

                        delete_batch_dialog()

        st.markdown("---")
        st.subheader("📋 Текущий остаток на складе")
        if flat_stock:
            df_display = pd.DataFrame(flat_stock).sort_values(by=["Товар", "Дата поступления"])
            for col in ["Закупка (1 шт)", "Продажа (1 шт)", "Итого стоимость закупки"]:
                df_display[col] = df_display[col].map(fmt)
            st.dataframe(df_display, use_container_width=True)
        else:
            st.write("Склад пуст.")


# ─────────────────────────────────────────────
# ВКЛАДКА 2: КАССА / ПРОДАЖИ
# ─────────────────────────────────────────────
elif menu == "💰 Касса / Продажи":
    st.header("Оформить продажу")

    if not data["products"]:
        st.warning("Сначала добавьте товары на склад.")
    else:
        available = {
            p.capitalize(): p
            for p, batches in data["products"].items()
            if isinstance(batches, list) and any(b["qty"] > 0 for b in batches)
        }

        if not available:
            st.error("Нет товаров в наличии!")
        else:
            sel_display = st.selectbox("🔍 Выберите товар для продажи", sorted(available.keys()))
            p_key = available[sel_display]

            batches_options = {
                f"Поступление от {b['date']} (Остаток: {b['qty']} шт., Цена: {fmt(b['price'])})": i
                for i, b in enumerate(data["products"][p_key])
                if b["qty"] > 0
            }

            selected_batch_label = st.selectbox("📦 С какой партии списать товар?", list(batches_options.keys()))
            b_index = batches_options[selected_batch_label]
            chosen = data["products"][p_key][b_index]

            sqty = st.number_input("Количество для продажи (шт)", min_value=1, max_value=int(chosen["qty"]), value=1)
            custom_price = st.number_input(
                "💰 Цена продажи за 1 шт, сом", min_value=0.0, value=float(chosen["price"]), step=10.0
            )
            pay_method = st.radio("💳 Способ оплаты", ["Наличные", "Рассрочка"], horizontal=True)
            total_sum = sqty * custom_price

            # Предупреждение об убытке
            if custom_price < chosen["cost"]:
                st.error(f"⚠️ Цена продажи ({fmt(custom_price)}) ниже себестоимости ({fmt(chosen['cost'])})! Продажа в убыток.")

            st.info(f"💵 **Итого к оплате: {fmt(total_sum)}**")

            if st.button("💵 Оформить продажу", type="primary"):
                st.session_state.show_confirmation = {
                    "p_key": p_key, "b_index": b_index, "name": sel_display,
                    "batch_date": chosen["date"], "qty": sqty,
                    "price": custom_price, "total": total_sum, "payment": pay_method
                }

            if st.session_state.get("show_confirmation"):
                conf = st.session_state.show_confirmation

                @st.dialog("📋 Подтверждение операции")
                def confirm_dialog():
                    st.warning("Проверьте данные перед продажей:")
                    st.markdown(f"**Товар:** {conf['name']} (Поступление: {conf['batch_date']})")
                    st.markdown(f"**Количество:** {conf['qty']} шт. | **Цена:** {fmt(conf['price'])}")
                    st.markdown(f"### Итого: {fmt(conf['total'])} ({conf['payment']})")

                    col_yes, col_no = st.columns(2)
                    if col_yes.button("✅ Подтвердить", type="primary", use_container_width=True):
                        # Проверяем, что партия ещё существует и остатка достаточно
                        products = data["products"]
                        pk, bi = conf["p_key"], conf["b_index"]
                        if pk not in products or bi >= len(products[pk]):
                            st.error("Ошибка: партия не найдена. Обновите страницу.")
                            st.session_state.show_confirmation = None
                            st.rerun()

                        batch = products[pk][bi]
                        if batch["qty"] < conf["qty"]:
                            st.error(f"Недостаточно товара! Доступно: {batch['qty']} шт.")
                            st.session_state.show_confirmation = None
                            st.rerun()

                        # Фиксируем себестоимость ДО изменения остатка
                        t_cost = conf["qty"] * batch["cost"]
                        batch["qty"] -= conf["qty"]

                        data["sales"].append({
                            "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "day": datetime.now().strftime("%Y-%m-%d"),
                            "name": f"{conf['name']} (Приход {conf['batch_date']})",
                            "pure_name": conf["p_key"],
                            "batch_date": conf["batch_date"],
                            "qty": conf["qty"],
                            "total_sale": conf["total"],
                            "total_cost": t_cost,
                            "profit": conf["total"] - t_cost,
                            "payment": conf["payment"],
                        })
                        save_data(data)
                        st.session_state.show_confirmation = None
                        st.success("🎉 Продажа успешно проведена!")
                        st.rerun()

                    if col_no.button("❌ Отмена", type="secondary", use_container_width=True):
                        st.session_state.show_confirmation = None
                        st.rerun()

                confirm_dialog()


# ─────────────────────────────────────────────
# ВКЛАДКА 3: БАЛАНС КАССЫ
# ─────────────────────────────────────────────
elif menu == "💵 Баланс Кассы":
    st.header("💵 Состояние кассы магазина")

    cash_from_sales = sum(s["total_sale"] for s in data["sales"] if s.get("payment") == "Наличные")
    credit_from_sales = sum(s["total_sale"] for s in data["sales"] if s.get("payment") == "Рассрочка")
    manual_cash_flow = sum(op["amount"] for op in data.get("cash_operations", []))
    current_cash = cash_from_sales + manual_cash_flow
    total_profit = sum(s["profit"] for s in data["sales"])

    c1, c2, c3 = st.columns(3)
    c1.metric("💵 Наличные в кассе", fmt(current_cash))
    c2.metric("📝 В рассрочке (долги)", fmt(credit_from_sales))
    c3.metric("📈 Чистая прибыль (все продажи)", fmt(total_profit))

    st.markdown("---")
    st.subheader("📥 / 📤 Внести или взять деньги из кассы")

    with st.form("cash_op_form", clear_on_submit=True):
        op_type = st.selectbox("Тип операции", [
            "Взять деньги (Инкассация / Личные нужды)",
            "Положить деньги (Пополнение / Сдача)",
        ])
        op_amount = st.number_input("Сумма, сом", min_value=1.0, value=100.0, step=50.0)
        op_comment = st.text_input("Комментарий / Причина")

        if st.form_submit_button("Выполнить операцию"):
            actual_amount = -op_amount if "Взять" in op_type else op_amount
            data["cash_operations"].append({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "amount": actual_amount,
                "comment": op_comment.strip() if op_comment.strip() else op_type,
            })
            save_data(data)
            st.success("✅ Операция записана!")
            st.rerun()

    st.markdown("---")
    st.subheader("📜 История ручных операций по кассе")
    ops = data.get("cash_operations", [])
    if not ops:
        st.write("Ручных движений денег не было.")
    else:
        op_list = [
            {
                "Дата/Время": op["date"],
                "Изменение баланса": f"{op['amount']:+,.2f} {CURRENCY}",
                "Комментарий": op["comment"],
            }
            for op in reversed(ops)
        ]
        st.dataframe(pd.DataFrame(op_list), use_container_width=True)


# ─────────────────────────────────────────────
# ВКЛАДКА 4: ОТЧЕТЫ
# ─────────────────────────────────────────────
elif menu == "📊 Отчеты по дням":
    st.header("Аналитика и история продаж")

    if not data["sales"]:
        st.write("Продаж еще не было.")
    else:
        df = pd.DataFrame(data["sales"])
        df["day"] = pd.to_datetime(df["day"]).dt.date

        st.subheader("🔍 Выберите период")
        today = datetime.now().date()
        date_range = st.date_input("Диапазон дат", value=(today, today))

        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
            filtered_df = df[(df["day"] >= start_date) & (df["day"] <= end_date)]
        else:
            filtered_df = df

        if filtered_df.empty:
            st.info("За выбранный период продаж не найдено.")
        else:
            c1, c2 = st.columns(2)
            c1.metric("💰 Выручка за период", fmt(filtered_df["total_sale"].sum()))
            c2.metric("📈 Чистая прибыль за период", fmt(filtered_df["profit"].sum()))

            st.markdown("---")
            st.subheader("📋 Детализация продаж")
            tab1, tab2, tab3 = st.tabs(["Все продажи", "💵 Наличные", "📝 Рассрочка"])

            def render_sales_table(dataframe: pd.DataFrame, tab_key: str):
                if dataframe.empty:
                    st.write("Нет операций за этот период.")
                    return

                h1, h2, h3, h4, h5, h6 = st.columns([2, 2.5, 1, 1.5, 1.5, 1.5])
                for col, label in zip(
                    [h1, h2, h3, h4, h5, h6],
                    ["**Дата/Время**", "**Товар (Партия)**", "**Кол-во**", "**Сумма**", "**Оплата**", "**Действие**"]
                ):
                    col.markdown(label)
                st.markdown("---")

                for idx, row in dataframe.iloc[::-1].iterrows():
                    r1, r2, r3, r4, r5, r6 = st.columns([2, 2.5, 1, 1.5, 1.5, 1.5])
                    r1.write(row["date"])
                    r2.write(str(row["name"]))
                    r3.write(f"{row['qty']} шт.")
                    r4.write(fmt(row["total_sale"]))
                    r5.write(row.get("payment", "Наличные"))

                    btn_key = f"del_{tab_key}_{row.get('id', idx)}"
                    if r6.button("❌ Отменить", key=btn_key, type="secondary"):
                        st.session_state.show_sale_delete = {
                            "index_in_data_sales": idx,
                            "name": row["name"],
                            "qty": row["qty"],
                            "total": row["total_sale"],
                        }
                        st.rerun()

            if st.session_state.get("show_sale_delete"):
                s_del = st.session_state.show_sale_delete

                @st.dialog("⚠️ Отмена продажи")
                def delete_sale_dialog():
                    st.error("Вы уверены, что хотите ОТМЕНИТЬ эту продажу?")
                    st.markdown(f"**{s_del['name']}** — {s_del['qty']} шт. на сумму **{fmt(s_del['total'])}**")

                    cy, cn = st.columns(2)
                    if cy.button("🔥 Да, отменить", type="primary", use_container_width=True):
                        actual_idx = s_del["index_in_data_sales"]

                        # Защита от устаревшего индекса
                        if actual_idx >= len(data["sales"]) or actual_idx < 0:
                            st.error("Ошибка: продажа не найдена. Обновите страницу.")
                            st.session_state.show_sale_delete = None
                            st.rerun()

                        sale_item = data["sales"][actual_idx]
                        p_pure = sale_item.get("pure_name")
                        b_date = sale_item.get("batch_date")

                        # Возвращаем товар на склад
                        if p_pure and b_date and p_pure in data["products"]:
                            batch_restored = False
                            for b in data["products"][p_pure]:
                                if b["date"] == b_date:
                                    b["qty"] += sale_item["qty"]
                                    batch_restored = True
                                    break
                            if not batch_restored:
                                # Партия удалена — пересоздаём её
                                single_cost = sale_item["total_cost"] / sale_item["qty"] if sale_item["qty"] else 0
                                single_price = sale_item["total_sale"] / sale_item["qty"] if sale_item["qty"] else 0
                                data["products"][p_pure].append({
                                    "date": b_date,
                                    "qty": sale_item["qty"],
                                    "cost": single_cost,
                                    "price": single_price,
                                })

                        data["sales"].pop(actual_idx)
                        save_data(data)
                        st.session_state.show_sale_delete = None
                        st.success("✅ Продажа отменена, остаток на складе восстановлен!")
                        st.rerun()

                    if cn.button("Назад", type="secondary", use_container_width=True):
                        st.session_state.show_sale_delete = None
                        st.rerun()

                delete_sale_dialog()

            with tab1:
                render_sales_table(filtered_df, "all")
            with tab2:
                render_sales_table(filtered_df[filtered_df["payment"] == "Наличные"], "cash")
            with tab3:
                render_sales_table(filtered_df[filtered_df["payment"] == "Рассрочка"], "credit")
