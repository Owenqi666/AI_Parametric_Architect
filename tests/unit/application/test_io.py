from __future__ import annotations

from pathlib import Path

import pytest

from ai_parametric_architect.application import ModelDocumentDecodeError, load_model_document


def test_load_model_document_reads_json_object(tmp_path: Path) -> None:
    path = tmp_path / "model.json"
    path.write_text('{"schema_version": "1.0.0"}', encoding="utf-8")

    assert load_model_document(path) == {"schema_version": "1.0.0"}


@pytest.mark.parametrize("content", ["[1, 2]", '{"value": NaN}', '{"broken":'])
def test_load_model_document_rejects_non_object_or_non_standard_json(
    tmp_path: Path, content: str
) -> None:
    path = tmp_path / "model.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ModelDocumentDecodeError):
        load_model_document(path)
