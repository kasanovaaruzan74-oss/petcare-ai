"""Pet-scoped conversation powered by the intent classifier and the care adviser."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from petcare.ai.adviser import recommend

from .widgets import combo, field, formatted_day, label, panel, rule


TOPICS = {
    "general": "Күтім кестесі",
    "activity": "Ойын және серуен",
    "feeding": "Тамақтандыру",
}
QUICK_QUESTIONS = (
    ("Күтім кестесін қарау", "Күтім кестесінде қандай әрекет бар?"),
    ("Ойын және серуен", "Қашан серуендейміз?"),
    ("Тамақтандыру тәртібі", "Келесі тамақтандыру қашан?"),
)


def assistant(window):
    page = window.workspace("ai", "Ақылды көмекші", "Жануарға күнделікті күтім жасау туралы кеңес")
    pets = window.store.list_pets(window.session, sort="id")
    if not pets:
        page.addWidget(label("Кеңес алу үшін жануарды тіркеңіз.", "hint"))
        page.addWidget(window.action("+  Жануар қосу", window.pet_form, "primary"))
        return

    columns = QHBoxLayout()
    columns.setSpacing(20)
    chat, dialog = panel()
    chat.setMinimumHeight(505)
    dialog.addWidget(label("Күтім туралы сұхбат", "heading"))
    dialog.addWidget(rule())
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setObjectName("conversation")
    transcript = QWidget()
    transcript.setObjectName("transcript")
    messages = QVBoxLayout(transcript)
    messages.setContentsMargins(2, 6, 8, 4)
    messages.setSpacing(14)
    messages.setAlignment(Qt.AlignmentFlag.AlignTop)
    scroll.setWidget(transcript)
    dialog.addWidget(scroll, 1)
    composer = QHBoxLayout()
    question = field(placeholder="Сұрақ жазыңыз…")
    question.setObjectName("adviceQuestion")
    question.setClearButtonEnabled(True)
    composer.addWidget(question, 1)
    dialog.addLayout(composer)
    columns.addWidget(chat, 645)

    aside, controls = panel()
    controls.addWidget(label("Жануар", "heading"))
    pet = combo((p["id"], p["name"]) for p in pets)
    pet.setObjectName("advicePet")
    controls.addWidget(pet)
    pet_detail = label("", "hint", True)
    controls.addWidget(pet_detail)
    controls.addWidget(rule())
    controls.addWidget(label("Дайын сұрақтар", "heading"))
    columns.addWidget(aside, 311)
    page.addLayout(columns)

    welcome = label("Жануарыңыздың күтім кестесі, белсенділігі немесе тамақтануы туралы сұраңыз.", "hint", True)
    messages.addWidget(welcome)

    def reset():
        question.clear()
        while messages.count() > 1:
            item = messages.takeAt(1).widget()
            item.setParent(None)
            item.deleteLater()
        welcome.show()
        selected = pets[pet.currentIndex()]
        pet_detail.setText(f"{selected['species']}   ·   {formatted_day(selected['birth_date'])}")

    def add_line(layout, text, role="", name=""):
        widget = label(text, role, True)
        widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        widget.setObjectName(name)
        layout.addWidget(widget)
        return widget

    def submit(preset=None):
        query = (preset or question.text()).strip()
        if not query:
            question.setFocus()
            return

        welcome.hide()
        turn = QFrame()
        turn.setObjectName("chatTurn")
        reply = QVBoxLayout(turn)
        reply.setContentsMargins(0, 0, 0, 10)
        reply.setSpacing(8)
        bubble = add_line(reply, query, "question")
        bubble.setAlignment(Qt.AlignmentFlag.AlignRight)
        add_line(reply, "PetCare AI", "accent")
        messages.addWidget(turn)
        try:
            intent = window.classify_intent(query)
            topic = intent["intent"]
            if topic == "clarify":
                add_line(reply, "Нақтылау қажет", "accent")
                add_line(reply, intent["reason"], name="adviceResult")
            else:
                advice = recommend(window.store, window.session, pet.currentData(), topic, window.clock())
                add_line(reply, advice["result"], name="adviceResult")
                add_line(reply, f"{TOPICS[topic]}  ·  Модель сенімділігі {intent['confidence']:.0%}", "accent", "intentCategory")
                evidence = ", ".join(intent["evidence"])
                explanation = add_line(reply, "Модельге әсер еткен сөздер: " + evidence, "hint", "intentEvidence")
                explanation.setToolTip(intent["reason"])
                add_line(reply, "Ұсынысқа негіз болған деректер", "accent")
                add_line(reply, advice["input_summary"], "hint", "adviceSummary")
                for record in advice["evidence"]:
                    stamp = record["scheduled_at"]
                    add_line(reply, f"{record['title']} · {formatted_day(stamp)} {stamp[11:16]}", "hint", "adviceRecord")
                add_line(reply, advice["reason"], "hint")
                add_line(reply, advice["limitations"], "hint")
        except (ValueError, RuntimeError, OSError, KeyError):
            # Errors can originate from either model. Keep private internals out of the chat.
            add_line(reply, "Кеңесті дайындау мүмкін болмады. Сұрағыңызды қайта жіберіңіз.", "error", "adviceError")
        else:
            question.clear()
        QTimer.singleShot(0, scroll, lambda: scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum()))

    for caption, query in QUICK_QUESTIONS:
        controls.addWidget(window.action(caption, lambda q=query: submit(q)))
    controls.addStretch()
    pet.currentIndexChanged.connect(reset)
    composer.addWidget(window.action("Жіберу", submit, "primary"))
    question.returnPressed.connect(lambda: window.run(submit))
    reset()
    if window.demo:
        submit(f"{pets[0]['name']} үшін күнделікті күтімді қалай жоспарлаймын?")

