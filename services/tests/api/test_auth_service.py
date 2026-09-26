import pytest

from api.dashboard.auth import otp, passwords
from api.dashboard.auth.service import LOGIN_WINDOW, AuthError, hash_token, normalize_email
from tests.api.auth_fakes import FAST, UID1, make

GOOD = "correct horse battery"
EMAIL = "ada@example.com"


def registered(service, mail, email=EMAIL, password=GOOD):
    service.register(email, password, "Ada")
    return service.verify_registration(email, mail.code(email))


# ---- passwords ------------------------------------------------------------------------------


def test_a_password_round_trips_and_uses_a_fresh_salt_each_time():
    a, b = FAST("hunter2-hunter2"), FAST("hunter2-hunter2")
    assert a != b and passwords.verify_password("hunter2-hunter2", a)
    assert not passwords.verify_password("hunter2-hunter3", a)


def test_a_tampered_or_malformed_hash_never_verifies():
    good = FAST("some long password")
    assert not passwords.verify_password("some long password", good[:-4] + "AAAA")
    for bad in ("", "plain", "scrypt$x$y", "bcrypt$1$2$3$4$5"):
        assert not passwords.verify_password("some long password", bad)


def test_old_hashes_are_flagged_for_upgrade_and_the_current_one_is_not():
    assert passwords.needs_rehash(FAST("some long password"))
    assert not passwords.needs_rehash(passwords.hash_password("some long password"))


@pytest.mark.parametrize(
    ("password", "email"),
    [
        ("short1", ""),
        ("password123", ""),
        ("aaaaaaaaaaaa", ""),
        ("x" * 200, ""),
        ("adalovelace99", "adalovelace@example.com"),
    ],
)
def test_weak_passwords_are_refused_with_a_reason(password, email):
    assert passwords.policy_errors(password, email)


def test_a_long_passphrase_is_accepted():
    assert passwords.policy_errors("correct horse battery staple", "ada@example.com") == []


# ---- one-time codes -------------------------------------------------------------------------


def test_a_code_is_bound_to_its_email_and_purpose():
    secret = b"k" * 32
    h = otp.code_hash(secret, "a@x.com", "register", "123456")
    assert otp.matches(secret, "a@x.com", "register", "123456", h)
    assert not otp.matches(secret, "b@x.com", "register", "123456", h)
    assert not otp.matches(secret, "a@x.com", "reset", "123456", h)
    assert not otp.matches(b"z" * 32, "a@x.com", "register", "123456", h)


def test_pasted_codes_are_cleaned_up():
    assert otp.clean(" 123 456 ") == "123456" and otp.clean("123-456") == "123456"


def test_codes_are_six_digits():
    assert all(len(otp.new_code()) == 6 and otp.new_code().isdigit() for _ in range(50))


# ---- registration ---------------------------------------------------------------------------


def test_registering_emails_a_code_and_stores_it_only_hashed():
    service, store, mail, _ = make()
    result = service.register(EMAIL, GOOD, "Ada")
    code = mail.code(EMAIL)
    assert result == {"email": EMAIL, "resend_after": 60, "expires_in": 600}
    assert len(code) == 6
    stored = store.otps[(EMAIL, "register")]["code_hash"]
    assert code not in stored and code not in str(store.users)
    assert GOOD not in store.users[UID1]["password_hash"]


def test_email_is_normalized_and_validated():
    assert normalize_email("  Ada@Example.COM ") == "ada@example.com"
    for bad in ("", "nope", "a@b", "@x.com", "a b@x.com", "a" * 260 + "@x.com"):
        with pytest.raises(AuthError) as e:
            normalize_email(bad)
        assert e.value.code == "invalid_email"


def test_a_weak_password_is_refused_before_anything_is_sent():
    service, store, mail, _ = make()
    with pytest.raises(AuthError) as e:
        service.register(EMAIL, "short", "")
    assert e.value.code == "weak_password" and e.value.status == 422
    assert mail.sent == [] and store.users == {}


def test_the_right_code_verifies_and_signs_the_user_in():
    service, store, mail, _ = make()
    signed = registered(service, mail)
    assert signed.user["email"] == EMAIL and store.users[UID1]["email_verified_at"]
    assert service.authenticate(signed.token)["email"] == EMAIL


def test_the_first_verified_user_is_the_admin_and_later_ones_are_not():
    service, _, mail, _ = make()
    assert registered(service, mail, "first@example.com").user["role"] == "admin"
    second = registered(service, mail, "second@example.com")
    assert second.user["role"] == "user" and second.user["can_scan_local"] is False


def test_an_unverified_account_cannot_be_the_admin_that_locks_out_the_real_first_user():
    service, _, mail, _ = make()
    service.register("squatter@example.com", GOOD, "")  # never verifies
    assert registered(service, mail, "real@example.com").user["role"] == "admin"


def test_listed_admin_emails_are_admins_even_when_not_first():
    service, _, mail, _ = make(admin_emails=("boss@example.com",))
    registered(service, mail, "first@example.com")
    assert registered(service, mail, "boss@example.com").user["role"] == "admin"


def test_a_wrong_code_counts_down_and_the_fifth_burns_the_code():
    service, store, mail, _ = make()
    service.register(EMAIL, GOOD, "")
    real = mail.code()
    wrong = "000000" if real != "000000" else "111111"
    for left in (4, 3, 2, 1):
        with pytest.raises(AuthError) as e:
            service.verify_registration(EMAIL, wrong)
        assert e.value.code == "invalid_code" and e.value.extra["attempts_left"] == left
    with pytest.raises(AuthError) as e:
        service.verify_registration(EMAIL, wrong)
    assert e.value.code == "too_many_attempts"
    with pytest.raises(AuthError):
        service.verify_registration(EMAIL, real)  # even the right code no longer works
    assert (EMAIL, "register") not in store.otps


def test_a_code_expires_after_ten_minutes_and_works_once():
    service, _, mail, clock = make()
    service.register(EMAIL, GOOD, "")
    code = mail.code()
    clock.advance(minutes=10, seconds=1)
    with pytest.raises(AuthError) as e:
        service.verify_registration(EMAIL, code)
    assert e.value.code == "code_expired"

    service.resend(EMAIL, "register")  # cooldown has long passed
    fresh = mail.code()
    service.verify_registration(EMAIL, fresh)
    with pytest.raises(AuthError):
        service.verify_registration(EMAIL, fresh)


def test_a_registration_code_does_not_reset_a_password():
    service, _, mail, _ = make()
    registered(service, mail)
    service.register("other@example.com", GOOD, "")
    with pytest.raises(AuthError):
        service.reset(
            "other@example.com", mail.code("other@example.com"), "another long passphrase"
        )


def test_registering_again_before_verifying_replaces_the_password_and_the_old_code():
    service, _, mail, clock = make()
    service.register(EMAIL, GOOD, "")
    old = mail.code()
    clock.advance(seconds=61)
    service.register(EMAIL, "a different long passphrase", "")
    new = mail.code()
    with pytest.raises(AuthError):
        service.verify_registration(EMAIL, old)
    service.verify_registration(EMAIL, new)
    service.login(EMAIL, "a different long passphrase")
    with pytest.raises(AuthError):
        service.login(EMAIL, GOOD)


def test_registering_a_verified_email_sends_no_code_and_answers_the_same():
    service, _, mail, clock = make()
    registered(service, mail)
    clock.advance(seconds=61)
    before = len(mail.sent)
    result = service.register(EMAIL, "someone elses attempt", "")
    assert result == {"email": EMAIL, "resend_after": 60, "expires_in": 600}
    notice = mail.sent[before:]
    assert len(notice) == 1 and "already have" in notice[0]["subject"].lower()
    assert "verification code" not in notice[0]["subject"]
    service.login(EMAIL, GOOD)  # the real password is untouched


# ---- sending limits ------------------------------------------------------------------------------


def test_asking_for_codes_too_fast_is_a_cooldown_with_a_wait_time():
    service, _, _, clock = make()
    service.register(EMAIL, GOOD, "")
    with pytest.raises(AuthError) as e:
        service.resend(EMAIL, "register")
    assert (
        e.value.code == "cooldown"
        and e.value.status == 429
        and 1 <= e.value.extra["retry_after"] <= 60
    )
    clock.advance(seconds=61)
    service.resend(EMAIL, "register")


def test_at_most_five_codes_an_hour():
    service, _, _, clock = make()
    for _ in range(5):
        service.register(EMAIL, GOOD, "")
        clock.advance(seconds=61)
    with pytest.raises(AuthError) as e:
        service.register(EMAIL, GOOD, "")
    assert e.value.code == "too_many_requests"
    clock.advance(hours=1)
    service.register(EMAIL, GOOD, "")


# ---- signing in ------------------------------------------------------------------------------


def test_signing_in_needs_the_password_and_a_verified_email():
    service, _, mail, clock = make()
    registered(service, mail)
    assert service.login(EMAIL, GOOD).user["email"] == EMAIL
    assert service.login("  ADA@example.com ", GOOD).user["email"] == EMAIL

    service.register("new@example.com", GOOD, "")
    clock.advance(seconds=61)
    with pytest.raises(AuthError) as e:
        service.login("new@example.com", GOOD)
    assert e.value.code == "email_not_verified" and e.value.extra["email"] == "new@example.com"


def test_a_wrong_password_and_an_unknown_email_are_indistinguishable():
    service, _, mail, _ = make()
    registered(service, mail)
    errors = []
    for email, password in ((EMAIL, "wrong password here"), ("nobody@example.com", GOOD)):
        with pytest.raises(AuthError) as e:
            service.login(email, password)
        errors.append((e.value.code, e.value.message, e.value.status))
    assert (
        errors[0]
        == errors[1]
        == ("invalid_credentials", "The email or password is not right.", 401)
    )


def test_an_unverified_account_with_a_wrong_password_is_not_revealed():
    service, _, _, _ = make()
    service.register(EMAIL, GOOD, "")
    with pytest.raises(AuthError) as e:
        service.login(EMAIL, "wrong password here")
    assert e.value.code == "invalid_credentials"


def test_five_failures_lock_the_address_out_until_the_window_passes():
    service, _, mail, clock = make()
    registered(service, mail)
    for _ in range(5):
        with pytest.raises(AuthError):
            service.login(EMAIL, "wrong password here")
    with pytest.raises(AuthError) as e:
        service.login(EMAIL, GOOD)  # even the right password is refused while locked
    assert e.value.code == "locked" and e.value.status == 429
    clock.advance(seconds=LOGIN_WINDOW.total_seconds() + 1)
    assert service.login(EMAIL, GOOD).user["email"] == EMAIL


def test_a_successful_login_clears_the_failure_count():
    service, _, mail, _ = make()
    registered(service, mail)
    for _ in range(4):
        with pytest.raises(AuthError):
            service.login(EMAIL, "wrong password here")
    service.login(EMAIL, GOOD)
    for _ in range(4):
        with pytest.raises(AuthError) as e:
            service.login(EMAIL, "wrong password here")
        assert e.value.code == "invalid_credentials"


def test_one_address_cannot_lock_out_another_email_but_can_be_stopped():
    service, _, mail, _ = make()
    registered(service, mail)
    for i in range(25):
        with pytest.raises(AuthError):
            service.login(f"victim{i}@example.com", "guess", ip="6.6.6.6")
    with pytest.raises(AuthError) as e:
        service.login(EMAIL, GOOD, ip="6.6.6.6")
    assert e.value.code == "locked"
    assert service.login(EMAIL, GOOD, ip="7.7.7.7").user["email"] == EMAIL


def test_a_disabled_account_cannot_sign_in():
    service, store, mail, _ = make()
    registered(service, mail)
    store.users[UID1]["disabled"] = True
    with pytest.raises(AuthError) as e:
        service.login(EMAIL, GOOD)
    assert e.value.code == "invalid_credentials"


# ---- forgot / reset ------------------------------------------------------------------------


def test_forgot_answers_the_same_for_unknown_and_known_emails_but_only_mails_the_known_one():
    service, _, mail, clock = make()
    registered(service, mail)
    clock.advance(seconds=61)
    before = len(mail.sent)
    known = service.forgot(EMAIL)
    unknown = service.forgot("nobody@example.com")
    assert known["resend_after"] == unknown["resend_after"] and set(known) == set(unknown)
    sent = mail.sent[before:]
    assert [m["to"] for m in sent] == [EMAIL]


def test_forgot_is_rate_limited_even_for_unknown_emails():
    service, _, _, _ = make()
    service.forgot("nobody@example.com")
    with pytest.raises(AuthError) as e:
        service.forgot("nobody@example.com")
    assert e.value.code == "cooldown"


def test_an_unverified_account_cannot_use_forgot_password_to_skip_verification():
    service, _, mail, _ = make()
    service.register(EMAIL, GOOD, "")
    before = len(mail.sent)
    service.forgot(EMAIL)
    assert len(mail.sent) == before


def test_resetting_sets_the_new_password_ends_every_session_and_tells_the_owner():
    service, store, mail, clock = make()
    signed = registered(service, mail)
    other = service.login(EMAIL, GOOD)
    clock.advance(seconds=61)
    service.forgot(EMAIL)
    service.reset(EMAIL, mail.code(EMAIL), "a brand new long passphrase")
    assert service.authenticate(signed.token) is None and service.authenticate(other.token) is None
    with pytest.raises(AuthError):
        service.login(EMAIL, GOOD)
    assert service.login(EMAIL, "a brand new long passphrase").user["email"] == EMAIL
    assert "changed" in mail.to(EMAIL)[-1]["subject"].lower()


def test_a_weak_new_password_does_not_use_up_the_code():
    service, _, mail, clock = make()
    registered(service, mail)
    clock.advance(seconds=61)
    service.forgot(EMAIL)
    code = mail.code(EMAIL)
    with pytest.raises(AuthError) as e:
        service.reset(EMAIL, code, "short")
    assert e.value.code == "weak_password"
    service.reset(EMAIL, code, "a brand new long passphrase")


def test_resetting_clears_a_lockout():
    service, _, mail, clock = make()
    registered(service, mail)
    for _ in range(5):
        with pytest.raises(AuthError):
            service.login(EMAIL, "wrong password here")
    clock.advance(seconds=61)
    service.forgot(EMAIL)
    service.reset(EMAIL, mail.code(EMAIL), "a brand new long passphrase")
    assert service.login(EMAIL, "a brand new long passphrase")


# ---- sessions and account --------------------------------------------------------------------


def test_sessions_expire_and_are_removed():
    service, store, mail, clock = make()
    signed = registered(service, mail)
    clock.advance(days=29)
    assert service.authenticate(signed.token)
    clock.advance(days=2)
    assert service.authenticate(signed.token) is None
    assert hash_token(signed.token) not in store.sessions


def test_logging_out_ends_only_that_session():
    service, _, mail, _ = make()
    a = registered(service, mail)
    b = service.login(EMAIL, GOOD)
    service.logout(a.token)
    assert service.authenticate(a.token) is None and service.authenticate(b.token)


@pytest.mark.parametrize("token", [None, "", "not-a-token", "x" * 43])
def test_unknown_tokens_are_not_users(token):
    service, _, _, _ = make()
    assert service.authenticate(token) is None


def test_only_the_hash_of_a_token_is_stored():
    service, store, mail, _ = make()
    signed = registered(service, mail)
    assert signed.token not in store.sessions and hash_token(signed.token) in store.sessions


def test_changing_a_password_needs_the_current_one_and_ends_the_other_sessions():
    service, _, mail, _ = make()
    a = registered(service, mail)
    b = service.login(EMAIL, GOOD)
    keep = service.authenticate(a.token)["session"]
    with pytest.raises(AuthError) as e:
        service.change_password(UID1, "not my password", "a brand new long passphrase", keep)
    assert e.value.code == "invalid_credentials"
    service.change_password(UID1, GOOD, "a brand new long passphrase", keep)
    assert service.authenticate(a.token) and service.authenticate(b.token) is None
    with pytest.raises(AuthError):
        service.login(EMAIL, GOOD)


def test_the_new_password_must_differ_and_pass_the_policy():
    service, _, mail, _ = make()
    a = registered(service, mail)
    keep = service.authenticate(a.token)["session"]
    for bad in (GOOD, "short"):
        with pytest.raises(AuthError) as e:
            service.change_password(UID1, GOOD, bad, keep)
        assert e.value.code == "weak_password"


def test_signing_out_other_devices_keeps_this_one():
    service, _, mail, _ = make()
    a = registered(service, mail)
    b = service.login(EMAIL, GOOD)
    keep = service.authenticate(a.token)["session"]
    assert service.sign_out_others(UID1, keep) == 1
    assert service.authenticate(a.token) and service.authenticate(b.token) is None
    assert [s["current"] for s in service.sessions(UID1, keep)] == [True]


def test_a_mail_failure_does_not_break_the_request():
    service, _, _, _ = make()

    class Broken:
        def send(self, *a, **k):
            raise ConnectionError("smtp down")

    service.mailer = Broken()
    assert service.register(EMAIL, GOOD, "")["email"] == EMAIL
