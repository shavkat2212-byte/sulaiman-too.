# Магазин «Сулайман-Тоо» — Модуль: Выписка клиента (для скриншота в WhatsApp)
# Версия: 1.0
# Только чтение из базы: clients, sales (Рассрочка), credit_payments.
# Долг считается так же, как во вкладке «Клиенты → Рассрочки»:
# остаток = credit_balance договора − сумма amount_paid по его графику.

import base64
import html
import re
from datetime import datetime
from urllib.parse import quote

import streamlit as st
import streamlit.components.v1 as components
from database import supabase
from clients import parse_due
from utils import fix_contract_name_on_fly

SHOP_NAME = "Магазин «Сулайман-Тоо»"
STATEMENT_MENU = "📱 Выписка клиента"
STATE_MARKS = {"paid": "✅", "partial": "🟡", "wait": "⚪", "overdue": "🔴"}


def money(value):
    return f"{int(float(value or 0)):,}".replace(",", " ") + " сом"


def num(value):
    return float(value or 0)


def open_statement(client_id):
    """Колбэк кнопки из других разделов: открыть выписку нужного клиента."""
    st.session_state["menu_choice"] = STATEMENT_MENU
    # Сбрасываем состояние меню: оно пересоздастся с выбранным пунктом «Выписка клиента».
    st.session_state.pop("menu_radio", None)
    st.session_state["statement_client_id"] = client_id


def close_statement():
    st.session_state["statement_client_id"] = None


def parse_goods(sale):
    """Достаёт список товаров из названия договора «... [Товар (2 шт.), ...] — ФИО»."""
    name = fix_contract_name_on_fly(str(sale.get("name") or ""), sale.get("date") or "")
    match = re.search(r"\[(.*)\]", name)
    if not match:
        return [name or "Товар"]
    goods = [g.strip() for g in re.split(r",\s*(?![^()]*\))", match.group(1)) if g.strip()]
    return goods or [name]


def sale_day(sale):
    return parse_due(sale.get("day") or sale.get("date"))


def build_statement(client_id, sales, payments, today):
    """Считает всё для выписки. sales — договоры «Рассрочка» этого клиента."""
    contracts = []
    for sale in sales:
        if sale.get("client_id") != client_id:
            continue
        sale_pays = [p for p in payments if p.get("sale_id") == sale.get("id")]
        paid = sum(num(p.get("amount_paid")) for p in sale_pays)
        balance = num(sale.get("credit_balance"))
        schedule = []
        for p in sorted(sale_pays, key=lambda x: parse_due(x.get("due_date")) or today):
            due = parse_due(p.get("due_date"))
            expected = num(p.get("amount_expected"))
            got = num(p.get("amount_paid"))
            left = expected - got
            if left <= 0.5:
                state = "paid"
            elif due and due < today:
                state = "overdue"
            elif got > 0:
                state = "partial"
            else:
                state = "wait"
            mark = STATE_MARKS[state]
            schedule.append({
                "due": due,
                "due_raw": p.get("due_date"),
                "expected": expected,
                "paid": got,
                "left": left,
                "mark": mark,
                "state": state,
            })
        contracts.append({
            "sale": sale,
            "day": sale_day(sale),
            "goods": parse_goods(sale),
            "total_sale": num(sale.get("total_sale")),
            "down": num(sale.get("down_payment")),
            "balance": balance,
            "paid": paid,
            "debt": balance - paid,
            "schedule": schedule,
        })

    contracts.sort(key=lambda c: c["day"] or datetime.min.date())
    unpaid = [r for c in contracts for r in c["schedule"] if r["left"] > 0.5]
    unpaid.sort(key=lambda r: r["due"] or today)
    overdue = sum(r["left"] for r in unpaid if r["due"] and r["due"] < today)
    return {
        "contracts": contracts,
        "taken": sum(c["balance"] for c in contracts),
        "paid": sum(c["paid"] for c in contracts),
        "debt": sum(c["debt"] for c in contracts),
        "overdue": overdue,
        "next": unpaid[0] if unpaid else None,
    }


def whatsapp_phone(phone):
    digits = re.sub(r"\D", "", str(phone or ""))
    if not digits:
        return ""
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 10 and digits.startswith("0"):
        digits = "996" + digits[1:]
    elif len(digits) == 9:
        digits = "996" + digits
    return digits if len(digits) >= 11 else ""


def whatsapp_text(client, data, today):
    lines = [
        f"Здравствуйте, {client.get('fio', '')}!",
        f"{SHOP_NAME}, выписка на {today.strftime('%d.%m.%Y')}.",
        f"Остаток по рассрочке: {money(max(data['debt'], 0))}.",
    ]
    if data["overdue"] > 0.5:
        lines.append(f"Просрочено: {money(data['overdue'])}.")
    nxt = data["next"]
    if nxt and data["debt"] > 0.5:
        due_txt = nxt["due"].strftime("%d.%m.%Y") if nxt["due"] else str(nxt["due_raw"])
        lines.append(f"Ближайший платёж: {due_txt} — {money(nxt['left'])}.")
    return "\n".join(lines)


STATEMENT_CSS = """
<style>
[data-testid="stToolbarActions"], [data-testid="stMainMenu"], [data-testid="stAppDeployButton"],
[data-testid="stDecoration"], [data-testid="stStatusWidget"], footer {
    display: none !important;
}
.block-container { padding-top: 2.6rem !important; padding-bottom: 1rem !important; }
.sl-card { max-width: 480px; margin: 0 auto; background: #ffffff; color: #1f2933;
    border: 1px solid #e3e6ea; border-radius: 14px; padding: 14px 14px 10px 14px;
    font-size: 14px; line-height: 1.35; font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }
.sl-card .shop { font-weight: 700; font-size: 16px; text-align: center; }
.sl-card .sub { color: #6b7480; font-size: 12px; text-align: center; margin-bottom: 8px; }
.sl-card .client { font-weight: 700; font-size: 17px; }
.sl-card .phone { color: #52606d; font-size: 13px; }
.sl-card .debt { margin: 10px 0 8px 0; padding: 10px; border-radius: 12px; text-align: center; }
.sl-card .debt.red { background: #fdecec; color: #b42318; }
.sl-card .debt.green { background: #e8f6ee; color: #1a7f45; }
.sl-card .debt .lbl { font-size: 13px; font-weight: 600; }
.sl-card .debt .val { font-size: 32px; font-weight: 800; line-height: 1.15; }
.sl-card .debt .note { font-size: 12px; margin-top: 2px; }
.sl-card .totals { display: flex; gap: 6px; margin-bottom: 8px; }
.sl-card .totals div { flex: 1; background: #f4f6f8; border-radius: 10px; padding: 6px; text-align: center; }
.sl-card .totals .t { font-size: 11px; color: #6b7480; }
.sl-card .totals .v { font-size: 14px; font-weight: 700; }
.sl-card .contract { border-top: 1px dashed #cfd5dc; padding-top: 8px; margin-top: 8px; }
.sl-card .c-head { font-weight: 700; font-size: 13px; }
.sl-card .goods { margin: 2px 0 4px 16px; padding: 0; font-size: 13px; }
.sl-card .c-sum { font-size: 12px; color: #3e4c59; margin-bottom: 4px; }
.sl-card table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.sl-card th { text-align: left; color: #6b7480; font-weight: 600; border-bottom: 1px solid #e3e6ea; padding: 2px 3px; }
.sl-card td { padding: 2px 3px; border-bottom: 1px solid #f0f2f4; }
.sl-card td.n, .sl-card th.n { text-align: right; white-space: nowrap; }
.sl-card .legend { color: #6b7480; font-size: 11px; margin-top: 8px; text-align: center; }
.sl-card .c-left { font-size: 12.5px; font-weight: 700; text-align: right; margin-top: 3px; }
</style>
"""


def render_card(client, data, today, show_closed):
    e = html.escape
    debt = data["debt"]
    st.markdown(STATEMENT_CSS, unsafe_allow_html=True)
    parts = ['<div class="sl-card">']
    parts.append(f'<div class="shop">🛍️ {e(SHOP_NAME)}</div>')
    parts.append(f'<div class="sub">Выписка по рассрочке на {today.strftime("%d.%m.%Y")}</div>')
    parts.append(f'<div class="client">{e(str(client.get("fio") or "Клиент"))}</div>')
    if client.get("phone"):
        parts.append(f'<div class="phone">📞 {e(str(client.get("phone")))}</div>')

    if debt > 0.5:
        note = ""
        if data["overdue"] > 0.5:
            note = f'<div class="note">из них просрочено: {money(data["overdue"])}</div>'
        elif data["next"]:
            nxt = data["next"]
            due_txt = nxt["due"].strftime("%d.%m.%Y") if nxt["due"] else e(str(nxt["due_raw"]))
            note = f'<div class="note">ближайший платёж: {due_txt} — {money(nxt["left"])}</div>'
        parts.append(
            f'<div class="debt red"><div class="lbl">ТЕКУЩИЙ ДОЛГ</div>'
            f'<div class="val">{money(debt)}</div>{note}</div>'
        )
    else:
        parts.append('<div class="debt green"><div class="lbl">ТЕКУЩИЙ ДОЛГ</div>'
                     '<div class="val">0 сом</div><div class="note">Долга нет, спасибо! ✅</div></div>')

    parts.append(
        '<div class="totals">'
        f'<div><div class="t">Взято в рассрочку</div><div class="v">{money(data["taken"])}</div></div>'
        f'<div><div class="t">Оплачено</div><div class="v">{money(data["paid"])}</div></div>'
        f'<div><div class="t">Остаток</div><div class="v">{money(max(debt, 0))}</div></div>'
        '</div>'
    )

    shown = [c for c in data["contracts"] if show_closed or c["debt"] > 0.5]
    hidden = len(data["contracts"]) - len(shown)
    for c in shown:
        day_txt = c["day"].strftime("%d.%m.%Y") if c["day"] else "—"
        closed = " (закрыт ✅)" if c["debt"] <= 0.5 else ""
        parts.append('<div class="contract">')
        parts.append(f'<div class="c-head">🧾 Покупка от {day_txt}{closed}</div>')
        parts.append('<ul class="goods">' + "".join(f"<li>{e(g)}</li>" for g in c["goods"]) + "</ul>")
        sum_line = f'Сумма покупки: {money(c["total_sale"])}'
        if c["down"] > 0.5:
            sum_line += f' · взнос: {money(c["down"])}'
        sum_line += f' · в рассрочку: {money(c["balance"])}'
        parts.append(f'<div class="c-sum">{sum_line}</div>')
        if c["schedule"]:
            parts.append('<table><tr><th>Дата</th><th class="n">Надо</th><th class="n">Оплачено</th><th></th></tr>')
            for r in c["schedule"]:
                due_txt = r["due"].strftime("%d.%m.%Y") if r["due"] else e(str(r["due_raw"] or "—"))
                parts.append(
                    f'<tr><td>{due_txt}</td><td class="n">{money(r["expected"])}</td>'
                    f'<td class="n">{money(r["paid"])}</td><td>{r["mark"]}</td></tr>'
                )
            parts.append("</table>")
        parts.append(f'<div class="c-left">Оплачено {money(c["paid"])} · остаток {money(max(c["debt"], 0))}</div>')
        parts.append("</div>")

    if hidden and shown:
        parts.append(f'<div class="legend">Ещё закрытых договоров: {hidden} (учтены в итогах выше)</div>')
    if not data["contracts"]:
        parts.append('<div class="contract">Покупок в рассрочку нет.</div>')
    elif hidden and not shown:
        parts.append(f'<div class="contract">Все договоры закрыты ({hidden}).</div>')

    parts.append('<div class="legend">✅ оплачено · 🟡 частично · ⚪ ожидается · 🔴 просрочено</div>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


SHARE_HTML = """
<div style="font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;">
  <button id="share-btn" style="width:100%;padding:10px 12px;border:none;border-radius:8px;
      background:#ff4b4b;color:#fff;font-size:16px;font-weight:600;cursor:pointer;">
    📤 Поделиться картинкой
  </button>
  <div id="share-msg" style="color:#6b7480;font-size:13px;margin-top:6px;text-align:center;"></div>
</div>
<script>
const PNG_B64 = "__PNG__";
const FILE_NAME = "__NAME__";
const btn = document.getElementById("share-btn");
const msg = document.getElementById("share-msg");
const FALLBACK = "Здесь поделиться не получится. Нажмите «Скачать картинку» ниже.";

function makeFile() {
  const bin = atob(PNG_B64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new File([bytes], FILE_NAME, {type: "image/png"});
}

function navigators() {
  const list = [navigator];
  try { if (window.parent && window.parent !== window && window.parent.navigator) list.push(window.parent.navigator); } catch (e) {}
  return list;
}

function canShareFile(nav, file) {
  try { return !!(nav.share && nav.canShare && nav.canShare({files: [file]})); } catch (e) { return false; }
}

const probe = makeFile();
if (!navigators().some(n => canShareFile(n, probe))) {
  btn.disabled = true;
  btn.style.opacity = "0.5";
  msg.textContent = FALLBACK;
}

btn.addEventListener("click", async () => {
  const file = makeFile();
  for (const nav of navigators()) {
    if (!canShareFile(nav, file)) continue;
    try {
      await nav.share({files: [file], title: "Выписка клиента"});
      msg.textContent = "";
      return;
    } catch (e) {
      if (e && e.name === "AbortError") return;
    }
  }
  msg.textContent = FALLBACK;
});
</script>
"""


def show_image_buttons(client, data, today, show_closed, cid):
    try:
        from statement_image import render_statement_png
        png = render_statement_png(SHOP_NAME, client, data, today, show_closed)
    except Exception as e:
        st.warning(f"Картинку сделать не получилось: {e}")
        return
    file_name = f"vypiska_{cid}_{today.strftime('%Y-%m-%d')}.png"
    file_name = re.sub(r"[^A-Za-z0-9_.-]", "_", file_name)
    share_html = SHARE_HTML.replace("__PNG__", base64.b64encode(png).decode("ascii")).replace("__NAME__", file_name)
    if hasattr(st, "iframe"):
        st.iframe(share_html, height=100)
    else:
        components.html(share_html, height=100)
    st.download_button(
        "⬇️ Скачать картинку",
        data=png,
        file_name=file_name,
        mime="image/png",
        use_container_width=True,
        key="statement_png_download",
    )
    with st.expander("🖼️ Показать картинку"):
        st.caption("На телефоне можно нажать на картинку и удерживать, чтобы сохранить или отправить.")
        st.image(png, use_container_width=True)


def show_statement_page():
    try:
        clients = supabase.table("clients").select("*").order("fio").execute().data or []
    except Exception as e:
        st.error(f"Ошибка загрузки: {e}")
        return

    clients_map = {c["id"]: c for c in clients}
    today = datetime.now().date()
    cid = st.session_state.get("statement_client_id")

    if cid and cid in clients_map:
        try:
            sales = (
                supabase.table("sales").select("*")
                .eq("payment", "Рассрочка").eq("client_id", cid)
                .execute().data or []
            )
            sale_ids = [s["id"] for s in sales if s.get("id") is not None]
            payments = []
            if sale_ids:
                payments = supabase.table("credit_payments").select("*").in_("sale_id", sale_ids).execute().data or []
        except Exception as e:
            st.error(f"Ошибка загрузки: {e}")
            return

        client = clients_map[cid]
        data = build_statement(cid, sales, payments, today)
        show_closed = st.session_state.get("statement_show_closed", False)
        render_card(client, data, today, show_closed)

        st.caption("Сделайте скриншот экрана или отправьте выписку картинкой.")
        show_image_buttons(client, data, today, show_closed, cid)
        wa = whatsapp_phone(client.get("phone"))
        if wa:
            url = f"https://wa.me/{wa}?text={quote(whatsapp_text(client, data, today))}"
            st.link_button("💬 Открыть WhatsApp клиента", url, use_container_width=True)
        st.checkbox("Показывать закрытые договоры", key="statement_show_closed")
        st.button("⬅️ Выбрать другого клиента", on_click=close_statement, use_container_width=True)
        return

    st.title(STATEMENT_MENU)
    st.caption("Выберите клиента и нажмите «Показать выписку». На экране будет долг, покупки и график — сделайте скриншот и отправьте в WhatsApp.")
    if not clients:
        st.info("Клиентов пока нет.")
        return

    search = st.text_input("Поиск по фамилии или телефону", key="statement_search")
    found = clients
    if search:
        q = search.strip().lower()
        found = [c for c in clients if q in str(c.get("fio") or "").lower() or q in str(c.get("phone") or "")]
    if not found:
        st.warning("Клиент не найден.")
        return

    opts = {f"{c.get('fio') or 'Без имени'} ({c.get('phone') or 'без телефона'})": c["id"] for c in found}
    label = st.selectbox("Клиент", list(opts.keys()), key="statement_pick")
    st.button(
        "📱 Показать выписку",
        type="primary",
        use_container_width=True,
        on_click=open_statement,
        args=(opts[label],),
    )
