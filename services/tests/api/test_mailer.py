import smtplib

import pytest

from api.dashboard.auth import mailer
from api.dashboard.auth.mailer import ConsoleMailer, SmtpMailer, mailer_from_env


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host, port, local_hostname=None, timeout=None, context=None):
        self.args = (host, port, local_hostname, timeout)
        self.actions: list = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        self.actions.append("starttls")

    def login(self, user, password):
        self.actions.append(("login", user))

    def send_message(self, message):
        self.actions.append(("send", message["To"], message["Subject"]))
        self.message = message


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    FakeSMTP.instances = []
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)


def test_the_greeting_name_is_always_given_so_smtplib_never_asks_the_os_for_it():
    # Regression: leaving it out made every email wait ~35 s on macOS for a hostname lookup.
    SmtpMailer(host="mail.test", port=1025, starttls=False).send("a@b.com", "s", "t")
    assert FakeSMTP.instances[0].args[2] == "localhost"
    SmtpMailer(host="mail.test", port=465).send("a@b.com", "s", "t")
    assert FakeSMTP.instances[1].args[2] == "localhost"


def test_a_custom_greeting_name_is_used():
    SmtpMailer(host="h", port=25, starttls=False, helo="dbinsight.example.com").send(
        "a@b.com", "s", "t"
    )
    assert FakeSMTP.instances[0].args[2] == "dbinsight.example.com"


def test_starttls_and_login_are_used_when_configured():
    SmtpMailer(host="h", port=587, user="u", password="p").send(
        "a@b.com", "subject", "text", "<b>html</b>"
    )
    actions = FakeSMTP.instances[0].actions
    assert actions[:2] == ["starttls", ("login", "u")] and actions[2] == (
        "send",
        "a@b.com",
        "subject",
    )
    assert FakeSMTP.instances[0].message.is_multipart(), "text and html alternatives"


def test_a_local_catcher_gets_no_tls_and_no_login():
    SmtpMailer(host="localhost", port=1025, starttls=False).send("a@b.com", "s", "t")
    assert FakeSMTP.instances[0].actions == [("send", "a@b.com", "s")]


def test_smtp_settings_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("DBINSIGHT_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("DBINSIGHT_SMTP_PORT", "2525")
    monkeypatch.setenv("DBINSIGHT_SMTP_USER", "me")
    monkeypatch.setenv("DBINSIGHT_SMTP_HELO", "app.example.com")
    m = mailer_from_env()
    assert isinstance(m, SmtpMailer) and (m.host, m.port, m.user, m.helo) == (
        "smtp.example.com",
        2525,
        "me",
        "app.example.com",
    )
    assert m.starttls is True


def test_port_1025_defaults_to_no_tls_for_the_dev_mail_catcher(monkeypatch):
    monkeypatch.setenv("DBINSIGHT_SMTP_HOST", "localhost")
    monkeypatch.setenv("DBINSIGHT_SMTP_PORT", "1025")
    assert mailer_from_env().starttls is False


def test_without_smtp_configured_messages_go_to_the_console(monkeypatch, capsys):
    monkeypatch.delenv("DBINSIGHT_SMTP_HOST", raising=False)
    m = mailer_from_env()
    assert isinstance(m, ConsoleMailer)
    m.send("a@b.com", "Hello", "your code is 123 456")
    err = capsys.readouterr().err
    assert "not sent" in err and "123 456" in err


def test_message_templates_carry_the_code_and_the_expiry():
    subject, text, html = mailer.otp_message("register", "123456", 10)
    assert "123 456" in subject and "123 456" in text and "123 456" in html and "10 minutes" in text
    subject, text, _ = mailer.otp_message("reset", "654321", 10)
    assert "reset" in subject and "654 321" in text
