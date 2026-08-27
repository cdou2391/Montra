from pydantic import Field

from app.schemas.common import MontraModel


class AttachmentCreate(MontraModel):
    """What the client knows before the upload happens.

    file_size is a claim, verified against the real object on completion. It is
    here so an oversized upload is refused before a link is issued.
    """

    file_name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=120)
    file_size: int = Field(gt=0)
