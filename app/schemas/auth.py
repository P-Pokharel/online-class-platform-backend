from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import UserRole

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


def _normalize_email(email: str) -> str:
    return email.strip().lower()

NormalizedEmail = Annotated[EmailStr, AfterValidator(_normalize_email)]

class RegisterRequest(BaseModel):
    email: NormalizedEmail
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    full_name: str = Field(min_length=1, max_length=150)

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("full_name must not be blank")
        return value


class LoginRequest(BaseModel):
    email: Annotated[str, AfterValidator(_normalize_email)] = Field(max_length=255)
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: UserRole
