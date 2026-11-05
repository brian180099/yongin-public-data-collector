import pytest
import io
import zipfile

from yongin_collector.pipeline import QualityError, prepare_content_key_csv_snapshot
from yongin_collector.collect import validate_large_csv_zip


def test_content_keys_preserve_identical_rows_and_ignore_order():
    first = prepare_content_key_csv_snapshot("name,value\nA,1\nA,1\nB,2\n".encode())
    reordered = prepare_content_key_csv_snapshot("name,value\nB,2\nA,1\nA,1\n".encode())
    assert len(first.records) == 3
    assert first.quality["duplicate_row_count"] == 1
    assert first.records == reordered.records


def test_malformed_row_is_rejected():
    with pytest.raises(QualityError):
        prepare_content_key_csv_snapshot(b"name,value\nA,1,extra\n")


def test_large_zip_validator_requires_flat_csv_members():
    def archive(name):
        target = io.BytesIO()
        with zipfile.ZipFile(target, "w") as out:
            out.writestr(name, "name,value\nA,1\n")
        return target.getvalue()

    validate_large_csv_zip(archive("safe.csv"))
    with pytest.raises(ValueError):
        validate_large_csv_zip(archive("../escape.csv"))
    with pytest.raises(ValueError):
        validate_large_csv_zip(archive("notes.txt"))
