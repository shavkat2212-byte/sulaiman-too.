# Магазин «Сулайман-Тоо» — Модуль: Отчеты
# Версия: 2.5 (полный сводный отчет + рассрочки по клиентам)

import streamlit as st
import pandas as pd
import io
from datetime import datetime, timedelta
from database import supabase
from utils import format_date_to_ddmmyyyy, fix_contract_name_on_fly


def get_category_from_comment(comment: str) -> str:
    comment = str(comment or "").strip()
    if comment.startswith("[НУЖДЫ]"):
        return "Нужды магазина"
    if comment.startswith("[ПОСТАВЩИК]"):
        return "Оплата контрагенту"
    return "Без категории"


def parse_day(x):
    try:
        x = str(x)[:10]
        if "." in x:
            return datetime.strptime(x, "%d.%m.%Y").date()
        return datetime.strptime(x, "%Y-%m-%d").date()
    except:
        return None


def show_reports_page():
    user_role = st.session_state.get("user", {}).get("role", "Кассир")

    if user_role == "Администратор":
        st.header("📊 Аналитика и отчеты (Панель Администратора)")
        tab_full, tab_credit, tab_sales = st.tabs([
            "📦 Полный отчет",
            "👥 Рассрочки по клиентам",
            "📋 Продажи и аналитика"
        ])
    else:
        st.header("📋 Ежедневный отчет по продажам (Панель Кассира)")
        tab_full = tab_credit = None
        tab_sales = st.container()

    try:
        sales_all = supabase.table("sales").select("*").order("date", desc=True).execute()
        products_all = supabase.table("products").select("*").execute()
        ops_all = supabase.table("cash_operations").select("*").execute()
        clients_all = supabase.table("clients").select("*").execute()
        payments_all = supabase.table("credit_payments").select("*").execute()
    except Exception as e:
        st.error(f"Ошибка: {e}")
        return

    sales_data = sales_all.data or []
    products_data = products_all.data or []
    ops_data = ops_all.data or []
    clients_data = clients_all.data or []
    payments_data = payments_all.data or []
    clients_map = {c["id"]: c for c in clients_data}

    # =========================================================================
    # ВКЛАДКА 1: ПОЛНЫЙ ОТЧЕТ
    # =========================================================================
    if user_role == "Администратор":
        with tab_full:
            st.subheader("📦 Полный отчет на текущий момент")

            # 1) Склад
            stock_qty = 0
            stock_cost = 0.0
            stock_retail = 0.0
            for p in products_data:
                qty = int(p.get("qty", 0) or 0)
                if qty <= 0:
                    continue
                cost = float(p.get("cost", 0) or 0)
                price = float(p.get("price", 0) or 0)
                stock_qty += qty
                stock_cost += qty * cost
                stock_retail += qty * price

            # 2) Касса
            cash_sales = sum(float(s.get("total_sale", 0) or 0) for s in sales_data if s.get("payment") == "Наличные")
            cash_ops = sum(float(op.get("amount", 0) or 0) for op in ops_data)
            cash_now = cash_sales + cash_ops

            # 3) Долг клиентов
            credit_balance_sum = sum(
                float(s.get("credit_balance", 0) or 0)
                for s in sales_data if s.get("payment") == "Рассрочка"
            )
            paid_sum = sum(float(p.get("amount_paid", 0) or 0) for p in payments_data)
            client_debt = credit_balance_sum - paid_sum

            m1, m2, m3 = st.columns(3)
            m1.metric("📦 Товары на складе (закупка)", f"{stock_cost:,.0f} сом")
            m2.metric("💵 Наличные в кассе", f"{cash_now:,.0f} сом")
            m3.metric("📝 Задолженность клиентов", f"{client_debt:,.0f} сом")

            st.caption(f"На складе: **{stock_qty:,} шт.** | Розничная стоимость склада: **{stock_retail:,.0f} сом**")

            st.markdown("---")
            st.subheader("📅 Отчет за выбранный период")

            today = datetime.now().date()
            month_start = today.replace(day=1)
            period = st.date_input(
                "Период",
                value=(month_start, today),
                key="full_report_period"
            )

            if isinstance(period, tuple) and len(period) == 2:
                p_start, p_end = period
            else:
                p_start = p_end = today

            received_qty = 0
            received_cost = 0.0
            for p in products_data:
                d = parse_day(p.get("date"))
                if not d or d < p_start or d > p_end:
                    continue
                qty = int(p.get("qty", 0) or 0)
                cost = float(p.get("cost", 0) or 0)
                received_qty += qty
                received_cost += qty * cost

            supplier_pay = 0.0
            needs_pay = 0.0
            for op in ops_data:
                amount = float(op.get("amount", 0) or 0)
                if amount >= 0:
                    continue
                d = parse_day(op.get("date"))
                if not d or d < p_start or d > p_end:
                    continue
                cat = get_category_from_comment(op.get("comment", ""))
                if cat == "Оплата контрагенту":
                    supplier_pay += abs(amount)
                elif cat == "Нужды магазина":
                    needs_pay += abs(amount)

            p1, p2, p3 = st.columns(3)
            p1.metric("📥 Принято товаров за период", f"{received_cost:,.0f} сом")
            p2.metric("🚚 Оплаты контрагентам", f"{supplier_pay:,.0f} сом")
            p3.metric("🏪 Расходы на нужды", f"{needs_pay:,.0f} сом")
            st.caption(f"Принято товаров: **{received_qty:,} шт.** за период {p_start.strftime('%d.%m.%Y')} — {p_end.strftime('%d.%m.%Y')}")

            summary_df = pd.DataFrame([
                {"Показатель": "Товары на складе (закупка)", "Сумма": stock_cost},
                {"Показатель": "Товары на складе (розница)", "Сумма": stock_retail},
                {"Показатель": "Наличные в кассе", "Сумма": cash_now},
                {"Показатель": "Задолженность клиентов", "Сумма": client_debt},
                {"Показатель": "Принято товаров за период", "Сумма": received_cost},
                {"Показатель": "Оплаты контрагентам за период", "Сумма": supplier_pay},
                {"Показатель": "Расходы на нужды за период", "Сумма": needs_pay},
            ])

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                summary_df.to_excel(writer, index=False, sheet_name="Полный отчет")
            buffer.seek(0)
            st.download_button(
                "📥 Скачать полный отчет (Excel)",
                data=buffer,
                file_name=f"Polnyy_otchet_{p_start}_{p_end}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

        # =====================================================================
        # ВКЛАДКА 2: РАССРОЧКИ ПО КЛИЕНТАМ
        # =====================================================================
        with tab_credit:
            st.subheader("👥 Полный отчет по рассрочке (по клиентам)")

            rows = []
            for s in sales_data:
                if s.get("payment") != "Рассрочка":
                    continue

                client = clients_map.get(s.get("client_id"), {})
                fio = client.get("fio", "Неизвестный")
                phone = client.get("phone", "—")

                sale_pays = [p for p in payments_data if p.get("sale_id") == s.get("id")]
                paid = sum(float(p.get("amount_paid", 0) or 0) for p in sale_pays)
                balance = float(s.get("credit_balance", 0) or 0)
                down = float(s.get("down_payment", 0) or 0)
                debt_left = balance - paid

                unpaid = [p for p in sale_pays if p.get("status") != "Оплачен"]
                next_pay = 0
                next_date = ""
                if unpaid:
                    def sort_due(x):
                        d = parse_day(x.get("due_date"))
                        return d or datetime.now().date()
                    unpaid_sorted = sorted(unpaid, key=sort_due)
                    next_pay = float(unpaid_sorted[0].get("amount_expected", 0) or 0)
                    nd = parse_day(unpaid_sorted[0].get("due_date"))
                    next_date = nd.strftime("%d.%m.%Y") if nd else ""

                rows.append({
                    "Клиент": fio,
                    "Телефон": phone,
                    "Договор": str(s.get("name", ""))[:70],
                    "Дата": s.get("date", ""),
                    "Сумма продажи": int(s.get("total_sale", 0) or 0),
                    "Перв. взнос": int(down),
                    "Долг + наценка": int(balance),
                    "Оплачено": int(paid),
                    "Остаток долга": int(debt_left),
                    "След. платёж": int(next_pay),
                    "Дата след. платежа": next_date
                })

            if not rows:
                st.info("Договоров рассрочки нет.")
            else:
                df_cred = pd.DataFrame(rows)
                df_cred = df_cred.sort_values(["Клиент", "Дата"])

                only_active = st.checkbox("Показать только с остатком долга", value=True, key="only_active_debt")
                if only_active:
                    df_show = df_cred[df_cred["Остаток долга"] > 0].copy()
                else:
                    df_show = df_cred.copy()

                st.dataframe(df_show, use_container_width=True, hide_index=True)

                total_debt = int(df_show["Остаток долга"].sum()) if not df_show.empty else 0
                total_clients = df_show["Клиент"].nunique() if not df_show.empty else 0
                c1, c2 = st.columns(2)
                c1.metric("Клиентов с долгом", f"{total_clients}")
                c2.metric("Общий остаток долга", f"{total_debt:,} сом")

                # Сводка по фамилиям
                st.markdown("#### Сводка по клиентам")
                if not df_show.empty:
                    by_fio = (
                        df_show.groupby(["Клиент", "Телефон"], as_index=False)
                        .agg({
                            "Остаток долга": "sum",
                            "Оплачено": "sum",
                            "Долг + наценка": "sum"
                        })
                        .sort_values("Остаток долга", ascending=False)
                    )
                    st.dataframe(by_fio, use_container_width=True, hide_index=True)

                buffer2 = io.BytesIO()
                with pd.ExcelWriter(buffer2, engine="openpyxl") as writer:
                    df_show.to_excel(writer, index=False, sheet_name="Договоры")
                    if not df_show.empty:
                        by_fio.to_excel(writer, index=False, sheet_name="По клиентам")
                buffer2.seek(0)
                st.download_button(
                    "📥 Скачать отчет по рассрочке (Excel)",
                    data=buffer2,
                    file_name=f"Rassrochka_po_klientam_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

    # =========================================================================
    # ВКЛАДКА 3 / КАССИР: ПРОДАЖИ И АНАЛИТИКА (как было)
    # =========================================================================
    sales_container = tab_sales if user_role == "Администратор" else tab_sales
    with sales_container:
        if not sales_data:
            st.write("Продаж еще не было.")
            return

        df = pd.DataFrame(sales_data)
        df['day_obj'] = df['day'].apply(parse_day)

        if user_role == "Администратор":
            st.subheader("🔍 Выберите период")
            date_range = st.date_input(
                "Диапазон дат",
                value=(df['day_obj'].min(), df['day_obj'].max()),
                key="main_period"
            )
            if isinstance(date_range, tuple) and len(date_range) == 2:
                start_date, end_date = date_range
                filtered_df = df[(df['day_obj'] >= start_date) & (df['day_obj'] <= end_date)].copy()
            else:
                filtered_df = pd.DataFrame()
        else:
            today = datetime.now().date()
            filtered_df = df[df['day_obj'] == today].copy()
            st.info(f"📅 Продажи за сегодня: **{today.strftime('%d.%m.%Y')}**")
            start_date = end_date = today

        if filtered_df.empty:
            st.info("За выбранный период продаж нет.")
            return

        needs_expense = 0.0
        supplier_expense = 0.0
        today_k = datetime.now().date()

        for op in ops_data:
            amount = float(op.get("amount", 0) or 0)
            if amount >= 0:
                continue
            op_day = parse_day(op.get("date"))
            if not op_day:
                continue
            if user_role == "Администратор":
                if not (start_date <= op_day <= end_date):
                    continue
            else:
                if op_day != today_k:
                    continue
            cat = get_category_from_comment(op.get("comment", ""))
            if cat == "Нужды магазина":
                needs_expense += abs(amount)
            elif cat == "Оплата контрагенту":
                supplier_expense += abs(amount)

        df_cash = filtered_df[filtered_df['payment'] == 'Наличные']
        df_credit = filtered_df[filtered_df['payment'] == 'Рассрочка']

        cash_turnover = float(df_cash['total_sale'].sum()) if not df_cash.empty else 0
        credit_turnover = float(df_credit['total_sale'].sum()) if not df_credit.empty else 0

        cash_profit = float((df_cash['total_sale'] - df_cash['total_cost']).sum()) if not df_cash.empty else 0
        credit_profit = 0
        if not df_credit.empty:
            for _, row in df_credit.iterrows():
                cost = float(row.get("total_cost", 0) or 0)
                down = float(row.get("down_payment", 0) or 0)
                bal = float(row.get("credit_balance", 0) or 0)
                credit_profit += (down + bal) - cost

        total_profit = cash_profit + credit_profit
        net_income = total_profit - needs_expense

        st.markdown("---")
        if user_role == "Администратор":
            c1, c2, c3 = st.columns(3)
            c1.metric("💵 Оборот (Наличные)", f"{int(cash_turnover):,} сом")
            c2.metric("📦 Оборот (Рассрочка)", f"{int(credit_turnover):,} сом")
            c3.metric("🔥 Общий оборот", f"{int(cash_turnover + credit_turnover):,} сом")

            p1, p2, p3 = st.columns(3)
            p1.metric("📈 Прибыль (Нал)", f"{int(cash_profit):,} сом")
            p2.metric("📈 Прибыль (Рассрочка)", f"{int(credit_profit):,} сом")
            p3.metric("🏆 Суммарная прибыль", f"{int(total_profit):,} сом")

            e1, e2, e3 = st.columns(3)
            e1.metric("🏪 Расходы на нужды", f"{int(needs_expense):,} сом")
            e2.metric("🚚 Выплаты поставщикам", f"{int(supplier_expense):,} сом")
            e3.metric("💰 Чистый доход", f"{int(net_income):,} сом")
        else:
            k1, k2, k3 = st.columns(3)
            k1.metric("🟢 Наличные", f"{int(cash_turnover):,} сом")
            k2.metric("🔵 Рассрочки", f"{int(credit_turnover):,} сом")
            k3.metric("🛍️ Всего", f"{int(cash_turnover + credit_turnover):,} сом")

        if user_role == "Администратор":
            st.markdown("---")
            st.subheader("📋 Полный отчет по дням")

            daily_data = []
            current = start_date
            while current <= end_date:
                day_sales = filtered_df[filtered_df['day_obj'] == current]
                day_cash = day_sales[day_sales['payment'] == 'Наличные']
                day_credit = day_sales[day_sales['payment'] == 'Рассрочка']

                cash_sale = float(day_cash['total_sale'].sum()) if not day_cash.empty else 0
                credit_sale = float(day_credit['total_sale'].sum()) if not day_credit.empty else 0
                cash_p = float((day_cash['total_sale'] - day_cash['total_cost']).sum()) if not day_cash.empty else 0

                credit_p = 0
                if not day_credit.empty:
                    for _, r in day_credit.iterrows():
                        cost = float(r.get("total_cost", 0) or 0)
                        down = float(r.get("down_payment", 0) or 0)
                        bal = float(r.get("credit_balance", 0) or 0)
                        credit_p += (down + bal) - cost

                day_products = [p for p in products_data if parse_day(p.get("date")) == current]
                qty_rec = sum(int(p.get("qty", 0) or 0) for p in day_products)
                cost_rec = sum(float(p.get("qty", 0) or 0) * float(p.get("cost", 0) or 0) for p in day_products)

                if cash_sale or credit_sale or qty_rec:
                    daily_data.append({
                        "Дата": current.strftime("%Y-%m-%d"),
                        "Продажи наличкой": cash_sale,
                        "Продажи в рассрочку": credit_sale,
                        "Прибыль наличные": cash_p,
                        "Прибыль рассрочка": credit_p,
                        "Товаров принято (шт)": qty_rec,
                        "Сумма принятых товаров": cost_rec,
                        "Общая прибыль": cash_p + credit_p
                    })
                current += timedelta(days=1)

            if daily_data:
                report_df = pd.DataFrame(daily_data)
                display = report_df.copy()
                for col in display.columns[1:]:
                    display[col] = display[col].map("{:,.0f}".format)
                st.dataframe(display, use_container_width=True, hide_index=True)

                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                    report_df.to_excel(writer, index=False, sheet_name="Полный отчет")
                buffer.seek(0)
                st.download_button(
                    "📥 Скачать отчет по дням",
                    data=buffer,
                    file_name=f"Otchet_po_dnyam_{start_date}_{end_date}.xlsx",
                    use_container_width=True
                )

        st.markdown("---")
        st.subheader("📋 Список оформленных чеков")

        report_display = []
        for _, row in filtered_df.iterrows():
            total_sale = float(row.get('total_sale', 0) or 0)
            total_cost = float(row.get('total_cost', 0) or 0)
            down = float(row.get('down_payment', 0) or 0)
            credit_balance = float(row.get('credit_balance', 0) or 0)
            base_profit = float(row.get('profit', 0) or 0)
            if not base_profit:
                base_profit = total_sale - total_cost

            if row.get('payment') == 'Рассрочка':
                profit_with_markup = (down + credit_balance) - total_cost
            else:
                profit_with_markup = base_profit

            report_display.append({
                "Дата": format_date_to_ddmmyyyy(row['date'], include_time=True),
                "Наименование": fix_contract_name_on_fly(row['name'], row['date']),
                "Кол-во": int(row['qty']),
                "Тип оплаты": row['payment'],
                "Сумма": int(total_sale),
                "Закупка": int(total_cost),
                "Прибыль": int(base_profit),
                "Прибыль с наценкой": int(profit_with_markup),
                "sale_id": row['id'],
                "raw_payment": row['payment'],
                "down_payment": int(down),
                "pure_name": row.get('pure_name', ''),
                "batch_date": row.get('batch_date', ''),
                "qty_raw": int(row.get('qty', 0))
            })

        df_display = pd.DataFrame(report_display)
        st.dataframe(
            df_display.drop(
                columns=["sale_id", "raw_payment", "down_payment", "pure_name", "batch_date", "qty_raw"],
                errors="ignore"
            ),
            use_container_width=True,
            hide_index=True
        )

        if user_role != "Администратор":
            return

        st.markdown("---")
        st.subheader("✏️ Редактировать выбранную операцию")

        edit_options = {
            f"{row['Дата']} | {row['Наименование']} | {row['Сумма']} сом": row
            for _, row in df_display.iterrows()
        }
        selected_label = st.selectbox("Выберите операцию", ["-- Не выбрано --"] + list(edit_options.keys()), key="edit_select")

        if selected_label != "-- Не выбрано --":
            selected = edit_options[selected_label]
            sale_id = selected["sale_id"]
            sale_data = supabase.table("sales").select("*").eq("id", sale_id).execute().data

            if sale_data:
                sale = sale_data[0]
                with st.form("edit_form"):
                    new_name = st.text_input("Наименование", value=str(sale.get("name", "")))
                    new_qty = st.number_input("Количество", min_value=0, value=int(sale.get("qty", 0)))
                    new_total_sale = st.number_input("Сумма продажи", min_value=0, value=int(sale.get("total_sale", 0)))
                    new_total_cost = st.number_input("Себестоимость (Закупка)", min_value=0, value=int(sale.get("total_cost", 0)))
                    st.info(f"Прибыль будет: **{new_total_sale - new_total_cost:,} сом**")
                    col1, col2 = st.columns(2)
                    with col1:
                        new_payment = st.selectbox(
                            "Тип оплаты",
                            ["Наличные", "Рассрочка"],
                            index=0 if sale.get("payment") == "Наличные" else 1
                        )
                    with col2:
                        new_down = st.number_input("Перв. взнос", min_value=0, value=int(sale.get("down_payment", 0) or 0))
                    new_balance = st.number_input("Остаток рассрочки", min_value=0, value=int(sale.get("credit_balance", 0) or 0))

                    if st.form_submit_button("💾 Сохранить изменения", type="primary"):
                        try:
                            supabase.table("sales").update({
                                "name": new_name.strip(),
                                "qty": new_qty,
                                "total_sale": new_total_sale,
                                "total_cost": new_total_cost,
                                "profit": new_total_sale - new_total_cost,
                                "payment": new_payment,
                                "down_payment": new_down,
                                "credit_balance": new_balance
                            }).eq("id", sale_id).execute()
                            st.success("✅ Сохранено!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Ошибка: {e}")

        st.markdown("---")
        st.subheader("🔄 Умная отмена продажи (с возвратом на склад)")

        cancel_options = {
            f"{row['Дата']} | {row['Наименование']} | {row['Сумма']} сом | {row['Тип оплаты']}": row
            for _, row in df_display.iterrows()
        }
        selected_cancel = st.selectbox(
            "Выберите продажу для отмены",
            ["-- Не выбрано --"] + list(cancel_options.keys()),
            key="smart_cancel_select"
        )

        if selected_cancel != "-- Не выбрано --":
            s_del = cancel_options[selected_cancel]
            sale_id = s_del["sale_id"]
            payment_type = s_del["raw_payment"]

            related_sales = []
            if payment_type == "Наличные" and "_" in str(sale_id):
                base_id = str(sale_id).rsplit("_", 1)[0]
                related_sales = [s for s in sales_data if str(s.get("id", "")).startswith(base_id)]
            else:
                related_sales = [s for s in sales_data if str(s.get("id")) == str(sale_id)]

            if not related_sales:
                related_sales = [next((s for s in sales_data if str(s.get("id")) == str(sale_id)), None)]
                related_sales = [s for s in related_sales if s]

            st.markdown("#### 📋 Что будет сделано при отмене:")
            restore_preview = []
            total_restore_qty = 0

            if payment_type == "Наличные":
                for s in related_sales:
                    pure = str(s.get("pure_name", "") or "").lower().strip()
                    batch_d = str(s.get("batch_date", "") or "")[:10]
                    qty = int(s.get("qty", 0) or 0)
                    name_display = s.get("name", pure)
                    matching = [
                        p for p in products_data
                        if str(p.get("name", "")).lower().strip() == pure
                        and str(p.get("date", ""))[:10] == batch_d
                    ]
                    if matching:
                        p = matching[0]
                        restore_preview.append({
                            "Товар": name_display,
                            "Партия": batch_d,
                            "Вернуть шт.": qty,
                            "Текущий остаток": int(p.get("qty", 0)),
                            "Станет": int(p.get("qty", 0)) + qty,
                            "product_id": p["id"]
                        })
                    else:
                        matching_any = [p for p in products_data if str(p.get("name", "")).lower().strip() == pure]
                        if matching_any:
                            p = matching_any[0]
                            restore_preview.append({
                                "Товар": name_display,
                                "Партия": "(найдена другая)",
                                "Вернуть шт.": qty,
                                "Текущий остаток": int(p.get("qty", 0)),
                                "Станет": int(p.get("qty", 0)) + qty,
                                "product_id": p["id"]
                            })
                        else:
                            restore_preview.append({
                                "Товар": name_display,
                                "Партия": batch_d or "—",
                                "Вернуть шт.": qty,
                                "Текущий остаток": "не найден",
                                "Станет": "нужно добавить вручную",
                                "product_id": None
                            })
                    total_restore_qty += qty

                if restore_preview:
                    st.dataframe(
                        pd.DataFrame(restore_preview).drop(columns=["product_id"], errors="ignore"),
                        use_container_width=True,
                        hide_index=True
                    )
                    st.success(f"Будет возвращено на склад: **{total_restore_qty} шт.** товаров")
                else:
                    st.warning("Не удалось определить товары для возврата.")
            else:
                st.info("Это договор рассрочки.")
                st.write("• Будут удалены все платежи по договору")
                down = int(s_del.get("down_payment", 0) or 0)
                if down > 0:
                    st.write(f"• Будет откатан первоначальный взнос **{down:,} сом** из кассы (если найдётся)")
                st.warning("⚠️ Товар по рассрочке нужно будет вернуть на склад **вручную**.")

            confirm = st.checkbox("Я понимаю последствия и подтверждаю отмену", key="confirm_smart_cancel")
            if st.button("🚨 ОТМЕНИТЬ ПРОДАЖУ И ВЕРНУТЬ ТОВАР", type="primary", disabled=not confirm):
                try:
                    errors = []
                    if payment_type == "Наличные":
                        for item in restore_preview:
                            pid = item.get("product_id")
                            qty = item.get("Вернуть шт.", 0)
                            if pid and isinstance(qty, int) and qty > 0:
                                try:
                                    cur = supabase.table("products").select("qty").eq("id", pid).execute()
                                    if cur.data:
                                        new_qty = int(cur.data[0]["qty"]) + qty
                                        supabase.table("products").update({"qty": new_qty}).eq("id", pid).execute()
                                except Exception as e:
                                    errors.append(f"Ошибка возврата товара: {e}")

                    for s in related_sales:
                        try:
                            supabase.table("sales").delete().eq("id", s["id"]).execute()
                        except Exception as e:
                            errors.append(f"Ошибка удаления продажи {s.get('id')}: {e}")

                    try:
                        supabase.table("credit_payments").delete().eq("sale_id", sale_id).execute()
                    except Exception as e:
                        errors.append(f"Ошибка удаления платежей: {e}")

                    if payment_type == "Рассрочка":
                        down = float(s_del.get("down_payment", 0) or 0)
                        if down > 0:
                            try:
                                for op in ops_data:
                                    comment = str(op.get("comment", "") or "")
                                    amount = float(op.get("amount", 0) or 0)
                                    if ("Перв. взнос" in comment or "перв" in comment.lower()) and abs(amount - down) < 1:
                                        supabase.table("cash_operations").delete().eq("id", op["id"]).execute()
                                        st.info(f"Откатан взнос из кассы: {down:,.0f} сом")
                                        break
                            except Exception as e:
                                errors.append(f"Не удалось откатить взнос: {e}")

                    if errors:
                        for err in errors:
                            st.error(err)
                    else:
                        st.success("✅ Продажа успешно отменена!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Критическая ошибка при отмене: {e}")


def show_supplier_page():
    user_role = st.session_state.get("user", {}).get("role", "Кассир")
    if user_role != "Администратор":
        return
    st.header("Выплаты поставщикам и контрагентам")
    with st.form("supplier_payment"):
        supplier = st.text_input("Название контрагента")
        amount = st.number_input("Сумма выплаты", min_value=1.0, value=1000.0)
        comment = st.text_input("Комментарий")
        if st.form_submit_button("Зафиксировать выплату"):
            if supplier:
                now_formatted = datetime.now().strftime("%d.%m.%Y %H:%M")
                supabase.table("supplier_payments").insert({
                    "date": now_formatted,
                    "supplier": supplier.strip(),
                    "amount": amount,
                    "comment": comment
                }).execute()
                st.success("Выплата отправлена!")
                st.rerun()
