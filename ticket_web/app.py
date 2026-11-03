# -*- coding: utf-8 -*-
"""
TicketPro — сайт заказа билетов на мероприятия.
Flask + MySQL (ticket_db). База данных создаётся автоматически при запуске.
"""
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from datetime import datetime
import hashlib
import uuid

import mysql.connector

# ===================== НАСТРОЙКИ ПОДКЛЮЧЕНИЯ =====================
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "1234",   # <-- впишите пароль от вашего MySQL
}
DB_NAME = "ticket_db"

app = Flask(__name__)
app.secret_key = "ticketpro-secret-change-me"

GENRES = {
    "кино": "🎬", "театр": "🎭", "концерт": "🎤",
    "стендап": "😄", "спорт": "⚽", "фестиваль": "🎪",
}

# ===================== ПОДКЛЮЧЕНИЕ К БАЗЕ =====================
def get_db():
    if "db" not in g:
        g.db = mysql.connector.connect(
            host=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_NAME,
        )
    return g.db

def close_db(_e=None):
    db = g.pop("db", None)
    if db:
        db.close()

app.teardown_appcontext(close_db)

def init_db():
    """Создаёт базу, таблицы и демо-данные при запуске сервера."""
    try:
        conn = mysql.connector.connect(
            host=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
        )
    except Exception as e:
        print("ОШИБКА: не удалось подключиться к MySQL.")
        print("Проверьте, запущен ли MySQL и верен ли пароль в DB_CONFIG.")
        print("Подробности:", e)
        raise SystemExit(1)

    cur = conn.cursor()
    cur.execute("CREATE DATABASE IF NOT EXISTS " + DB_NAME +
                " CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cur.execute("USE " + DB_NAME)

    cur.execute("""CREATE TABLE IF NOT EXISTS venues (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        address TEXT,
        city VARCHAR(100),
        capacity INT CHECK (capacity > 0)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    cur.execute("""CREATE TABLE IF NOT EXISTS categories (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100) NOT NULL UNIQUE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        email VARCHAR(255) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        full_name VARCHAR(255),
        phone VARCHAR(50),
        role VARCHAR(20) DEFAULT 'customer',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    cur.execute("""CREATE TABLE IF NOT EXISTS events (
        id INT AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        description TEXT,
        event_date DATETIME NOT NULL,
        venue_id INT NOT NULL,
        status VARCHAR(20) DEFAULT 'active',
        FOREIGN KEY (venue_id) REFERENCES venues(id) ON DELETE CASCADE,
        INDEX idx_events_date (event_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    cur.execute("""CREATE TABLE IF NOT EXISTS event_categories (
        event_id INT NOT NULL,
        category_id INT NOT NULL,
        PRIMARY KEY (event_id, category_id),
        FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
        FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    cur.execute("""CREATE TABLE IF NOT EXISTS ticket_types (
        id INT AUTO_INCREMENT PRIMARY KEY,
        event_id INT NOT NULL,
        name VARCHAR(100) NOT NULL,
        price DECIMAL(10,2) NOT NULL CHECK (price >= 0),
        total_seats INT NOT NULL,
        FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    cur.execute("""CREATE TABLE IF NOT EXISTS tickets (
        id INT AUTO_INCREMENT PRIMARY KEY,
        event_id INT NOT NULL,
        ticket_type_id INT NOT NULL,
        seat_row VARCHAR(10),
        seat_number VARCHAR(10),
        status VARCHAR(20) DEFAULT 'free',
        qr_code VARCHAR(64) UNIQUE,
        UNIQUE KEY uniq_seat (event_id, seat_row, seat_number),
        FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
        FOREIGN KEY (ticket_type_id) REFERENCES ticket_types(id),
        INDEX idx_tickets_event_status (event_id, status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    cur.execute("""CREATE TABLE IF NOT EXISTS orders (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        total_price DECIMAL(12,2) NOT NULL,
        status VARCHAR(20) DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id),
        INDEX idx_orders_user (user_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    cur.execute("""CREATE TABLE IF NOT EXISTS order_items (
        id INT AUTO_INCREMENT PRIMARY KEY,
        order_id INT NOT NULL,
        ticket_id INT NOT NULL,
        price DECIMAL(10,2) NOT NULL,
        FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
        FOREIGN KEY (ticket_id) REFERENCES tickets(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    # ---- Демо-данные, только если афиша пуста ----
    cur.execute("SELECT COUNT(*) FROM events")
    if cur.fetchone()[0] == 0:
        venues_data = [
            ("Кинотеатр «Родина»", "ул. Крестовая, 39", "Ярославль", 300),
            ("Театр драмы им. Волкова", "пл. Свободы, 1", "Ярославль", 200),
            ("Клуб «Молния»", "ул. Свободы, 32", "Ярославль", 250),
            ("Арена «Ярославль»", "ул. Труфаева, 13", "Ярославль", 900),
            ("Летний амфитеатр", "Волжская набережная", "Ярославль", 500),
        ]
        for v in venues_data:
            cur.execute("INSERT INTO venues (name, address, city, capacity) VALUES (%s,%s,%s,%s)", v)

        cats = ["кино", "театр", "концерт", "стендап", "спорт", "фестиваль"]
        for c in cats:
            cur.execute("INSERT INTO categories (name) VALUES (%s)", (c,))
        cat_ids = {c: i + 1 for i, c in enumerate(cats)}

        events_data = [
            ("Интерстеллар", "Легендарная космическая сага на большом экране.",
             "2026-11-20 18:30", 1, "кино",
             [("Стандарт", 350.00, 6, 10), ("VIP-диван", 550.00, 2, 6)]),
            ("Война и мир", "Классическая постановка по роману Льва Толстого.",
             "2026-11-25 19:00", 2, "театр",
             [("Партер", 800.00, 8, 10), ("Балкон", 500.00, 4, 10)]),
            ("Рок-концерт «Гром»", "Электрическая ночь с лучшими каверами.",
             "2026-11-28 20:00", 3, "концерт",
             [("Танцпол", 1200.00, 10, 15), ("Балкон", 900.00, 3, 10)]),
            ("Стендап «Полный смех»", "Вечер монологов лучших резидентов.",
             "2026-12-02 19:30", 3, "стендап",
             [("Обычный", 700.00, 8, 12), ("VIP-столик", 1500.00, 2, 8)]),
            ("Хоккей: «Полёт» — «Мотор»", "Принципиальное дерби в высшей лиге.",
             "2026-12-05 17:00", 4, "спорт",
             [("Сектор А", 600.00, 12, 20), ("Сектор Б", 600.00, 12, 20)]),
            ("Джаз-фестиваль «Осенний свинг»", "Открытая сцена у Волги.",
             "2026-12-10 16:00", 5, "фестиваль",
             [("Общая зона", 400.00, 15, 20), ("Фан-зона", 700.00, 5, 10)]),
        ]
        for title, desc, dt, vid, cat, types in events_data:
            cur.execute(
                "INSERT INTO events (title, description, event_date, venue_id) VALUES (%s,%s,%s,%s)",
                (title, desc, dt, vid),
            )
            eid = cur.lastrowid
            cur.execute("INSERT INTO event_categories (event_id, category_id) VALUES (%s,%s)",
                        (eid, cat_ids[cat]))
            for tname, price, rows, cols in types:
                cur.execute(
                    "INSERT INTO ticket_types (event_id, name, price, total_seats) VALUES (%s,%s,%s,%s)",
                    (eid, tname, price, rows * cols),
                )
                tt_id = cur.lastrowid
                for r in range(rows):
                    for cnum in range(cols):
                        row_letter = chr(ord("А") + r) if r < 32 else str(r)
                        cur.execute(
                            "INSERT INTO tickets (event_id, ticket_type_id, seat_row, seat_number) "
                            "VALUES (%s,%s,%s,%s)",
                            (eid, tt_id, row_letter, str(cnum + 1)),
                        )
        print("Демо-данные добавлены: 6 мероприятий.")

    conn.commit()
    cur.close()
    conn.close()
    print("База данных проверена/создана:", DB_NAME)

# ===================== ХЕЛПЕРЫ =====================
def hash_password(password: str) -> str:
    salt = "ticketpro_salt"
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT id, email, full_name, role FROM users WHERE id=%s", (uid,))
    u = cur.fetchone()
    cur.close()
    return u

def now_year():
    return datetime.now().year

app.jinja_env.globals["now_year"] = now_year
app.jinja_env.globals["GENRES"] = GENRES

# ===================== МАРШРУТЫ =====================
@app.route("/")
def index():
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT e.id, e.title, e.description, e.event_date,
               v.name AS venue_name, v.city,
               (SELECT MIN(t.price) FROM ticket_types t WHERE t.event_id = e.id) AS min_price,
               (SELECT c.name FROM event_categories ec
                 JOIN categories c ON c.id = ec.category_id
                 WHERE ec.event_id = e.id LIMIT 1) AS category
        FROM events e
        JOIN venues v ON v.id = e.venue_id
        WHERE e.status = 'active'
        ORDER BY e.event_date
    """)
    events = cur.fetchall()
    cur.close()
    for ev in events:
        ev["icon"] = GENRES.get(ev.get("category", ""), "🎟")
    return render_template("index.html", events=events, user=current_user())

@app.route("/auth", methods=["GET", "POST"])
def auth():
    if request.method == "POST":
        mode = request.form.get("mode", "login")
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        db = get_db()
        cur = db.cursor(dictionary=True)

        if mode == "register":
            full_name = (request.form.get("full_name") or "").strip()
            if "@" not in email or "." not in email.split("@")[-1]:
                cur.close()
                return render_template("auth.html", error="Введите корректный e-mail", mode=mode, user=None)
            if len(password) < 6:
                cur.close()
                return render_template("auth.html", error="Пароль должен быть не короче 6 символов", mode=mode, user=None)
            cur.execute("SELECT id FROM users WHERE email=%s", (email,))
            if cur.fetchone():
                cur.close()
                return render_template("auth.html", error="Пользователь с таким e-mail уже зарегистрирован", mode=mode, user=None)
            cur.execute(
                "INSERT INTO users (email, password_hash, full_name) VALUES (%s,%s,%s)",
                (email, hash_password(password), full_name),
            )
            db.commit()
            session["uid"] = cur.lastrowid
            cur.close()
            return redirect(url_for("index"))
        else:
            cur.execute("SELECT * FROM users WHERE email=%s", (email,))
            u = cur.fetchone()
            cur.close()
            if not u:
                return render_template("auth.html", error="Пользователь не найден", mode=mode, user=None)
            if u["password_hash"] != hash_password(password):
                return render_template("auth.html", error="Неверный пароль", mode=mode, user=None)
            session["uid"] = u["id"]
            return redirect(url_for("index"))

    return render_template("auth.html", mode=request.args.get("mode", "login"), user=None)

@app.route("/logout")
def logout():
    session.pop("uid", None)
    return redirect(url_for("index"))

@app.route("/event/<int:eid>")
def event(eid):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT e.*, v.name AS venue_name, v.city
        FROM events e JOIN venues v ON v.id = e.venue_id
        WHERE e.id=%s AND e.status='active'
    """, (eid,))
    ev = cur.fetchone()
    if not ev:
        return redirect(url_for("index"))
    cur.execute("""
        SELECT c.name AS category FROM event_categories ec
        JOIN categories c ON c.id = ec.category_id
        WHERE ec.event_id = %s
    """, (eid,))
    cats = cur.fetchall()
    ev["category"] = cats[0]["category"] if cats else ""
    ev["icon"] = GENRES.get(ev.get("category", ""), "🎟")

    cur.execute("SELECT * FROM ticket_types WHERE event_id=%s ORDER BY id", (eid,))
    types = cur.fetchall()
    seats = {}
    for t in types:
        cur.execute("SELECT * FROM tickets WHERE ticket_type_id=%s ORDER BY seat_row, seat_number", (t["id"],))
        seats[t["id"]] = cur.fetchall()
    cur.close()
    return render_template("event.html", event=ev, types=types, seats=seats, user=current_user())

@app.route("/book/<int:eid>", methods=["POST"])
def book(eid):
    u = current_user()
    if not u:
        return redirect(url_for("auth", next=request.path))
    selected = request.form.getlist("seats")   # ids билетов, до 6
    if not selected:
        flash("Выберите хотя бы одно место", "error")
        return redirect(url_for("event", eid=eid))
    if len(selected) > 6:
        flash("Максимум 6 билетов за заказ", "error")
        return redirect(url_for("event", eid=eid))

    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("START TRANSACTION")
    fmt = ",".join(["%s"] * len(selected))
    cur.execute("SELECT * FROM tickets WHERE id IN (" + fmt + ") AND event_id=%s FOR UPDATE",
                tuple(selected) + (eid,))
    rows = cur.fetchall()

    ok = [r for r in rows if r["status"] == "free"]
    if len(ok) != len(selected):
        db.rollback()
        cur.close()
        flash("Часть мест уже занята — выберите другие", "error")
        return redirect(url_for("event", eid=eid))

    total = 0.0
    prices = {}
    for r in ok:
        cur.execute("SELECT price FROM ticket_types WHERE id=%s", (r["ticket_type_id"],))
        p = cur.fetchone()["price"]
        prices[r["id"]] = p
        total += float(p)

    cur.execute("INSERT INTO orders (user_id, total_price) VALUES (%s,%s)", (u["id"], total))
    order_id = cur.lastrowid
    for r in ok:
        cur.execute(
            "INSERT INTO order_items (order_id, ticket_id, price) VALUES (%s,%s,%s)",
            (order_id, r["id"], prices[r["id"]]),
        )
        qr = uuid.uuid4().hex
        cur.execute("UPDATE tickets SET status='reserved', qr_code=%s WHERE id=%s", (qr, r["id"]))
    db.commit()
    cur.close()
    flash("Заказ создан! Оплатите его в разделе «Мои заказы»", "success")
    return redirect(url_for("orders"))

@app.route("/orders")
def orders():
    u = current_user()
    if not u:
        return redirect(url_for("auth", next=request.path))
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM orders WHERE user_id=%s ORDER BY id DESC", (u["id"],))
    ords = cur.fetchall()
    for o in ords:
        cur.execute("""
            SELECT oi.price, t.seat_row, t.seat_number, t.qr_code, tt.name AS type_name,
                   e.title AS event_title
            FROM order_items oi
            JOIN tickets t ON t.id = oi.ticket_id
            JOIN ticket_types tt ON tt.id = t.ticket_type_id
            JOIN events e ON e.id = t.event_id
            WHERE oi.order_id=%s
        """, (o["id"],))
        o["positions"] = cur.fetchall()
    cur.close()
    return render_template("orders.html", orders=ords, user=current_user())

@app.route("/pay/<int:oid>", methods=["POST"])
def pay(oid):
    u = current_user()
    if not u:
        return redirect(url_for("auth", next=request.path))
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM orders WHERE id=%s AND user_id=%s", (oid, u["id"]))
    o = cur.fetchone()
    if o and o["status"] == "pending":
        cur.execute("UPDATE orders SET status='paid' WHERE id=%s", (oid,))
        cur.execute("""
            UPDATE tickets t JOIN order_items oi ON oi.ticket_id = t.id
            SET t.status='sold' WHERE oi.order_id=%s
        """, (oid,))
        db.commit()
        flash("Заказ оплачен ✅", "success")
    cur.close()
    return redirect(url_for("orders"))

@app.route("/cancel/<int:oid>", methods=["POST"])
def cancel(oid):
    u = current_user()
    if not u:
        return redirect(url_for("auth", next=request.path))
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM orders WHERE id=%s AND user_id=%s", (oid, u["id"]))
    o = cur.fetchone()
    if o and o[3] == "pending":
        cur.execute("UPDATE orders SET status='cancelled' WHERE id=%s", (oid,))
        cur.execute("""
            UPDATE tickets t JOIN order_items oi ON oi.ticket_id = t.id
            SET t.status='free', t.qr_code=NULL WHERE oi.order_id=%s
        """, (oid,))
        db.commit()
        flash("Заказ отменён, места вернулись в продажу", "success")
    cur.close()
    return redirect(url_for("orders"))

@app.route("/admin", methods=["GET", "POST"])
def admin():
    u = current_user()
    if not u:
        return redirect(url_for("auth", next=request.path))
    if u.get("role") != "admin":
        return "Доступ только для администратора", 403

    db = get_db()
    if request.method == "POST":
        act = request.form.get("action")
        cur = db.cursor()
        if act == "add_venue":
            cur.execute("INSERT INTO venues (name, address, city, capacity) VALUES (%s,%s,%s,%s)",
                        (request.form["name"], request.form.get("address"),
                         request.form.get("city"), request.form.get("capacity") or 100))
            flash("Площадка добавлена", "success")
        elif act == "add_event":
            cur.execute("INSERT INTO events (title, description, event_date, venue_id) VALUES (%s,%s,%s,%s)",
                        (request.form["title"], request.form.get("description"),
                         request.form["event_date"], request.form["venue_id"]))
            eid = cur.lastrowid
            cat = request.form.get("category")
            if cat:
                cur.execute("SELECT id FROM categories WHERE name=%s", (cat,))
                row = cur.fetchone()
                if row:
                    cur.execute("INSERT INTO event_categories (event_id, category_id) VALUES (%s,%s)",
                                (eid, row[0]))
            flash("Мероприятие добавлено", "success")
        elif act == "add_type":
            cur.execute("INSERT INTO ticket_types (event_id, name, price, total_seats) VALUES (%s,%s,%s,%s)",
                        (request.form["event_id"], request.form["tname"],
                         request.form["price"], request.form["total_seats"]))
            tt = cur.lastrowid
            rows_n = int(request.form["rows"])
            cols_n = int(request.form["cols"])
            for r in range(rows_n):
                for c in range(cols_n):
                    row_letter = chr(ord("А") + r) if r < 32 else str(r)
                    cur.execute(
                        "INSERT INTO tickets (event_id, ticket_type_id, seat_row, seat_number) "
                        "VALUES (%s,%s,%s,%s)",
                        (request.form["event_id"], tt, row_letter, str(c + 1)),
                    )
            flash("Тип билета добавлен, места созданы", "success")
        db.commit()
        cur.close()

    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM venues ORDER BY id")
    venues = cur.fetchall()
    cur.execute("SELECT * FROM categories ORDER BY id")
    cats = cur.fetchall()
    cur.execute("SELECT e.*, v.name AS venue_name FROM events e JOIN venues v ON v.id=e.venue_id ORDER BY e.id DESC")
    events = cur.fetchall()
    cur.close()
    return render_template("admin.html", user=u, venues=venues, cats=cats, events=events)

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
