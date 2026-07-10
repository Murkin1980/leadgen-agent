from __future__ import annotations

import re


class PhoneNumberError(ValueError):
    pass


class PhoneNumberService:
    """Normalize Kazakhstan phone numbers to E.164 and mask them for logs."""

    @staticmethod
    def normalize(value: str | None) -> str:
        if not value:
            raise PhoneNumberError("Phone number is required")
        digits = re.sub(r"\D", "", value)
        if digits.startswith("8") and len(digits) == 11:
            digits = "7" + digits[1:]
        elif digits.startswith("7") and len(digits) == 11:
            pass
        elif len(digits) == 10:
            digits = "7" + digits
        else:
            raise PhoneNumberError("Invalid Kazakhstan phone number")
        if not digits.startswith("7") or len(digits) != 11:
            raise PhoneNumberError("Phone number must be Kazakhstan E.164")
        if digits[1:] == "0" * 10 or len(set(digits[-7:])) == 1:
            raise PhoneNumberError("Service or obviously invalid phone number")
        return "+" + digits

    @classmethod
    def provider_recipient(cls, value: str | None) -> str:
        return cls.normalize(value).lstrip("+")

    @classmethod
    def mask(cls, value: str | None) -> str:
        try:
            normalized = cls.normalize(value)
        except PhoneNumberError:
            return "<invalid-phone>"
        return f"{normalized[:2]}******{normalized[-4:]}"
