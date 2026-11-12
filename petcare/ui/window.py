"""Desktop workspace and navigation. Feature services are passed in by the launcher."""
from datetime import datetime
from sqlite3 import Error as DatabaseError

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox, QScrollArea,
    QVBoxLayout, QWidget,
)

from petcare.ai.intent import classify_intent as predict_intent
from petcare.services.scoring import rank_plans as score_plans
from . import dialogs
from .widgets import ASSETS, button, field, formatted_time, icon, label, panel, rule

PAGES = (("home", "Негізгі бет"), ("pets", "Жануарларым"),
         ("add", "Жануар қосу"), ("ai", "Ақылды көмекші"))
MONTHS = ("қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым", "шілде", "тамыз", "қыркүйек", "қазан", "қараша", "желтоқсан")
DAYS = ("дүйсенбі", "сейсенбі", "сәрсенбі", "бейсенбі", "жұма", "сенбі", "жексенбі")


class MainWindow(QMainWindow):
    def __init__(self, store, session=None, clock=datetime.now, rank_plans=None,
                 classify_intent=None, demo=False):
        super().__init__()
        self.store = store
        self.session = session
        self.clock = clock
        self.demo = demo
        self.rank_plans = rank_plans or score_plans
        self.classify_intent = classify_intent or predict_intent
        self.setWindowTitle("PetCare AI")
        self.setWindowIcon(QIcon(str(ASSETS / "brand.svg")))
        self.resize(1280, 820)
        self.setMinimumSize(940, 650)
        bundled_font = ASSETS / "fonts" / "Inter.ttf"
        if bundled_font.is_file() and "Inter" not in QFontDatabase.families():
            QFontDatabase.addApplicationFont(str(bundled_font))
        theme = (ASSETS / "theme.qss").read_text(encoding="utf-8")
        self.setStyleSheet(theme.replace("{ASSETS}", ASSETS.as_posix()))
        if session is None:
            self.login_page()
        else:
            self.home()

    def notice(self, message):
        QMessageBox.information(self, "PetCare AI", message)

    def run(self, fn):
        try:
            return fn()
        except DatabaseError:
            self.notice("Деректер базасын ашу немесе жазу мүмкін болмады.")
        except (ValueError, RuntimeError, PermissionError, OSError) as exc:
            self.notice(str(exc))

    def action(self, title, callback, role=""):
        return button(title, lambda: self.run(callback), role)

    def login_page(self, email="", notice=""):
        self.session = None
        page = QWidget()
        root = QVBoxLayout(page)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card, form = panel()
        card.setFixedWidth(420)
        logo = QLabel()
        logo.setPixmap(QIcon(str(ASSETS / "brand.svg")).pixmap(48, 48))
        form.addWidget(logo)
        form.addWidget(label("PetCare AI", "title"))
        form.addWidget(label("Жеке аккаунтқа кіру", "heading"))
        mail = field(email, "name@example.com")
        mail.setObjectName("loginEmail")
        password = field(secret=True)
        password.setObjectName("loginPassword")
        form.addWidget(label("Электрондық пошта", "hint"))
        form.addWidget(mail)
        form.addWidget(label("Құпиясөз", "hint"))
        form.addWidget(password)
        status = label(notice, "hint", True)
        status.setObjectName("loginMessage")
        form.addWidget(status)

        def enter():
            if not mail.text().strip() or not password.text():
                status.setText("Электрондық пошта мен құпиясөзді енгізіңіз.")
                (mail if not mail.text().strip() else password).setFocus()
                return
            try:
                self.session = self.store.login(mail.text(), password.text())
            except ValueError as exc:
                status.setText(str(exc))
                return
            self.home()

        form.addWidget(self.action("Кіру", enter, "primary"))
        password.returnPressed.connect(lambda: self.run(enter))
        form.addWidget(self.action("Аккаунт ашу", lambda: dialogs.signup(self)))
        form.addWidget(self.action("Құпиясөзді ұмыттым", lambda: dialogs.reset(self)))
        root.addWidget(card)
        self.setCentralWidget(page)

    def sign_out(self):
        if self.session:
            self.store.logout(self.session)
        self.demo = False
        self.login_page()

    def closeEvent(self, event):
        if self.session:
            self.store.logout(self.session)
            self.session = None
        super().closeEvent(event)

    def account_menu(self, anchor):
        menu = QMenu(self)
        for title, callback in [("Жеке профиль", dialogs.profile), ("Құпиясөзді өзгерту", dialogs.password_change),
                                ("Күтім жоспарларын салыстыру", dialogs.compare), ("Апталық күтім", dialogs.weekly),
                                ("Күтім еске салғыштары", dialogs.reminders),
                                ("Әрекеттер тарихы", dialogs.history),
                                ("Есепті сақтау", dialogs.export), ("Есепті поштаға жіберу", dialogs.email_report)]:
            action = menu.addAction(title)
            action.triggered.connect(lambda checked=False, func=callback: self.run(lambda: func(self)))
        menu.addSeparator()
        menu.addAction("Аккаунттан шығу", self.sign_out)
        menu.exec(anchor.mapToGlobal(anchor.rect().topRight()))

    def workspace(self, section, title, subtitle, header_button=None):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        rail = QFrame()
        rail.setObjectName("sidebar")
        rail.setFixedWidth(224)
        rail_lay = QVBoxLayout(rail)
        rail_lay.setContentsMargins(12, 32, 12, 24)
        rail_lay.setSpacing(8)
        brand = QHBoxLayout()
        brand.setContentsMargins(12, 0, 0, 0)
        logo = QLabel()
        logo.setPixmap(QIcon(str(ASSETS / "brand.svg")).pixmap(36, 36))
        brand.addWidget(logo)
        brand_name = label("PetCare")
        brand_name.setStyleSheet("font-size:25px;font-weight:bold")
        brand.addWidget(brand_name)
        brand.addWidget(label("AI", "accent"))
        brand.addStretch()
        rail_lay.addLayout(brand)
        rail_lay.addSpacing(19)
        rail_lay.addWidget(rule())
        rail_lay.addSpacing(20)
        callbacks = (self.home, self.registry, self.pet_form, self.assistant)
        for (key, caption), func in zip(PAGES, callbacks):
            selected = key == section
            b = self.action("  " + caption, func, "active" if selected else "nav")
            b.setIcon(icon(key, "#74DFCB" if selected else "#B4C2C4"))
            b.setIconSize(QSize(20, 20))
            b.setFixedHeight(46)
            rail_lay.addWidget(b)
        rail_lay.addStretch()
        rail_lay.addWidget(rule())
        username = self.store.profile(self.session)["name"]
        account = button(username + "   ···", role="nav")
        account.setAccessibleName("Жеке аккаунт және басқа әрекеттер")
        account.setToolTip("Профиль, жоспарларды салыстыру, тарих, есеп, аккаунттан шығу")
        account.clicked.connect(lambda: self.account_menu(account))
        rail_lay.addWidget(account)
        rail_lay.addWidget(label("    Жеке аккаунт", "hint"))
        layout.addWidget(rail)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        content = QVBoxLayout(container)
        content.setContentsMargins(40, 29, 40, 32)
        content.setSpacing(0)
        content.setAlignment(Qt.AlignmentFlag.AlignTop)
        content.addWidget(label("PetCare AI   /   " + title, "hint"))
        content.addSpacing(24)
        head = QHBoxLayout()
        head.addWidget(label(title, "title"))
        head.addStretch()
        if header_button:
            header_button.setMinimumWidth(184)
            head.addWidget(header_button)
        content.addLayout(head)
        content.addSpacing(5)
        content.addWidget(label(subtitle, "hint"))
        content.addSpacing(40)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)
        self.setCentralWidget(page)
        return content

    def home(self):
        now = self.clock()
        day = now.date()
        caption = f"{day.day} {MONTHS[day.month-1]} {day.year}, {DAYS[day.weekday()]}"
        content = self.workspace("home", "Негізгі бет", caption,
                                 self.action("+  Жануар қосу", self.pet_form, "primary"))
        stats = self.store.stats(self.session, day)
        cards = QHBoxLayout()
        cards.setSpacing(14)
        for idx, (name, value) in enumerate([
            ("Жануарлар", stats["pet_count"]), ("Бүгінгі тапсырмалар", stats["task_count"]),
            ("Орындалды", f"{stats['done_count']} / {stats['task_count']}")]):
            box, lay = panel("feature" if idx == 0 else "panel")
            box.setMinimumHeight(125)
            card_header = QHBoxLayout()
            card_header.addWidget(label(name, "hint"), 1)
            symbol = QLabel()
            symbol.setPixmap(icon(("pets", "calendar", "check")[idx], "#74DFCB").pixmap(22, 22))
            card_header.addWidget(symbol)
            lay.addLayout(card_header)
            number = label(value, "metric")
            if idx == 0:
                number.setStyleSheet("color:#74DFCB")
            lay.addWidget(number)
            cards.addWidget(box, 1)
        content.addLayout(cards)
        content.addSpacing(27)
        detail = QHBoxLayout()
        detail.setSpacing(20)
        care, tasks_lay = panel()
        care.setMinimumHeight(395)
        caption = QHBoxLayout()
        caption.addWidget(label("Бүгінгі күтім", "heading"))
        caption.addStretch()
        caption.addWidget(self.action("+ Тапсырма", lambda: dialogs.care(self)))
        tasks_lay.addLayout(caption)
        tasks = self.store.tasks(self.session)
        today = sorted((t for t in tasks if t["scheduled_at"][:10] == day.isoformat()), key=lambda t:t["scheduled_at"])
        if not today:
            tasks_lay.addWidget(label("Бүгінге тапсырма жоспарланбаған.", "hint"))
        for item in today:
            tasks_lay.addWidget(rule())
            row = QHBoxLayout()
            row.addWidget(label(formatted_time(item["scheduled_at"])))
            row.addSpacing(15)
            col = QVBoxLayout()
            col.setSpacing(3)
            col.addWidget(label(item["title"]))
            col.addWidget(label(item["pet_name"], "hint"))
            row.addLayout(col, 1)
            if item["status"] == "done":
                row.addWidget(label("Орындалды", "accent"))
            else:
                done_button = self.action("Белгілеу", lambda i=item["id"]: self.complete(i))
                done_button.setIcon(icon("check", "#74DFCB"))
                row.addWidget(done_button)
            tasks_lay.addLayout(row)
        tasks_lay.addStretch()
        detail.addWidget(care, 605)
        vacc, vacc_lay = panel()
        vacc_header = QHBoxLayout()
        vacc_header.addWidget(label("Алдағы вакциналар", "heading"), 1)
        cal = QLabel()
        cal.setPixmap(icon("calendar", "#74DFCB").pixmap(20, 20))
        vacc_header.addWidget(cal)
        vacc_lay.addLayout(vacc_header)
        upcoming = self.store.reminders(self.session, now, task_type="vaccination")
        for task in upcoming:
            vacc_lay.addWidget(rule())
            due = datetime.fromisoformat(task["scheduled_at"])
            vacc_lay.addWidget(label(f"{due.day:02} {MONTHS[due.month-1]}   ·   {task['pet_name']}", "accent"))
            vacc_lay.addWidget(label(task["title"], "hint"))
        if not upcoming:
            vacc_lay.addWidget(label("Жоспарланған вакцинация жоқ.", "hint", True))
        vacc_lay.addStretch()
        vacc_lay.addWidget(self.action("Жануарларды көру", self.registry))
        detail.addWidget(vacc, 351)
        content.addLayout(detail)
        content.addStretch()

    def complete(self, task_id):
        self.store.complete_task(self.session, task_id)
        self.home()

    def registry(self, notice=""):
        from .pets import registry
        registry(self, notice)

    def pet_form(self, record=None):
        from .pets import pet_form
        pet_form(self, record)

    def assistant(self):
        from .assistant import assistant
        assistant(self)

