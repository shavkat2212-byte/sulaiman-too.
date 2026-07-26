# Магазин «Сулайман-Тоо» — Модуль: Отчеты
# Версия: 2.3 (расходы + чистый доход + экспорт)

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


def show_reports_page():
    user_role = st.session_state.get("user", {}).get("role", "Кассир")
    
    if user_role == "Администратор":
        st.header("📊 Аналитика и история продаж (Панель Администратора)")
    else:
        st.header("📋 Ежедневный отчет по продажам (Панель Кассира)")

    try:
        sales_all = supabase.table("sales").select("*").order("date", desc=True).execute()
        products_all = supabase.table("products").select("*").execute()
        ops_all = supabase.table("cash_operations").select("*").execute()
    except Exception as e:
        st.error(f"Ошибка: {e}")
        return

    if not sales_all.data:
        st.write("Продаж еще не было.")
        return

    df = pd.DataFrame(sales_all.data)
    products_data = products_all.data or []
    ops_data = ops_all.data or []
    all_sales_list = sales_all.data or []

    def parse_day(x):
        try:
            x = str(x)[:10]
            if "." in x:
                return datetime.strptime(x, "%d.%m.%Y").date()
            return datetime.strptime(x, "%Y-%m-%d").date()
        except:
            return None

    df['day_obj'] = df['day'].apply(parse_day)

    # ===== ВЫБОР ПЕРИОДА =====
    if user_role == "Администратор":
        st.subheader("🔍 Выберите период")
        date_range = st.date_input("Диапазон дат", value=(df['day_obj'].min(), df['day_obj'].max()), key="main_period")
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

    # ===== РАСЧЁТ РАСХОДОВ ЗА ПЕРИОД =====
    needs_expense = 0.0
    supplier_expense = 0.0

    for op in ops_data:
        amount = float(op.get("amount", 0) or 0)
        if amount >= 0:
            continue
        # Парсим дату операции
        op_day = None
        try:
            d_str = str(op.get("date", ""))[:10]
            if "." in d_str:
                op_day = datetime.strptime(d_str, "%d.%m.%Y").date()
            else:
                op_day = datetime.strptime(d_str, "%Y-%m-%d").date()
        except:
            continue

        if user_role == "Администратор":
            if not (start_date <= op_day <= end_date):
                continue
        else:
            if op_day != today:
                continue

        cat = get_category_from_comment(op.get("comment", ""))
        if cat == "Нужды магазина":
            needs_expense += abs(amount)
        elif cat == "Оплата контрагенту":
            supplier_expense += abs(amount)

    # ===== МЕТРИКИ ПРОДАЖ =====
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
    net_income = total_profit - needs_expense   # Чистый доход

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
        e3.metric("💰 Чистый доход", f"{int(net_income):,} сом",
                  delta=f"{int(net_income - total_profit):,}" if needs_expense else None)
    else:
        k1, k2, k3 = st.columns(3)
        k1.metric("🟢 Наличные", f"{int(cash_turnover):,} сом")
        k2.metric("🔵 Рассрочки", f"{int(credit_turnover):,} сом")
        k3.metric("🛍️ Всего", f"{int(cash_turnover + credit_turnover):,} сом")

    # ===== ПОЛНЫЙ ОТЧЁТ ПО ДНЯМ (Админ) =====
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
                    "Товаров на складе (шт)": qty_rec,
                    "Сумма товаров": cost_rec,
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
            st.download_button("📥 Скачать Полный отчет", data=buffer,
                               file_name=f"Polnyy_otchet_{start_date}_{end_date}.xlsx",
                               use_container_width=True)

    # ===== СПИСОК ЧЕКОВ =====
    st.markdown("---")
    st.subheader("📋 Список оформленных чеков")

    report_display = []
    for _, row in filtered_df.iterrows():
        item = {
            "Дата": format_date_to_ddmmyyyy(row['date'], include_time=True),
            "Наименование": fix_contract_name_on_fly(row['name'], row['date']),
            "Кол-во": int(row['qty']),
            "Тип оплаты": row['payment'],
            "Сумма": int(row['total_sale']),
            "Закупка": int(row.get('total_cost', 0)),
            "Прибыль": int(row.get('profit', 0)),
            "sale_id": row['id'],
            "raw_payment": row['payment'],
            "down_payment": int(row.get('down_payment', 0) or 0),
            "pure_name": row.get('pure_name', ''),
            "batch_date": row.get('batch_date', ''),
            "qty_raw": int(row.get('qty', 0))
        }
        report_display.append(item)

    df_display = pd.DataFrame(report_display)
    st.dataframe(df_display.drop(columns=["sale_id", "raw_payment", "down_payment", "pure_name", "batch_date", "qty_raw"], errors="ignore"),
                 use_container_width=True, hide_index=True)

    # ===== РЕДАКТИРОВАНИЕ (Админ) =====
    if user_role == "Администратор":
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
                        new_payment = st.selectbox("Тип оплаты", ["Наличные", "Рассрочка"],
                                                   index=0 if sale.get("payment") == "Наличные" else 1)
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

    # ===== УМНАЯ ОТМЕНА (Админ) =====
    if user_role == "Администратор":
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
                related_sales = [s for s in all_sales_list if str(s.get("id", "")).startswith(base_id)]
            else:
                related_sales = [s for s in all_sales_list if str(s.get("id")) == str(sale_id)]

            if not related_sales:
                related_sales = [next((s for s in all_sales_list if str(s.get("id")) == str(sale_id)), None)]
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
                        matching_any = [
                            p for p in products_data
                            if str(p.get("name", "")).lower().strip() == pure
                        ]
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
                    st.dataframe(pd.DataFrame(restore_preview).drop(columns=["product_id"], errors="ignore"),
                                 use_container_width=True, hide_index=True)
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

            st.markdown("---")
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
                                ops_res = supabase.table("cash_operations").select("*").execute()
                                ops = ops_res.data or []
                                for op in ops:
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
                        st.warning("Часть операций выполнена с ошибками. Проверьте склад и кассу.")
                    else:
                        st.success("✅ Продажа успешно отменена! Товар возвращён на склад.")
                    st.rerun()

                except Exception as e:
                    st.error(f"Критическая ошибка при отмене: {e}")
