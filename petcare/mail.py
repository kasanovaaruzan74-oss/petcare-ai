"""Optional SMTP transport for recovery codes and owner-requested CSV reports."""
from email.message import EmailMessage
import os
import smtplib
import ssl

from .db.auth import normalized_email


def _deliver(message, recipient):
    recipient = normalized_email(recipient)
    host = os.environ.get("PETCARE_SMTP_HOST", "").strip()
    sender = os.environ.get("PETCARE_SMTP_FROM", "").strip()
    if not host or not sender:
        raise ValueError("Пошта қызметі бапталмаған. SMTP сервері мен жіберушіні көрсетіңіз.")
    sender = normalized_email(sender)
    mode = os.environ.get("PETCARE_SMTP_MODE", "starttls").lower()
    if mode not in {"starttls", "ssl"}:
        raise ValueError("SMTP режимі starttls немесе ssl болуы керек.")
    username = os.environ.get("PETCARE_SMTP_USER", "")
    password = os.environ.get("PETCARE_SMTP_PASSWORD", "")
    if bool(username) != bool(password):
        raise ValueError("SMTP пайдаланушысы мен құпиясөзін бірге көрсетіңіз.")
    message["To"] = recipient
    message["From"] = sender
    context = ssl.create_default_context()
    try:
        port = int(os.environ.get("PETCARE_SMTP_PORT", "465" if mode == "ssl" else "587"))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise ValueError("SMTP порты дұрыс емес.") from None
    try:
        connection = (smtplib.SMTP_SSL(host, port, timeout=10, context=context)
                      if mode == "ssl" else smtplib.SMTP(host, port, timeout=10))
        with connection as server:
            if mode == "starttls":
                server.starttls(context=context)
            if username:
                server.login(username, password)
            server.send_message(message)
    except (OSError, smtplib.SMTPException):
        raise ValueError("Хат жіберілмеді. Пошта баптауларын тексеріңіз.") from None


def send_reset_code(recipient, code):
    message = EmailMessage()
    message["Subject"] = "PetCare AI — бір реттік код"
    message.set_content(f"Құпиясөзді қалпына келтіру коды: {code}\nКод 10 минут жарамды.")
    _deliver(message, recipient)


def send_report(recipient, attachment):
    message = EmailMessage()
    message["Subject"] = "PetCare AI — күтім есебі"
    message.set_content("Күтім есебі CSV файлы ретінде тіркелді.")
    message.add_attachment(attachment, maintype="text", subtype="csv", filename="petcare-report.csv")
    _deliver(message, recipient)

