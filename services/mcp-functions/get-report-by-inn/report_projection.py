"""Context-safe projections for contractor reports.

The module is deliberately independent from a Cloud Function handler so the same
projection contract can be used by ``get-report-by-inn`` and
``compare-contractors``.  The default ``full`` view is a strict pass-through: it
returns the original object and therefore cannot change its JSON serialization.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


VALID_VIEWS = frozenset({"full", "compact", "sections"})
DEFAULT_ACTIVE_LIMIT = 20
MAX_ACTIVE_LIMIT = 100

# These are identification/provenance fields, not analytical sections.  They are
# always retained by the sections view when present in the source report.
IDENTITY_ROOT_FIELDS = ("reportDate", "inn", "ogrn", "error")
IDENTITY_BASE_INFO_FIELDS = (
    "inn",
    "ogrn",
    "kpp",
    "okpo",
    "shortName",
    "fullName",
)


class ProjectionValidationError(ValueError):
    """The caller requested an invalid projection."""


@dataclass(frozen=True)
class ProjectionOptions:
    view: str = "full"
    sections: tuple[str, ...] = ()
    active_limit: int = DEFAULT_ACTIVE_LIMIT


def parse_projection_options(params: Mapping[str, Any] | None) -> ProjectionOptions:
    """Parse optional MCP/HTTP parameters into a validated projection request.

    ``view`` is optional and defaults to ``full``.  Parameters unused by a view
    are intentionally ignored so adding them to an old request cannot change the
    default full response.
    """

    params = params or {}
    raw_view = params.get("view", "full")
    if raw_view is None or raw_view == "":
        raw_view = "full"
    if not isinstance(raw_view, str):
        raise ProjectionValidationError("Параметр view должен быть строкой")

    view = raw_view.strip().lower()
    if view not in VALID_VIEWS:
        raise ProjectionValidationError(
            "Параметр view должен быть одним из: full, compact, sections"
        )

    if view == "full":
        return ProjectionOptions(view="full")

    if view == "compact":
        active_limit = _parse_active_limit(
            params.get("active_limit", DEFAULT_ACTIVE_LIMIT)
        )
        return ProjectionOptions(view="compact", active_limit=active_limit)

    sections = _parse_sections(params.get("sections"))
    return ProjectionOptions(view="sections", sections=sections)


def project_from_params(
    report: Mapping[str, Any], params: Mapping[str, Any] | None
) -> Mapping[str, Any]:
    """Apply projection parameters taken directly from an MCP/HTTP request."""

    options = parse_projection_options(params)
    return project_report(
        report,
        view=options.view,
        sections=options.sections,
        active_limit=options.active_limit,
    )


def project_report(
    report: Mapping[str, Any],
    *,
    view: str = "full",
    sections: Sequence[str] | None = None,
    active_limit: int = DEFAULT_ACTIVE_LIMIT,
) -> Mapping[str, Any]:
    """Return a full, compact, or selected-sections report view.

    The full view returns ``report`` itself (not a copy).  Compact and sections
    views never mutate the source object.
    """

    if not isinstance(report, Mapping):
        raise TypeError("report должен быть объектом")

    options = parse_projection_options(
        {
            "view": view,
            "sections": sections,
            "active_limit": active_limit,
        }
    )
    if options.view == "full":
        return report
    if options.view == "compact":
        return _compact_report(report, active_limit=options.active_limit)
    return _sections_report(report, options.sections)


def project_reports(
    reports: Sequence[Mapping[str, Any]],
    *,
    view: str = "full",
    sections: Sequence[str] | None = None,
    active_limit: int = DEFAULT_ACTIVE_LIMIT,
) -> Sequence[Mapping[str, Any]]:
    """Apply one projection to a compare response's report list.

    The full view returns the original sequence, preserving the exact response
    object used by existing callers.
    """

    options = parse_projection_options(
        {
            "view": view,
            "sections": sections,
            "active_limit": active_limit,
        }
    )
    if options.view == "full":
        return reports
    return [
        project_report(
            report,
            view=options.view,
            sections=options.sections,
            active_limit=options.active_limit,
        )
        for report in reports
    ]


def _parse_active_limit(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProjectionValidationError("Параметр active_limit должен быть целым числом")
    if not 0 <= value <= MAX_ACTIVE_LIMIT:
        raise ProjectionValidationError(
            f"Параметр active_limit должен быть от 0 до {MAX_ACTIVE_LIMIT}"
        )
    return value


def _parse_sections(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ProjectionValidationError(
            "Для view=sections нужен непустой массив sections"
        )

    result: list[str] = []
    seen: set[str] = set()
    for raw_path in value:
        if not isinstance(raw_path, str):
            raise ProjectionValidationError(
                "Каждый элемент sections должен быть строкой"
            )
        path = raw_path.strip()
        parts = path.split(".")
        if not path or any(not part or part.startswith("_") for part in parts):
            raise ProjectionValidationError(
                "sections поддерживает имена полей и пути через точку"
            )
        if path not in seen:
            result.append(path)
            seen.add(path)
    return tuple(result)


def _compact_report(
    report: Mapping[str, Any], *, active_limit: int
) -> dict[str, Any]:
    projected = deepcopy(dict(report))
    projected.pop("executionProceedings", None)
    projected.pop("inspections", None)
    projected["executionProceedingsSummary"] = _summarize_execution_proceedings(
        report, active_limit=active_limit
    )
    projected["inspectionsSummary"] = _summarize_inspections(report)
    return projected


def _source_state(report: Mapping[str, Any], field: str) -> tuple[str, Any]:
    if field not in report:
        return "absent", None
    value = report[field]
    if value is None:
        return "null", None
    if isinstance(value, list) and not value:
        return "empty", value
    return "present", value


def _summarize_execution_proceedings(
    report: Mapping[str, Any], *, active_limit: int
) -> dict[str, Any]:
    state, value = _source_state(report, "executionProceedings")
    if state in {"absent", "null"}:
        return {"state": state}

    if state == "empty":
        return {
            "state": "empty",
            "totalCount": 0,
            "activeCount": 0,
            "inactiveCount": 0,
            "unknownActiveCount": 0,
            "activeItems": [],
            "activeItemsLimit": active_limit,
            "activeItemsTruncated": False,
        }

    if not isinstance(value, list):
        return {
            "state": "present",
            "sourceType": type(value).__name__,
            "projectionError": "expected array",
        }

    active_items: list[Any] = []
    active_count = 0
    inactive_count = 0
    unknown_active_count = 0

    for item in value:
        active = item.get("active") if isinstance(item, Mapping) else None
        if active is True:
            active_count += 1
            if len(active_items) < active_limit:
                active_items.append(deepcopy(item))
        elif active is False:
            inactive_count += 1
        else:
            unknown_active_count += 1

    return {
        "state": "present",
        "totalCount": len(value),
        "activeCount": active_count,
        "inactiveCount": inactive_count,
        "unknownActiveCount": unknown_active_count,
        "activeItems": active_items,
        "activeItemsLimit": active_limit,
        "activeItemsTruncated": active_count > len(active_items),
    }


def _summarize_inspections(report: Mapping[str, Any]) -> dict[str, Any]:
    state, value = _source_state(report, "inspections")
    if state in {"absent", "null"}:
        return {"state": state}

    if state == "empty":
        return {
            "state": "empty",
            "totalCount": 0,
            "statusCounts": {},
            "missingStatusCount": 0,
            "authorityCount": 0,
            "missingAuthorityCount": 0,
            "withEndDateCount": 0,
            "withoutEndDateCount": 0,
        }

    if not isinstance(value, list):
        return {
            "state": "present",
            "sourceType": type(value).__name__,
            "projectionError": "expected array",
        }

    statuses: Counter[str] = Counter()
    authorities: set[str] = set()
    missing_status_count = 0
    missing_authority_count = 0
    with_end_date_count = 0

    for item in value:
        if not isinstance(item, Mapping):
            missing_status_count += 1
            missing_authority_count += 1
            continue

        status = item.get("inspectionStatus")
        if isinstance(status, str) and status:
            statuses[status] += 1
        else:
            missing_status_count += 1

        authority = item.get("authorityName")
        if isinstance(authority, str) and authority:
            authorities.add(authority)
        else:
            missing_authority_count += 1

        if item.get("endDate") not in (None, ""):
            with_end_date_count += 1

    return {
        "state": "present",
        "totalCount": len(value),
        "statusCounts": dict(sorted(statuses.items())),
        "missingStatusCount": missing_status_count,
        "authorityCount": len(authorities),
        "missingAuthorityCount": missing_authority_count,
        "withEndDateCount": with_end_date_count,
        "withoutEndDateCount": len(value) - with_end_date_count,
    }


def _sections_report(
    report: Mapping[str, Any], sections: Sequence[str]
) -> dict[str, Any]:
    projected = _identification_fields(report)
    for path in sections:
        parts = path.split(".")
        found, value = _read_path(report, parts)
        if found:
            _write_path(projected, parts, deepcopy(value))
    return projected


def _identification_fields(report: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in IDENTITY_ROOT_FIELDS:
        if field in report:
            result[field] = deepcopy(report[field])

    base_info = report.get("baseInfo")
    if isinstance(base_info, Mapping):
        selected = {
            field: deepcopy(base_info[field])
            for field in IDENTITY_BASE_INFO_FIELDS
            if field in base_info
        }
        if selected:
            result["baseInfo"] = selected
    return result


def _read_path(source: Mapping[str, Any], parts: Sequence[str]) -> tuple[bool, Any]:
    current: Any = source
    for part in parts:
        if not isinstance(current, Mapping) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _write_path(target: dict[str, Any], parts: Sequence[str], value: Any) -> None:
    current = target
    for part in parts[:-1]:
        existing = current.get(part)
        if not isinstance(existing, dict):
            existing = {}
            current[part] = existing
        current = existing
    current[parts[-1]] = value
