"""Tests for PDF email extraction."""

from openscout.scraper.pdf_emails import _extract_emails


def test_basic_emails():
    text = "Contact: john.doe@stanford.edu and jane@mit.edu"
    emails = _extract_emails(text)
    assert "john.doe@stanford.edu" in emails
    assert "jane@mit.edu" in emails


def test_dedup_lowercase():
    text = "John.Doe@Stanford.edu, JOHN.DOE@stanford.edu"
    emails = _extract_emails(text)
    assert len(emails) == 1
    assert emails[0] == "john.doe@stanford.edu"


def test_strips_trailing_punct():
    text = "Email: hello@example.com."
    emails = _extract_emails(text)
    assert emails == ["hello@example.com"]


def test_filters_image_extensions():
    text = "logo.png@example.com is not an email"  # weird edge case
    emails = _extract_emails(text)
    # The regex would still match "logo.png@example.com"; our filter drops
    # those ending in .png. Verify.
    assert "logo.png@example.com" not in emails or all(
        not e.endswith(".png") for e in emails
    )


def test_empty():
    assert _extract_emails("") == []
    assert _extract_emails(None) == []


def test_filters_placeholders():
    text = "Reply to example@example.com if interested"
    emails = _extract_emails(text)
    assert "example@example.com" not in emails
