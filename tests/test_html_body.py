"""Tests for HTML email bodies (multipart/alternative with text fallback)."""

import base64
import email

from gmail_cli.api import GmailAPI


def _api():
    # Bypass __init__ (which requires auth); the message builders below do not
    # touch self.service.
    return GmailAPI.__new__(GmailAPI)


def _parse(msg_dict):
    raw = base64.urlsafe_b64decode(msg_dict["raw"].encode())
    return email.message_from_bytes(raw)


def test_plain_message_is_single_text_plain_part():
    msg = _parse(_api()._create_message("a@x.com", "Hi", "Hello", cc=None, html=False))
    assert msg.get_content_type() == "text/plain"
    assert "Hello" in msg.get_payload(decode=True).decode()


def test_html_message_is_multipart_alternative_with_fallback():
    body = "<p>Hello <b>world</b></p><br><a href='https://x.com'>link</a>"
    msg = _parse(_api()._create_message("a@x.com", "Hi", body, cc="c@x.com", html=True))

    assert msg.get_content_type() == "multipart/alternative"
    assert msg["cc"] == "c@x.com"

    parts = {p.get_content_type(): p.get_payload(decode=True).decode() for p in msg.get_payload()}
    assert set(parts) == {"text/plain", "text/html"}
    assert "<b>world</b>" in parts["text/html"]     # HTML preserved verbatim
    assert "world" in parts["text/plain"]           # readable fallback present
    assert "<b>" not in parts["text/plain"]         # tags stripped from fallback


def test_html_to_text_strips_tags_and_unescapes_entities():
    out = _api()._html_to_text("<p>A &amp; B</p><br>C")
    assert "A & B" in out
    assert "C" in out
    assert "<" not in out
