from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.db.enums import TransactionType
from app.schemas.common import MontraModel, amount_validator


class TransactionCreate(MontraModel):
    transaction_type: TransactionType
    account_id: str
    amount: Decimal
    occurred_at: datetime
    category_id: str | None = None
    description: str | None = Field(default=None, max_length=255)
    merchant: str | None = Field(default=None, max_length=160)
    notes: str | None = None
    reference: str | None = Field(default=None, max_length=120)
    # A charge levied alongside the expense — posted as its own line, not
    # added to the amount above.
    fee_amount: Decimal | None = None

    _v_amount = amount_validator("amount")
    _v_fee = amount_validator("fee_amount")


class TransactionUpdate(MontraModel):
    amount: Decimal | None = None
    occurred_at: datetime | None = None
    category_id: str | None = None
    description: str | None = Field(default=None, max_length=255)
    merchant: str | None = Field(default=None, max_length=160)
    notes: str | None = None
    reference: str | None = Field(default=None, max_length=120)

    _v_amount = amount_validator("amount")


class TransferCreate(MontraModel):
    source_account_id: str
    destination_account_id: str
    source_amount: Decimal
    destination_amount: Decimal | None = None
    occurred_at: datetime
    notes: str | None = None
    # Charged to the sender, posted as its own expense line on the source
    # account rather than being added to the amount that moves.
    fee_amount: Decimal | None = None

    _v_source = amount_validator("source_amount")
    _v_dest = amount_validator("destination_amount")
    _v_fee = amount_validator("fee_amount")


class CategoryCreate(MontraModel):
    name: str = Field(min_length=1, max_length=120)
    category_type: str
    parent_category_id: str | None = None
