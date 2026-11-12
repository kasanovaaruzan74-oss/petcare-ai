import csv
import io
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QDateTimeEdit, QDialog, QFileDialog, QHBoxLayout, QProgressBar, QSpinBox,
    QVBoxLayout, QWidget,
)

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
    available = QSpinBox()
    available.setRange(1, 1440)
    available.setSuffix(" мин")
    available.setValue(30)
    desired = QSpinBox()
    desired.setRange(1, 50)
    desired.setValue(2)
    form.fields.addRow("Күніне бос уақыт", available)
    form.fields.addRow("Күніне қажетті күтім саны", desired)
    input_rows = []
    for name, time, count in [("А жоспары", 30, 1), ("Б жоспары", 60, 2)]:
        time_box, count_box = QSpinBox(), QSpinBox()
        time_box.setRange(1, 1440)
        time_box.setSuffix(" мин")
        time_box.setValue(time)
        count_box.setRange(1, 50)
        count_box.setValue(count)
        count_box.setSuffix(" рет")
        group = QWidget()
        lay = QHBoxLayout(group)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(time_box)
        lay.addWidget(count_box)
        form.fields.addRow(name, group)
        input_rows.append((name, time_box, count_box))
    result = label("", wrap=True)
    result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    def update():
        plans = [{"name": name, "time_fit": min(1, available.value() / t.value()),
                  "frequency_fit": min(1, c.value() / desired.value())}
                 for name, t, c in input_rows]
        ranked = window.rank_plans(plans, (0.6, 0.4))
        lines = [f"{p['name']}: уақыт {p['time_fit']:.0%} × 60 + жиілік {p['frequency_fit']:.0%} × 40 = {p['score']:.1f} балл"
                 for p in ranked]
        leaders = [p["name"] for p in ranked if abs(p["score"] - ranked[0]["score"]) < 1e-8]
        lines.append("Тең нәтиже." if len(leaders) > 1 else f"Ұсынылған нұсқа — {leaders[0]}.")
        result.setText("\n".join(lines))

    for _, t, c in input_rows:
        t.valueChanged.connect(update)
        c.valueChanged.connect(update)
    available.valueChanged.connect(update)
    desired.valueChanged.connect(update)
    update()
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
    records = window.store.history(window.session)

    def filter_rows():
        grid.setRowCount(0)
        for r in records:
            time = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")).astimezone()
            values = [time.strftime("%d.%m.%Y %H:%M"), r["action"], r["detail"]]
            if search.text().casefold() in " ".join(map(str, values)).casefold():
                table_row(grid, values)

    search.textChanged.connect(filter_rows)
    filter_rows()
    dialog.exec()


def export(window):
    payload = window.store.export_report(window.session)
    rows = csv.reader(io.StringIO(payload.decode("utf-8-sig")))
    preview = QDialog(window)
    preview.setWindowTitle("Күтім есебі")
    preview.resize(780, 460)
    layout = QVBoxLayout(preview)
    grid = table(next(rows))
    for row in rows:
        table_row(grid, row)
    layout.addWidget(grid)

    def save():
        name, _ = QFileDialog.getSaveFileName(preview, "Күтім есебін сақтау", "petcare.csv", "CSV (*.csv)")
        if name:
            Path(name).write_bytes(payload)
            preview.accept()
            window.notice("Күтім есебі сақталды.")

    layout.addWidget(window.action("CSV файлын сақтау", save, "primary"))
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

