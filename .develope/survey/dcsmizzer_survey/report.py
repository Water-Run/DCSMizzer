from __future__ import annotations

import json

from .model import SurveyResult


def manifest_to_json(
    result: SurveyResult,
    *,
    include_file_details: bool = False,
) -> str:
    return (
        json.dumps(
            result.to_dict(include_file_details=include_file_details),
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
