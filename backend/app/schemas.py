"""Request models with server-side validation (design §11). Errors are returned in the
§10.2 shape by errors.py, with the field name and a readable message."""
import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.services.dates import today_ist

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _min_comment(v: str) -> str:
    v = (v or "").strip()
    if len(v) < 10:
        raise ValueError("Comment must be at least 10 characters")
    return v


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_.]+$")
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=2, max_length=100)


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=72)
    # "Sign in as" dropdown. Omitted = all roles of the account (backward compatible).
    role: Literal["APPLICANT", "KYC_OFFICER", "COMPLIANCE_OFFICER", "KYC_AND_COMPLIANCE"] | None = None


class ApplicationCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    dob: date
    gender: Literal["M", "F", "O"]
    pan_number: str
    aadhaar_last4: str
    mobile: str
    email: str = Field(max_length=120)
    address: str = Field(min_length=5, max_length=300)
    city: str = Field(min_length=2, max_length=60)
    state: str = Field(min_length=2, max_length=60)
    pincode: str
    occupation_code: str = Field(min_length=2, max_length=40)
    annual_income: float = Field(ge=0, le=1e12)
    consent: bool

    @field_validator("full_name", "address", "city", "state")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("dob")
    @classmethod
    def _dob(cls, v: date) -> date:
        if v > today_ist():
            raise ValueError("Date of birth cannot be in the future")
        return v

    @field_validator("pan_number")
    @classmethod
    def _pan(cls, v: str) -> str:
        v = v.strip().upper()
        if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", v):
            raise ValueError("PAN must look like ABCDE1234F")
        return v

    @field_validator("aadhaar_last4")
    @classmethod
    def _aadhaar(cls, v: str) -> str:
        digits = re.sub(r"[\s-]", "", v or "")
        if re.fullmatch(r"[0-9]{12}", digits):
            raise ValueError("Enter only the last 4 digits of Aadhaar, not the full 12-digit number")
        if not re.fullmatch(r"[0-9]{4}", digits):
            raise ValueError("Enter the last 4 digits of your Aadhaar")
        return digits

    @field_validator("mobile")
    @classmethod
    def _mobile(cls, v: str) -> str:
        v = v.strip()
        if not re.fullmatch(r"[6-9][0-9]{9}", v):
            raise ValueError("Mobile must be a 10-digit Indian number")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip()
        if not _EMAIL.match(v):
            raise ValueError("Enter a valid email address")
        return v

    @field_validator("pincode")
    @classmethod
    def _pincode(cls, v: str) -> str:
        v = v.strip()
        if not re.fullmatch(r"[1-9][0-9]{5}", v):
            raise ValueError("Pincode must be 6 digits and not start with 0")
        return v

    @field_validator("consent")
    @classmethod
    def _consent(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("Consent to KYC checks is required")
        return v


class FieldCorrectionIn(BaseModel):
    doc_id: str
    field_name: str
    value: str = Field(max_length=300)
    reason: str
    version: int | None = None

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str) -> str:
        return _min_comment(v)


class RecommendIn(BaseModel):
    action: Literal["APPROVE", "REJECT", "REQUEST_RESUBMISSION"]
    comment: str
    version: int | None = None

    @field_validator("comment")
    @classmethod
    def _comment(cls, v: str) -> str:
        return _min_comment(v)


class CheckIn(BaseModel):
    action: Literal["APPROVE", "REJECT", "SEND_BACK"]
    comment: str
    version: int | None = None

    @field_validator("comment")
    @classmethod
    def _comment(cls, v: str) -> str:
        return _min_comment(v)


class ConfigUpdateIn(BaseModel):
    value: Any
