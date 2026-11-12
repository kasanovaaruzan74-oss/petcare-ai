"""Exercise mail composition with an in-process fake, without a mail account."""
from unittest.mock import patch
import pytest

from petcare.mail import send_report, send_reset_code


def test_csv_sent_after_tls(monkeypatch):
    monkeypatch.setenv("PETCARE_SMTP_HOST", "smtp.example.invalid")
    monkeypatch.setenv("PETCARE_SMTP_FROM", "demo@example.invalid")
    monkeypatch.setenv("PETCARE_SMTP_MODE", "starttls")
    with patch("petcare.mail.smtplib.SMTP") as smtp:
        session = smtp.return_value.__enter__.return_value
        send_report("owner@example.invalid", b"sample")
        session.starttls.assert_called_once()
        message = session.send_message.call_args.args[0]
        assert message["To"] == "owner@example.invalid"
        assert next(message.iter_attachments()).get_payload(decode=True) == b"sample"


def test_unconfigured_reset(monkeypatch):
    monkeypatch.delenv("PETCARE_SMTP_HOST", raising=False)
    with pytest.raises(ValueError, match="бапталмаған"):
        send_reset_code("owner@example.invalid", "123456")

