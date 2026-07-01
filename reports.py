import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime
from database import supabase

def show_reports_page():
    st.header("📊 Аналитика и история продаж")
    
    # Загружаем продажи и кассовые операции по погашению рассрочек
    sales_all = supabase.table("sales").select("*").order("date", desc=True).execute()
    ops_res = supabase.table("cash_operations").select("*").order("date", desc=True).execute()
    
    if not sales_all.data:
        st.write("Продаж еще не было.")
        return

    df = pd.DataFrame(sales_all.data)
    df['day'] = pd.to_datetime(df['day']).dt.date
    
    st.subheader("🔍 Выберите период для анализа")
    date_range = st.date_input("Диапазон дат", value=(df['day'].min(), df['day'].max()))
    
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
        filtered_df = df[(df['day'] >= start_date) & (df['day'] <= end_date)]
        
        # Фильтруем оплаты по рассрочкам для нижнего отчета
        if ops_res.data:
            df_ops_raw = pd.DataFrame(ops_res.data)
            df_ops_raw['day'] = pd.to_datetime(df_ops_raw['date']).dt.date
            filtered_ops = df_ops_raw[(df_ops_raw['day'] >= start_date) & (df_ops_raw['day'] <= end_date) & (df_ops_raw['comment'].str.contains("Погашение рассрочки", na=False))]
        else:
            filtered_ops = pd.DataFrame()
    else: 
        filtered_df = df
        if ops_res.data:
            df_ops_raw = pd.DataFrame(ops_res.data)
            filtered_ops = df_ops_raw[df_ops_raw['comment'].str.contains("Погашение рассрочки", na=False)]
        else:
            filtered_ops = pd.DataFrame()
        
    if not filtered_df.empty:
        # Считаем живую выручку: наличные продажи + первоначальные взносы + принятые платежи по рассрочкам за период!
        revenue_cash = filtered_df[filtered_df["payment"] == "Наличные"]["total_sale"].sum()
        revenue_down = filtered_df[filtered_df["payment"] == "Рассрочка"]["down_payment"].sum()
        revenue_collected = filtered_ops['amount'].sum() if not filtered_ops.empty else 0.0
        
        total_real_revenue = revenue_cash + revenue_down + revenue_collected

        c1, c2, c3 = st.columns(3)
        c1.metric("💰 Живая Выручка (Нал + Взносы + Оплаты)", f"{total_real_revenue:,.2f} сом")
        c2.metric("📈 Прибыль от заключенных сделок", f"{filtered_df['profit'].sum():,.2f} сом")
        c3.metric("✅ Собрано оплат по рассрочкам за период", f"{revenue_collected:,.2f} сом")

        st.markdown("### 🖨️ Печать и Экспорт основных продаж")
        excel_df = filtered_df.copy()
        excel_df["В рассрочку"] = excel_df.apply(lambda r: float(r["credit_balance"]) if r["payment"] == "Рассрочка" else 0.0, axis=1)
        excel_df = excel_df.rename(columns={"date": "Дата", "name": "Наименование", "qty": "Кол-во", "total_sale": "Сумма", "down_payment": "Взнос", "payment": "Оплата"})
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            excel_df[["Дата", "Наименование", "Кол-во", "Сумма", "Взнос", "В рассрочку", "Оплата"]].to_excel(writer, index=False)
        
        st.download_button(label="📥 Скачать этот отчёт в Excel", data=buffer.getvalue(), file_name="Otchet.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", use_container_width=True)
        
        st.subheader("📋 Детализация основных продаж и договоров")
        st.dataframe(filtered_df[["date", "name", "qty", "total_sale", "payment"]], use_container_width=True, hide_index=True)

    # ==================== 🧾 НОВЫЙ БЛОК: ОТЧЕТ ПО ПОСТУПЛЕНИЯМ РАССВРОЧКИ ====================
    st.markdown("---")
    st.subheader("💵 Поступления по рассрочкам (Оплаты клиентов за период)")
    if filtered_ops.empty:
        st.info("За выбранный период платежей от клиентов по рассрочкам не поступало.")
    else:
        df_ops_view = filtered_ops.copy().rename(columns={
            "date": "Дата и время платежа",
            "amount": "Внесенная сумма (сом)",
            "comment": "Информация о платеже"
        })
        st.dataframe(df_ops_view[["Дата и время платежа", "Внесенная сумма (сом)", "Информация о платеже"]], use_container_width=True, hide_index=True)

    # ==================== 🛠️ БЛОК: УМНАЯ ОТМЕНА С ВОЗВРАТОМ НА СКЛАД ====================
    st.markdown("---")
    st.subheader("✏️ Редактировать или Отменить (Удалить) операцию")
    
    sales_options = {
        f"[{s['date']}] {s['name']} — {float(s['total_sale']):.0f} сом ({s['payment']})": idx 
        for idx, s in enumerate(sales_all.data)
    }
    
    if sales_options:
        selected_sale_label = st.selectbox("Выберите операцию из списка для исправления/удаления", list(sales_options.keys()))
        target_sale_idx = sales_options[selected_sale_label]
        sale_to_edit = sales_all.data[target_sale_idx]
        
        with st.form("edit_sale_form_modular"):
            col_e1, col_e2, col_e3, col_e4 = st.columns(4)
            old_qty = int(sale_to_edit["qty"])
            old_price_one = float(sale_to_edit["total_sale"] / old_qty) if old_qty > 0 else float(sale_to_edit["total_sale"])
            
            new_s_qty = col_e1.number_input("Исправить Количество (шт/поз)", min_value=1, value=old_qty)
            new_s_price = col_e2.number_input("Исправить Цену за 1 шт (сом)", min_value=0.0, value=old_price_one)
            new_s_payment = col_e3.selectbox("Способ оплаты", ["Наличные", "Рассрочка"], index=0 if sale_to_edit["payment"] == "Наличные" else 1)
            
            new_total_sum = new_s_qty * new_s_price
            new_s_down = 0.0
            if new_s_payment == "Рассрочка":
                old_down = float(sale_to_edit.get("down_payment", 0.0))
                new_s_down = col_e4.number_input("Первоначальный взнос (сом)", min_value=0.0, max_value=float(new_total_sum), value=min(old_down, new_total_sum))
            
            new_credit_balance = new_total_sum - new_s_down
            
            btn_save_sale, btn_del_sale = st.columns(2)
            click_save = btn_save_sale.form_submit_button("💾 Сохранить изменения в продаже", type="primary")
            click_del = btn_del_sale.form_submit_button("❌ Полностью отменить (удалить) эту операцию", type="secondary")
            
            if click_save:
                st.session_state.pending_edit_sale = {
                    "id": sale_to_edit["id"], "old_qty": old_qty, "new_qty": new_s_qty,
                    "new_price": new_s_price, "new_total": new_total_sum, "payment": new_s_payment,
                    "down_payment": new_s_down, "credit_balance": new_credit_balance,
                    "pure_name": sale_to_edit.get("pure_name", ""), "batch_date": sale_to_edit.get("batch_date", ""),
                    "total_cost": float(sale_to_edit["total_cost"])
                }
                st.rerun()
            
            if click_del:
                st.session_state.show_sale_delete = {
                    "sale_id": sale_to_edit["id"], 
                    "name": sale_to_edit['name'], 
                    "qty": sale_to_edit['qty'], 
                    "total": sale_to_edit['total_sale'], 
                    "pure_name": sale_to_edit.get("pure_name", ""), 
                    "batch_date": sale_to_edit.get("batch_date", "")
                }
                st.rerun()

        if "pending_edit_sale" in st.session_state and st.session_state.pending_edit_sale:
            pe = st.session_state.pending_edit_sale
            @st.dialog("📋 Подтверждение изменения")
            def confirm_edit_dialog():
                st.warning("Внимательно проверьте исправленные данные:")
                st.markdown(f"### Новая сумма сделки: {pe['new_total']:.2f} сом ({pe['payment']})")
                col_y, col_n = st.columns(2)
                if col_y.button("✅ Да, сохранить изменения", type="primary", use_container_width=True):
                    if pe["pure_name"] != "рассрочка" and pe["pure_name"] != "":
                        qty_diff = pe["new_qty"] - pe["old_qty"]
                        exist_b = supabase.table("products").select("*").eq("name", pe["pure_name"]).eq("date", pe["batch_date"]).execute()
                        if exist_b.data:
                            new_stock = int(exist_b.data[0]["qty"]) - qty_diff
                            supabase.table("products").update({"qty": new_stock}).eq("id", exist_b.data[0]["id"]).execute()
                    
                    single_cost = pe["total_cost"] / pe["old_qty"] if pe["old_qty"] > 0 else pe["total_cost"]
                    new_cost = pe["new_qty"] * single_cost
                    
                    supabase.table("sales").update({
                        "qty": pe["new_qty"], "total_sale": int(pe["new_total"]), "total_cost": int(new_cost),
                        "profit": int(pe["new_total"] - new_cost), "payment": pe["payment"],
                        "down_payment": int(pe["down_payment"]), "credit_balance": int(pe["credit_balance"])
                    }).eq("id", pe["id"]).execute()
                    
                    st.session_state.pending_edit_sale = None
                    st.success("Изменения успешно сохранены!")
                    st.rerun()
                if col_n.button("Отмена", type="secondary", use_container_width=True):
                    st.session_state.pending_edit_sale = None
                    st.rerun()
            confirm_edit_dialog()

        if "show_sale_delete" in st.session_state and st.session_state.show_sale_delete:
            s_del = st.session_state.show_sale_delete
            @st.dialog("⚠️ Отмена и удаление операции")
            def delete_sale_dialog():
                st.error(f"Вы действительно хотите навсегда удалить эту запись из базы и вернуть товары на склад?\n\n{s_del['name']}")
                col_y, col_n = st.columns(2)
                if col_y.button("🔥 Да, удалить окончательно", type="primary", use_container_width=True):
                    if s_del["pure_name"] != "рассрочка" and s_del["pure_name"] != "":
                        exist_b = supabase.table("products").select("*").eq("name", s_del["pure_name"]).eq("date", s_del["batch_date"]).execute()
                        if exist_b.data:
                            new_stock = int(exist_b.data[0]["qty"]) + int(s_del["qty"])
                            supabase.table("products").update({"qty": new_stock}).eq("id", exist_b.data[0]["id"]).execute()
                    elif s_del["pure_name"] == "рассрочка":
                        match = re.search(r"\[(.*?)\]", s_del["name"])
                        if match:
                            items_content = match.group(1)
                            individual_items = items_content.split(", ")
                            for item_str in individual_items:
                                item_match = re.match(r"(.*?) \((\d+)\s*шт\.\)", item_str)
                                if item_match:
                                    t_name = item_match.group(1).strip().lower()
                                    t_qty = int(item_match.group(2))
                                    prod_res = supabase.table("products").select("*").eq("name", t_name).order("date", desc=True).execute()
                                    if prod_res.data:
                                        updated_qty = int(prod_res.data[0]["qty"]) + t_qty
                                        supabase.table("products").update({"qty": updated_qty}).eq("id", prod_res.data[0]["id"]).execute()
                    
                    supabase.table("sales").delete().eq("id", s_del["sale_id"]).execute()
                    supabase.table("credit_payments").delete().eq("sale_id", s_del["sale_id"]).execute()
                    
                    st.session_state.show_sale_delete = None
                    st.success("Операция удалена! Все товары успешно возвращены на склад.")
                    st.rerun()
                if col_n.button("Назад", type="secondary", use_container_width=True):
                    st.session_state.show_sale_delete = None
                    st.rerun()
            delete_sale_dialog()

def show_supplier_page():
    st.header("Выплаты поставщикам и контрагентам")
    with st.form("supplier_payment"):
        supplier = st.text_input("Название контрагента")
        amount = st.number_input("Сумма выплаты", min_value=1.0, value=1000.0)
        comment = st.text_input("Комментарий")
        if st.form_submit_button("Зафиксировать выплату"):
            if supplier:
                supabase.table("supplier_payments").insert({"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "supplier": supplier.strip(), "amount": amount, "comment": comment}).execute()
                st.success("Выплата отправлена!")
                st.rerun()

    payments_res = supabase.table("supplier_payments").select("*").order("id", desc=True).execute()
    if payments_res.data:
        df_pay = pd.DataFrame(payments_res.data).drop(columns=["id", "created_at"], errors="ignore")
        st.dataframe(df_pay, use_container_width=True, hide_index=True)
