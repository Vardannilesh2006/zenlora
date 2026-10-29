import os
import io
import pytest
from app import app, LOGIN_ATTEMPTS
from services.whatsapp_openwa import normalize_phone, check_gateway_health

def test_admin_password_and_login_success():
    """Verify that password 'Nilesh@2006' logs in successfully and sets authenticated session"""
    client = app.test_client()

    # Reset any test lockout
    LOGIN_ATTEMPTS.clear()

    # 1. Incorrect password returns 401
    res_bad = client.post("/login", data={"password": "WrongPassword!"})
    assert res_bad.status_code == 401
    assert b"Password was not accepted" in res_bad.data

    # 2. Correct password 'Nilesh@2006' returns 302 redirect to cockpit/dashboard
    res_good = client.post("/login", data={"password": "Nilesh@2006"}, follow_redirects=False)
    assert res_good.status_code == 302
    assert res_good.headers.get("Location") in {"/dashboard", "/cockpit", "/"}

    # 3. Authenticated session can access cockpit
    with client.session_transaction() as sess:
        sess["zenos_admin_authenticated"] = True
    res_auth = client.get("/cockpit")
    assert res_auth.status_code == 200


def test_login_brute_force_lockout():
    """Verify that 5 failed attempts locks the IP for 15 minutes with 429 status"""
    client = app.test_client()
    LOGIN_ATTEMPTS.clear()

    for i in range(4):
        res = client.post("/login", data={"password": "WrongPassword!"})
        assert res.status_code == 401

    # 5th attempt triggers lockout
    res_lock = client.post("/login", data={"password": "WrongPassword!"})
    assert res_lock.status_code == 429
    assert b"Too many failed attempts" in res_lock.data or b"Locked" in res_lock.data


def test_openwa_health_and_normalization():
    """Verify Indian phone normalization and OpenWA gateway connection check"""
    # 1. Normalization
    assert normalize_phone("7250366344") == "917250366344"
    assert normalize_phone("+91-7250366344") == "917250366344"
    assert normalize_phone("07250366344") == "917250366344"
    assert normalize_phone("917250366344") == "917250366344"

    # 2. Health check against active OpenWA on :2785
    health = check_gateway_health()
    assert health.get("online") is True
    assert health.get("connected") is True
    assert health.get("phone") == "919771370945"


def test_security_headers_present():
    """Verify enterprise HTTP security headers are attached on all responses"""
    client = app.test_client()
    res = client.get("/api/health")
    assert res.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-XSS-Protection") == "1; mode=block"
    assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
