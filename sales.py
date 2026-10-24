# Магазин «Сулайман-Тоо» — Модуль: Продажи
# Версия: 1.7 (договор сразу в продаже)

import os
import streamlit as st
import pandas as pd
from datetime import datetime
from database import supabase


from installment_logic import add_month, month_schedule
from client_logic import client_label, find_duplicates, new_client_payload

MODE_EXISTING = "Выбрать существующего"
MODE_NEW = "Добавить нового"
NEW_CLIENT_KEYS = ("nc_fio", "nc_phone", "nc_address", "nc_passport", "nc_force_new",
                   "nc_pin", "nc_issued", "nc_pdate", "nc_comment")


def apply_pending_client():
    """После сохранения клиента/сделки: режим «существующий» с этим клиентом (до создания виджетов)."""
    cid = st.session_state.pop("_pending_client_select", None)
    if cid is not None:
        st.session_state["client_mode"] = MODE_EXISTING
        st.session_state["sale_client_select"] = cid
        for k in NEW_CLIENT_KEYS:
            st.session_state.pop(k, None)


def use_existing_client(cid):
    st.session_state["_pending_client_select"] = cid


def new_client_from_state():
    """Все поля формы «Добавить нового» (как во вкладке Клиенты) + обязательный комментарий."""
    from obligation import doc_fields_from_state, client_comment_available
    ss = st.session_state
    return new_client_payload(ss.get("nc_fio"), ss.get("nc_phone"), ss.get("nc_address"), ss.get("nc_passport"),
                              comment=ss.get("nc_comment"), extra=doc_fields_from_state("nc"),
                              comment_required=client_comment_available())


def save_new_client_cb(clients_all):
    payload, errors, _ = new_client_from_state()
    if errors:
        st.session_state["_nc_error"] = "; ".join(errors)
        return
    if find_duplicates(clients_all, payload["fio"], payload["phone"]) and not st.session_state.get("nc_force_new"):
        st.session_state["_nc_error"] = "Похожий клиент уже есть — выберите его или отметьте «Это другой человек»."
        return
    try:
        res = supabase.table("clients").insert(payload).execute()
        st.session_state["_pending_client_select"] = res.data[0]["id"]
        st.session_state["_nc_ok"] = f"Клиент {payload['fio']} сохранён и выбран."
    except Exception as e:
        st.session_state["_nc_error"] = f"Не удалось сохранить клиента: {e}"


def add_months(start_date, months, pay_day):
    year = start_date.year
    month = start_date.month + months
    while month > 12:
        month -= 12
        year += 1
    day = min(int(pay_day), 28)
    return datetime(year, month, day).date()


def build_sale_contract(number, sale_date, client, cart, total_cart_sum, down_payment, months, total_with_markup, schedule_preview):
    template = "contract_template.docx"
    if not os.path.exists(template):
        st.error("Нет файла contract_template.docx")
        return None
    try:
        from contract_generator import fill_contract
    except Exception as e:
        st.error(f"Не открылся генератор договора: {e}")
        return None
    goods = ", ".join(f"{item['name']} ({int(item['qty'])} шт.)" for item in cart)
    qty = sum(int(item["qty"]) for item in cart) or 1
    price = float(total_cart_sum)
    schedule = []
    balance = float(total_with_markup)
    for row in schedule_preview:
        amount = float(row["Сумма"])
        balance = max(0.0, balance - amount)
        schedule.append({"num": row["№"], "date": row["Дата платежа"], "amount": amount, "balance": balance})
    total_for_doc = float(down_payment) + float(total_with_markup)
    return fill_contract(
        template_path=template,
        contract_number=str(number),
        contract_date=sale_date.strftime("%d.%m.%Y"),
        client_name=client.get("fio", ""),
        client_address=client.get("address") or "—",
        client_passport=client.get("passport") or "—",
        total_amount=total_for_doc,
        months=int(months),
        product_name=goods,
        product_qty=qty,
        product_price=price,
        down_payment=float(down_payment),
        schedule=schedule,
    )


def show_sales_page():
    st.header("Оформить продажу (Корзина покупок)")
    if st.session_state.get("last_contract") and st.session_state["last_contract"].get("bytes"):
        last = st.session_state["last_contract"]
        st.success("Последний договор готов к печати.")
        st.download_button(
            "📄 Скачать последний договор",
            data=last["bytes"],
            file_name=last["name"],
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="last_contract_download",
        )
    if st.session_state.get("last_obligation_sale_id"):
        with st.container(border=True):
            st.subheader("📄 Бланк обязательства по последней рассрочке")
            from obligation import show_obligation
            show_obligation(st.session_state["last_obligation_sale_id"], key="obl_new")
            if st.button("✖️ Скрыть бланк", key="obl_hide"):
                st.session_state.pop("last_obligation_sale_id", None)
                st.rerun()

    if "cart" not in st.session_state:
        st.session_state.cart = []

    stock_res = supabase.table("products").select("*").gt("qty", 0).execute()

    if not stock_res.data:
        st.warning("На складе нет доступных товаров для продажи")
        return

    stock_by_id = {row["id"]: row for row in stock_res.data}

    col_form, col_cart = st.columns([1.2, 1])
    with col_form:
        st.subheader("🛒 Выбор товаров")
        search = st.text_input("Найти товар по названию", placeholder="например: iphone, холодильник", key="sale_product_search")
        names = {}
        for row in stock_res.data:
            title = str(row.get("name") or "").strip()
            if not title:
                continue
            if search and search.strip().lower() not in title.lower():
                continue
            names[title.capitalize()] = title.lower()
        unique_names = sorted(names.keys())
        if not unique_names:
            st.warning("Такого товара на складе нет.")
        else:
            st.caption(f"Найдено товаров: {len(unique_names)}")
            sel_display = st.selectbox("Выберите товар", unique_names)
            p_key = names[sel_display]

            def format_batch_date(d_str):
                try:
                    return datetime.strptime(str(d_str)[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
                except Exception:
                    return str(d_str)

            batches_options = {
                f"Поступление от {format_batch_date(row['date'])} (Остаток: {row['qty']} шт.)": row["id"]
                for row in stock_res.data if row["name"] == p_key
            }
            if not batches_options:
                st.warning("Нет партий этого товара")
            else:
                selected_batch_label = st.selectbox("📦 Выберите партию", list(batches_options.keys()))
                batch_id = batches_options[selected_batch_label]
                chosen_batch = stock_by_id.get(batch_id) or supabase.table("products").select("*").eq("id", batch_id).execute().data[0]

                sqty = st.number_input("Количество для продажи", min_value=1, max_value=int(chosen_batch["qty"]), value=1)
                custom_price = st.number_input("💰 Цена за 1 шт, сом", min_value=0.0, value=float(chosen_batch["price"]))
                st.caption(f"Закупка: {int(chosen_batch['cost'])} сом | На складе: {int(chosen_batch['qty'])} шт.")

                if st.button("➕ Добавить в чек", width="stretch"):
                    st.session_state.cart.append({
                        "batch_id": batch_id,
                        "name": sel_display,
                        "batch_date": chosen_batch["date"],
                        "qty": int(sqty),
                        "price": float(custom_price),
                        "total": int(sqty) * float(custom_price),
                        "cost": float(chosen_batch["cost"]),
                        "pure_name": p_key,
                        "max_qty": int(chosen_batch["qty"]),
                    })
                    st.success("Товар добавлен в чек!")
                    st.rerun()

    with col_cart:
        st.subheader("🧾 Текущий чек (Корзина)")
        if not st.session_state.cart:
            st.info("Чек пока пуст.")
            total_cart_sum = 0.0
        else:
            total_cart_sum = 0.0
            for i, item in enumerate(list(st.session_state.cart)):
                max_qty = int(item.get("max_qty") or item.get("qty") or 1)
                c1, c2, c3 = st.columns([3, 1.2, 0.8])
                c1.write(f"**{item['name']}**")
                new_qty = c2.number_input(
                    "Шт",
                    min_value=1,
                    max_value=max(max_qty, 1),
                    value=int(item["qty"]),
                    key=f"cart_qty_{i}",
                )
                if c3.button("✖", key=f"del_cart_{i}", help="Удалить позицию"):
                    st.session_state.cart.pop(i)
                    st.rerun()
                if int(new_qty) != int(item["qty"]):
                    item["qty"] = int(new_qty)
                    item["total"] = int(new_qty) * float(item["price"])
                    st.session_state.cart[i] = item
                c1.caption(f"{int(item['qty'])} × {int(item['price'])} = {item['total']:,.0f} сом")
                total_cart_sum += float(item["total"])

            st.markdown(f"### 💵 Сумма по чеку: {total_cart_sum:,.2f} сом")
            if st.button("🗑️ Очистить чек"):
                st.session_state.cart = []
                st.rerun()

    if not st.session_state.cart:
        return

    st.markdown("---")
    st.subheader("💳 Параметры оплаты чека")
    sale_date = st.date_input("📅 Дата продажи", value=datetime.now().date())
    pay_method = st.radio("Способ оплаты", ["Наличные", "Рассрочка"], horizontal=True)

    down_payment = 0.0
    months = 1
    client_id = None
    sel_client_name = ""
    monthly_payment = 0
    total_with_markup = 0
    pay_day = sale_date.day if sale_date.day <= 28 else 28
    client_opts = {}
    sel_client_label = ""
    new_client_ready = None
    schedule_preview = []

    if pay_method == "Рассрочка":
        st.markdown("#### 👤 Клиент")
        clients_all = supabase.table("clients").select("*").order("fio").execute().data or []
        clients_by_id = {c["id"]: c for c in clients_all}
        apply_pending_client()
        if st.session_state.get("_nc_error"):
            st.error(st.session_state.pop("_nc_error"))
        if st.session_state.get("_nc_ok"):
            st.success(st.session_state.pop("_nc_ok"))
        client_mode = st.radio(
            "Клиент",
            [MODE_EXISTING, MODE_NEW],
            horizontal=True,
            key="client_mode"
        )

        if client_mode == MODE_NEW:
            # Поля без st.form: значения сразу доступны кнопке «Оформить», отдельное сохранение не обязательно
            with st.container(border=True):
                st.text_input("ФИО клиента *", key="nc_fio")
                st.text_input("Телефон", key="nc_phone", placeholder="0555 12-34-56")
                st.text_input("Адрес", key="nc_address")
                st.text_area("Паспортные данные", key="nc_passport")
                from obligation import doc_fields_input, client_comment_available
                doc_fields_input(prefix="nc")  # ПИН / кем выдан / дата выдачи — как во вкладке Клиенты
                if client_comment_available():
                    st.text_area("Комментарий *", key="nc_comment",
                                 placeholder="Например: место работы, поручитель, откуда узнал о магазине")
                else:
                    st.caption("ℹ️ Чтобы сохранять «Комментарий» клиента, выполните в Supabase "
                               "migrations/004_client_comment.sql")
                payload, nc_errors, nc_warnings = new_client_from_state()
                for w in nc_warnings:
                    if st.session_state.get("nc_fio"):
                        st.caption(f"⚠️ {w}")
                if st.session_state.get("nc_fio") and "Заполните «Комментарий»" in nc_errors:
                    st.caption("⚠️ Заполните «Комментарий» — без него клиент не сохранится")
                dups = find_duplicates(clients_all, payload["fio"], payload["phone"]) if payload["fio"] or payload["phone"] else []
                if dups:
                    st.warning("Похожий клиент уже есть в базе (тот же телефон или ФИО):")
                    for d in dups[:5]:
                        st.button(f"✅ Оформить на существующего: {client_label(d)}", key=f"nc_use_{d['id']}",
                                  on_click=use_existing_client, args=(d["id"],), width="stretch")
                    st.checkbox("Это другой человек — создать нового клиента", key="nc_force_new")
                st.button("💾 Сохранить клиента (необязательно — сохранится и при оформлении)", key="nc_save",
                          on_click=save_new_client_cb, args=(clients_all,))
            if not nc_errors and (not dups or st.session_state.get("nc_force_new")):
                new_client_ready = payload
            sel_client_name = payload["fio"]
        else:
            if not clients_all:
                st.warning("Клиентов пока нет. Выберите «Добавить нового».")
            else:
                ids = [c["id"] for c in clients_all]
                if st.session_state.get("sale_client_select") not in ids:
                    st.session_state["sale_client_select"] = None
                client_id = st.selectbox("Выберите клиента", ids, index=None, key="sale_client_select",
                                         format_func=lambda i: client_label(clients_by_id[i]),
                                         placeholder="Начните вводить ФИО...")
                if client_id is not None:
                    sel_client_label = client_id
                    sel_client_name = clients_by_id[client_id]["fio"]
                    client_opts = {client_id: clients_by_id[client_id]}

        c_r1, c_r2, c_r3 = st.columns(3)
        down_payment = c_r1.number_input("💵 Первоначальный взнос, сом", min_value=0.0, max_value=float(total_cart_sum), value=0.0)
        months = c_r2.number_input("📅 Срок рассрочки (месяцев)", min_value=1, max_value=24, value=6)
        first_due = c_r3.date_input("📅 Дата первого платежа", value=add_month(sale_date, 1, sale_date.day),
                                    min_value=sale_date, format="DD.MM.YYYY", key="sale_first_due")
        pay_day = first_due.day

        net_debt = total_cart_sum - down_payment
        default_markup = months * 3

        st.markdown("#### 🛠️ Корректировка условий рассрочки")
        col_m1, col_m2 = st.columns(2)
        custom_markup_percent = col_m1.number_input("Процент наценки (всего за срок), %", min_value=0.0, value=float(default_markup), step=1.0)
        calculated_with_markup = net_debt + (net_debt * (custom_markup_percent / 100))
        default_monthly = round(calculated_with_markup / months) if months > 0 else 0
        monthly_payment = col_m2.number_input("Ежемесячный платёж, сом", min_value=0, value=int(default_monthly), step=10)

        total_with_markup = monthly_payment * months
        overpayment = total_with_markup - net_debt
        st.warning(f"📊 Чистый долг: {net_debt:,.0f} | Всего с наценкой: {total_with_markup:,.0f} | Переплата: {overpayment:,.0f}")

        st.markdown("#### 🗓️ График платежей")
        st.caption(f"Первый платёж {first_due.strftime('%d.%m.%Y')}, дальше каждый месяц {int(pay_day)}-го числа "
                   "(если в месяце нет такого числа — последний день месяца).")

        schedule_preview = []
        balance = float(total_with_markup)
        for i in range(1, int(months) + 1):
            due = month_schedule(first_due, int(months))[i - 1]
            if i == int(months):
                amount = round(balance, 2)
            else:
                amount = float(monthly_payment)
                balance = round(balance - amount, 2)
            schedule_preview.append({
                "№": i,
                "Дата платежа": due.strftime("%d.%m.%Y"),
                "Сумма": int(amount)
            })
        st.dataframe(pd.DataFrame(schedule_preview), width="stretch", hide_index=True)

        if client_id:
            client_row = client_opts[sel_client_label]
            contract_preview_no = datetime.now().strftime("%d%m-%H%M")
            doc_bytes = build_sale_contract(
                contract_preview_no,
                sale_date,
                client_row,
                st.session_state.cart,
                total_cart_sum,
                down_payment,
                months,
                total_with_markup,
                schedule_preview,
            )
            if doc_bytes:
                st.download_button(
                    "📄 Скачать договор Word",
                    data=doc_bytes,
                    file_name=f"Dogovor_{contract_preview_no}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    width="stretch",
                )
                st.caption("Можно скачать до оформления и проверить. После проведения кнопка останется сверху.")

    if pay_method == "Рассрочка":
        if client_id:
            c = client_opts.get(client_id, {})
            st.info(f"👤 Рассрочка будет оформлена на: **{c.get('fio')}**, 📞 {c.get('phone') or 'без телефона'}")
        elif new_client_ready:
            st.info(f"👤 Рассрочка будет оформлена на **нового клиента: {new_client_ready['fio']}**, "
                    f"📞 {new_client_ready['phone'] or 'без телефона'} — клиент сохранится вместе со сделкой")
        else:
            st.warning("👤 Клиент не выбран — оформить рассрочку пока нельзя.")

    if st.button("🚀 Оформить и провести сделку", type="primary", width="stretch"):
        if pay_method == "Рассрочка" and not client_id:
            if st.session_state.get("client_mode") == MODE_NEW:
                if not new_client_ready:
                    st.error("❌ Заполните ФИО и «Комментарий» нового клиента (и решите вопрос с похожим клиентом выше).")
                    return
                try:
                    res = supabase.table("clients").insert(new_client_ready).execute()
                    client_id = res.data[0]["id"]
                    st.session_state["_pending_client_select"] = client_id  # даже если дальше ошибка — дубля не будет
                except Exception as e:
                    st.error(f"❌ Не удалось сохранить нового клиента, сделка не проведена: {e}")
                    return
                sel_client_name = new_client_ready["fio"]
                client_opts = {client_id: {**new_client_ready, "id": client_id}}
                sel_client_label = client_id
            else:
                st.error("❌ Выберите клиента для рассрочки!")
                return

        base_group_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
        day_str = sale_date.strftime("%Y-%m-%d")
        formatted_date_full = f"{sale_date.strftime('%d.%m.%Y')} {datetime.now().strftime('%H:%M')}"
        contract_num_suffix = datetime.now().strftime("%d%m-%H%M%S")

        try:
            total_cost_sum = 0.0
            items_list_str = []
            for item in st.session_state.cart:
                p_res = supabase.table("products").select("qty").eq("id", item["batch_id"]).execute().data[0]
                new_qty = int(p_res["qty"]) - item["qty"]
                if new_qty < 0:
                    st.error(f"Не хватает товара: {item['name']}")
                    return
                supabase.table("products").update({"qty": new_qty}).eq("id", item["batch_id"]).execute()
                total_cost_sum += (item["qty"] * item["cost"])
                items_list_str.append(f"{item['name']} ({item['qty']} шт.)")

            goods_summary = ", ".join(items_list_str)

            if pay_method == "Наличные":
                for idx, item in enumerate(st.session_state.cart):
                    t_cost = item["qty"] * item["cost"]
                    unique_sale_id = f"{base_group_id}_{idx}"
                    try:
                        b_date_formatted = datetime.strptime(str(item["batch_date"])[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
                    except Exception:
                        b_date_formatted = item["batch_date"]

                    supabase.table("sales").insert({
                        "id": unique_sale_id,
                        "date": formatted_date_full,
                        "day": day_str,
                        "name": f"{item['name']} (приход {b_date_formatted})",
                        "pure_name": item["pure_name"],
                        "batch_date": item["batch_date"],
                        "qty": item["qty"],
                        "total_sale": int(item["total"]),
                        "total_cost": int(t_cost),
                        "profit": int(item["total"] - t_cost),
                        "payment": "Наличные",
                        "down_payment": 0,
                        "credit_balance": 0,
                        "client_id": None
                    }).execute()
            else:
                contract_name = f"Договор рассрочки №{contract_num_suffix[:9]} [{goods_summary}] — {sel_client_name}"
                supabase.table("sales").insert({
                    "id": base_group_id,
                    "date": formatted_date_full,
                    "day": day_str,
                    "name": contract_name,
                    "pure_name": "рассрочка",
                    "batch_date": day_str,
                    "qty": 1,
                    "total_sale": int(total_cart_sum),
                    "total_cost": int(total_cost_sum),
                    "profit": int(total_cart_sum - total_cost_sum),
                    "payment": "Рассрочка",
                    "down_payment": int(down_payment),
                    "credit_balance": int(total_with_markup),
                    "client_id": client_id
                }).execute()

                if down_payment > 0:
                    supabase.table("cash_operations").insert({
                        "date": formatted_date_full,
                        "amount": float(down_payment),
                        "comment": f"Перв. взнос по рассрочке №{contract_num_suffix[:9]} от {sel_client_name}"
                    }).execute()

                balance = float(total_with_markup)
                for i in range(1, int(months) + 1):
                    due = month_schedule(first_due, int(months))[i - 1]
                    if i == int(months):
                        amount = round(balance, 2)
                    else:
                        amount = float(monthly_payment)
                        balance = round(balance - amount, 2)

                    supabase.table("credit_payments").insert({
                        "sale_id": base_group_id,
                        "client_id": client_id,
                        "due_date": due.strftime("%Y-%m-%d"),
                        "amount_expected": int(amount),
                        "amount_paid": 0,
                        "status": "Не оплачен"
                    }).execute()

            if pay_method == "Рассрочка":
                saved_client = client_opts.get(sel_client_label, {"fio": sel_client_name})
                st.session_state["last_obligation_sale_id"] = base_group_id
                st.session_state["_pending_client_select"] = client_id
                st.session_state["last_contract"] = {
                    "name": f"Dogovor_{contract_num_suffix[:9]}.docx",
                    "bytes": build_sale_contract(
                        contract_num_suffix[:9],
                        sale_date,
                        saved_client,
                        list(st.session_state.cart),
                        total_cart_sum,
                        down_payment,
                        months,
                        total_with_markup,
                        schedule_preview,
                    ),
                }
            st.session_state.cart = []
            st.success("🎉 Сделка успешно проведена!")
            st.rerun()
        except Exception as e:
            st.error(f"Ошибка базы данных: {e}")
