from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout

from petcare.ai.adviser import recommend
from .widgets import combo, field, label, panel, rule


TOPICS = (("general", "Күтім кестесі"), ("feeding", "Тамақтандыру"),
          ("activity", "Ойын және серуен"), ("vaccine", "Вакцина жазбалары"))


def assistant(window):
    page = window.workspace("ai", "Ақылды көмекші", "Жануарға күнделікті күтім жасау туралы кеңес")
    pets = window.store.list_pets(window.session, sort="id")
    if not pets:
        page.addWidget(label("Кеңес алу үшін жануарды тіркеңіз.", "hint"))
        page.addWidget(window.action("+  Жануар қосу",window.pet_form,"primary"))
        return

    columns = QHBoxLayout()
    columns.setSpacing(20)
    chat, dialog = panel()
    chat.setMinimumHeight(500)
    dialog.addWidget(label("Күтім туралы сұхбат","heading"))
    dialog.addWidget(rule())
    asked = label("",wrap=True)
    asked.setAlignment(Qt.AlignmentFlag.AlignRight)
    dialog.addWidget(asked)
    dialog.addWidget(label("PetCare AI","accent"))
    answer = label("", wrap=True)
    answer.setObjectName("adviceResult")
    reason = label("", "hint", True)
    detail = label("","accent",True)
    limit = label("","hint",True)
    for widget in (answer, reason, detail, limit):
        widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        dialog.addWidget(widget)
    dialog.addStretch()
    composer = QHBoxLayout()
    question = field(placeholder="Сұрақ жазыңыз…")
    question.setObjectName("adviceQuestion")
    composer.addWidget(question,1)
    columns.addWidget(chat,645)
    aside, controls = panel()
    controls.addWidget(label("Жануар","heading"))
    pet = combo((p["id"],p["name"]) for p in pets)
    pet.setObjectName("advicePet")
    controls.addWidget(pet)
    controls.addWidget(rule())
    controls.addWidget(label("Күтім тақырыбы","hint"))
    topic = combo(TOPICS)
    controls.addWidget(topic)
    controls.addWidget(label("Дайын сұрақтар","hint"))

    def reset(*_):
        asked.clear()
        answer.setText("Жануарды және күтім тақырыбын таңдап, сұрақ қойыңыз.")
        reason.clear()
        detail.clear()
        limit.clear()

    def submit(preset=None, intent=None):
        query = (preset or question.text()).strip()
        if not query:
            answer.setText("Сұрағыңызды жазыңыз.")
            return
        reset()
        asked.setText(query)
        if window.classify_intent and intent is None:
            inferred = window.classify_intent(query)
            if isinstance(inferred,dict):
                intent = inferred.get("intent") or inferred.get("result")
            else:
                intent = inferred
            if intent in {None,"unknown","clarify"}:
                answer.setText("Сұрақтың тақырыбын нақтылаңыз немесе дайын сұрақты таңдаңыз.")
                return
        data = recommend(window.store, window.session, pet.currentData(), intent or topic.currentData(), window.clock())
        answer.setText(data["result"])
        reason.setText(data["reason"])
        detail.setText(data["input_summary"])
        limit.setText(data["limitations"])
        question.clear()

    for caption,query,intent in [
        ("Күтім кестесін қарау","Күтім кестесінде қандай әрекет бар?","general"),
        ("Ойын және серуен","Алдағы белсенділік жоспары қандай?","activity"),
        ("Тамақтандыру тәртібі","Келесі тамақтандыру қашан?","feeding")]:
        def choose(q=query,i=intent):
            topic.setCurrentIndex(max(0, topic.findData(i)))
            submit(q,i)
        controls.addWidget(window.action(caption,choose))
    pet.currentIndexChanged.connect(reset)
    topic.currentIndexChanged.connect(reset)
    reset()
    controls.addStretch()
    columns.addWidget(aside,311)
    composer.addWidget(window.action("Жіберу",submit,"primary"))
    question.returnPressed.connect(lambda:window.run(submit))
    dialog.addLayout(composer)
    page.addLayout(columns)

