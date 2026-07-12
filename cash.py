# Магазин «Сулайман-Тоо» — Модуль: Касса
# Версия: 2.2 (даты теперь в формате как в твоей базе Supabase)

import streamlit as st
import pandas as pd
import io
from datetime import datetime, timedelta
from database import supabase

def show_cash_page():
    st.header("💵 Состояние кассы магазина")
    
    user_role = st.session_state.get("user", {}).get("role", "Кассир")

    try:
        sales_res = supabase.table("sales").select("*").execute()
        ops_res = supabase.table("cash_operations").select("*").order("date", desc=True).execute()
    except Exception as e:
        st.error(f"Ошибка подключения к базе: {e}")
        return

    sales_data = sales_res.data if sales_res.data else []
    ops_data = ops_res.data if ops_res.data else []

    # ==================== ОСНОВНЫЕ МЕТРИКИ ====================
    full_cash_sales = sum(float(s["total_sale"]) for s in sales_data if s.get("payment") == "Наличные")
    manual_cash_flow = sum(float(op.get('amount', 0)) for op in ops_data)
    current_cash_in_hand = full_cash_sales + manual_cash_flow

    c1, c2, c3 = st.columns(3)
    c1.metric("💵 Наличные в кассе", f"{current_cash_in_hand:,.2f} сом")
    c2.metric("📝 Долг клиентов по рассрочкам", 
              f"{sum(float(s.get('credit_balance', 0)) for s in sales_data if s.get('payment') == 'Рассрочка'):,} сом")
    c3.metric("📈 Чистая прибыль (всего)", 
              f"{sum(float(s.get('profit', 0)) for s in sales_data):,.2f} сом")

    st.markdown("---")
    st.subheader("📜 История кассовых операций + Итоги")

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        start_date = st.date_input("Начало периода", value=datetime.now().date() - timedelta(days=30))
    with col_f2:
        end_date = st.date_input("Конец периода", value=datetime.now().date())

    df_ops = pd.DataFrame(ops_data) if ops_data else pd.DataFrame()
    df_sales = pd.DataFrame(sales_data) if sales_data else pd.DataFrame()

    # ==================== ПРАВИЛЬНЫЙ ПАРСИНГ ДАТ (под твой формат в базе) ====================
    filtered_ops = pd.DataFrame()
    if not df_ops.empty:
        try:
            # Берём первые 16 символов (YYYY-MM-DD HH:MM) и явно указываем формат
            df_ops['date_obj'] = pd.to_datetime(
                df_ops['date'].astype(str).str[:16], 
                format='%Y-%m-%d %H:%M', 
                errors='coerce'
            ).dt.date
            
            valid_dates = df_ops['date_obj'].notna()
            filtered_ops = df_ops[valid_dates & 
                                  (df_ops['date_obj'] >= start_date) & 
                                  (df_ops['date_obj'] <= end_date)].copy()
        except Exception as e:
            st.warning(f"Ошибка при обработке дат: {e}")
            filtered_ops = df_ops

    # Расчёт наличных продаж за период
    cash_sales_period = 0
    if not df_sales.empty:
        try:
            df_sales['day_obj'] = pd.to_datetime(
                df_sales['day'].astype(str).str[:10], 
                format='%Y-%m-%d', 
                errors='coerce'
            ).dt.date
            filtered_sales = df_sales[(df_sales['day_obj'] >= start_date) & 
                                      (df_sales['day_obj'] <= end_date)]
            cash_sales_period = filtered_sales[filtered_sales['payment'] == 'Наличные']['total_sale'].sum()
        except:
            cash_sales_period = 0

    total_in_ops = filtered_ops[filtered_ops['amount'] > 0]['amount'].sum() if not filtered_ops.empty else 0
    total_out = abs(filtered_ops[filtered_ops['amount'] < 0]['amount'].sum()) if not filtered_ops.empty else 0
    total_in = cash_sales_period + total_in_ops
    net = total_in - total_out

    # ==================== ТАБЛИЦА + ЭКСПОРТ ====================
    if not filtered_ops.empty:
        col_exp1, col_exp2 = st.columns([5, 2])
        with col_exp2:
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                filtered_ops[["id", "date", "amount", "comment", "created_at"]].to_excel(
                    writer, index=False, sheet_name="Касса"
                )
            excel_buffer.seek(0)
            st.download_button(
                label="📥 Экспорт в Excel",
                data=excel_buffer,
                file_name=f"Касса_{start_date}_{end_date}.xlsx",
                use_container_width=True
            )

        display_df = filtered_ops[["id", "date", "amount", "comment", "created_at"]].copy()
        display_df["amount"] = display_df["amount"].map('{:,.0f}'.format)
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("Операций за выбранный период нет.")

    # ==================== УДАЛЕНИЕ ОПЕРАЦИИ ====================
    if user_role == "Администратор" and not filtered_ops.empty:
        st.markdown("---")
        st.subheader("🗑️ Удалить операцию из истории (только для Администратора)")

        with st.form("delete_form"):
            options = {
                f"{row['id']} | {row['date']} | {int(row['amount']):,} сом | {row.get('comment', '')}": row['id']
                for _, row in filtered_ops.iterrows()
            }
            selected_label = st.selectbox("Выберите операцию для удаления", list(options.keys()))
            selected_id = options[selected_label]

            confirm = st.checkbox("Я подтверждаю удаление этой операции")
            
            if st.form_submit_button("🗑️ Удалить операцию", type="primary"):
                if confirm:
                    try:
                        supabase.table("cash_operations").delete().eq("id", selected_id).execute()
                        st.success("✅ Операция успешно удалена!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Ошибка при удалении: {e}")
                else:
                    st.warning("Поставьте галочку подтверждения перед удалением.")

    # ==================== НОВАЯ ОПЕРАЦИЯ ====================
    st.markdown("---")
    st.subheader("📤 Новая операция (только расходы / изъятия из кассы)")

    with st.form("cash_op_form", clear_on_submit=True):
        op_type = st.selectbox("Тип расхода", [
            "Взять деньги (Инкассация / Личные нужды)",
            "Выплата за товар (Поставщику)"
        ])
        amount = st.number_input("Сумма, сом", min_value=1.0, value=1000.0, step=100.0)
        comment = st.text_input("Комментарий / Причина", value=op_type)

        if st.form_submit_button("Списать из кассы", type="primary"):
            # Теперь дата в том же формате, что и у тебя в базе
            supabase.table("cash_operations").insert({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "amount": -amount,
                "comment": comment or op_type
            }).execute()
            st.success("✅ Расход успешно зафиксирован!")
            st.rerun()
