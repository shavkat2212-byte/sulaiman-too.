# Магазин «Сулайман-Тоо» — Модуль: Клиенты и рассрочки
# Версия: 1.5 (редактирование клиента договора + пересчёт графика)

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from database import supabase
import os

def show_clients_page():
    st.title("👥 Управление клиентами и рассрочками")
    
    user_role = st.session_state.get("user", {}).get("role", "Кассир")
    tab_manage, tab_installments_window = st.tabs(["🗂️ База и Редактирование", "💳 Окно контроля рассрочек"])
    c_all = supabase.table("clients").select("*").order("fio").execute()

    # =========================================================================
    # ВКЛАДКА 1: УПРАВЛЕНИЕ БАЗОЙ КЛИЕНТОВ
    # =========================================================================
    with tab_manage:
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
                            "fio": fio,
                            "phone": phone if phone else None, 
                            "address": address if address else None,
                            "passport": passport if passport else None
                        }).execute()
                        st.success("Клиент успешно добавлен!")
                        st.rerun()
                        
        with col_c2:
            st.subheader("✏️ Редактировать данные клиента")
            if c_all.data:
                client_edit_opts = {c["fio"]: c for c in c_all.data}
                selected_edit_name = st.selectbox("Выберите клиента для изменения", list(client_edit_opts.keys()))
                client_to_update = client_edit_opts[selected_edit_name]
                
                with st.form("client_edit_form"):
                    new_fio = st.text_input("Изменить ФИО", value=str(client_to_update["fio"]))
                    new_phone = st.text_input("Изменить телефон", value=str(client_to_update["phone"] or ""))
                    new_address = st.text_input("Изменить адрес", value=str(client_to_update.get("address") or ""))
                    new_passport = st.text_area("Изменить паспортные данные", value=str(client_to_update["passport"] or ""))
                    
                    if st.form_submit_button("💾 Сохранить изменения"):
                        supabase.table("clients").update({
                            "fio": new_fio.strip(),
                            "phone": new_phone.strip() if new_phone.strip() else None,
                            "address": new_address.strip() if new_address.strip() else None,
                            "passport": new_passport.strip() if new_passport.strip() else None
                        }).eq("id", client_to_update["id"]).execute()
                        st.success("Данные успешно обновлены!")
                        st.rerun()

        st.markdown("---")
        st.subheader("📋 Список всех клиентов в базе")
        if c_all.data:
            df_c = pd.DataFrame(c_all.data).drop(columns=["created_at"], errors="ignore")
            df_c = df_c.rename(columns={
                "id": "ID", "fio": "ФИО Клиента", "phone": "Телефон",
                "address": "Адрес проживания", "passport": "Паспортные данные"
            })
            st.dataframe(
                df_c[["ID", "ФИО Клиента", "Телефон", "Адрес проживания", "Паспортные данные"]],
                use_container_width=True, hide_index=True
            )

    # =========================================================================
    # ВКЛАДКА 2: КОНТРОЛЬ РАССРОЧЕК
    # =========================================================================
    with tab_installments_window:
        st.subheader("📋 Мониторинг договоров, Прибыли и Погашений")
        
        if not c_all.data:
            st.info("В базе данных ещё нет клиентов.")
            return

        try:
            sales_res = supabase.table("sales").select("*").eq("payment", "Рассрочка").execute()
            all_sales = sales_res.data if sales_res.data else []
            payments_res = supabase.table("credit_payments").select("*").execute()
            all_payments = payments_res.data if payments_res.data else []
        except Exception as e:
            st.error(f"Ошибка Supabase: {e}")
            all_sales, all_payments = [], []

        # ----- Аналитика -----
        st.markdown("### 📊 Аналитика активных договоров рассрочки")
        installments_summary = []
        
        for s in all_sales:
            client_fio = next((cl["fio"] for cl in c_all.data if cl["id"] == s["client_id"]), "Неизвестный")
            sale_payments = [p for p in all_payments if p["sale_id"] == s["id"]]
            already_paid = sum(float(p.get("amount_paid", 0) or 0) for p in sale_payments)
            retail_with_markup = int(s.get("credit_balance", 0) or 0)
            current_debt_left = retail_with_markup - already_paid
            
            unpaid = [p for p in sale_payments if p["status"] != "Оплачен"]
            def get_unpaid_sort(x):
                p_d = str(x.get('due_date', ''))
                if ".00." in p_d: p_d = p_d.replace(".00.", f".{datetime.now().strftime('%m')}.")
                try: return datetime.strptime(p_d, "%d.%m.%Y")
                except: return datetime.now()
            unpaid_sorted = sorted(unpaid, key=get_unpaid_sort)
            monthly_payment_sum = int(unpaid_sorted[0]["amount_expected"]) if unpaid_sorted else 0
            
            cost_price = int(s.get("total_cost", 0) or 0)
            sale_price = int(s.get("total_sale", 0) or 0)
            down_pay = int(s.get("down_payment", 0) or 0)
            expected_profit = (down_pay + retail_with_markup) - cost_price

            if current_debt_left > 0:
                installments_summary.append({
                    "Клиент": client_fio,
                    "Договор / Состав товаров": s["name"],
                    "Закупка (сом)": cost_price,
                    "Цена продажи (сом)": sale_price,
                    "Перв. взнос (сом)": down_pay,
                    "Долг + наценка (сом)": retail_with_markup,
                    "Остаток долга (сом)": int(current_debt_left),
                    "Ежемес. платёж (сом)": monthly_payment_sum,
                    "Чистая прибыль (сом)": expected_profit
                })

        if installments_summary:
            st.dataframe(pd.DataFrame(installments_summary), use_container_width=True, hide_index=True)
        else:
            st.info("Нет активных рассрочек.")

        st.markdown("---")

        # =====================================================
        # КАРТОЧКА КЛИЕНТА
        # =====================================================
        st.markdown("### 🔍 Карточка и индивидуальный график клиента")
        debtor_opts = {cl["fio"]: cl["id"] for cl in c_all.data}
        selected_debtor_fio = st.selectbox(
            "Выберите ФИО клиента:",
            ["-- Выберите ФИО --"] + list(debtor_opts.keys()),
            key="debtor_view_sb"
        )
        
        if selected_debtor_fio == "-- Выберите ФИО --":
            return

        chosen_client_id = debtor_opts[selected_debtor_fio]
        chosen_cl_sales = [s for s in all_sales if s["client_id"] == chosen_client_id]
        
        if not chosen_cl_sales:
            st.info("У этого клиента нет договоров рассрочки.")
            return

        st.markdown(f"🛍️ **Договоры клиента:** {selected_debtor_fio}")
        details_list = []
        for idx, s in enumerate(chosen_cl_sales):
            details_list.append({
                "№": idx + 1,
                "Дата": s["date"],
                "Договор": s["name"],
                "Цена продажи": int(s.get("total_sale", 0)),
                "Перв. взнос": int(s.get("down_payment", 0)),
                "Долг + наценка": int(s.get("credit_balance", 0))
            })
        st.table(pd.DataFrame(details_list))

        # ----- График платежей -----
        st.markdown("#### 🗓️ Календарный график платежей")
        client_payments = [p for p in all_payments if p["client_id"] == chosen_client_id]
        
        if client_payments:
            def get_date_sort(x):
                p_d = str(x['due_date'])
                if ".00." in p_d: p_d = p_d.replace(".00.", f".{datetime.now().strftime('%m')}.")
                try: return datetime.strptime(p_d, "%d.%m.%Y")
                except: return datetime.now()

            for p_row in sorted(client_payments, key=get_date_sort):
                display_due = str(p_row['due_date'])
                if ".00." in display_due:
                    display_due = display_due.replace(".00.", f".{datetime.now().strftime('%m')}.")

                col_p1, col_p2, col_p3, col_p4 = st.columns([2, 2, 2, 2])
                col_p1.write(f"📅 {display_due}")
                col_p2.write(f"💵 Ожидается: {int(p_row['amount_expected'])} сом")
                col_p3.write(f"✅ Оплачено: {int(p_row['amount_paid'])} ({p_row['status']})")
                
                if p_row['status'] != 'Оплачен':
                    pay_amount = col_p4.number_input(
                        "Внести", min_value=0.0,
                        value=float(p_row['amount_expected'] - p_row['amount_paid']),
                        key=f"win_pay_{p_row['id']}"
                    )
                    if col_p4.button("💳 Принять", key=f"win_btn_{p_row['id']}", use_container_width=True):
                        new_paid = float(p_row['amount_paid']) + pay_amount
                        new_status = "Оплачен" if new_paid >= float(p_row['amount_expected']) else "Частично"
                        now_fmt = datetime.now().strftime("%d.%m.%Y %H:%M")
                        supabase.table("credit_payments").update({
                            "amount_paid": new_paid, "status": new_status
                        }).eq("id", p_row['id']).execute()
                        supabase.table("cash_operations").insert({
                            "date": now_fmt, "amount": pay_amount,
                            "comment": f"Погашение рассрочки от {selected_debtor_fio}"
                        }).execute()
                        st.success("Оплата принята!")
                        st.rerun()
        else:
            st.info("График платежей отсутствует.")

        # =================================================
        # РЕДАКТИРОВАНИЕ (только Админ)
        # =================================================
        if user_role == "Администратор":
            st.markdown("---")
            st.subheader("🛠️ Редактирование договора (Админ)")

            sale_opts = {
                f"{s['date']} | {str(s['name'])[:40]} | {int(s.get('total_sale',0)):,} сом": s
                for s in chosen_cl_sales
            }
            selected_sale_label = st.selectbox("Выберите договор", list(sale_opts.keys()), key="edit_sale_select")
            selected_sale = sale_opts[selected_sale_label]

            # --- 1. Поменять клиента ---
            st.markdown("##### 1. Перепривязать к другому клиенту")
            other_clients = {c["fio"]: c["id"] for c in c_all.data if c["id"] != chosen_client_id}
            if other_clients:
                new_client_fio = st.selectbox("Новый клиент", list(other_clients.keys()), key="new_client_select")
                if st.button("🔄 Сменить клиента у этого договора", type="primary"):
                    new_client_id = other_clients[new_client_fio]
                    try:
                        # Обновляем sale
                        supabase.table("sales").update({"client_id": new_client_id}).eq("id", selected_sale["id"]).execute()
                        # Обновляем все платежи этого договора
                        supabase.table("credit_payments").update({"client_id": new_client_id}).eq("sale_id", selected_sale["id"]).execute()
                        st.success(f"Договор перепривязан к клиенту: {new_client_fio}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Ошибка: {e}")
            else:
                st.info("Нет других клиентов для перепривязки.")

            st.markdown("---")

            # --- 2. Пересчитать график ---
            st.markdown("##### 2. Разбить / пересчитать график платежей")
            current_payments = [p for p in all_payments if p.get("sale_id") == selected_sale["id"]]
            current_months = len(current_payments) if current_payments else 1

            new_months = st.number_input(
                "Количество месяцев (новый график)",
                min_value=1, max_value=36,
                value=max(current_months, 3),
                key="new_months_input"
            )

            total = float(selected_sale.get("total_sale", 0) or 0)
            down = float(selected_sale.get("down_payment", 0) or 0)
            remaining = max(0, total - down)

            st.info(f"Сумма договора: **{total:,.0f}** | Первоначальный взнос: **{down:,.0f}** | К рассрочке: **{remaining:,.0f}**")

            if st.button("📅 Пересоздать график платежей", type="primary"):
                try:
                    # Удаляем старые платежи этого договора
                    for p in current_payments:
                        supabase.table("credit_payments").delete().eq("id", p["id"]).execute()

                    # Создаём новый график
                    monthly = round(remaining / new_months, 2)
                    balance = remaining
                    start = datetime.now()

                    for i in range(1, new_months + 1):
                        due = start + timedelta(days=30 * i)
                        if i == new_months:
                            amount = round(balance, 2)
                        else:
                            amount = monthly
                            balance = round(balance - monthly, 2)

                        supabase.table("credit_payments").insert({
                            "sale_id": selected_sale["id"],
                            "client_id": selected_sale["client_id"],
                            "due_date": due.strftime("%d.%m.%Y"),
                            "amount_expected": amount,
                            "amount_paid": 0,
                            "status": "Ожидается"
                        }).execute()

                    st.success(f"График пересоздан на {new_months} месяцев!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка при пересчёте: {e}")

        # =================================================
        # ГЕНЕРАЦИЯ ДОГОВОРА
        # =================================================
        st.markdown("---")
        st.subheader("📄 Сформировать договор")

        sale_options = {
            f"{s['date']} | {str(s['name'])[:50]} | {int(s.get('total_sale', 0)):,} сом": s
            for s in chosen_cl_sales
        }
        selected_sale_label2 = st.selectbox(
            "Выберите договор для печати",
            list(sale_options.keys()),
            key="contract_sale_select"
        )
        selected_sale2 = sale_options[selected_sale_label2]
        client_data = next((c for c in c_all.data if c["id"] == chosen_client_id), {})
        sale_payments2 = [p for p in all_payments if p.get("sale_id") == selected_sale2["id"]]
        months_count = len(sale_payments2) if sale_payments2 else 6

        if st.button("📄 Скачать договор (Word)", type="primary", use_container_width=True):
            try:
                from contract_generator import fill_contract, generate_payment_schedule
                template_path = "contract_template.docx"
                if not os.path.exists(template_path):
                    st.error("Файл contract_template.docx не найден!")
                else:
                    contract_num = str(selected_sale2.get("id", "б/н"))
                    contract_date = datetime.now().strftime("%d.%m.%Y")
                    total = float(selected_sale2.get("total_sale", 0) or 0)
                    down = float(selected_sale2.get("down_payment", 0) or 0)
                    product_name = selected_sale2.get("name", "Товар")
                    schedule = generate_payment_schedule(total, down, months_count)

                    doc_bytes = fill_contract(
                        template_path=template_path,
                        contract_number=contract_num,
                        contract_date=contract_date,
                        client_name=client_data.get("fio", ""),
                        client_address=client_data.get("address", "") or "—",
                        client_passport=client_data.get("passport", "") or "—",
                        total_amount=total,
                        months=months_count,
                        product_name=product_name,
                        product_qty=int(selected_sale2.get("qty", 1) or 1),
                        product_price=total,
                        down_payment=down,
                        schedule=schedule,
                    )
                    safe_name = (client_data.get("fio") or "client").replace(" ", "_")
                    st.download_button(
                        label="⬇️ Скачать договор",
                        data=doc_bytes,
                        file_name=f"Dogovor_{contract_num}_{safe_name}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True
                    )
                    st.success("Договор готов!")
            except Exception as e:
                st.error(f"Ошибка: {e}")
                st.exception(e)
