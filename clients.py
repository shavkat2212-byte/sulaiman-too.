import streamlit as st
import pandas as pd
from datetime import datetime
from database import supabase

def show_clients_page():
    st.header("👥 Управление клиентами и рассрочками")
    c_all = supabase.table("clients").select("*").order("fio").execute()
    
    col_c1, col_c2 = st.columns([1, 1.2])
    with col_c1:
        st.subheader("➕ Регистрация нового клиента")
        with st.form("client_reg", clear_on_submit=True):
            fio = st.text_input("ФИО Клиента").strip()
            phone = st.text_input("Номер телефона").strip()
            address = st.text_input("Адрес проживания").strip()
            passport = st.text_area("Паспортные данные").strip()
            if st.form_submit_button("Зарегистрировать"):
                if fio:
                    supabase.table("clients").insert({
                        "fio": fio, "phone": phone if phone else None, 
                        "address": address if address else None, "passport": passport if passport else None
                    }).execute()
                    st.success("Клиент успешно добавлен!")
                    st.rerun()
                    
    with col_c2:
        st.subheader("✏️ Редактировать данные клиента")
        if c_all.data:
            client_edit_opts = {c["fio"]: c for c in c_all.data}
            selected_edit_name = st.selectbox("Выберите клиента", list(client_edit_opts.keys()))
            client_to_update = client_edit_opts[selected_edit_name]
            
            with st.form("client_edit_form"):
                new_fio = st.text_input("Изменить ФИО", value=str(client_to_update["fio"]))
                new_phone = st.text_input("Изменить телефон", value=str(client_to_update["phone"] or ""))
                new_address = st.text_input("Изменить адрес", value=str(client_to_update.get("address") or ""))
                new_passport = st.text_area("Изменить паспортные данные", value=str(client_to_update["passport"] or ""))
                
                if st.form_submit_button("💾 Сохранить изменения"):
                    supabase.table("clients").update({
                        "fio": new_fio.strip(), "phone": new_phone.strip() if new_phone.strip() else None,
                        "address": new_address.strip() if new_address.strip() else None, "passport": new_passport.strip() if new_passport.strip() else None
                    }).eq("id", client_to_update["id"]).execute()
                    st.success("Обновлено!")
                    st.rerun()

    st.markdown("---")
    st.subheader("📋 Список всех клиентов в базе")
    if c_all.data:
        df_c = pd.DataFrame(c_all.data).drop(columns=["created_at"], errors="ignore")
        df_c = df_c.rename(columns={"id": "ID", "fio": "ФИО Клиента", "phone": "Телефон", "address": "Адрес проживания", "passport": "Паспортные данные"})
        st.dataframe(df_c[["ID", "ФИО Клиента", "Телефон", "Адрес проживания", "Паспортные данные"]], use_container_width=True, hide_index=True)
            
    st.markdown("---")
    st.subheader("🔍 Карточка рассрочки, История покупок и Прием оплаты")
    if c_all.data:
        client_opts = {c["fio"]: c["id"] for c in c_all.data}
        selected_client_name = st.selectbox("Просмотр деталей клиента", list(client_opts.keys()))
        c_id = client_opts[selected_client_name]
        
        st.markdown("### 📦 История купленных товаров / Договоров")
        client_sales_res = supabase.table("sales").select("*").eq("client_id", c_id).order("date").execute()
        for s_row in client_sales_res.data:
            st.markdown(f"🔹 **{s_row['date']}** — {s_row['name']} | **{s_row['total_sale']} сом**")

        payments_res = supabase.table("credit_payments").select("*").eq("client_id", c_id).order("due_date").execute()
        if payments_res.data:
            st.markdown("### 📅 Календарный график платежей")
            for idx, row in pd.DataFrame(payments_res.data).iterrows():
                col_p1, col_p2, col_p3, col_p4 = st.columns([2, 2, 2, 2])
                col_p1.write(f"📅 Срок: {row['due_date']}")
                col_p2.write(f"💵 Ожидается: {row['amount_expected']} сом")
                col_p3.write(f"✅ Оплачено: {row['amount_paid']} сом ({row['status']})")
                
                if row['status'] != 'Оплачен':
                    pay_amount = col_p4.number_input("Сумма оплаты", min_value=0.0, value=float(row['amount_expected'] - row['amount_paid']), key=f"pay_{row['id']}")
                    if col_p4.button("💳 Принять", key=f"btn_{row['id']}", use_container_width=True):
                        new_paid = float(row['amount_paid']) + pay_amount
                        new_status = "Оплачен" if new_paid >= float(row['amount_expected']) else "Частично"
                        
                        supabase.table("credit_payments").update({"amount_paid": new_paid, "status": new_status}).eq("id", row['id']).execute()
                        supabase.table("cash_operations").insert({"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "amount": pay_amount, "comment": f"Погашение рассрочки от {selected_client_name}"}).execute()
                        st.success("Успешно!")
                        st.rerun()
