import pytest
from pydantic import ValidationError

from app.state.release_notes_models import (
    CodeBlock,
    HeadingBlock,
    ImageBlock,
    ListBlock,
    ParagraphBlock,
    ReleaseNoteItem,
    ReleaseNoteRecord,
    ReleaseNotesIndex,
    TableBlock,
)


# ---------------------------------------------------------------------------
# Block roundtrips
# ---------------------------------------------------------------------------

def test_paragraph_roundtrip():
    b = ParagraphBlock(text="Hello world")
    raw = b.model_dump(mode="json")
    assert raw == {"type": "paragraph", "text": "Hello world"}
    assert ParagraphBlock.model_validate(raw) == b


def test_heading_roundtrip():
    b = HeadingBlock(level=3, text="Bug Description")
    raw = b.model_dump(mode="json")
    assert raw == {"type": "heading", "level": 3, "text": "Bug Description"}
    assert HeadingBlock.model_validate(raw) == b


def test_image_roundtrip():
    b = ImageBlock(image_id="p2_img1", describes="Screenshot of the config screen")
    raw = b.model_dump(mode="json")
    assert raw["type"] == "image"
    assert raw["image_id"] == "p2_img1"
    assert ImageBlock.model_validate(raw) == b


def test_list_roundtrip():
    b = ListBlock(ordered=True, items=["first", "second"])
    raw = b.model_dump(mode="json")
    assert raw == {"type": "list", "ordered": True, "items": ["first", "second"]}
    assert ListBlock.model_validate(raw) == b


def test_table_roundtrip():
    b = TableBlock(headers=["Col A", "Col B"], rows=[["1", "2"], ["3", "4"]])
    raw = b.model_dump(mode="json")
    assert raw["type"] == "table"
    assert len(raw["rows"]) == 2
    assert TableBlock.model_validate(raw) == b


def test_code_roundtrip():
    b = CodeBlock(text="SELECT * FROM flights")
    raw = b.model_dump(mode="json")
    assert raw == {"type": "code", "text": "SELECT * FROM flights"}
    assert CodeBlock.model_validate(raw) == b


# ---------------------------------------------------------------------------
# Discriminated union
# ---------------------------------------------------------------------------

def test_discriminated_union_resolves_correct_types():
    item = ReleaseNoteItem(
        section="Test",
        am_card="AM100",
        title="T",
        summary="S",
        body=[
            {"type": "paragraph", "text": "p"},
            {"type": "heading", "level": 3, "text": "h"},
            {"type": "image", "image_id": "p1_img1", "describes": "d"},
            {"type": "list", "ordered": False, "items": ["a"]},
            {"type": "table", "headers": ["H"], "rows": [["R"]]},
            {"type": "code", "text": "x"},
        ],
    )
    types = [type(b) for b in item.body]
    assert types == [ParagraphBlock, HeadingBlock, ImageBlock, ListBlock, TableBlock, CodeBlock]


def test_discriminated_union_rejects_unknown_type():
    with pytest.raises(ValidationError):
        ReleaseNoteItem(
            section="Test",
            am_card="AM100",
            title="T",
            summary="S",
            body=[{"type": "unknown", "text": "x"}],
        )


# ---------------------------------------------------------------------------
# HeadingBlock level
# ---------------------------------------------------------------------------

def test_heading_level_preserved():
    for lvl in (1, 2, 3):
        h = HeadingBlock(level=lvl, text="title")
        assert h.level == lvl
        assert HeadingBlock.model_validate(h.model_dump(mode="json")).level == lvl


# ---------------------------------------------------------------------------
# am_card validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("valid", ["AM10", "AM123", "AM1234", "AM12345"])
def test_am_card_valid(valid):
    item = ReleaseNoteItem(section="S", am_card=valid, title="T", summary="S")
    assert item.am_card == valid


@pytest.mark.parametrize("invalid", ["AM1", "AM123456", "XY123", "", "am123", "1234"])
def test_am_card_invalid(invalid):
    with pytest.raises(ValidationError):
        ReleaseNoteItem(section="S", am_card=invalid, title="T", summary="S")


# ---------------------------------------------------------------------------
# Full record roundtrip
# ---------------------------------------------------------------------------

def test_record_roundtrip(sample_release_note_record):
    raw = sample_release_note_record.model_dump(mode="json")
    reloaded = ReleaseNoteRecord.model_validate(raw)
    assert reloaded.version == "8.0.18.1"
    assert len(reloaded.items) == 1
    assert reloaded.items[0].am_card == "AM1393"
    assert len(reloaded.items[0].body) == 4
    types = [type(b).__name__ for b in reloaded.items[0].body]
    assert types == ["HeadingBlock", "ParagraphBlock", "ImageBlock", "CodeBlock"]


# ---------------------------------------------------------------------------
# Index with multiple records
# ---------------------------------------------------------------------------

def test_index_multiple_records(sample_release_note_record):
    import copy
    rec2 = copy.deepcopy(sample_release_note_record)
    rec2.version = "8.0.19.0"

    index = ReleaseNotesIndex(
        product_id="ACARS_V8_0",
        updated_at="2026-04-11T12:00:00+00:00",
        release_notes={
            sample_release_note_record.version: sample_release_note_record,
            rec2.version: rec2,
        },
    )
    raw = index.model_dump(mode="json")
    reloaded = ReleaseNotesIndex.model_validate(raw)
    assert len(reloaded.release_notes) == 2
    assert "8.0.18.1" in reloaded.release_notes
    assert "8.0.19.0" in reloaded.release_notes


# ---------------------------------------------------------------------------
# Empty defaults
# ---------------------------------------------------------------------------

def test_empty_defaults():
    item = ReleaseNoteItem(section="S", am_card="AM100", title="T", summary="S")
    assert item.customers == []
    assert item.body == []

    record = ReleaseNoteRecord(
        version="1.0.0",
        extracted_at="2026-01-01T00:00:00+00:00",
        extractor="test",
        extractor_version=1,
        source_pdf_path="test.pdf",
        source_pdf_hash="abc",
        source_pdf_pages=1,
    )
    assert record.items == []
