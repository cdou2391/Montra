from pydantic import EmailStr, Field

from app.schemas.common import MontraModel


class RegisterRequest(MontraModel):
    email: EmailStr
    password: str = Field(min_length=1)
    display_name: str | None = Field(default=None, max_length=120)
    base_currency: str = Field(min_length=3, max_length=3)
    timezone: str = Field(default="UTC", max_length=64)


class LoginRequest(MontraModel):
    email: EmailStr
    password: str


class PreferencesUpdate(MontraModel):
    hide_balances: bool | None = None
    persist_balance_privacy: bool | None = None
    default_context: str | None = None
    default_reminder_days: int | None = Field(default=None, ge=0, le=30)
    notifications_enabled: bool | None = None
