from pydantic import EmailStr, Field

from app.db.enums import FamilyRole
from app.schemas.common import MontraModel


class FamilyCreate(MontraModel):
    name: str = Field(min_length=1, max_length=160)
    base_currency: str = Field(min_length=3, max_length=3)


class FamilyUpdate(MontraModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    base_currency: str | None = Field(default=None, min_length=3, max_length=3)


class InvitationCreate(MontraModel):
    invitee_email: EmailStr | None = None
    proposed_role: FamilyRole = FamilyRole.ADULT


class MemberRoleUpdate(MontraModel):
    role: FamilyRole
