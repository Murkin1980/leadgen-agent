import pytest

from app.outreach.phone import PhoneNumberError, PhoneNumberService


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("8 707 123 45 67", "+77071234567"),
        ("+7 (707) 123-45-67", "+77071234567"),
        ("77071234567", "+77071234567"),
        ("7071234567", "+77071234567"),
    ],
)
def test_normalize_kz_phone(raw, expected):
    assert PhoneNumberService.normalize(raw) == expected


def test_mask_phone():
    assert PhoneNumberService.mask("+7 707 123 45 67") == "+7******4567"


@pytest.mark.parametrize("raw", [None, "123", "+70000000000", "not-a-phone"])
def test_invalid_phone(raw):
    with pytest.raises(PhoneNumberError):
        PhoneNumberService.normalize(raw)
