from datetime import datetime, timedelta

from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import (
    QDateTimeEdit, QDialog, QFileDialog, QPlainTextEdit, QProgressBar, QSpinBox, QVBoxLayout,
)

from petcare.services.reports import save_report
from petcare.services.scoring import normalize_plan
from .widgets import Form, TASK_TYPES, button, combo, field, formatted_day, label, table, table_row


def signup(window):
    form = Form(window, "Аккаунт ашу")
    name, email = field(), field(placeholder="name@example.com")
    password, repeat = field(secret=True), field(secret=True)
    for title, item in [("Аты-жөні", name), ("Электрондық пошта", email),
                        ("Құпиясөз", password), ("Құпиясөзді қайталаңыз", repeat)]:
        form.fields.addRow(title, item)

    def save():
        if password.text() != repeat.text():
            raise ValueError("Құпиясөздер сәйкес келмейді.")
        window.store.register(name.text(), email.text(), password.text())

    form.submit("Аккаунт ашу", save)
    if form.exec():
        window.login_page(email=email.text(), notice="Аккаунт ашылды. Құпиясөзіңізбен кіріңіз.")


def reset(window):
    from petcare.mail import send_reset_code

    form = Form(window, "Құпиясөзді қалпына келтіру")
    email, code, password = field(), field(), field(secret=True)
    form.fields.addRow("Электрондық пошта", email)

    def send():
        window.store.request_reset(email.text(), send_reset_code)
        form.error.setText("Осы пошта тіркелген болса, код келеді.")

    form.fields.addRow("", button("Код жіберу", lambda: window.run(send)))
    form.fields.addRow("Поштадағы код", code)
    form.fields.addRow("Жаңа құпиясөз", password)
    form.submit("Құпиясөзді жаңарту", lambda: window.store.reset_password(
        email.text(), code.text(), password.text()))
    if form.exec():
        window.login_page(email=email.text(), notice="Құпиясөз өзгерді.")


def profile(window):
    user = window.store.profile(window.session)
    form = Form(window, "Жеке профиль")
    name, email = field(user["name"]), field(user["email"])
    form.fields.addRow("Аты-жөні", name)
    form.fields.addRow("Электрондық пошта", email)
    form.submit("Сақтау", lambda: window.store.update_profile(window.session, name.text(), email.text()))
    if form.exec():
        window.home()


def password_change(window):
    form = Form(window, "Құпиясөзді өзгерту")
    old, new = field(secret=True), field(secret=True)
    form.fields.addRow("Қазіргі құпиясөз", old)
    form.fields.addRow("Жаңа құпиясөз", new)
    form.submit("Өзгерту", lambda: window.store.change_password(window.session, old.text(), new.text()))
    if form.exec():
        window.sign_out()


def care(window):
    pets = window.store.list_pets(window.session, sort="id")
    if not pets:
        window.notice("Алдымен жануарды тіркеңіз.")
        return
    form = Form(window, "Күтім тапсырмасын қосу")
    pet = combo((p["id"], p["name"]) for p in pets)
    kind = combo(TASK_TYPES.items())
    title = field(placeholder="Мысалы, кешкі ас")
    when = QDateTimeEdit()
    when.setCalendarPopup(True)
    when.setDisplayFormat("dd.MM.yyyy HH:mm")
    when.setDateTime(QDateTime(window.clock()))
    for name, item in [("Жануар", pet), ("Күтім түрі", kind), ("Тапсырма", title), ("Күні мен уақыты", when)]:
        form.fields.addRow(name, item)
    form.submit("Сақтау", lambda: window.store.schedule_task(window.session, pet.currentData(), {
        "task_type": kind.currentData(), "title": title.text().strip() or kind.currentText(),
        "scheduled_at": when.dateTime().toPython().isoformat(timespec="minutes")}))
    if form.exec():
        window.home()


def compare(window):
    form = Form(window, "Күтім жоспарларын салыстыру")
    form.resize(660, 640)
    available = QSpinBox()
    available.setObjectName("availableMinutes")
    available.setRange(0, 1440)
    available.setSuffix(" мин")
    available.setValue(30)
    desired = QSpinBox()
    desired.setObjectName("targetCareCount")
    desired.setRange(1, 50)
    desired.setValue(2)
    form.fields.addRow("Күніне бос уақыт", available)
    form.fields.addRow("Күніне қажетті күтім саны", desired)
    grid = table(["Жоспар", "Қажетті уақыт", "Күніне күтім"])
    grid.setObjectName("planInputs")
    grid.setMinimumHeight(143)
    form.layout_.addWidget(grid)
    result = QPlainTextEdit()
    result.setObjectName("planScores")
    result.setReadOnly(True)
    form.layout_.addWidget(label("Уақыт сәйкестігі = бос уақыт / қажетті уақыт. Жиілік = жоспарланған / қажетті күтім. Екі көрсеткіштің де ең жоғары мәні — 1.", "hint", True))

    def add_plan():
        index = grid.rowCount()
        name = ("А жоспары", "Б жоспары")[index] if index < 2 else f"№{index + 1} жоспар"
        row = table_row(grid, [name, "", ""])
        time_box, count_box = QSpinBox(), QSpinBox()
        time_box.setRange(1, 1440)
        time_box.setSuffix(" мин")
        time_box.setValue(60 if index == 1 else 30)
        count_box.setRange(0, 50)
        count_box.setValue(2 if index == 1 else 1)
        count_box.setSuffix(" рет")
        grid.setCellWidget(row, 1, time_box)
        grid.setCellWidget(row, 2, count_box)
        time_box.valueChanged.connect(update)
        count_box.valueChanged.connect(update)
        if grid.rowCount() >= 2:
            update()

    def update():
        plans = [normalize_plan({"name": grid.item(i, 0).text(), "available_minutes": available.value(),
                                 "required_minutes": grid.cellWidget(i, 1).value(),
                                 "planned_count": grid.cellWidget(i, 2).value(), "target_count": desired.value()})
                 for i in range(grid.rowCount())]
        ranked = window.rank_plans(plans, (0.6, 0.4))
        leaders = [p["name"] for p in ranked if p["score"] == ranked[0]["score"]]
        prefix = "Тең нәтиже" if len(leaders) > 1 else "Ұсынылған жоспар"
        lines = [prefix + " — " + ", ".join(leaders), ""]
        for p in ranked:
            time_points = p.get("time_points", p["time_fit"] * 60)
            frequency_points = p.get("frequency_points", p["frequency_fit"] * 40)
            tied = p.get("tied")
            if tied is None:
                tied = sum(other["score"] == p["score"] for other in ranked) > 1
            lines.append(f"{p['name']} · {p['score']:.8g}/100" + (" · Тең нәтиже" if tied else ""))
            lines.append(f"Уақыт {p['time_fit']:.2f} × 60 = {time_points:.2f}, "
                         f"жиілік {p['frequency_fit']:.2f} × 40 = {frequency_points:.2f}")
        result.setPlainText("\n".join(lines))

    add_plan()
    add_plan()
    available.valueChanged.connect(update)
    desired.valueChanged.connect(update)
    form.layout_.addWidget(button("+  Жоспар қосу", add_plan))
    form.layout_.addWidget(result)
    form.layout_.addWidget(button("Жабу", form.accept))
    form.exec()


def history(window):
    dialog = QDialog(window)
    dialog.setWindowTitle("Әрекеттер тарихы")
    dialog.resize(780, 450)
    layout = QVBoxLayout(dialog)
    search = field(placeholder="Күн немесе әрекет бойынша іздеу")
    layout.addWidget(search)
    grid = table(["Уақыт", "Әрекет", "Мәлімет"])
    layout.addWidget(grid)

    def filter_rows():
        grid.setRowCount(0)
        for r in window.store.history(window.session, search.text()):
            time = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")).astimezone()
            values = [time.strftime("%d.%m.%Y %H:%M"), r["action"], r["detail"]]
            table_row(grid, values)

    search.textChanged.connect(lambda: window.run(filter_rows))
    filter_rows()
    dialog.exec()


def reminders(window):
    form = Form(window, "Күтім еске салғыштары")
    form.resize(700, 410)
    period = combo([(1, "Келесі 24 сағат"), (7, "Келесі 7 күн"), (None, "Барлық алдағы күтім")])
    form.fields.addRow("Уақыт аралығы", period)
    grid = table(["Күні мен уақыты", "Жануар", "Тапсырма"])
    form.layout_.addWidget(grid)
    count = label("", "hint")
    form.layout_.addWidget(count)

    def refresh():
        now = window.clock()
        days = period.currentData()
        until = now + timedelta(days=days) if days else None
        rows = window.store.reminders(window.session, now, until)
        grid.setRowCount(0)
        for row in rows:
            when = datetime.fromisoformat(row["scheduled_at"]).strftime("%d.%m.%Y %H:%M")
            table_row(grid, [when, row["pet_name"], row["title"]])
        count.setText(f"Алдағы тапсырмалар саны: {len(rows)}" if rows else "Бұл кезеңде жоспарланған күтім жоқ.")

    period.currentIndexChanged.connect(lambda: window.run(refresh))
    refresh()
    form.layout_.addWidget(button("Жабу", form.accept))
    form.exec()


def export(window):
    preview = QDialog(window)
    preview.setWindowTitle("Күтім есебі")
    preview.resize(780, 460)
    layout = QVBoxLayout(preview)
    layout.addWidget(label("Есеп пішімі", "hint"))
    formats = combo([("csv", "CSV · электрондық кесте"), ("json", "JSON · құрылымдалған дерек")])
    formats.setObjectName("reportFormat")
    layout.addWidget(formats)
    layout.addWidget(label("Файлдың алдын ала көрінісі", "hint"))
    contents = QPlainTextEdit()
    contents.setObjectName("reportPreview")
    contents.setReadOnly(True)
    layout.addWidget(contents)
    payload = None

    def refresh():
        nonlocal payload
        payload = None
        contents.clear()
        payload = window.store.export_report(window.session, file_format=formats.currentData())
        contents.setPlainText(payload.decode("utf-8-sig"))

    def save():
        if payload is None:
            raise ValueError("Есепті қайта құрастырыңыз.")
        ext = formats.currentData()
        name, _ = QFileDialog.getSaveFileName(preview, "Күтім есебін сақтау", f"petcare.{ext}",
                                              f"{ext.upper()} (*.{ext})")
        if not name:
            return
        path = save_report(name, payload, ext)
        preview.accept()
        window.notice(f"Күтім есебі сақталды.\n{path}")

    refresh()
    formats.currentIndexChanged.connect(lambda: window.run(refresh))
    layout.addWidget(window.action("Файлды сақтау", save, "primary"))
    preview.exec()


def weekly(window):
    series = window.store.stats(window.session, window.clock().date())["weekly"]
    form = Form(window, "Апталық күтім")
    form.layout_.addWidget(label("Орындалған тапсырмалар / барлығы", "hint"))
    for day in series:
        bar = QProgressBar()
        bar.setRange(0, max(day["planned"], 1))
        bar.setValue(day["done"])
        bar.setFormat(f"{day['done']} / {day['planned']}")
        form.fields.addRow(formatted_day(day["date"]), bar)
    form.layout_.addWidget(button("Жабу", form.accept))
    form.exec()


def email_report(window):
    from petcare.mail import send_report

    form = Form(window, "Күтім есебін жіберу")
    to = field(placeholder="name@example.com")
    form.fields.addRow("Алушының поштасы", to)
    form.layout_.addWidget(label("Хатқа күтім тапсырмаларының CSV есебі тіркеледі.", "hint", True))
    form.submit("Есепті жіберу", lambda: send_report(to.text().strip(), window.store.export_report(window.session)))
    if form.exec():
        window.notice("Есеп поштаға жіберілді.")

