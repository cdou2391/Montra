"""Household endpoints (API spec sections 15-17)."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.api.deps import current_user, db_session
from app.core.errors import NotFound
from app.core.responses import collection, single
from app.models.family import Family, FamilyInvitation
from app.models.user import User
from app.schemas.families import (
    FamilyCreate,
    FamilyUpdate,
    InvitationCreate,
    MemberRoleUpdate,
)
from app.services import audit
from app.services import families as family_service

router = APIRouter(tags=["families"])


@router.post("/families", status_code=status.HTTP_201_CREATED)
def create_family(
    payload: FamilyCreate,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    family = family_service.create_family(
        db, user=user, name=payload.name, base_currency=payload.base_currency
    )
    membership = family_service.active_membership(db, user)
    db.commit()
    db.refresh(family)
    return single(family_service.serialize_family(db, family, membership))


@router.get("/families/current")
def current_family(
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    """The caller's active household, or null. Never an error: not being in one
    is a normal state, not a failure."""
    membership = family_service.active_membership(db, user)
    if membership is None:
        db.commit()
        return single(None)
    family = db.get(Family, membership.family_id)
    payload = family_service.serialize_family(db, family, membership)
    db.commit()
    return single(payload)


@router.patch("/families/{family_id}")
def update_family(
    family_id: uuid.UUID,
    payload: FamilyUpdate,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    membership = family_service.require_owner(db, user, family_id)
    family = db.get(Family, family_id)
    if payload.name is not None:
        family.name = payload.name.strip()
    if payload.base_currency is not None:
        family.base_currency = payload.base_currency.upper()
    db.commit()
    db.refresh(family)
    return single(family_service.serialize_family(db, family, membership))


# ----------------------------------------------------------------- invitations


@router.post("/families/{family_id}/invitations", status_code=status.HTTP_201_CREATED)
def create_invitation(
    family_id: uuid.UUID,
    payload: InvitationCreate,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    invitation, token = family_service.invite(
        db,
        user=user,
        family_id=family_id,
        invitee_email=payload.invitee_email,
        proposed_role=payload.proposed_role,
    )
    db.commit()
    db.refresh(invitation)
    # The token is returned once here and nowhere else; only its hash is kept.
    return single(family_service.serialize_invitation(invitation, token=token))


@router.get("/families/{family_id}/invitations")
def list_invitations(
    family_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    family_service.require_owner(db, user, family_id)
    rows = list(
        db.scalars(
            select(FamilyInvitation)
            .where(FamilyInvitation.family_id == family_id)
            .order_by(FamilyInvitation.created_at.desc())
        )
    )
    payload = [family_service.serialize_invitation(i) for i in rows]
    db.commit()
    return collection(payload, limit=len(payload))


@router.delete("/families/{family_id}/invitations/{invitation_id}")
def cancel_invitation(
    family_id: uuid.UUID,
    invitation_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    invitation = family_service.cancel_invitation(
        db, user=user, family_id=family_id, invitation_id=invitation_id
    )
    db.commit()
    db.refresh(invitation)
    return single(family_service.serialize_invitation(invitation))


@router.post("/family-invitations/{token}/accept")
def accept_invitation(
    token: str,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    membership = family_service.accept_invitation(db, user=user, token=token)
    family = db.get(Family, membership.family_id)
    payload = family_service.serialize_family(db, family, membership)
    db.commit()
    return single(payload)


@router.post("/family-invitations/{token}/decline")
def decline_invitation(
    token: str,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    invitation = family_service.decline_invitation(db, user=user, token=token)
    db.commit()
    db.refresh(invitation)
    return single(family_service.serialize_invitation(invitation))


# --------------------------------------------------------------------- members


@router.get("/families/{family_id}/members")
def list_members(
    family_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    family_service.require_membership(db, user, family_id)
    payload = [
        {
            "user_id": str(m.user_id),
            "display_name": u.display_name,
            "email": u.email,
            "role": m.role.value,
            "status": m.status.value,
            "joined_at": m.joined_at.isoformat(),
        }
        for m, u in family_service.members(db, family_id)
    ]
    db.commit()
    return collection(payload, limit=len(payload))


@router.get("/families/{family_id}/activity")
def family_activity(
    family_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    """The household's audit trail (Implementation Plan Phase 28).

    Membership is the only requirement to read it: the trail exists so members
    can see what changed in the household, and it carries no financial detail
    that would need a narrower audience.
    """
    family_service.require_membership(db, user, family_id)
    events = audit.for_family(db, family_id=family_id, limit=limit)
    names = {
        m.user_id: u.display_name or u.email for m, u in family_service.members(db, family_id)
    }
    payload = [audit.serialize(e, actor_names=names) for e in events]
    db.commit()
    return collection(payload, limit=len(payload))


@router.patch("/families/{family_id}/members/{member_user_id}")
def update_member(
    family_id: uuid.UUID,
    member_user_id: uuid.UUID,
    payload: MemberRoleUpdate,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    membership = family_service.set_member_role(
        db, user=user, family_id=family_id, member_user_id=member_user_id, role=payload.role
    )
    db.commit()
    db.refresh(membership)
    return single({"user_id": str(membership.user_id), "role": membership.role.value})


@router.delete("/families/{family_id}/members/{member_user_id}")
def remove_member(
    family_id: uuid.UUID,
    member_user_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    membership = family_service.remove_member(
        db, user=user, family_id=family_id, member_user_id=member_user_id
    )
    db.commit()
    db.refresh(membership)
    return single({"user_id": str(membership.user_id), "status": membership.status.value})


@router.post("/families/{family_id}/leave")
def leave_family(
    family_id: uuid.UUID,
    db: DbSession = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    membership = family_service.active_membership(db, user)
    if membership is None or membership.family_id != family_id:
        raise NotFound("Household not found.", code="FAMILY_NOT_FOUND")
    membership = family_service.leave_family(db, user=user)
    db.commit()
    return single({"status": membership.status.value})
