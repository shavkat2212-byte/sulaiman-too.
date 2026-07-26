    # ==================== ИСТОРИЯ ОПЕРАЦИЙ ====================
    st.markdown("---")
    st.subheader("📜 История кассовых операций")

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        start_date = st.date_input("Начало периода", value=datetime.now().date() - timedelta(days=30))
    with col_f2:
        end_date = st.date_input("Конец периода", value=datetime.now().date())
    with col_f3:
        filter_cat = st.selectbox("Фильтр по типу", ["Все", "Нужды магазина", "Оплата контрагенту", "Без категории"])

    df_ops = pd.DataFrame(ops_data) if ops_data else pd.DataFrame()
    if not df_ops.empty:
        try:
            df_ops['date_norm'] = df_ops['date'].apply(normalize_date)
            df_ops['date_obj'] = pd.to_datetime(df_ops['date_norm'], errors='coerce').dt.date
            df_ops['category'] = df_ops['comment'].apply(get_category_from_comment)
            filtered_ops = df_ops[(df_ops['date_obj'] >= start_date) & (df_ops['date_obj'] <= end_date)].copy()
            
            if filter_cat != "Все":
                filtered_ops = filtered_ops[filtered_ops['category'] == filter_cat]
        except:
            filtered_ops = df_ops
    else:
        filtered_ops = pd.DataFrame()

    if not filtered_ops.empty:
        display_df = filtered_ops[["id", "date", "amount", "category", "comment"]].copy()
        display_df["amount"] = display_df["amount"].map('{:,.0f}'.format)
        display_df = display_df.rename(columns={
            "id": "ID",
            "date": "Дата",
            "amount": "Сумма",
            "category": "Тип",
            "comment": "Комментарий"
        })
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        # ===== ИТОГИ =====
        total_sum = filtered_ops["amount"].sum()
        count_ops = len(filtered_ops)
        
        # Разбивка по категориям внутри текущего фильтра
        needs_sum = filtered_ops[filtered_ops["category"] == "Нужды магазина"]["amount"].sum()
        supplier_sum = filtered_ops[filtered_ops["category"] == "Оплата контрагенту"]["amount"].sum()
        other_sum = filtered_ops[filtered_ops["category"] == "Без категории"]["amount"].sum()

        st.markdown("---")
        st.markdown("### 📊 Итоги по выбранному периоду и фильтру")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Всего операций", f"{count_ops}")
        c2.metric("Общая сумма", f"{total_sum:,.0f} сом")
        c3.metric("Нужды магазина", f"{needs_sum:,.0f} сом")
        c4.metric("Оплата контрагенту", f"{supplier_sum:,.0f} сом")

        if other_sum != 0:
            st.caption(f"Без категории: {other_sum:,.0f} сом")

    else:
        st.info("Операций за выбранный период нет.")
