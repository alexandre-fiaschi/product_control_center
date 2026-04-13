from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Body block types — discriminated union on "type"
# ---------------------------------------------------------------------------

class ParagraphBlock(BaseModel):
    type: Literal["paragraph"] = "paragraph"
    text: str


class HeadingBlock(BaseModel):
    type: Literal["heading"] = "heading"
    level: int
    text: str


class ImageBlock(BaseModel):
    type: Literal["image"] = "image"
    image_id: str
    describes: str


class ListBlock(BaseModel):
    type: Literal["list"] = "list"
    ordered: bool = False
    items: list[str] = Field(default_factory=list)


class TableBlock(BaseModel):
    type: Literal["table"] = "table"
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class CodeBlock(BaseModel):
    type: Literal["code"] = "code"
    text: str


BodyBlock = Annotated[
    Union[ParagraphBlock, HeadingBlock, ImageBlock, ListBlock, TableBlock, CodeBlock],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Release note item + record + index
# ---------------------------------------------------------------------------

class ReleaseNoteItem(BaseModel):
    section: str
    am_card: str = Field(pattern=r"^AM\d{2,5}$")
    customers: list[str] = Field(default_factory=list)
    title: str
    summary: str
    body: list[BodyBlock] = Field(default_factory=list)


class ExtractionUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    model: str
    cost_usd: float


class ReleaseNoteRecord(BaseModel):
    version: str
    extracted_at: datetime
    extractor: str
    extractor_version: int
    source_pdf_path: str
    source_pdf_hash: str
    source_pdf_pages: int
    usage: ExtractionUsage | None = None
    items: list[ReleaseNoteItem] = Field(default_factory=list)


class ReleaseNotesIndex(BaseModel):
    product_id: str
    schema_version: int = 1
    updated_at: datetime
    release_notes: dict[str, ReleaseNoteRecord] = Field(default_factory=dict)
