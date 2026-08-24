"""Household membership and invitations (Implementation Plan Phase 16).

A Family governs visibility; it never owns money. Accounts and loans keep their
own owner, and membership only decides who may see or touch them.
"""

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from app.core.security import generate_session_token, hash_session_token
from app.db.base import utcnow
from app.db.enums import (
    FamilyRole,
    FamilyStatus,
    InvitationStatus,
    MembershipStatus,
)
from app.models.family import Family, FamilyInvitation, FamilyMembership
from app.models.user import User

INVITATION_TTL_DAYS = 7


# ------------------------------------------------------------------ membership


def active_membership(db: DbSession, user: User) -> FamilyMembership | None:
    return db.scalar(
        select(FamilyMembership).where(
            FamilyMembership.user_id == user.id,
            FamilyMembership.status == MembershipStatus.ACTIVE,
        )
    )


def create_family(db: DbSession, *, user: User, name: str, base_currency: str) -> Family:
    if active_membership(db, user) is not None:
        raise Conflict("You already belong to a household.", code="ACTIVE_FAMILY_ALREADY_EXISTS")

    family = Family(
        name=name.strip(),
        base_currency=base_currency.upper(),
        status=FamilyStatus.ACTIVE,
        created_by=user.id,
    )
    db.add(family)
    db.flush()

    db.add(
        FamilyMembership(
            family_id=family.id,
            user_id=user.id,
            role=FamilyRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )
    )
    try:
        db.flush()
    except IntegrityError as exc:  # pragma: no cover - guarded above too
        db.rollback()
        raise Conflict(
            "You already belong to a household.", code="ACTIVE_FAMILY_ALREADY_EXISTS"
        ) from exc
    return family


def require_membership(db: DbSession, user: User, family_id: uuid.UUID) -> FamilyMembership:
    membership = db.scalar(
        select(FamilyMembership).where(
            FamilyMembership.user_id == user.id,
            FamilyMembership.family_id == family_id,
            FamilyMembership.status == MembershipStatus.ACTIVE,
        )
    )
    if membership is None:
        # 404 rather than 403: the API should not confirm that a household the
        # caller has nothing to do with exists.
        raise NotFound("Household not found.", code="FAMILY_NOT_FOUND")
    return membership


def require_owner(db: DbSession, user: User, family_id: uuid.UUID) -> FamilyMembership:
    membership = require_membership(db, user, family_id)
    if membership.role is not FamilyRole.OWNER:
        raise PermissionDenied("Only the household owner can do that.", code="INVITE_NOT_ALLOWED")
    return membership


def members(db: DbSession, family_id: uuid.UUID) -> list[tuple[FamilyMembership, User]]:
    rows = db.execute(
        select(FamilyMembership, User)
        .join(User, User.id == FamilyMembership.user_id)
        .where(FamilyMembership.family_id == family_id)
        .order_by(FamilyMembership.joined_at)
    ).all()
    return [(m, u) for m, u in rows]


# ----------------------------------------------------------------- invitations


def invite(
    db: DbSession,
    *,
    user: User,
    family_id: uuid.UUID,
    invitee_email: str | None,
    proposed_role: FamilyRole = FamilyRole.ADULT,
) -> tuple[FamilyInvitation, str]:
    """Create an invitation. Returns the row and the raw token, which is shown
    once and never stored."""
    require_owner(db, user, family_id)

    if proposed_role is FamilyRole.OWNER:
        raise ValidationFailed(
            "A household has one owner.",
            code="INVALID_ROLE",
            details=[{"field": "proposed_role", "message": "Invite as ADULT or MEMBER."}],
        )

    email = invitee_email.strip().lower() if invitee_email else None

    if email:
        existing_user = db.scalar(select(User).where(User.email == email))
        if existing_user is not None:
            already = db.scalar(
                select(FamilyMembership).where(
                    FamilyMembership.user_id == existing_user.id,
                    FamilyMembership.family_id == family_id,
                    FamilyMembership.status == MembershipStatus.ACTIVE,
                )
            )
            if already is not None:
                raise Conflict("They are already in this household.", code="MEMBER_ALREADY_EXISTS")

        pending = db.scalar(
            select(FamilyInvitation).where(
                FamilyInvitation.family_id == family_id,
                FamilyInvitation.invitee_email == email,
                FamilyInvitation.status == InvitationStatus.PENDING,
            )
        )
        if pending is not None:
            raise Conflict(
                "There is already a pending invitation for that address.",
                code="INVITATION_ALREADY_PENDING",
            )

    token = generate_session_token()
    invitation = FamilyInvitation(
        family_id=family_id,
        invited_by=user.id,
        invitee_email=email,
        token_hash=hash_session_token(token),
        proposed_role=proposed_role,
        status=InvitationStatus.PENDING,
        expires_at=utcnow() + timedelta(days=INVITATION_TTL_DAYS),
    )
    db.add(invitation)
    db.flush()
    return invitation, token


def _resolve_invitation(db: DbSession, token: str) -> FamilyInvitation:
    invitation = db.scalar(
        select(FamilyInvitation).where(FamilyInvitation.token_hash == hash_session_token(token))
    )
    if invitation is None:
        raise NotFound("Invitation not found.", code="INVITATION_NOT_FOUND")
    return invitation


def accept_invitation(db: DbSession, *, user: User, token: str) -> FamilyMembership:
    """Join a household.

    Atomic: validate, check the caller is free to join, mark accepted, create
    membership. Existing accounts stay PRIVATE — joining a household shares
    nothing by itself (Implementation Plan Phase 18).
    """
    invitation = _resolve_invitation(db, token)

    if invitation.status is not InvitationStatus.PENDING:
        raise Conflict("That invitation is no longer open.", code="INVITATION_NOT_PENDING")
    if invitation.expires_at <= utcnow():
        invitation.status = InvitationStatus.EXPIRED
        db.flush()
        raise Conflict("That invitation has expired.", code="INVITATION_EXPIRED")

    # An address-specific invitation belongs to that address.
    if invitation.invitee_email and invitation.invitee_email != user.email:
        raise NotFound("Invitation not found.", code="INVITATION_NOT_FOUND")

    if active_membership(db, user) is not None:
        raise Conflict(
            "Leave your current household before joining another.",
            code="ACTIVE_FAMILY_ALREADY_EXISTS",
        )

    previous = db.scalar(
        select(FamilyMembership).where(
            FamilyMembership.user_id == user.id,
            FamilyMembership.family_id == invitation.family_id,
        )
    )
    if previous is not None:
        # Rejoining a household they left: reuse the row, since (family, user)
        # is unique.
        previous.status = MembershipStatus.ACTIVE
        previous.role = invitation.proposed_role
        previous.joined_at = utcnow()
        previous.left_at = None
        membership = previous
    else:
        membership = FamilyMembership(
            family_id=invitation.family_id,
            user_id=user.id,
            role=invitation.proposed_role,
            status=MembershipStatus.ACTIVE,
        )
        db.add(membership)

    invitation.status = InvitationStatus.ACCEPTED
    invitation.accepted_by = user.id
    invitation.accepted_at = utcnow()
    db.flush()
    return membership


def decline_invitation(db: DbSession, *, user: User, token: str) -> FamilyInvitation:
    invitation = _resolve_invitation(db, token)
    if invitation.status is not InvitationStatus.PENDING:
        raise Conflict("That invitation is no longer open.", code="INVITATION_NOT_PENDING")
    if invitation.invitee_email and invitation.invitee_email != user.email:
        raise NotFound("Invitation not found.", code="INVITATION_NOT_FOUND")
    invitation.status = InvitationStatus.DECLINED
    db.flush()
    return invitation


def cancel_invitation(
    db: DbSession, *, user: User, family_id: uuid.UUID, invitation_id: uuid.UUID
) -> FamilyInvitation:
    require_owner(db, user, family_id)
    invitation = db.get(FamilyInvitation, invitation_id)
    if invitation is None or invitation.family_id != family_id:
        raise NotFound("Invitation not found.", code="INVITATION_NOT_FOUND")
    if invitation.status is not InvitationStatus.PENDING:
        raise Conflict("That invitation is no longer open.", code="INVITATION_NOT_PENDING")
    invitation.status = InvitationStatus.CANCELLED
    db.flush()
    return invitation


# ------------------------------------------------------------------- departure


def _unshare_everything(db: DbSession, *, user_id: uuid.UUID, family_id: uuid.UUID) -> None:
    """Return a departing member's accounts and loans to PRIVATE.

    Leaving a household must not leave their finances visible to it.
    """
    from app.db.enums import Visibility
    from app.models.finance import Account
    from app.models.loans import Loan

    for model in (Account, Loan):
        rows = db.scalars(
            select(model).where(model.owner_user_id == user_id, model.family_id == family_id)
        ).all()
        for row in rows:
            row.visibility = Visibility.PRIVATE
            row.family_id = None


def leave_family(db: DbSession, *, user: User) -> FamilyMembership:
    membership = active_membership(db, user)
    if membership is None:
        raise NotFound("You are not in a household.", code="NO_ACTIVE_FAMILY")

    if membership.role is FamilyRole.OWNER:
        others = db.scalar(
            select(FamilyMembership).where(
                FamilyMembership.family_id == membership.family_id,
                FamilyMembership.user_id != user.id,
                FamilyMembership.status == MembershipStatus.ACTIVE,
            )
        )
        if others is not None:
            raise Conflict(
                "Hand ownership to another member before leaving.",
                code="OWNER_CANNOT_LEAVE",
            )
        # Last one out closes the household.
        family = db.get(Family, membership.family_id)
        if family is not None:
            family.status = FamilyStatus.INACTIVE
            family.deactivated_at = utcnow()

    _unshare_everything(db, user_id=user.id, family_id=membership.family_id)
    membership.status = MembershipStatus.LEFT
    membership.left_at = utcnow()
    db.flush()
    return membership


def remove_member(
    db: DbSession, *, user: User, family_id: uuid.UUID, member_user_id: uuid.UUID
) -> FamilyMembership:
    require_owner(db, user, family_id)
    if member_user_id == user.id:
        raise ValidationFailed(
            "Use leave rather than removing yourself.", code="CANNOT_REMOVE_SELF"
        )

    membership = db.scalar(
        select(FamilyMembership).where(
            FamilyMembership.family_id == family_id,
            FamilyMembership.user_id == member_user_id,
            FamilyMembership.status == MembershipStatus.ACTIVE,
        )
    )
    if membership is None:
        raise NotFound("Member not found.", code="MEMBER_NOT_FOUND")

    _unshare_everything(db, user_id=member_user_id, family_id=family_id)
    membership.status = MembershipStatus.REMOVED
    membership.left_at = utcnow()
    db.flush()
    return membership


def set_member_role(
    db: DbSession,
    *,
    user: User,
    family_id: uuid.UUID,
    member_user_id: uuid.UUID,
    role: FamilyRole,
) -> FamilyMembership:
    require_owner(db, user, family_id)
    membership = db.scalar(
        select(FamilyMembership).where(
            FamilyMembership.family_id == family_id,
            FamilyMembership.user_id == member_user_id,
            FamilyMembership.status == MembershipStatus.ACTIVE,
        )
    )
    if membership is None:
        raise NotFound("Member not found.", code="MEMBER_NOT_FOUND")

    if role is FamilyRole.OWNER:
        # Ownership transfers rather than duplicates.
        current = require_owner(db, user, family_id)
        current.role = FamilyRole.ADULT
    membership.role = role
    db.flush()
    return membership


# ----------------------------------------------------------------- serializing


def serialize_family(db: DbSession, family: Family, membership: FamilyMembership) -> dict:
    return {
        "id": str(family.id),
        "name": family.name,
        "base_currency": family.base_currency,
        "status": family.status.value,
        "role": membership.role.value,
        "members": [
            {
                "user_id": str(m.user_id),
                "display_name": u.display_name,
                "email": u.email,
                "role": m.role.value,
                "status": m.status.value,
                "joined_at": m.joined_at.isoformat(),
            }
            for m, u in members(db, family.id)
        ],
    }


def serialize_invitation(invitation: FamilyInvitation, token: str | None = None) -> dict:
    payload = {
        "id": str(invitation.id),
        "invitee_email": invitation.invitee_email,
        "proposed_role": invitation.proposed_role.value,
        "status": invitation.status.value,
        "expires_at": invitation.expires_at.isoformat(),
        "created_at": invitation.created_at.isoformat(),
    }
    if token is not None:
        # Returned once, at creation. It is not recoverable afterwards.
        payload["token"] = token
    return payload
