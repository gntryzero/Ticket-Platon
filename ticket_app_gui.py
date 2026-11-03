# -*- coding: utf-8 -*-
# TicketPro - приложение для заказа билетов на мероприятия.
# Tkinter (графика) + MySQL (база ticket_db).
#
# Запуск:
#     pip install mysql-connector-python
#     заполните DB_CONFIG ниже и выполните: python ticket_app_gui.py

import os
import uuid
import hashlib
import datetime as dt

import mysql.connector
from mysql.connector import Error as MySQLError

import tkinter as tk
from tkinter import ttk, messagebox

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "1234",   # <-- впишите свой пароль MySQL
    "database": "ticket_db",
    "charset": "utf8mb4",
    "autocommit": False,
}

PALETTE = {
    "bg": "#F1F2F7",
    "card": "#FFFFFF",
    "border": "#E4E6F0",
    "primary": "#4F46E5",
    "primary_dark": "#3B34C4",
    "primary_light": "#EEF0FF",
    "dark": "#1F2340",
    "text": "#23263B",
    "muted": "#7A7E93",
    "green": "#16A34A",
    "red": "#DC2626",
    "amber": "#D97706",
    "free": "#DFF5E1",
    "free_border": "#3BA55C",
    "taken": "#C9CCD9",
}

ICON_BY_CATEGORY = {
    "Кино": "🎬",
    "Театр": "🎭",
    "Концерт": "🎤",
    "Стендап": "😄",
    "Спорт": "⚽",
    "Фестиваль": "🎪",
}

FONT = "Segoe UI"

STATUS_RU = {"pending": "⏳ Не оплачен", "paid": "✅ Оплачен", "cancelled": "❌ Отменён"}
TICKET_STATUS_RU = {"free": "свободен", "reserved": "забронирован", "sold": "продан"}


def get_conn():
    return mysql.connector.connect(**DB_CONFIG)


def q(conn, sql, params=None, fetch=True, one=False):
    cur = conn.cursor(dictionary=True)
    cur.execute(sql, params or ())
    data = None
    if fetch:
        data = cur.fetchone() if one else cur.fetchall()
    cur.close()
    return data


def init_db():
    conn = get_conn()
    ddl = [
        "CREATE TABLE IF NOT EXISTS venues (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255) NOT NULL, address TEXT, city VARCHAR(100), capacity INT) ENGINE=InnoDB",
        "CREATE TABLE IF NOT EXISTS categories (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100) NOT NULL UNIQUE) ENGINE=InnoDB",
        "CREATE TABLE IF NOT EXISTS users (id INT AUTO_INCREMENT PRIMARY KEY, email VARCHAR(255) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL, full_name VARCHAR(255), phone VARCHAR(50), role VARCHAR(20) DEFAULT 'customer', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB",
        "CREATE TABLE IF NOT EXISTS events (id INT AUTO_INCREMENT PRIMARY KEY, title VARCHAR(255) NOT NULL, description TEXT, event_date DATETIME NOT NULL, venue_id INT NOT NULL, status VARCHAR(20) DEFAULT 'active', FOREIGN KEY (venue_id) REFERENCES venues(id) ON DELETE CASCADE) ENGINE=InnoDB",
        "CREATE TABLE IF NOT EXISTS event_categories (event_id INT NOT NULL, category_id INT NOT NULL, PRIMARY KEY (event_id, category_id), FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE, FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE) ENGINE=InnoDB",
        "CREATE TABLE IF NOT EXISTS ticket_types (id INT AUTO_INCREMENT PRIMARY KEY, event_id INT NOT NULL, name VARCHAR(100) NOT NULL, price DECIMAL(10,2) NOT NULL, total_seats INT NOT NULL, FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE) ENGINE=InnoDB",
        "CREATE TABLE IF NOT EXISTS tickets (id INT AUTO_INCREMENT PRIMARY KEY, event_id INT NOT NULL, ticket_type_id INT NOT NULL, seat_row VARCHAR(10), seat_number VARCHAR(10), status VARCHAR(20) DEFAULT 'free', qr_code VARCHAR(255) UNIQUE, FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE, FOREIGN KEY (ticket_type_id) REFERENCES ticket_types(id)) ENGINE=InnoDB",
        "CREATE TABLE IF NOT EXISTS orders (id INT AUTO_INCREMENT PRIMARY KEY, user_id INT NOT NULL, total_price DECIMAL(12,2) NOT NULL, status VARCHAR(20) DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users(id)) ENGINE=InnoDB",
        "CREATE TABLE IF NOT EXISTS order_items (id INT AUTO_INCREMENT PRIMARY KEY, order_id INT NOT NULL, ticket_id INT NOT NULL, price DECIMAL(10,2) NOT NULL, FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE, FOREIGN KEY (ticket_id) REFERENCES tickets(id)) ENGINE=InnoDB",
    ]
    for stmt in ddl:
        q(conn, stmt, fetch=False)
    conn.commit()

    row = q(conn, "SELECT COUNT(*) AS c FROM events", one=True)
    if not row or row["c"] == 0:
        seed_demo_data(conn)
    conn.close()


def seed_demo_data(conn):
    today = dt.datetime.now()
    venues = [
        ("Кинотеатр «Родина»", "ул. Крестовая, 42", "Ярославль", 300),
        ("Театр драмы им. Волкова", "пл. Свободы, 23", "Ярославль", 400),
        ("Клуб «Молния»", "ул. Нахимова, 8", "Ярославль", 250),
        ("Арена «Ярославль»", "ул. Титова, 7", "Ярославль", 900),
        ("Летний амфитеатр", "Волжская набережная", "Ярославль", 500),
    ]
    for v in venues:
        q(conn, "INSERT INTO venues (name, address, city, capacity) VALUES (%s,%s,%s,%s)", v, fetch=False)
    conn.commit()

    for name in ["Кино", "Театр", "Концерт", "Стендап", "Спорт", "Фестиваль"]:
        q(conn, "INSERT INTO categories (name) VALUES (%s)", (name,), fetch=False)
    conn.commit()

    def add_event(title, desc, offset_days, hour, venue_idx, cat_name, types):
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id FROM venues ORDER BY id LIMIT 1 OFFSET %s", (venue_idx,))
        v = cur.fetchone()
        cur.execute("INSERT INTO events (title, description, event_date, venue_id) VALUES (%s,%s,%s,%s)",
                    (title, desc, today + dt.timedelta(days=offset_days, hours=hour - 12), v["id"]))
        event_id = cur.lastrowid
        cur.execute("SELECT id FROM categories WHERE name = %s", (cat_name,))
        cat = cur.fetchone()
        cur.execute("INSERT INTO event_categories (event_id, category_id) VALUES (%s,%s)", (event_id, cat["id"]))
        type_ids = []
        for tname, price, rows, seats in types:
            cur.execute("INSERT INTO ticket_types (event_id, name, price, total_seats) VALUES (%s,%s,%s,%s)",
                        (event_id, tname, price, rows * seats))
            type_ids.append((cur.lastrowid, rows, seats))
        for type_id, n_rows, seats_per_row in type_ids:
            for r in range(n_rows):
                row_label = chr(ord("А") + r) if r < 26 else "Я"
                for s in range(1, seats_per_row + 1):
                    cur.execute(
                        "INSERT INTO tickets (event_id, ticket_type_id, seat_row, seat_number, status, qr_code) "
                        "VALUES (%s,%s,%s,%s,'free',%s)",
                        (event_id, type_id, row_label, str(s), uuid.uuid4().hex))
        cur.close()
        conn.commit()

    add_event("Интерстеллар", "Культовая фантастика Кристофера Нолана на большом экране.",
              1, 19, 0, "Кино", [("Стандарт", 350, 8, 10), ("VIP-диван", 550, 2, 6)])
    add_event("Война и мир", "Постановка по роману Л. Н. Толстого.",
              3, 18, 1, "Театр", [("Партер", 900, 6, 12), ("Балкон", 600, 3, 10)])
    add_event("Рок-концерт «Гром»", "Тотальный рок и световое шоу.",
              5, 20, 2, "Концерт", [("Танцпол", 1800, 5, 12), ("Балкон", 1200, 2, 10)])
    add_event("Стендап «Полный смех»", "Лучшие резиденты за один вечер.",
              2, 19, 2, "Стендап", [("Стандарт", 1200, 5, 10), ("VIP-столик", 2500, 2, 4)])
    add_event("Хоккей: «Полёт» - «Мотор»", "Очередное дерби регулярного чемпионата.",
              4, 17, 3, "Спорт", [("Сектор А", 700, 6, 14), ("Сектор Б", 500, 5, 14)])
    add_event("Джаз-фестиваль «Осенний свинг»", "Три часа живого джаза под открытым небом.",
              10, 16, 4, "Фестиваль", [("Танцевальная зона", 800, 5, 12), ("Сидячие места", 1100, 3, 12)])


# ======================================================================
#  ПАРОЛИ И АВТОРИЗАЦИЯ (переписанный блок)
# ======================================================================
def hash_password(password, salt=None):
    # Соль + SHA-256. Храним в формате salt$digest
    if salt is None:
        salt = os.urandom(16).hex()
    digest = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return salt + "$" + digest


def check_password(password, stored):
    if not stored:
        return False
    if "$" in stored:
        salt, digest = stored.split("$", 1)
        return hash_password(password, salt) == salt + "$" + digest
    return password == stored  # старые пароли без хеша тоже работают


def register_user(email, password, full_name, phone):
    email = (email or "").strip().lower()
    password = password or ""
    full_name = (full_name or "").strip()
    phone = (phone or "").strip()

    if not email or "@" not in email or "." not in email:
        return False, "Введите корректный e-mail (например, ivan@mail.ru)."
    if len(password) < 6:
        return False, "Пароль должен быть не короче 6 символов."
    if not full_name:
        return False, "Укажите имя и фамилию."

    conn = get_conn()
    try:
        existing = q(conn, "SELECT id FROM users WHERE LOWER(email) = %s", (email,), one=True)
        if existing:
            return False, "Пользователь с таким e-mail уже зарегистрирован."
        q(conn, "INSERT INTO users (email, password_hash, full_name, phone) VALUES (%s,%s,%s,%s)",
          (email, hash_password(password), full_name, phone), fetch=False)
        conn.commit()
        user = q(conn, "SELECT * FROM users WHERE LOWER(email) = %s", (email,), one=True)
        return True, user
    except MySQLError as e:
        conn.rollback()
        if getattr(e, "errno", None) == 1062:
            return False, "Пользователь с таким e-mail уже зарегистрирован."
        return False, "Ошибка базы данных: " + str(e)
    finally:
        conn.close()


def login_user(email, password):
    email = (email or "").strip().lower()
    password = password or ""
    if not email or not password:
        return None, "Заполните e-mail и пароль."

    conn = get_conn()
    try:
        user = q(conn, "SELECT * FROM users WHERE LOWER(email) = %s", (email,), one=True)
        if not user:
            return None, "Пользователь с таким e-mail не найден."
        if not check_password(password, user["password_hash"]):
            return None, "Неверный пароль."
        # Апгрейд старых паролей (без хеша) до хешированных
        if "$" not in (user["password_hash"] or ""):
            q(conn, "UPDATE users SET password_hash = %s WHERE id = %s",
              (hash_password(password), user["id"]), fetch=False)
            conn.commit()
        return user, "Добро пожаловать, " + (user["full_name"] or user["email"]) + "!"
    except MySQLError as e:
        return None, "Ошибка базы данных: " + str(e)
    finally:
        conn.close()


# ======================================================================
#  ОБЩИЕ GUI-КОМПОНЕНТЫ
# ======================================================================
def _darken(hexcolor):
    r = int(hexcolor[1:3], 16)
    g = int(hexcolor[3:5], 16)
    b = int(hexcolor[5:7], 16)
    return "#{:02X}{:02X}{:02X}".format(max(r - 30, 0), max(g - 30, 0), max(b - 30, 0))


def make_button(parent, text, bg, command, fg="#FFFFFF", width=None, font_size=10):
    btn = tk.Button(parent, text=text, command=command, cursor="hand2",
                    bg=bg, fg=fg, activebackground=bg, activeforeground=fg,
                    relief="flat", bd=0, font=(FONT, font_size, "bold"),
                    padx=14, pady=7, width=width)

    def on_enter(_):
        btn["bg"] = PALETTE["primary_dark"] if bg == PALETTE["primary"] else _darken(bg)

    def on_leave(_):
        btn["bg"] = bg

    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)
    return btn


def header_bar(parent, subtitle=""):
    bar = tk.Frame(parent, bg=PALETTE["dark"], height=64)
    bar.pack(fill="x")
    bar.pack_propagate(False)
    tk.Label(bar, text="🎟", font=(FONT, 22), bg=PALETTE["dark"], fg="#FFFFFF").pack(side="left", padx=(18, 6))
    box = tk.Frame(bar, bg=PALETTE["dark"])
    box.pack(side="left")
    tk.Label(box, text="TicketPro", font=(FONT, 16, "bold"),
             bg=PALETTE["dark"], fg="#FFFFFF").pack(anchor="w")
    if subtitle:
        tk.Label(box, text=subtitle, font=(FONT, 9),
                 bg=PALETTE["dark"], fg="#9BA0C0").pack(anchor="w")
    return bar


# ======================================================================
#  ОКНО ВХОДА И РЕГИСТРАЦИИ
# ======================================================================
class LoginFrame(tk.Frame):
    def __init__(self, master, on_success):
        super().__init__(master, bg=PALETTE["bg"])
        self.on_success = on_success

        card = tk.Frame(self, bg=PALETTE["card"], bd=1, relief="solid")
        card.place(relx=0.5, rely=0.5, anchor="center", width=420)

        inner = tk.Frame(card, bg=PALETTE["card"])
        inner.pack(padx=34, pady=28, fill="both", expand=True)

        tk.Label(inner, text="🎟", font=(FONT, 40), bg=PALETTE["card"]).pack()
        tk.Label(inner, text="TicketPro", font=(FONT, 24, "bold"),
                 bg=PALETTE["card"], fg=PALETTE["text"]).pack()
        tk.Label(inner, text="Билеты на лучшие мероприятия города",
                 font=(FONT, 10), bg=PALETTE["card"], fg=PALETTE["muted"]).pack(pady=(2, 14))

        tabs = tk.Frame(inner, bg=PALETTE["card"])
        tabs.pack()
        self.tab_login = make_button(tabs, "Вход", PALETTE["primary"],
                                     lambda: self.switch("login"), width=14)
        self.tab_reg = make_button(tabs, "Регистрация", PALETTE["card"],
                                   lambda: self.switch("register"), width=14, fg=PALETTE["muted"])
        self.tab_login.pack(side="left", padx=(0, 8))
        self.tab_reg.pack(side="left")

        self.body = tk.Frame(inner, bg=PALETTE["card"])
        self.body.pack(fill="x", pady=(14, 0))

        self.msg = tk.Label(inner, text="", font=(FONT, 10), bg=PALETTE["card"], wraplength=330)
        self.msg.pack(fill="x", pady=(10, 0))

        self.switch("login")

    def switch(self, mode):
        if mode == "login":
            self.tab_login["bg"] = PALETTE["primary"]
            self.tab_login["fg"] = "#FFFFFF"
            self.tab_reg["bg"] = PALETTE["card"]
            self.tab_reg["fg"] = PALETTE["muted"]
        else:
            self.tab_reg["bg"] = PALETTE["primary"]
            self.tab_reg["fg"] = "#FFFFFF"
            self.tab_login["bg"] = PALETTE["card"]
            self.tab_login["fg"] = PALETTE["muted"]

        for w in self.body.winfo_children():
            w.destroy()

        self.entries = {}
        fields = ([("email", "E-mail"), ("password", "Пароль")]
                  if mode == "login" else
                  [("email", "E-mail"), ("password", "Пароль (мин. 6 символов)"),
                   ("full_name", "Имя и фамилия"), ("phone", "Телефон")])
        for key, label in fields:
            tk.Label(self.body, text=label, font=(FONT, 9),
                     bg=PALETTE["card"], fg=PALETTE["muted"], anchor="w").pack(fill="x", pady=(8, 1))
            show = "*" if key == "password" else ""
            ent = tk.Entry(self.body, font=(FONT, 12), show=show, relief="solid", bd=1,
                           bg="#F7F8FC", fg=PALETTE["text"])
            ent.pack(fill="x", ipady=6)
            self.entries[key] = ent
        if mode == "login":
            self.entries["password"].bind("<Return>", lambda e: self.do_action())

        action_text = "Войти" if mode == "login" else "Зарегистрироваться"
        make_button(self.body, action_text, PALETTE["primary"],
                    self.do_action, font_size=11).pack(fill="x", pady=(16, 0))

    def do_action(self):
        values = {k: e.get() for k, e in self.entries.items()}
        if self._mode_is_login():
            user, message = login_user(values["email"], values["password"])
            if user:
                self.msg.config(text="", fg=PALETTE["green"])
                self.on_success(user)
            else:
                self.msg.config(text=message, fg=PALETTE["red"])
        else:
            ok, result = register_user(values["email"], values["password"],
                                       values["full_name"], values["phone"])
            if ok:
                self.msg.config(text="Регистрация успешна! Входим...", fg=PALETTE["green"])
                self.after(400, lambda: self.on_success(result))
            else:
                self.msg.config(text=result, fg=PALETTE["red"])

    def _mode_is_login(self):
        return self.tab_login["bg"] == PALETTE["primary"]


# ======================================================================
#  ГЛАВНОЕ ОКНО: КАРТОЧКИ МЕРОПРИЯТИЙ
# ======================================================================
class MainFrame(tk.Frame):
    def __init__(self, master, user, on_logout):
        super().__init__(master, bg=PALETTE["bg"])
        self.user = user
        self.on_logout = on_logout

        bar = header_bar(self, "Заказ билетов на мероприятия")
        right = tk.Frame(bar, bg=PALETTE["dark"])
        right.pack(side="right", padx=14)
        tk.Label(right, text=user["full_name"] or user["email"],
                 font=(FONT, 11, "bold"), bg=PALETTE["dark"], fg="#FFFFFF").pack(side="left", padx=4)
        role_badge = "👑 Админ" if user.get("role") == "admin" else "👤 Покупатель"
        tk.Label(right, text=role_badge, font=(FONT, 10),
                 bg=PALETTE["dark"], fg="#9BA0C0").pack(side="left", padx=8)
        make_button(right, "Выйти", PALETTE["dark"], on_logout).pack(side="left", padx=4)

        toolbar = tk.Frame(self, bg=PALETTE["bg"])
        toolbar.pack(fill="x", padx=18, pady=(14, 4))
        make_button(toolbar, "🔄 Обновить", PALETTE["primary"], self.refresh).pack(side="left")
        make_button(toolbar, "🎫 Мои заказы", PALETTE["green"], self.open_orders).pack(side="left", padx=8)
        if user.get("role") == "admin":
            make_button(toolbar, "🛠 Панель администратора", PALETTE["amber"], self.open_admin).pack(side="left")

        self.scroll_area = tk.Canvas(self, bg=PALETTE["bg"], highlightthickness=0)
        self.scroll_area.pack(side="left", fill="both", expand=True, padx=18)
        vs = ttk.Scrollbar(self, orient="vertical", command=self.scroll_area.yview)
        vs.pack(side="right", fill="y")
        self.scroll_area.configure(yscrollcommand=vs.set)
        self.cards_frame = tk.Frame(self.scroll_area, bg=PALETTE["bg"])
        self.cards_win = self.scroll_area.create_window((0, 0), window=self.cards_frame, anchor="nw")
        self.cards_frame.bind("<Configure>", self._on_cards_configure)
        self.scroll_area.bind("<Configure>", lambda e: self.scroll_area.itemconfig(
            self.cards_win, width=e.width))
        self.scroll_area.bind_all("<MouseWheel>", self._on_wheel)

        self.refresh()

    def _on_cards_configure(self, _):
        self.scroll_area.configure(scrollregion=self.scroll_area.bbox("all"))

    def _on_wheel(self, event):
        delta = -1 if event.delta > 0 else 1
        self.scroll_area.yview_scroll(delta, "units")

    def refresh(self):
        for w in self.cards_frame.winfo_children():
            w.destroy()
        conn = get_conn()
        events = q(conn, """
            SELECT e.id, e.title, e.description, e.event_date,
                   v.name AS venue, MIN(tt.price) AS min_price,
                   GROUP_CONCAT(DISTINCT c.name) AS cats
            FROM events e
            JOIN venues v ON v.id = e.venue_id
            LEFT JOIN ticket_types tt ON tt.event_id = e.id
            LEFT JOIN event_categories ec ON ec.event_id = e.id
            LEFT JOIN categories c ON c.id = ec.category_id
            WHERE e.status = 'active'
            GROUP BY e.id, e.title, e.description, e.event_date, v.name
            ORDER BY e.event_date
        """) or []
        conn.close()

        if not events:
            tk.Label(self.cards_frame, text="Мероприятий пока нет.\nДобавьте их в панели администратора.",
                     font=(FONT, 12), bg=PALETTE["bg"], fg=PALETTE["muted"],
                     justify="center").pack(pady=60)
            return

        for i, ev in enumerate(events):
            card = tk.Frame(self.cards_frame, bg=PALETTE["card"], bd=1, relief="solid")
            row, col = divmod(i, 2)
            card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
            self.cards_frame.columnconfigure(col, weight=1)

            cats = (ev["cats"] or "").split(",")
            cat_name = cats[0].strip() if cats and cats[0].strip() else "Кино"
            icon = ICON_BY_CATEGORY.get(cat_name, "🎟")

            top = tk.Frame(card, bg=PALETTE["card"])
            top.pack(fill="x", padx=16, pady=(14, 4))
            tk.Label(top, text=icon, font=(FONT, 30), bg=PALETTE["card"]).pack(side="left", padx=(0, 12))
            title_box = tk.Frame(top, bg=PALETTE["card"])
            title_box.pack(side="left", fill="x", expand=True)
            tk.Label(title_box, text=ev["title"], font=(FONT, 13, "bold"),
                     bg=PALETTE["card"], fg=PALETTE["text"], anchor="w",
                     wraplength=260, justify="left").pack(anchor="w")
            chip = tk.Label(title_box, text=cat_name, font=(FONT, 8, "bold"),
                            bg=PALETTE["primary_light"], fg=PALETTE["primary"], padx=8, pady=2)
            chip.pack(anchor="w", pady=(4, 0))

            date_str = ev["event_date"].strftime("%d.%m.%Y в %H:%M") \
                if isinstance(ev["event_date"], dt.datetime) else str(ev["event_date"])
            tk.Label(card, text="📍 " + ev["venue"] + "   ·   🕒 " + date_str,
                     font=(FONT, 10), bg=PALETTE["card"], fg=PALETTE["muted"]).pack(anchor="w", padx=16)
            price = ("от " + str(int(float(ev["min_price"]))) + " ₽") if ev["min_price"] else "цена уточняется"
            tk.Label(card, text=price, font=(FONT, 12, "bold"),
                     bg=PALETTE["card"], fg=PALETTE["green"]).pack(anchor="w", padx=16, pady=(4, 2))
            make_button(card, "Купить билеты", PALETTE["primary"],
                        lambda e=ev: self.open_buy(e)).pack(padx=16, pady=(2, 14), fill="x")

    def open_buy(self, event):
        BuyWindow(self, event)

    def open_orders(self):
        OrdersWindow(self, self.user)

    def open_admin(self):
        AdminWindow(self)


# ======================================================================
#  ОКНО ПОКУПКИ: ТИПЫ БИЛЕТОВ + СХЕМА ЗАЛА
# ======================================================================
class BuyWindow(tk.Toplevel):
    MAX_SEATS = 6

    def __init__(self, master, event):
        super().__init__(master)
        self.event = event
        self.title("Покупка билетов — " + event["title"])
        self.configure(bg=PALETTE["bg"])
        self.geometry("1080x680")
        self.transient(master)

        header_bar(self, event["title"])

        body = tk.Frame(self, bg=PALETTE["bg"])
        body.pack(fill="both", expand=True, padx=14, pady=10)

        # левая панель: типы билетов
        self.type_panel = tk.Frame(body, bg=PALETTE["card"], bd=1, relief="solid")
        self.type_panel.pack(side="left", fill="y", padx=(0, 12), pady=2)
        tk.Label(self.type_panel, text="Тип билета", font=(FONT, 12, "bold"),
                 bg=PALETTE["card"], fg=PALETTE["text"]).pack(anchor="w", padx=14, pady=(14, 8))

        self.selected_type = None
        self.type_buttons = {}
        self.types = []
        self.load_types()

        # правая часть: схема зала
        right = tk.Frame(body, bg=PALETTE["bg"])
        right.pack(side="left", fill="both", expand=True)

        self.canvas = tk.Canvas(right, bg=PALETTE["bg"], highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        vs = ttk.Scrollbar(right, orient="vertical", command=self.canvas.yview)
        vs.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=vs.set)

        self.legend = tk.Frame(right, bg=PALETTE["bg"])
        for color, label in [(PALETTE["free"], "свободно"),
                             (PALETTE["primary"], "выбрано вами"),
                             (PALETTE["taken"], "занято")]:
            box = tk.Frame(self.legend, bg=PALETTE["bg"])
            box.pack(side="left", padx=(0, 16))
            tk.Label(box, text="  ", bg=color, width=2, relief="solid", bd=1).pack(side="left")
            tk.Label(box, text=label, font=(FONT, 9), bg=PALETTE["bg"],
                     fg=PALETTE["muted"]).pack(side="left", padx=4)

        self.footer = tk.Frame(self, bg=PALETTE["card"], bd=1, relief="solid")
        self.footer.pack(fill="x", side="bottom")
        self.total_label = tk.Label(self.footer, text="Выберите места", font=(FONT, 11, "bold"),
                                    bg=PALETTE["card"], fg=PALETTE["text"])
        self.total_label.pack(side="left", padx=18, pady=10)
        make_button(self.footer, "🎫 Забронировать", PALETTE["green"],
                    self.confirm_booking, font_size=11).pack(side="right", padx=18, pady=8)

        self.selected = set()
        if self.types:
            self.select_type(self.types[0]["id"])

    def load_types(self):
        conn = get_conn()
        self.types = q(conn, """
            SELECT tt.id, tt.name, tt.price,
                   SUM(CASE WHEN t.status='free' THEN 1 ELSE 0 END) AS free_cnt
            FROM ticket_types tt
            LEFT JOIN tickets t ON t.ticket_type_id = tt.id
            WHERE tt.event_id = %s
            GROUP BY tt.id, tt.name, tt.price
            ORDER BY tt.price
        """, (self.event["id"],)) or []
        conn.close()

        for w in self.type_panel.winfo_children():
            if isinstance(w, tk.Button):
                w.destroy()
        for t in self.types:
            price = int(float(t["price"]))
            free = t["free_cnt"] or 0
            label = t["name"] + "\n" + str(price) + " ₽ · свободно " + str(free)
            btn = tk.Button(self.type_panel, text=label, font=(FONT, 10),
                            cursor="hand2", relief="flat", bd=0, justify="left",
                            padx=12, pady=8, bg=PALETTE["card"], fg=PALETTE["text"],
                            command=lambda tid=t["id"]: self.select_type(tid))
            btn.pack(fill="x", padx=10, pady=4)
            if not free:
                btn["state"] = "disabled"
                btn["fg"] = PALETTE["taken"]
            self.type_buttons[t["id"]] = btn

    def select_type(self, type_id):
        self.selected_type = type_id
        for tid, btn in self.type_buttons.items():
            if tid == type_id:
                btn["bg"] = PALETTE["primary_light"]
                btn["fg"] = PALETTE["primary"]
            else:
                btn["bg"] = PALETTE["card"]
                btn["fg"] = PALETTE["text"]
        self.draw_seats()

    def draw_seats(self):
        self.canvas.delete("all")
        self.rects = {}
        conn = get_conn()
        tickets = q(conn, """
            SELECT id, seat_row, seat_number, status
            FROM tickets WHERE ticket_type_id = %s
            ORDER BY seat_row, CAST(seat_number AS UNSIGNED)
        """, (self.selected_type,)) or []
        conn.close()

        rows = {}
        for t in tickets:
            rows.setdefault(t["seat_row"], []).append(t)

        self.canvas.configure(scrollregion=(0, 0, 1000, 80 + len(rows) * 46 + 30))

        cw = max(self.canvas.winfo_width() or 900, 700)
        self.canvas.create_polygon(cw // 2 - 170, 34, cw // 2 + 170, 34,
                                   cw // 2 + 130, 10, cw // 2 - 130, 10,
                                   fill="#D7DBF5", outline="#A9AEE0")
        self.canvas.create_text(cw // 2, 23, text="Э К Р А Н",
                                font=(FONT, 10, "bold"), fill="#6B7096")

        w, h, gap = 44, 34, 8
        y = 70
        for row_label in sorted(rows.keys()):
            self.canvas.create_text(26, y + h // 2, text=row_label,
                                    font=(FONT, 10, "bold"), fill=PALETTE["muted"])
            for idx, t in enumerate(rows[row_label]):
                x = 56 + idx * (w + gap)
                if t["status"] == "free":
                    color, outline = PALETTE["free"], PALETTE["free_border"]
                else:
                    color, outline = PALETTE["taken"], PALETTE["taken"]
                if t["status"] == "free" and t["id"] in self.selected:
                    color, outline = PALETTE["primary"], PALETTE["primary_dark"]
                self.canvas.create_rectangle(x, y, x + w, y + h, fill=color,
                                             outline=outline, width=1.5,
                                             tags=("seat" + str(t["id"]),))
                text_fill = "#FFFFFF" if color == PALETTE["primary"] else PALETTE["text"]
                self.canvas.create_text(x + w // 2, y + h // 2, text=t["seat_number"],
                                        font=(FONT, 9), fill=text_fill,
                                        tags=("seat" + str(t["id"]),))
                if t["status"] == "free":
                    self.rects[t["id"]] = True
                    self.canvas.tag_bind("seat" + str(t["id"]), "<Button-1>",
                                         lambda _e, tid=t["id"]: self.toggle_seat(tid))
                else:
                    self.canvas.tag_bind("seat" + str(t["id"]), "<Button-1>",
                                         lambda _e: messagebox.showinfo(
                                             "Занято", "Это место уже занято или забронировано.",
                                             parent=self))
            y += h + gap

    def toggle_seat(self, tid):
        if tid in self.selected:
            self.selected.discard(tid)
        else:
            if len(self.selected) >= self.MAX_SEATS:
                messagebox.showwarning("Лимит",
                                       "За один заказ — не более " + str(self.MAX_SEATS) + " билетов.",
                                       parent=self)
                return
            self.selected.add(tid)
        self.draw_seats()
        self.update_total()

    def update_total(self):
        if not self.selected:
            self.total_label.config(text="Выберите места")
            return
        ttype = next(t for t in self.types if t["id"] == self.selected_type)
        total = len(self.selected) * float(ttype["price"])
        self.total_label.config(text="Выбрано билетов: " + str(len(self.selected)) +
                                "   ·   Итого: " + str(int(total)) + " ₽")

    def confirm_booking(self):
        if not self.selected:
            messagebox.showwarning("Нет мест",
                                   "Сначала выберите хотя бы одно место на схеме.", parent=self)
            return
        conn = get_conn()
        order_id = None
        total = 0
        try:
            conn.start_transaction()
            cur = conn.cursor(dictionary=True)
            ids = ",".join(str(i) for i in self.selected)
            cur.execute("SELECT id, seat_row, seat_number, status FROM tickets "
                        "WHERE id IN (" + ids + ") FOR UPDATE")
            locked = cur.fetchall()
            for t in locked:
                if t["status"] != "free":
                    conn.rollback()
                    messagebox.showerror(
                        "Место занято",
                        "Ряд " + str(t["seat_row"]) + ", место " + str(t["seat_number"]) +
                        " уже занято.\nОбновите схему и выберите другие места.", parent=self)
                    self.selected.clear()
                    self.draw_seats()
                    self.update_total()
                    return

            ttype = next(t for t in self.types if t["id"] == self.selected_type)
            price = float(ttype["price"])
            total = price * len(self.selected)
            cur.execute("INSERT INTO orders (user_id, total_price, status) VALUES (%s,%s,'pending')",
                        (self.master.user["id"], total))
            order_id = cur.lastrowid
            for tid in self.selected:
                cur.execute("INSERT INTO order_items (order_id, ticket_id, price) VALUES (%s,%s,%s)",
                            (order_id, tid, price))
                cur.execute("UPDATE tickets SET status='reserved' WHERE id=%s", (tid,))
            conn.commit()
            cur.close()
        except MySQLError as e:
            conn.rollback()
            messagebox.showerror("Ошибка", "Не удалось оформить бронь:\n" + str(e), parent=self)
            return
        finally:
            conn.close()

        self.selected.clear()
        self.draw_seats()
        self.update_total()
        self.load_types()
        if messagebox.askyesno("Бронь оформлена!",
                               "Заказ №" + str(order_id) + " на сумму " + str(int(total)) +
                               " ₽ создан.\nПерейти к оплате сейчас?", parent=self):
            user = self.master.user
            OrdersWindow(self.master, user, focus_order=order_id)
            self.destroy()


# ======================================================================
#  ОКНО "МОИ ЗАКАЗЫ"
# ======================================================================
class OrdersWindow(tk.Toplevel):
    def __init__(self, master, user, focus_order=None):
        super().__init__(master)
        self.user = user
        self.title("Мои заказы")
        self.configure(bg=PALETTE["bg"])
        self.geometry("820x560")
        self.transient(master)

        header_bar(self, "История покупок и оплата")

        main = tk.Frame(self, bg=PALETTE["bg"])
        main.pack(fill="both", expand=True, padx=14, pady=10)

        style = ttk.Style(self)
        style.configure("TP.Treeview", font=(FONT, 10), rowheight=30)
        style.configure("TP.Treeview.Heading", font=(FONT, 10, "bold"))

        self.tree = ttk.Treeview(main, columns=("id", "date", "total", "status", "items"),
                                 show="headings", style="TP.Treeview", height=9)
        for col, title, width in [("id", "№", 50), ("date", "Дата", 150),
                                  ("total", "Сумма", 110), ("status", "Статус", 130),
                                  ("items", "Билеты", 100)]:
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, anchor="center")
        self.tree.pack(fill="x")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        detail = tk.Frame(main, bg=PALETTE["card"], bd=1, relief="solid")
        detail.pack(fill="both", expand=True, pady=(10, 0))
        self.detail = tk.Label(detail, text="Выберите заказ, чтобы увидеть билеты.",
                               font=(FONT, 10), bg=PALETTE["card"], fg=PALETTE["muted"],
                               justify="left", anchor="nw")
        self.detail.pack(fill="both", expand=True, padx=14, pady=10)

        btns = tk.Frame(main, bg=PALETTE["bg"])
        btns.pack(fill="x", pady=(10, 0))
        make_button(btns, "💳 Оплатить", PALETTE["green"], self.pay_order).pack(side="left")
        make_button(btns, "❌ Отменить", PALETTE["red"], self.cancel_order).pack(side="left", padx=8)
        make_button(btns, "🔄 Обновить", PALETTE["primary"], self.refresh).pack(side="right")

        self.orders = {}
        self.refresh()
        if focus_order:
            for iid in self.tree.get_children():
                if str(self.tree.item(iid, "values")[0]) == str(focus_order):
                    self.tree.selection_set(iid)
                    self.tree.see(iid)

    def refresh(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        conn = get_conn()
        orders = q(conn, """
            SELECT o.id, o.created_at, o.total_price, o.status,
                   COUNT(oi.id) AS items_cnt
            FROM orders o
            LEFT JOIN order_items oi ON oi.order_id = o.id
            WHERE o.user_id = %s
            GROUP BY o.id, o.created_at, o.total_price, o.status
            ORDER BY o.created_at DESC
        """, (self.user["id"],)) or []
        conn.close()
        self.orders = {o["id"]: o for o in orders}
        for o in orders:
            date_str = o["created_at"].strftime("%d.%m.%Y %H:%M") \
                if isinstance(o["created_at"], dt.datetime) else str(o["created_at"])
            self.tree.insert("", "end", values=(o["id"], date_str,
                                                str(int(float(o["total_price"]))) + " ₽",
                                                STATUS_RU.get(o["status"], o["status"]),
                                                o["items_cnt"]))

    def on_select(self, _):
        sel = self.tree.selection()
        if not sel:
            return
        order_id = int(self.tree.item(sel[0], "values")[0])
        conn = get_conn()
        items = q(conn, """
            SELECT t.seat_row, t.seat_number, t.status, t.qr_code,
                   tt.name AS type_name, tt.price, e.title
            FROM order_items oi
            JOIN tickets t ON t.id = oi.ticket_id
            JOIN ticket_types tt ON tt.id = t.ticket_type_id
            JOIN events e ON e.id = t.event_id
            WHERE oi.order_id = %s
        """, (order_id,)) or []
        conn.close()
        lines = []
        for it in items:
            lines.append("🎟 " + it["title"] + " · " + it["type_name"] +
                         " · ряд " + str(it["seat_row"]) + ", место " + str(it["seat_number"]) +
                         " · " + str(int(float(it["price"]))) + " ₽ · " +
                         TICKET_STATUS_RU.get(it["status"], it["status"]) +
                         "\n    QR: " + str(it["qr_code"]))
        self.detail.config(text="\n".join(lines) or "Билеты не найдены.")

    def _selected_order(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Выберите заказ", "Сначала выберите заказ в списке.", parent=self)
            return None
        order_id = int(self.tree.item(sel[0], "values")[0])
        if self.orders.get(order_id, {}).get("status") != "pending":
            messagebox.showinfo("Недоступно", "Действие доступно только для неоплаченных заказов.", parent=self)
            return None
        return order_id

    def pay_order(self):
        order_id = self._selected_order()
        if not order_id:
            return
        conn = get_conn()
        try:
            conn.start_transaction()
            cur = conn.cursor()
            cur.execute("UPDATE orders SET status='paid' WHERE id=%s AND status='pending'", (order_id,))
            if cur.rowcount == 0:
                conn.rollback()
                messagebox.showinfo("Недоступно", "Заказ уже обработан.", parent=self)
                return
            cur.execute("""UPDATE tickets t
                           JOIN order_items oi ON oi.ticket_id = t.id
                           SET t.status='sold' WHERE oi.order_id = %s""", (order_id,))
            conn.commit()
        except MySQLError as e:
            conn.rollback()
            messagebox.showerror("Ошибка", str(e), parent=self)
            return
        finally:
            conn.close()
        messagebox.showinfo("Оплачено", "Заказ №" + str(order_id) + " оплачен. Приятного просмотра!", parent=self)
        self.refresh()

    def cancel_order(self):
        order_id = self._selected_order()
        if not order_id:
            return
        conn = get_conn()
        try:
            conn.start_transaction()
            cur = conn.cursor()
            cur.execute("UPDATE orders SET status='cancelled' WHERE id=%s AND status='pending'", (order_id,))
            if cur.rowcount == 0:
                conn.rollback()
                messagebox.showinfo("Недоступно", "Заказ уже обработан.", parent=self)
                return
            cur.execute("""UPDATE tickets t
                           JOIN order_items oi ON oi.ticket_id = t.id
                           SET t.status='free' WHERE oi.order_id = %s""", (order_id,))
            conn.commit()
        except MySQLError as e:
            conn.rollback()
            messagebox.showerror("Ошибка", str(e), parent=self)
            return
        finally:
            conn.close()
        messagebox.showinfo("Отменено", "Заказ отменён, места снова свободны.", parent=self)
        self.refresh()


# ======================================================================
#  ПАНЕЛЬ АДМИНИСТРАТОРА
# ======================================================================
class AdminWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Панель администратора")
        self.configure(bg=PALETTE["bg"])
        self.geometry("760x560")
        self.transient(master)

        header_bar(self, "Управление площадками, мероприятиями и билетами")

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=14, pady=12)

        f1 = tk.Frame(nb, bg=PALETTE["card"])
        nb.add(f1, text="  Площадка  ")
        self.venue_name = self._entry_row(f1, "Название")
        self.venue_city = self._entry_row(f1, "Город")
        self.venue_addr = self._entry_row(f1, "Адрес")
        self.venue_cap = self._entry_row(f1, "Вместимость")
        make_button(f1, "Добавить площадку", PALETTE["primary"], self.add_venue).pack(
            padx=18, pady=12, anchor="w")

        f2 = tk.Frame(nb, bg=PALETTE["card"])
        nb.add(f2, text="  Мероприятие  ")
        self.ev_title = self._entry_row(f2, "Название")
        self.ev_desc = self._entry_row(f2, "Описание")
        self.ev_date = self._entry_row(f2, "Дата и время (ГГГГ-ММ-ДД ЧЧ:ММ)")
        self.venue_combo = self._combo_row(f2, "Площадка", "SELECT id, name FROM venues", "name")
        self.cat_combo = self._combo_row(f2, "Категория", "SELECT id, name FROM categories", "name")
        make_button(f2, "Добавить мероприятие", PALETTE["primary"], self.add_event).pack(
            padx=18, pady=12, anchor="w")

        f3 = tk.Frame(nb, bg=PALETTE["card"])
        nb.add(f3, text="  Тип билета  ")
        self.ev_combo = self._combo_row(f3, "Мероприятие",
                                        "SELECT id, title FROM events WHERE status='active'", "title")
        self.tt_name = self._entry_row(f3, "Название типа (например, Партер)")
        self.tt_price = self._entry_row(f3, "Цена")
        self.tt_rows = self._entry_row(f3, "Количество рядов")
        self.tt_seats = self._entry_row(f3, "Мест в ряду")
        make_button(f3, "Добавить тип билетов (с местами)", PALETTE["primary"], self.add_type).pack(
            padx=18, pady=12, anchor="w")

    def _entry_row(self, parent, label):
        tk.Label(parent, text=label, font=(FONT, 9), bg=PALETTE["card"],
                 fg=PALETTE["muted"]).pack(fill="x", padx=18, pady=(10, 1))
        ent = tk.Entry(parent, font=(FONT, 11), relief="solid", bd=1, bg="#F7F8FC")
        ent.pack(fill="x", padx=18, ipady=5)
        return ent

    def _combo_row(self, parent, label, sql, display_col):
        tk.Label(parent, text=label, font=(FONT, 9), bg=PALETTE["card"],
                 fg=PALETTE["muted"]).pack(fill="x", padx=18, pady=(10, 1))
        combo = ttk.Combobox(parent, font=(FONT, 11), state="readonly")
        conn = get_conn()
        rows = q(conn, sql) or []
        conn.close()
        combo["values"] = [str(r["id"]) + ". " + r[display_col] for r in rows]
        if rows:
            combo.current(0)
        combo.pack(fill="x", padx=18, ipady=4)
        return combo

    def _combo_id(self, combo):
        return int(combo.get().split(".")[0]) if combo.get() else None

    def add_venue(self):
        name = self.venue_name.get().strip()
        if not name:
            messagebox.showwarning("Заполните поля", "Укажите название площадки.", parent=self)
            return
        cap = self.venue_cap.get().strip()
        conn = get_conn()
        q(conn, "INSERT INTO venues (name, address, city, capacity) VALUES (%s,%s,%s,%s)",
          (name, self.venue_addr.get().strip(), self.venue_city.get().strip(),
           int(cap) if cap.isdigit() else None), fetch=False)
        conn.commit()
        conn.close()
        messagebox.showinfo("Готово", "Площадка добавлена.", parent=self)

    def add_event(self):
        title = self.ev_title.get().strip()
        date_raw = self.ev_date.get().strip()
        if not title or not date_raw:
            messagebox.showwarning("Заполните поля", "Укажите название и дату мероприятия.", parent=self)
            return
        venue_id = self._combo_id(self.venue_combo)
        cat_id = self._combo_id(self.cat_combo)
        try:
            event_date = dt.datetime.strptime(date_raw, "%Y-%m-%d %H:%M")
        except ValueError:
            messagebox.showerror("Дата",
                                 "Формат даты: ГГГГ-ММ-ДД ЧЧ:ММ, например 2026-12-31 19:00.", parent=self)
            return
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("INSERT INTO events (title, description, event_date, venue_id) VALUES (%s,%s,%s,%s)",
                    (title, self.ev_desc.get().strip(), event_date, venue_id))
        event_id = cur.lastrowid
        if cat_id:
            cur.execute("INSERT INTO event_categories (event_id, category_id) VALUES (%s,%s)",
                        (event_id, cat_id))
        conn.commit()
        cur.close()
        conn.close()
        messagebox.showinfo("Готово", "Мероприятие добавлено.", parent=self)

    def add_type(self):
        event_id = self._combo_id(self.ev_combo)
        name = self.tt_name.get().strip()
        price_raw = self.tt_price.get().strip().replace(",", ".")
        rows_raw = self.tt_rows.get().strip()
        seats_raw = self.tt_seats.get().strip()
        if not (event_id and name and price_raw and rows_raw.isdigit() and seats_raw.isdigit()):
            messagebox.showwarning("Заполните поля",
                                   "Проверьте поля: мероприятие, название, цену, ряды и места.", parent=self)
            return
        n_rows, seats_per_row, price = int(rows_raw), int(seats_raw), float(price_raw)
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("INSERT INTO ticket_types (event_id, name, price, total_seats) VALUES (%s,%s,%s,%s)",
                    (event_id, name, price, n_rows * seats_per_row))
        type_id = cur.lastrowid
        for r in range(n_rows):
            row_label = chr(ord("А") + r) if r < 26 else "Я"
            for s in range(1, seats_per_row + 1):
                cur.execute("INSERT INTO tickets (event_id, ticket_type_id, seat_row, seat_number, status, qr_code) "
                            "VALUES (%s,%s,%s,%s,'free',%s)",
                            (event_id, type_id, row_label, str(s), uuid.uuid4().hex))
        conn.commit()
        cur.close()
        conn.close()
        messagebox.showinfo("Готово",
                            "Тип билетов добавлен: " + str(n_rows) + " рядов по " + str(seats_per_row) + " мест.",
                            parent=self)


# ======================================================================
#  ЗАПУСК
# ======================================================================
def main():
    try:
        init_db()
    except MySQLError as e:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Нет соединения с базой",
            "Не удалось подключиться к MySQL:\n" + str(e) + "\n\n"
            "Проверьте, что сервер MySQL запущен, а в DB_CONFIG вверху файла указан верный пароль.")
        return

    root = tk.Tk()
    root.title("TicketPro — билеты на мероприятия")
    root.geometry("1100x720")
    root.configure(bg=PALETTE["bg"])

    def show_main(user):
        for w in root.winfo_children():
            if isinstance(w, tk.Frame):
                w.destroy()
        MainFrame(root, user, on_logout=logout).pack(fill="both", expand=True)

    def logout():
        for w in root.winfo_children():
            w.destroy()
        LoginFrame(root, show_main).pack(fill="both", expand=True)

    LoginFrame(root, show_main).pack(fill="both", expand=True)
    root.mainloop()


if __name__ == "__main__":
    main()
