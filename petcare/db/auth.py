import hashlib
import hmac
import re
import secrets
import sqlite3
import time


RESET_LIFETIME_SECONDS = 600
RESET_RESEND_SECONDS = 60


def normalized_email(value):
    value = value.strip().casefold()
    forbidden = ',;:<>()"\\[]'
    if (len(value) > 254 or any(c in forbidden or ord(c) < 32 or ord(c) == 127 for c in value)
            or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value)):
        raise ValueError("Пошта мекенжайын тексеріңіз.")
    return value


def password_fields(password):
    if not isinstance(password, str) or len(password) < 8:
        raise ValueError("Құпиясөз кемінде 8 таңба болуы керек.")
    salt = secrets.token_bytes(16)
    return salt, digest(password, salt)


def digest(value, salt):
    return hashlib.pbkdf2_hmac("sha256", value.encode(), salt, 600_000)


def token_hash(token):
    return hashlib.sha256(str(token).encode()).digest()


class Accounts:
    def register(self, name, email, password):
        name = name.strip()
        if not name:
            raise ValueError("Атыңызды енгізіңіз.")
        email = normalized_email(email)
        salt, hashed = password_fields(password)
        try:
            with self.conn:
                return self.conn.execute(
                    "INSERT INTO owners(name,email,salt,password_hash) VALUES (?,?,?,?)",
                    (name, email, salt, hashed),
                ).lastrowid
        except sqlite3.IntegrityError as exc:
            raise ValueError("Бұл пошта бұрын тіркелген.") from exc

    def login(self, email, password):
        with self.conn:
            row = self.conn.execute(
                "SELECT * FROM owners WHERE email=?", (normalized_email(email),)
            ).fetchone()
            if row is None or not hmac.compare_digest(digest(password, row["salt"]), row["password_hash"]):
                raise ValueError("Пошта немесе құпиясөз қате.")
            token = secrets.token_urlsafe(32)
            now = int(time.time())
            self.conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
            # A reset on a second connection may have replaced the verified password.
            created = self.conn.execute(
                "INSERT INTO sessions(token_hash, owner_id, expires_at) "
                "SELECT ?,id,? FROM owners WHERE id=? AND password_hash=?",
                (token_hash(token), now + 86400, row["id"], row["password_hash"]),
            )
            if not created.rowcount:
                raise ValueError("Пошта немесе құпиясөз қате.")
        return token

    def owner(self, session):
        row = self.conn.execute(
            "SELECT owner_id FROM sessions WHERE token_hash=? AND expires_at>?",
            (token_hash(session), int(time.time())),
        ).fetchone()
        if row is None:
            raise ValueError("Сеанс аяқталды. Аккаунтқа қайта кіріңіз.")
        return row[0]

    def logout(self, session):
        with self.conn:
            key = token_hash(session)
            self.conn.execute(
                "INSERT INTO events(owner_id,action,detail) SELECT owner_id,?,? FROM sessions "
                "WHERE token_hash=? AND expires_at>?",
                ("Сеанс аяқталды", "Аккаунттан шығу", key, int(time.time())),
            )
            self.conn.execute("DELETE FROM sessions WHERE token_hash=?", (key,))

    def profile(self, session):
        return dict(self.conn.execute(
            "SELECT id,name,email FROM owners WHERE id=?", (self.owner(session),)
        ).fetchone())

    def update_profile(self, session, name, email):
        if not name.strip():
            raise ValueError("Атыңызды енгізіңіз.")
        try:
            with self.conn:
                oid = self.owner(session)
                new_email = normalized_email(email)
                self.conn.execute(
                    "DELETE FROM password_resets WHERE owner_id=? AND EXISTS "
                    "(SELECT 1 FROM owners WHERE id=? AND email<>?)", (oid, oid, new_email)
                )
                self.conn.execute("UPDATE owners SET name=?,email=? WHERE id=?",
                                  (name.strip(), new_email, oid))
                self._event(oid, "Профиль", "Профиль жаңартылды.")
        except sqlite3.IntegrityError as exc:
            raise ValueError("Бұл пошта бұрын тіркелген.") from exc

    def change_password(self, session, old, new):
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            oid = self.owner(session)
            row = self.conn.execute("SELECT salt,password_hash FROM owners WHERE id=?", (oid,)).fetchone()
            if not hmac.compare_digest(digest(old, row[0]), row[1]):
                raise ValueError("Қазіргі құпиясөз қате.")
            self.conn.execute("UPDATE owners SET salt=?,password_hash=? WHERE id=?",
                              (*password_fields(new), oid))
            self.conn.execute("DELETE FROM password_resets WHERE owner_id=?", (oid,))
            self.conn.execute("DELETE FROM sessions WHERE owner_id=? AND token_hash<>?", (oid, token_hash(session)))
            self._event(oid, "Құпиясөз өзгертілді", "Профильден жаңартылды.")

    def request_reset(self, email, send_callback):
        email = normalized_email(email)
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            row = self.conn.execute(
                "SELECT o.id,r.expires_at FROM owners o "
                "LEFT JOIN password_resets r ON o.id=r.owner_id WHERE o.email=?", (email,)
            ).fetchone()
            now = int(time.time())
            if row is None:
                return
            previous_expiry = row["expires_at"]
            if previous_expiry is not None and now < previous_expiry - RESET_LIFETIME_SECONDS + RESET_RESEND_SECONDS:
                return
            oid = row["id"]
            code = f"{secrets.randbelow(1_000_000):06d}"
            salt = secrets.token_bytes(16)
            self.conn.execute(
                "INSERT OR REPLACE INTO password_resets VALUES (?,?,?,?,0)",
                (oid, salt, digest(code, salt), now + RESET_LIFETIME_SECONDS),
            )
        try:
            send_callback(email, code)
        except Exception:
            with self.conn:
                self.conn.execute("DELETE FROM password_resets WHERE owner_id=? AND salt=?", (oid, salt))
            raise

    def reset_password(self, email, code, new):
        email = normalized_email(email)
        new_fields = password_fields(new)
        now = int(time.time())
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            row = self.conn.execute(
                "SELECT r.* FROM password_resets r JOIN owners o ON o.id=r.owner_id "
                "WHERE o.email=? AND r.expires_at>? AND r.attempts<5", (email, now)
            ).fetchone()
            if row is not None:
                oid = row["owner_id"]
                if hmac.compare_digest(digest(code.strip(), row["salt"]), row["code_hash"]):
                    self.conn.execute("UPDATE owners SET salt=?,password_hash=? WHERE id=?", (*new_fields, oid))
                    self.conn.execute("DELETE FROM password_resets WHERE owner_id=?", (oid,))
                    self.conn.execute("DELETE FROM sessions WHERE owner_id=?", (oid,))
                    self._event(oid, "Құпиясөз қалпына келтірілді", "Поштадағы код расталды.")
                    return
                self.conn.execute("UPDATE password_resets SET attempts=attempts+1 WHERE owner_id=?", (oid,))
        raise ValueError("Код қате немесе оның мерзімі аяқталған.")

