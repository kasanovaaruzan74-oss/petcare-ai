from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDateEdit, QDoubleSpinBox, QFileDialog, QGridLayout, QHBoxLayout, QMessageBox,
    QVBoxLayout, QWidget,
)
from .widgets import combo, field, formatted_day, label, panel, table, table_row

SPECIES = ("Мысық", "Ит", "Қоян", "Басқа")
SEX = ("Ұрғашы", "Еркек", "Белгісіз")


def registry(window, notice=""):
    page = window.workspace("pets", "Жануарларым", "Тіркелген үй жануарлары",
                            window.action("+  Жануар қосу", window.pet_form, "primary"))
    box, body = panel()
    if notice:
        saved = label(notice, "accent", True)
        saved.setObjectName("saveNotice")
        body.addWidget(saved)
    controls = QHBoxLayout()
    search = field(placeholder="Аты, түрі немесе тұқымы бойынша іздеу")
    search.setObjectName("petSearch")
    controls.addWidget(search, 1)
    species = combo([("", "Барлық түрі")] + [(s,s) for s in SPECIES])
    order = combo([("id","Тіркелу реті"), ("name","Аты бойынша"), ("species","Түрі бойынша"),
                   ("breed","Тұқымы бойынша"), ("birth_date","Туған күні"),
                   ("weight_kg","Салмағы")])
    controls.addWidget(species)
    controls.addWidget(order)
    body.addLayout(controls)
    count = label("", "hint")
    body.addWidget(count)
    grid = table(["Аты", "Түрі", "Туған күні", "Жынысы", "Салмағы", ""], {5:112})
    grid.setObjectName("petRegistry")
    grid.setMinimumHeight(435)
    body.addWidget(grid)

    def populate():
        data = window.store.list_pets(window.session, search.text().strip(), species.currentData(), order.currentData())
        grid.setRowCount(0)
        for pet in data:
            weight = format(float(pet["weight_kg"]), "g").replace(".", ",")
            row = table_row(grid, [pet["name"], pet["species"], formatted_day(pet["birth_date"]), pet["sex"], weight + " кг"])
            edit = window.action("Өзгерту", lambda p=pet:window.pet_form(p))
            edit.setAccessibleName(pet["name"] + " профилін өзгерту")
            grid.setCellWidget(row,5,edit)
        count.setText(f"{len(data)} жануар" if data else "Іздеу бойынша жануар табылмады.")

    for signal in (search.textChanged, species.currentIndexChanged, order.currentIndexChanged):
        signal.connect(lambda *_:window.run(populate))
    populate()
    page.addWidget(box,1)


def pet_form(window, record=None):
    editing = record is not None
    pet = record or {}
    page = window.workspace("pets" if editing else "add", "Мәліметті өзгерту" if editing else "Жануар қосу",
                            f"{pet['name']} профилі" if editing else "Жаңа жануардың мәліметтерін енгізіңіз")
    cols = QHBoxLayout()
    cols.setSpacing(20)
    cols.setAlignment(Qt.AlignmentFlag.AlignTop)
    box, body = panel()
    body.addWidget(label("Жеке мәліметтер", "heading"))
    body.addSpacing(10)
    form = QGridLayout()
    form.setHorizontalSpacing(16)
    form.setVerticalSpacing(6)
    form.setColumnStretch(0, 1)
    form.setColumnStretch(1, 1)
    name = field(pet.get("name",""), "Жануардың аты")
    name.setObjectName("petName")
    breed = field(pet.get("breed",""), "Тұқымын енгізіңіз")
    species = combo([(s,s) for s in SPECIES])
    sex = combo([(s,s) for s in SEX])
    species.setCurrentText(pet.get("species", SPECIES[0]))
    sex.setCurrentText(pet.get("sex", SEX[-1]))
    birth = QDateEdit()
    birth.setCalendarPopup(True)
    birth.setDisplayFormat("dd.MM.yyyy")
    today = window.clock().date()
    birth.setMaximumDate(max(QDate.currentDate(), QDate(today.year, today.month, today.day)))
    birth.setDate(QDate.fromString(pet.get("birth_date",today.isoformat()), "yyyy-MM-dd"))
    weight = QDoubleSpinBox()
    weight.setRange(.001,10000)
    weight.setDecimals(3)
    weight.setValue(pet.get("weight_kg",1.0))
    for j,(title,item) in enumerate([("Аты",name),("Түрі",species),("Тұқымы",breed),
                                       ("Жынысы",sex),("Туған күні",birth),("Салмағы, кг",weight)]):
        row, col = divmod(j,2)
        form.addWidget(label(title,"hint"),row*3,col)
        form.addWidget(item,row*3+1,col)
        form.setRowMinimumHeight(row*3+2,12)
    body.addLayout(form)
    body.addWidget(label("Ескертпе","hint"))
    notes = field(pet.get("notes",""),"Қосымша мәлімет")
    body.addWidget(notes)
    body.addStretch()
    box.setMinimumHeight(450)
    cols.addWidget(box,619)
    picture, pl = panel()
    pl.addWidget(label("Жануардың фотосы","heading"))
    image = label("")
    image.setAlignment(Qt.AlignmentFlag.AlignCenter)
    image.setFixedHeight(150)
    image.setStyleSheet("background:#141A1C;border:1px solid #374246;border-radius:8px;font-size:40px;color:#74DFCB")
    pl.addWidget(image)
    photo_path = pet.get("photo_path","")

    def display():
        pix = QPixmap(photo_path) if photo_path and Path(photo_path).is_file() else QPixmap()
        if pix.isNull():
            image.setText(pet.get("name","")[:1] or "+")
        else:
            image.setPixmap(pix.scaled(230,144,Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation))

    def choose():
        nonlocal photo_path
        path, _ = QFileDialog.getOpenFileName(window, "Жануардың фотосы", "", "Суреттер (*.png *.jpg *.jpeg *.webp)")
        if path:
            if QPixmap(path).isNull():
                raise ValueError("Суретті ашу мүмкін болмады.")
            photo_path = path
            display()

    display()
    pl.addWidget(window.action("Фотоны ауыстыру" if editing else "Фото жүктеу",choose))
    pl.addStretch()
    cols.addWidget(picture,337)
    page.addLayout(cols)
    message = label("","error",True)
    message.setObjectName("petFormError")
    page.addWidget(message)

    def flag_name(invalid):
        name.setProperty("invalid", invalid)
        name.style().unpolish(name)
        name.style().polish(name)

    def clear_name_error(text):
        if text.strip() and name.property("invalid"):
            flag_name(False)
            message.clear()

    name.textChanged.connect(clear_name_error)

    def save():
        if not name.text().strip():
            flag_name(True)
            name.setFocus()
            message.setText("Жануардың атын енгізіңіз.")
            return
        try:
            window.store.save_pet(window.session, {
                "name":name.text(), "species":species.currentText(), "breed":breed.text(),
                "birth_date":birth.date().toString("yyyy-MM-dd"), "sex":sex.currentText(),
                "weight_kg":weight.value(), "photo_path":photo_path, "notes":notes.text()},
                pet.get("id"))
        except ValueError as exc:
            message.setText(str(exc))
            return
        window.registry("Өзгерістер сақталды." if editing else f"{name.text().strip()} тізімге қосылды.")

    def remove():
        reply = QMessageBox.question(window,"Жоюды растау",
                                     f"{pet['name']} профилі мен күтім жазбаларын жою керек пе?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                     QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Yes:
            window.store.delete_pet(window.session,pet["id"])
            window.registry(f"{pet['name']} профилі жойылды.")

    actions = QHBoxLayout()
    if editing:
        actions.addWidget(window.action("Профильді жою",remove,"danger"))
    actions.addStretch()
    actions.addWidget(window.action("Бас тарту",window.registry))
    actions.addWidget(window.action("Өзгерісті сақтау" if editing else "Сақтау",save,"primary"))
    page.addLayout(actions)

