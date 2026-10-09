# Магазин «Сулайман-Тоо» — Модуль: Выписка клиента картинкой (PNG)
# Версия: 1.1 — клиентам в рассрочке не показываем сумму покупки
# Рисует ту же выписку, что и на экране, в PNG через Pillow.
# Шрифт DejaVu Sans лежит в папке fonts/ (лицензия: fonts/DejaVu-LICENSE.txt),
# чтобы кириллица работала на любом сервере.

import io
import os

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
FONT_REGULAR = os.path.join(FONT_DIR, "DejaVuSans.ttf")
FONT_BOLD = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")

SCALE = 2          # рисуем в 2 раза крупнее: 540 «точек» = 1080 пикселей
BASE_W = 540
PAD = 16

WHITE = (255, 255, 255)
TEXT = (31, 41, 51)
GREY = (107, 116, 128)
DARK_GREY = (62, 76, 89)
LINE = (227, 230, 234)
LIGHT_LINE = (240, 242, 244)
BOX = (244, 246, 248)
RED = (180, 35, 24)
RED_BG = (253, 236, 236)
GREEN = (26, 127, 69)
GREEN_BG = (232, 246, 238)

STATE_COLORS = {
    "paid": (34, 160, 90),
    "partial": (245, 179, 1),
    "wait": (196, 202, 209),
    "overdue": (217, 45, 32),
}
STATE_LABELS = [
    ("paid", "оплачено"),
    ("partial", "частично"),
    ("wait", "ожидается"),
    ("overdue", "просрочено"),
]

_FONTS = {}


def font(size, bold=False):
    key = (size, bold)
    if key not in _FONTS:
        path = FONT_BOLD if bold else FONT_REGULAR
        try:
            _FONTS[key] = ImageFont.truetype(path, int(round(size * SCALE)))
        except Exception:
            _FONTS[key] = ImageFont.load_default(int(round(size * SCALE)))
    return _FONTS[key]


def money(value):
    return f"{int(float(value or 0)):,}".replace(",", " ") + " сом"


def date_txt(day, raw=None):
    if day:
        return day.strftime("%d.%m.%Y")
    return str(raw or "—")


class Painter:
    """Рисует сверху вниз. В режиме dry только считает высоту."""

    def __init__(self, draw=None):
        self.d = draw
        self.y = PAD

    def s(self, v):
        return int(round(v * SCALE))

    def text_w(self, text, f):
        return f.getlength(text) / SCALE

    def text(self, x, y, text, f, fill=TEXT, anchor="la"):
        if self.d:
            self.d.text((self.s(x), self.s(y)), text, font=f, fill=fill, anchor=anchor)

    def rect(self, x0, y0, x1, y1, fill=None, outline=None, radius=10, width=1):
        if self.d:
            self.d.rounded_rectangle(
                (self.s(x0), self.s(y0), self.s(x1), self.s(y1)),
                radius=self.s(radius), fill=fill, outline=outline, width=self.s(width),
            )

    def line(self, x0, y0, x1, y1, fill=LINE, width=1, dashed=False):
        if not self.d:
            return
        if not dashed:
            self.d.line((self.s(x0), self.s(y0), self.s(x1), self.s(y1)), fill=fill, width=self.s(width))
            return
        x = x0
        while x < x1:
            self.d.line((self.s(x), self.s(y0), self.s(min(x + 4, x1)), self.s(y1)), fill=fill, width=self.s(width))
            x += 7

    def dot(self, cx, cy, r, state):
        if not self.d:
            return
        color = STATE_COLORS.get(state, STATE_COLORS["wait"])
        box = (self.s(cx - r), self.s(cy - r), self.s(cx + r), self.s(cy + r))
        self.d.ellipse(box, fill=color)
        if state == "paid":
            # галочка внутри зелёного круга
            pts = [(cx - r * 0.45, cy + r * 0.02), (cx - r * 0.1, cy + r * 0.38), (cx + r * 0.5, cy - r * 0.35)]
            self.d.line([(self.s(px), self.s(py)) for px, py in pts], fill=WHITE, width=max(2, self.s(r * 0.28)), joint="curve")

    def wrap(self, text, f, max_w):
        words = str(text).split()
        lines, cur = [], ""
        for w in words:
            test = f"{cur} {w}".strip()
            if self.text_w(test, f) <= max_w or not cur:
                cur = test
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        # очень длинное слово режем по символам
        out = []
        for ln in lines or [""]:
            while self.text_w(ln, f) > max_w and len(ln) > 1:
                cut = len(ln)
                while cut > 1 and self.text_w(ln[:cut], f) > max_w:
                    cut -= 1
                out.append(ln[:cut])
                ln = ln[cut:]
            out.append(ln)
        return out

    def para(self, x, text, f, max_w, fill=TEXT, line_h=None, align="left"):
        line_h = line_h or (f.size / SCALE) * 1.35
        for ln in self.wrap(text, f, max_w):
            if align == "center":
                self.text(x + max_w / 2, self.y, ln, f, fill, anchor="ma")
            elif align == "right":
                self.text(x + max_w, self.y, ln, f, fill, anchor="ra")
            else:
                self.text(x, self.y, ln, f, fill)
            self.y += line_h


def contract_sum_line(c):
    """Строка с суммами договора. Клиенту в рассрочке сумму покупки не показываем."""
    if c.get("installment"):
        line = f"Сумма рассрочки: {money(c['final'])}"
        if c["down"] > 0.5:
            line += f" · взнос: {money(c['down'])}"
        return line
    line = f"Сумма покупки: {money(c['total_sale'])}"
    if c["down"] > 0.5:
        line += f" · взнос: {money(c['down'])}"
    line += f" · в рассрочку: {money(c['balance'])}"
    return line


def paint(p, shop_name, client, data, today, show_closed):
    left = PAD
    right = BASE_W - PAD
    width = right - left
    debt = data["debt"]

    p.para(left, shop_name, font(19, True), width, align="center")
    p.y += 1
    p.para(left, f"Выписка по рассрочке на {today.strftime('%d.%m.%Y')}", font(12), width, GREY, align="center")
    p.y += 8
    p.para(left, str(client.get("fio") or "Клиент"), font(19, True), width)
    if client.get("phone"):
        p.para(left, f"Тел.: {client.get('phone')}", font(13), width, DARK_GREY)
    p.y += 8

    # Крупный блок «Текущий долг»
    top = p.y
    has_debt = debt > 0.5
    bg, fg = (RED_BG, RED) if has_debt else (GREEN_BG, GREEN)
    note = ""
    if has_debt and data["overdue"] > 0.5:
        note = f"из них просрочено: {money(data['overdue'])}"
    elif has_debt and data["next"]:
        nxt = data["next"]
        note = f"ближайший платёж: {date_txt(nxt['due'], nxt['due_raw'])} — {money(nxt['left'])}"
    elif not has_debt:
        note = "Долга нет, спасибо!"
    box_h = 12 + 18 + 46 + (20 if note else 0) + 8
    p.rect(left, top, right, top + box_h, fill=bg, radius=12)
    p.text(BASE_W / 2, top + 12, "ТЕКУЩИЙ ДОЛГ", font(14, True), fg, anchor="ma")
    p.text(BASE_W / 2, top + 32, money(max(debt, 0)), font(38, True), fg, anchor="ma")
    if note:
        p.text(BASE_W / 2, top + 80, note, font(12), fg, anchor="ma")
    p.y = top + box_h + 8

    # Три итога
    gap = 6
    col_w = (width - gap * 2) / 3
    totals = [
        ("Взято в рассрочку", money(data["taken"])),
        ("Оплачено", money(data["paid"])),
        ("Остаток", money(max(debt, 0))),
    ]
    top = p.y
    for i, (label, value) in enumerate(totals):
        x0 = left + i * (col_w + gap)
        p.rect(x0, top, x0 + col_w, top + 50, fill=BOX, radius=10)
        p.text(x0 + col_w / 2, top + 8, label, font(10.5), GREY, anchor="ma")
        p.text(x0 + col_w / 2, top + 26, value, font(14, True), TEXT, anchor="ma")
    p.y = top + 50 + 4

    shown = [c for c in data["contracts"] if show_closed or c["debt"] > 0.5]
    hidden = len(data["contracts"]) - len(shown)

    col_date = left + 4
    col_need = left + width * 0.58
    col_paid = left + width * 0.88
    col_mark = right - 8

    for c in shown:
        p.y += 6
        p.line(left, p.y, right, p.y, fill=(207, 213, 220), dashed=True)
        p.y += 8
        closed = " (закрыт)" if c["debt"] <= 0.5 else ""
        p.para(left, f"Покупка от {date_txt(c['day'])}{closed}", font(14, True), width)
        for g in c["goods"]:
            start = p.y
            p.text(left + 6, start, "•", font(13), TEXT)
            p.para(left + 18, g, font(13), width - 18)
        sum_line = contract_sum_line(c)
        p.y += 2
        p.para(left, sum_line, font(11.5), width, DARK_GREY)
        p.y += 4

        if c["schedule"]:
            hf = font(11.5, True)
            p.text(col_date, p.y, "Дата", hf, GREY)
            p.text(col_need, p.y, "Надо", hf, GREY, anchor="ra")
            p.text(col_paid, p.y, "Оплачено", hf, GREY, anchor="ra")
            p.y += 17
            p.line(left, p.y, right, p.y, fill=LINE)
            rf = font(13)
            for r in c["schedule"]:
                row_top = p.y
                p.y += 5
                p.text(col_date, p.y, date_txt(r["due"], r["due_raw"]), rf, TEXT)
                p.text(col_need, p.y, money(r["expected"]), rf, TEXT, anchor="ra")
                p.text(col_paid, p.y, money(r["paid"]), rf, TEXT, anchor="ra")
                p.dot(col_mark, p.y + 8, 6.5, r.get("state", "wait"))
                p.y = row_top + 26
                p.line(left, p.y, right, p.y, fill=LIGHT_LINE)
        p.y += 5
        p.para(left, f"Оплачено {money(c['paid'])} · остаток {money(max(c['debt'], 0))}",
               font(13, True), width, TEXT, align="right")

    p.y += 6
    if not data["contracts"]:
        p.line(left, p.y, right, p.y, fill=(207, 213, 220), dashed=True)
        p.y += 8
        p.para(left, "Покупок в рассрочку нет.", font(13), width)
    elif hidden and not shown:
        p.line(left, p.y, right, p.y, fill=(207, 213, 220), dashed=True)
        p.y += 8
        p.para(left, f"Все договоры закрыты ({hidden}).", font(13), width)
    elif hidden:
        p.para(left, f"Ещё закрытых договоров: {hidden} (учтены в итогах выше)", font(11), width, GREY, align="center")

    # Легенда кружков
    p.y += 6
    lf = font(11)
    items_w = sum(14 + p.text_w(label, lf) + 12 for _, label in STATE_LABELS) - 12
    x = left + (width - items_w) / 2
    for state, label in STATE_LABELS:
        p.dot(x + 5, p.y + 7, 5, state)
        p.text(x + 14, p.y, label, lf, GREY)
        x += 14 + p.text_w(label, lf) + 12
    p.y += 18 + PAD - 6


def render_statement_png(shop_name, client, data, today, show_closed=False):
    """Возвращает PNG (bytes) с выпиской клиента шириной 1080 пикселей."""
    measure = Painter()
    paint(measure, shop_name, client, data, today, show_closed)
    height = int(measure.y * SCALE) + 2

    img = Image.new("RGB", (BASE_W * SCALE, height), WHITE)
    painter = Painter(ImageDraw.Draw(img))
    paint(painter, shop_name, client, data, today, show_closed)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
