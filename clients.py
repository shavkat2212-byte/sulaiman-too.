# Магазин «Сулайман-Тоо» — Модуль: Клиенты и рассрочки
# Версия: 1.8 (редактирование дат/сумм платежей в графике)

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from database import supabase
import os

def show_clients_page():
    st.title("👥 Управление клиентами и рассрочками")
    
    user_role = st.session_state.get("user", {}).get("role", "Кассир")
    tab_manage, tab_installments_window, tab_today = st.tabs([
        "🗂️ База и Редактирование", 
        "💳 Окно контроля рассрочек",
        "📅 Платежи сегодня / Просрочки"
    ])
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
        else:
            try:
                sales_res = supabase.table("sales").select("*").eq("payment", "Рассрочка").execute()
                all_sales = sales_res.data if sales_res.data else []
                payments_res = supabase.table("credit_payments").select("*").execute()
                all_payments = payments_res.data if payments_res.data else []
            except Exception as e:
                st.error(f"Ошибка Supabase: {e}")
                all_sales, all_payments = [], []

            st.markdown("### 📊 Аналитика активных договоров рассрочки")
            installments_summary = []
            
            for s in all_sales:
                client_fio = next((cl["fio"] for cl in c_all.data if cl["id"] == s["client_id"]), "Неизвестный")
                sale_payments = [p for p in all_payments if p["sale_id"] == s["id"]]
                already_paid = sum(float(p.get("amount_paid", 0) or 0) for p in sale_payments)
                retail_with_markup = int(s.get("credit_balance", 0) or 0)
                current_debt_left = retail_with_markup - already_paid
                
                unpaid = [p for p in sale_payments if p.get("status") != "Оплачен"]
                def get_unpaid_sort(x):
                    p_d = str(x.get('due_date', ''))
                    if ".00." in p_d:
                        p_d = p_d.replace(".00.", f".{datetime.now().strftime('%m')}.")
                    try:
                        return datetime.strptime(p_d[:10], "%d.%m.%Y")
                    except:
                        try:
                            return datetime.strptime(p_d[:10], "%Y-%m-%d")
                        except:
                            return datetime.now()
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

            # Карточка клиента
            st.markdown("### 🔍 Карточка и индивидуальный график клиента")
            debtor_opts = {cl["fio"]: cl["id"] for cl in c_all.data}
            selected_debtor_fio = st.selectbox(
                "Выберите ФИО клиента:",
                ["-- Выберите ФИО --"] + list(debtor_opts.keys()),
                key="debtor_view_sb"
            )
            
            if selected_debtor_fio != "-- Выберите ФИО --":
                chosen_client_id = debtor_opts[selected_debtor_fio]
                chosen_cl_sales = [s for s in all_sales if s["client_id"] == chosen_client_id]
                
                if not chosen_cl_sales:
                    st.info("У этого клиента нет договоров рассрочки.")
                else:
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

                    st.markdown("#### 🗓️ Календарный график платежей")
                    client_payments = [p for p in all_payments if p["client_id"] == chosen_client_id]
                    
                    def get_date_sort(x):
                        p_d = str(x.get('due_date', ''))
                        if ".00." in p_d:
                            p_d = p_d.replace(".00.", f".{datetime.now().strftime('%m')}.")
                        try:
                            return datetime.strptime(p_d[:10], "%d.%m.%Y")
                        except:
                            try:
                                return datetime.strptime(p_d[:10], "%Y-%m-%d")
                            except:
                                return datetime.now()

                    if client_payments:
                        for p_row in sorted(client_payments, key=get_date_sort):
                            display_due = str(p_row.get('due_date', ''))
                            if ".00." in display_due:
                                display_due = display_due.replace(".00.", f".{datetime.now().strftime('%m')}.")
                            try:
                                if "-" in display_due[:10]:
                                    display_due = datetime.strptime(display_due[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
                            except:
                                pass

                            col_p1, col_p2, col_p3, col_p4 = st.columns([2, 2, 2, 2])
                            col_p1.write(f"📅 {display_due}")
                            col_p2.write(f"💵 Ожидается: {int(p_row.get('amount_expected', 0))} сом")
                            col_p3.write(f"✅ Оплачено: {int(p_row.get('amount_paid', 0))} ({p_row.get('status', '')})")
                            
                            if p_row.get('status') != 'Оплачен':
                                pay_amount = col_p4.number_input(
                                    "Внести", min_value=0.0,
                                    value=float(p_row.get('amount_expected', 0) - p_row.get('amount_paid', 0)),
                                    key=f"win_pay_{p_row['id']}"
                                )
                                if col_p4.button("💳 Принять", key=f"win_btn_{p_row['id']}", use_container_width=True):
                                    new_paid = float(p_row.get('amount_paid', 0)) + pay_amount
                                    new_status = "Оплачен" if new_paid >= float(p_row.get('amount_expected', 0)) else "Частично"
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

                    # ===== РЕДАКТИРОВАНИЕ (Админ) =====
                    if user_role == "Администратор":
                        st.markdown("---")
                        st.subheader("🛠️ Редактирование договора (Админ)")

                        sale_opts = {
                            f"{s['date']} | {str(s['name'])[:40]} | {int(s.get('total_sale',0)):,} сом": s
                            for s in chosen_cl_sales
                        }
                        selected_sale_label = st.selectbox("Выберите договор", list(sale_opts.keys()), key="edit_sale_select")
                        selected_sale = sale_opts[selected_sale_label]

                        st.markdown("##### 1. Перепривязать к другому клиенту")
                        other_clients = {c["fio"]: c["id"] for c in c_all.data if c["id"] != chosen_client_id}
                        if other_clients:
                            new_client_fio = st.selectbox("Новый клиент", list(other_clients.keys()), key="new_client_select")
                            if st.button("🔄 Сменить клиента у этого договора", type="primary"):
                                new_client_id = other_clients[new_client_fio]
                                try:
                                    supabase.table("sales").update({"client_id": new_client_id}).eq("id", selected_sale["id"]).execute()
                                    supabase.table("credit_payments").update({"client_id": new_client_id}).eq("sale_id", selected_sale["id"]).execute()
                                    st.success(f"Договор перепривязан к: {new_client_fio}")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Ошибка: {e}")
                        else:
                            st.info("Нет других клиентов.")

                        st.markdown("---")
                        st.markdown("##### 2. Разбить / пересчитать график платежей")
                        current_payments = [p for p in all_payments if p.get("sale_id") == selected_sale["id"]]
                        current_months = len(current_payments) if current_payments else 1

                        new_months = st.number_input("Количество месяцев", min_value=1, max_value=36, value=max(current_months, 3), key="new_months_input")

                        total = float(selected_sale.get("total_sale", 0) or 0)
                        down = float(selected_sale.get("down_payment", 0) or 0)
                        credit_balance = float(selected_sale.get("credit_balance", 0) or 0)
                        remaining = credit_balance if credit_balance > 0 else max(0, total - down)

                        st.info(f"Сумма: **{total:,.0f}** | Взнос: **{down:,.0f}** | К рассрочке: **{remaining:,.0f}**")

                        if st.button("📅 Пересоздать график платежей", type="primary"):
                            try:
                                for p in current_payments:
                                    supabase.table("credit_payments").delete().eq("id", p["id"]).execute()

                                monthly = round(remaining / new_months, 2)
                                balance = remaining
                                start = datetime.now().date()

                                for i in range(1, new_months + 1):
                                    year = start.year
                                    month = start.month + i
                                    while month > 12:
                                        month -= 12
                                        year += 1
                                    day = min(start.day, 28)
                                    due = datetime(year, month, day).date()

                                    if i == new_months:
                                        amount = round(balance, 2)
                                    else:
                                        amount = monthly
                                        balance = round(balance - monthly, 2)

                                    due_str = due.strftime("%Y-%m-%d")

                                    supabase.table("credit_payments").insert({
                                        "sale_id": selected_sale["id"],
                                        "client_id": selected_sale["client_id"],
                                        "due_date": due_str,
                                        "amount_expected": amount,
                                        "amount_paid": 0,
                                        "status": "Не оплачен"
                                    }).execute()

                                st.success(f"✅ График создан на {new_months} месяцев!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Ошибка: {e}")

                        # ===== 3. РЕДАКТИРОВАНИЕ ДАТ И СУММ ОТДЕЛЬНЫХ ПЛАТЕЖЕЙ =====
                        st.markdown("---")
                        st.markdown("##### 3. Изменить дату или сумму отдельного платежа")

                        sale_payments_edit = [p for p in all_payments if p.get("sale_id") == selected_sale["id"]]
                        if not sale_payments_edit:
                            st.info("У этого договора нет платежей для редактирования.")
                        else:
                            for p_row in sorted(sale_payments_edit, key=get_date_sort):
                                pid = p_row["id"]
                                raw_due = str(p_row.get("due_date", ""))[:10]

                                try:
                                    if "-" in raw_due:
                                        cur_date = datetime.strptime(raw_due, "%Y-%m-%d").date()
                                        show_due = cur_date.strftime("%d.%m.%Y")
                                    else:
                                        cur_date = datetime.strptime(raw_due, "%d.%m.%Y").date()
                                        show_due = raw_due
                                except:
                                    cur_date = datetime.now().date()
                                    show_due = raw_due

                                with st.expander(f"Платёж #{pid} | {show_due} | {int(p_row.get('amount_expected', 0))} сом | {p_row.get('status', '')}"):
                                    col_a, col_b, col_c = st.columns([2, 2, 1])
                                    new_due = col_a.date_input(
                                        "Дата платежа",
                                        value=cur_date,
                                        key=f"edit_due_{pid}"
                                    )
                                    new_expected = col_b.number_input(
                                        "Сумма (ожидается)",
                                        min_value=0.0,
                                        value=float(p_row.get("amount_expected", 0) or 0),
                                        step=50.0,
                                        key=f"edit_amt_{pid}"
                                    )
                                    if col_c.button("💾 Сохранить", key=f"save_pay_{pid}"):
                                        try:
                                            supabase.table("credit_payments").update({
                                                "due_date": new_due.strftime("%Y-%m-%d"),
                                                "amount_expected": new_expected
                                            }).eq("id", pid).execute()
                                            st.success(f"Платёж #{pid} обновлён")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Ошибка: {e}")

                    # ===== ГЕНЕРАЦИЯ ДОГОВОРА =====
                    st.markdown("---")
                    st.subheader("📄 Сформировать договор")

                    sale_options = {
                        f"{s['date']} | {str(s['name'])[:50]} | {int(s.get('total_sale', 0)):,} сом": s
                        for s in chosen_cl_sales
                    }
                    selected_sale_label2 = st.selectbox("Выберите договор для печати", list(sale_options.keys()), key="contract_sale_select")
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
                                down = float(selected_sale2.get("down_payment", 0) or 0)
                                credit_balance = float(selected_sale2.get("credit_balance", 0) or 0)
                                total_sale = float(selected_sale2.get("total_sale", 0) or 0)
                                total_with_markup = down + credit_balance if credit_balance > 0 else total_sale
                                product_name = selected_sale2.get("name", "Товар")
                                schedule = generate_payment_schedule(total_with_markup, down, months_count)

                                doc_bytes = fill_contract(
                                    template_path=template_path,
                                    contract_number=contract_num,
                                    contract_date=contract_date,
                                    client_name=client_data.get("fio", ""),
                                    client_address=client_data.get("address", "") or "—",
                                    client_passport=client_data.get("passport", "") or "—",
                                    total_amount=total_with_markup,
                                    months=months_count,
                                    product_name=product_name,
                                    product_qty=int(selected_sale2.get("qty", 1) or 1),
                                    product_price=total_with_markup,
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

    # =========================================================================
    # ВКЛАДКА 3: ПЛАТЕЖИ СЕГОДНЯ / ПРОСРОЧКИ
    # =========================================================================
    with tab_today:
        st.subheader("📅 Платежи на сегодня и просрочки")

        try:
            sales_res = supabase.table("sales").select("*").eq("payment", "Рассрочка").execute()
            all_sales = sales_res.data if sales_res.data else []
            payments_res = supabase.table("credit_payments").select("*").execute()
            all_payments = payments_res.data if payments_res.data else []
            clients_map = {c["id"]: c for c in (c_all.data or [])}
            sales_map = {s["id"]: s for s in all_sales}
        except Exception as e:
            st.error(f"Ошибка загрузки: {e}")
            return

        today = datetime.now().date()

        def parse_due(d):
            if not d:
                return None
            d = str(d)[:10]
            for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
                try:
                    return datetime.strptime(d, fmt).date()
                except:
                    continue
            return None

        today_list = []
        overdue_list = []
        overdue_sale_ids = set()

        for p in all_payments:
            if p.get("status") == "Оплачен":
                continue
            due = parse_due(p.get("due_date"))
            if not due:
                continue

            expected = float(p.get("amount_expected", 0) or 0)
            paid = float(p.get("amount_paid", 0) or 0)
            left = expected - paid
            if left <= 0:
                continue

            client = clients_map.get(p.get("client_id"), {})
            client_name = client.get("fio", "Неизвестный")
            phone = client.get("phone", "—")

            row = {
                "Клиент": client_name,
                "Телефон": phone,
                "Дата платежа": due.strftime("%d.%m.%Y"),
                "Ожидается": int(expected),
                "Оплачено": int(paid),
                "Осталось": int(left),
                "Статус": "🔴 ПРОСРОЧКА" if due < today else "🟡 Сегодня",
                "due_obj": due,
                "sale_id": p.get("sale_id"),
                "payment_id": p.get("id")
            }

            if due < today:
                overdue_list.append(row)
                if p.get("sale_id"):
                    overdue_sale_ids.add(p.get("sale_id"))
            elif due == today:
                today_list.append(row)

        st.markdown("### 🟡 Должны оплатить сегодня")
        if today_list:
            df_today = pd.DataFrame(today_list).drop(columns=["due_obj", "sale_id", "payment_id"], errors="ignore")
            st.dataframe(df_today, use_container_width=True, hide_index=True)
            st.metric("Сумма к получению сегодня", f"{sum(r['Осталось'] for r in today_list):,} сом")
        else:
            st.success("На сегодня платежей нет.")

        st.markdown("---")
        st.markdown("### 🔴 Просроченные платежи")
        if overdue_list:
            overdue_list = sorted(overdue_list, key=lambda x: x["due_obj"])
            df_over = pd.DataFrame(overdue_list).drop(columns=["due_obj", "sale_id", "payment_id"], errors="ignore")
            st.dataframe(df_over, use_container_width=True, hide_index=True)
            st.error(f"Всего просрочено: **{sum(r['Осталось'] for r in overdue_list):,} сом** у {len(overdue_list)} платежей")
        else:
            st.success("Просроченных платежей нет.")

        if user_role == "Администратор" and overdue_sale_ids:
            st.markdown("---")
            st.subheader("🛠️ Исправление неправильных графиков")
            st.warning(f"Найдено **{len(overdue_sale_ids)}** договоров с просроченными датами.")
            st.info("Кнопка удалит старые графики и создаст новые с текущего месяца.")

            if st.button("📅 Исправить все просроченные графики", type="primary"):
                fixed = 0
                errors = []
                for sale_id in overdue_sale_ids:
                    try:
                        sale = sales_map.get(sale_id)
                        if not sale:
                            continue
                        sale_payments = [p for p in all_payments if p.get("sale_id") == sale_id]
                        months = len(sale_payments) if sale_payments else 6
                        already_paid = sum(float(p.get("amount_paid", 0) or 0) for p in sale_payments)
                        credit_balance = float(sale.get("credit_balance", 0) or 0)
                        down = float(sale.get("down_payment", 0) or 0)
                        total_sale = float(sale.get("total_sale", 0) or 0)
                        remaining = credit_balance if credit_balance > 0 else max(0, total_sale - down)
                        remaining = max(0, remaining - already_paid)
                        if remaining <= 0 or months <= 0:
                            continue
                        for p in sale_payments:
                            supabase.table("credit_payments").delete().eq("id", p["id"]).execute()
                        monthly = round(remaining / months, 2)
                        balance = remaining
                        start = datetime.now().date()
                        for i in range(1, months + 1):
                            year = start.year
                            month = start.month + i
                            while month > 12:
                                month -= 12
                                year += 1
                            day = min(start.day, 28)
                            due = datetime(year, month, day).date()
                            if i == months:
                                amount = round(balance, 2)
                            else:
                                amount = monthly
                                balance = round(balance - monthly, 2)
                            supabase.table("credit_payments").insert({
                                "sale_id": sale_id,
                                "client_id": sale.get("client_id"),
                                "due_date": due.strftime("%Y-%m-%d"),
                                "amount_expected": amount,
                                "amount_paid": 0,
                                "status": "Не оплачен"
                            }).execute()
                        fixed += 1
                    except Exception as e:
                        errors.append(f"{sale_id}: {e}")
                if fixed:
                    st.success(f"✅ Исправлено договоров: {fixed}")
                if errors:
                    st.error(f"Ошибки: {errors}")
                st.rerun()

        st.markdown("---")
        st.markdown("### ⚠️ Проверка графиков платежей")
        sales_without_schedule = []
        for s in all_sales:
            has_payments = any(p.get("sale_id") == s["id"] for p in all_payments)
            if not has_payments:
                client_name = clients_map.get(s.get("client_id"), {}).get("fio", "Неизвестный")
                sales_without_schedule.append({
                    "Клиент": client_name,
                    "Договор": str(s.get("name", ""))[:60],
                    "Сумма": int(s.get("total_sale", 0)),
                    "Долг + наценка": int(s.get("credit_balance", 0)),
                    "Дата оформления": s.get("date", "")
                })
        if sales_without_schedule:
            st.warning(f"Найдено **{len(sales_without_schedule)}** договоров без графика:")
            st.dataframe(pd.DataFrame(sales_without_schedule), use_container_width=True, hide_index=True)
            st.info("Зайди в карточку клиента → Редактирование → «Пересоздать график»")
        else:
            st.success("✅ У всех договоров рассрочки есть график платежей.")
