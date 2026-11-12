"""Local repository. Each write and its audit entry commit in the same transaction."""
import csv
import io
import json
import math
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from .auth import Accounts
from .demo import PETS, TASKS


def required(mapping, key):
    value = str(mapping.get(key) or "").strip()
    if not value:
        raise ValueError("Міндетті өрістерді толтырыңыз.")
    return value


def pet_values(draft):
    name = required(draft, "name")
    species = required(draft, "species")
    sex = required(draft, "sex")
    try:
        birth = date.fromisoformat(str(draft.get("birth_date", "")))
    except ValueError as exc:
        raise ValueError("Туған күнді дұрыс енгізіңіз.") from exc
    if birth > date.today():
        raise ValueError("Туған күн болашақта болмауы керек.")
    try:
        weight = float(str(draft.get("weight_kg", "")).replace(",", "."))
    except ValueError as exc:
        raise ValueError("Салмақты санмен енгізіңіз.") from exc
    if not math.isfinite(weight) or weight <= 0:
        raise ValueError("Салмақ нөлден үлкен сан болуы керек.")
    return (
        name, species, str(draft.get("breed") or "").strip(), birth.isoformat(), sex,
        weight, str(draft.get("photo_path") or "").strip(), str(draft.get("notes") or "").strip(),
    )


def csv_text(value):
    # A user-supplied name must remain text when opened by a spreadsheet.
    if isinstance(value, str) and (value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n"))):
        return "'" + value
    return value


class Store(Accounts):
    def __init__(self, path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.create_function("fold", 1, lambda s: str(s or "").casefold(), deterministic=True)
        self.conn.execute("PRAGMA foreign_keys=ON")
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version > 1:
            self.conn.close()
            raise ValueError("Деректер базасы қосымшаның жаңарақ нұсқасына арналған.")
        if version == 0:
            schema = Path(__file__).with_name("migrations") / "001_initial.sql"
            try:
                self.conn.executescript(schema.read_text(encoding="utf-8"))
            except Exception:
                self.conn.close()
                raise

    def close(self):
        self.conn.close()

    def _event(self, owner_id, action, detail):
        self.conn.execute("INSERT INTO events(owner_id,action,detail) VALUES (?,?,?)",
                          (owner_id, action, detail))

    def _pet(self, owner_id, pet_id):
        row = self.conn.execute("SELECT * FROM pets WHERE owner_id=? AND id=?", (owner_id, pet_id)).fetchone()
        if row is None:
            raise ValueError("Жануар табылмады.")
        return row

    def get_pet(self, session, pet_id):
        return dict(self._pet(self.owner(session), pet_id))

    def list_pets(self, session, query="", species="", sort="name"):
        return self.search_pets(session, query, {"species": species}, sort)

    def search_pets(self, session, query="", filters=None, sort="name"):
        columns = {"name": "fold(name)", "species": "fold(species)", "breed": "fold(breed)",
                   "birth_date": "birth_date", "weight_kg": "weight_kg", "id": "id"}
        if sort not in columns:
            raise ValueError("Сұрыптау өрісі дұрыс емес.")
        filters = filters or {}
        if set(filters) - {"species", "breed"}:
            raise ValueError("Іздеу сүзгісі дұрыс емес.")
        species = str(filters.get("species") or "").strip()
        breed = str(filters.get("breed") or "").strip()
        query = query.strip()
        order = columns[sort]
        records = self.conn.execute(
            "SELECT * FROM pets WHERE owner_id=? AND (?='' OR fold(species)=fold(?)) "
            "AND (?='' OR fold(breed)=fold(?)) "
            "AND (instr(fold(name),fold(?))>0 OR instr(fold(breed),fold(?))>0 OR instr(fold(species),fold(?))>0) "
            f"ORDER BY {order}, fold(name), id",
            (self.owner(session), species, species, breed, breed, query, query, query),
        )
        return [dict(r) for r in records]

    def save_pet(self, session, draft, pet_id=None):
        with self.conn:
            oid = self.owner(session)
            if pet_id is None:
                values = pet_values(draft)
                pet_id = self.conn.execute(
                    "INSERT INTO pets(owner_id,name,species,breed,birth_date,sex,weight_kg,photo_path,notes) "
                    "VALUES (?,?,?,?,?,?,?,?,?)", (oid, *values),
                ).lastrowid
                action = "Жануар қосылды"
            else:
                values = pet_values({**dict(self._pet(oid, pet_id)), **draft})
                updated = self.conn.execute(
                    "UPDATE pets SET name=?,species=?,breed=?,birth_date=?,sex=?,weight_kg=?,photo_path=?,notes=? "
                    "WHERE id=? AND owner_id=?", (*values, pet_id, oid),
                )
                if not updated.rowcount:
                    raise ValueError("Жануар табылмады.")
                action = "Жануар өзгертілді"
            self._event(oid, action, values[0])
        return pet_id

    def delete_pet(self, session, pet_id):
        with self.conn:
            oid = self.owner(session)
            name = self._pet(oid, pet_id)["name"]
            deleted = self.conn.execute("DELETE FROM pets WHERE id=? AND owner_id=?", (pet_id, oid))
            if not deleted.rowcount:
                raise ValueError("Жануар табылмады.")
            self._event(oid, "Жануар жойылды", name)

    def schedule_task(self, session, pet_id, draft):
        kind = required(draft, "task_type")
        title = required(draft, "title")
        raw_time = required(draft, "scheduled_at")
        try:
            if len(raw_time) < 16:
                raise ValueError("Missing time")
            when = datetime.fromisoformat(raw_time)
        except ValueError as exc:
            raise ValueError("Күтімнің күні мен уақытын енгізіңіз.") from exc
        if when.tzinfo is not None:
            raise ValueError("Жергілікті уақытты енгізіңіз.")
        with self.conn:
            oid = self.owner(session)
            name = self._pet(oid, pet_id)["name"]
            task_id = self.conn.execute(
                "INSERT INTO care_tasks(pet_id,task_type,title,scheduled_at) VALUES (?,?,?,?)",
                (pet_id, kind, title, when.isoformat(timespec="minutes")),
            ).lastrowid
            self._event(oid, "Күтім жоспарланды", f"{name} · {title}")
        return task_id

    def complete_task(self, session, task_id):
        with self.conn:
            oid = self.owner(session)
            row = self.conn.execute(
                "SELECT t.title, p.name FROM care_tasks t JOIN pets p ON p.id=t.pet_id "
                "WHERE t.id=? AND p.owner_id=?", (task_id, oid),
            ).fetchone()
            if row is None:
                raise ValueError("Тапсырма табылмады.")
            updated = self.conn.execute(
                "UPDATE care_tasks SET status='done' WHERE id=? AND status='planned' "
                "AND pet_id IN (SELECT id FROM pets WHERE owner_id=?)", (task_id, oid),
            )
            if updated.rowcount:
                self._event(oid, "Күтім орындалды", f"{row['name']} · {row['title']}")

    def tasks(self, session, pet_id=None):
        oid = self.owner(session)
        if pet_id is not None:
            self._pet(oid, pet_id)
        records = self.conn.execute(
            "SELECT t.*, p.name AS pet_name FROM care_tasks t JOIN pets p ON p.id=t.pet_id "
            "WHERE p.owner_id=? AND (? IS NULL OR p.id=?) ORDER BY t.scheduled_at,t.id",
            (oid, pet_id, pet_id),
        )
        return [dict(r) for r in records]

    def reminders(self, session, now, until=None, task_type=None):
        """Upcoming unfinished care in local time, including both interval boundaries."""
        oid = self.owner(session)
        if not isinstance(now, datetime) or now.tzinfo is not None:
            raise ValueError("Еске салғышқа жергілікті уақытты беріңіз.")
        if until is not None and (not isinstance(until, datetime) or until.tzinfo is not None or until < now):
            raise ValueError("Еске салғыш кезеңінің соңғы уақытын тексеріңіз.")
        types = ("vaccine", "vaccination") if task_type in {"vaccine", "vaccination"} else (task_type, task_type)
        stop = until.isoformat() if until else None
        records = self.conn.execute(
            "SELECT t.*,p.name AS pet_name FROM care_tasks t JOIN pets p ON t.pet_id=p.id "
            "WHERE p.owner_id=? AND t.status='planned' AND julianday(t.scheduled_at)>=julianday(?) "
            "AND (? IS NULL OR julianday(t.scheduled_at)<=julianday(?)) "
            "AND (? IS NULL OR t.task_type IN (?,?)) ORDER BY t.scheduled_at,t.id",
            (oid, now.isoformat(), stop, stop, task_type, *types),
        )
        return [dict(row) for row in records]

    def stats(self, session, day):
        oid = self.owner(session)
        end = date.fromisoformat(str(day))
        days = [(end - timedelta(days=n)).isoformat() for n in range(6, -1, -1)]
        counts = self.conn.execute(
            "SELECT substr(t.scheduled_at,1,10) AS day,count(*) AS planned,sum(t.status='done') AS done "
            "FROM care_tasks t JOIN pets p ON p.id=t.pet_id WHERE p.owner_id=? "
            "AND t.scheduled_at>=? AND t.scheduled_at<? GROUP BY day",
            (oid, days[0], (end + timedelta(days=1)).isoformat()),
        )
        indexed = {r["day"]: r for r in counts}
        week = []
        for d in days:
            values = indexed.get(d, {"planned": 0, "done": 0})
            week.append({"date": d, "planned": values["planned"], "done": values["done"]})
        pets = self.conn.execute("SELECT count(*) FROM pets WHERE owner_id=?", (oid,)).fetchone()[0]
        return {"pet_count": pets, "task_count": week[-1]["planned"],
                "done_count": week[-1]["done"], "weekly": week}

    def history(self, session, query=""):
        query = query.strip()
        rows = self.conn.execute(
            "SELECT id,created_at,action,detail FROM events WHERE owner_id=? "
            "AND instr(fold(created_at || ' ' || strftime('%d.%m.%Y %H:%M',created_at,'localtime') "
            "|| ' ' || action || ' ' || detail),fold(?))>0 ORDER BY id DESC",
            (self.owner(session), query),
        )
        return [dict(row) for row in rows]

    def export_report(self, session, start_date=None, end_date=None, file_format="csv"):
        if file_format not in {"csv", "json"}:
            raise ValueError("Есеп пішімі CSV немесе JSON болуы керек.")
        start = date.fromisoformat(str(start_date)) if start_date is not None else date.min
        end = date.fromisoformat(str(end_date)) if end_date is not None else date.max
        if end < start:
            raise ValueError("Кезеңнің соңғы күні бастапқы күннен ерте.")
        headers = ["Жануар", "Күтім түрі", "Тапсырма", "Күні мен уақыты", "Мәртебесі"]
        rows = []
        for task in self.tasks(session):
            scheduled_day = date.fromisoformat(task["scheduled_at"][:10])
            if not start <= scheduled_day <= end:
                continue
            status = "Орындалды" if task["status"] == "done" else "Жоспарда"
            rows.append([task["pet_name"], task["task_type"], task["title"], task["scheduled_at"], status])
        if file_format == "json":
            data = [dict(zip(headers, row)) for row in rows]
            return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows([csv_text(value) for value in row] for row in rows)
        return output.getvalue().encode("utf-8-sig")

    def seed_demo(self, session):
        with self.conn:
            oid = self.owner(session)
            claimed = self.conn.execute(
                "UPDATE owners SET demo_installed=1 WHERE id=? AND demo_installed=0", (oid,),
            )
            if not claimed.rowcount:
                return
            ids = {}
            for name, species, birth, sex, weight in PETS:
                ids[name] = self.conn.execute(
                    "INSERT INTO pets(owner_id,name,species,birth_date,sex,weight_kg) VALUES (?,?,?,?,?,?)",
                    (oid, name, species, birth, sex, weight),
                ).lastrowid
            self.conn.executemany(
                "INSERT INTO care_tasks(pet_id,task_type,title,scheduled_at,status) VALUES (?,?,?,?,?)",
                [(ids[name], kind, title, when, state) for name, kind, title, when, state in TASKS],
            )
            self._event(oid, "Үлгі деректер", "10 жануар жүктелді.")

