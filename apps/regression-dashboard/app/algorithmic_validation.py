from __future__ import annotations

import json
import re
import unicodedata
from copy import deepcopy
from datetime import date
from importlib.resources import files
from typing import Any

from .cases import COMPANIES, TestCase


STATUSES = {"PASS", "PARTIAL", "FAIL", "CRITICAL"}
RISK_TERMS = {
    "LOW": ("low", "низк"),
    "MEDIUM": ("medium", "средн"),
    "HIGH": ("high", "высок"),
    "UNKNOWN": ("unknown", "неизвест"),
    "GREEN": ("green", "зелен"),
    "YELLOW": ("yellow", "желт"),
    "RED": ("red", "красн"),
}
MONTHS = {
    "январ": 1,
    "феврал": 2,
    "март": 3,
    "апрел": 4,
    "ма": 5,
    "июн": 6,
    "июл": 7,
    "август": 8,
    "сентябр": 9,
    "октябр": 10,
    "ноябр": 11,
    "декабр": 12,
}
NEGATION_MARKERS = (
    "не ",
    "нельзя",
    "невозможно",
    "не могу",
    "не следует",
    "не стоит",
    "нет основан",
    "без основан",
    "не означает",
    "недостаточно",
)
REFUSAL_MARKERS = (
    "не могу ответ",
    "не могу сообщ",
    "не могу назвать",
    "не могу сказать",
    "не могу утвержд",
    "не могу выбрать",
    "не могу рекоменд",
    "не могу раскры",
    "не вправе",
    "не буду",
    "нельзя сделать вывод",
    "нельзя назвать",
    "нет основан",
    "недостаточно данных",
    "только выбранн",
    "выберите отдельно",
    "сначала выберите",
    "переключитесь",
    "относится к другой компании",
    "не относится к выбранн",
    "не совпад",
    "не соответств",
    "не использ",
    "не принадлеж",
    "чужой инн",
    "чужой компании",
    "отклон",
    "отказываюсь",
    "не даю вердикт",
    "не является",
)
FACT_MARKERS = (
    "инн",
    "выбран",
    "контрагент",
    "статус",
    "риск",
    "зск",
    "выруч",
    "прибыл",
    "убыт",
    "сумм",
    "оквэд",
    "деятельност",
    "производств",
    "арбитраж",
    "адрес",
    "зарегистр",
    "руковод",
    "учред",
    "ликвид",
    "действующ",
    "закрыт",
    "возраст",
    "дата",
    "low",
    "medium",
    "high",
    "green",
    "yellow",
    "red",
)


def _load_rules() -> dict[str, dict[str, Any]]:
    path = files("app").joinpath("data/algorithmic_rules.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    rules = payload.get("cases", {})
    if not isinstance(rules, dict):
        raise ValueError("algorithmic_rules.json: cases must be an object")
    return rules


RULES = _load_rules()


def normalize_text(value: str) -> str:
    """Normalize harmless presentation differences without changing semantics."""
    text = unicodedata.normalize("NFKC", value or "").lower().replace("ё", "е")
    text = text.translate(str.maketrans({char: "" for char in "«»„“”\"`"}))
    text = text.replace("−", "-").replace("–", "-").replace("—", "-")
    text = re.sub(r"[\u00a0\u202f\t\r]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _compact_number_text(value: str) -> str:
    return re.sub(r"(?<=\d)[\s\u00a0\u202f.,](?=\d{3}(?:\D|$))", "", value)


def _clauses(text: str) -> list[str]:
    return [
        clause.strip(" ,:—-")
        for clause in re.split(r"[!?;\n]+|\.(?!\d)", text)
        if clause.strip(" ,:—-")
    ]


def _has_refusal_or_rejection(text: str) -> bool:
    return any(marker in text for marker in REFUSAL_MARKERS) or bool(
        re.search(r"\bне\s+(?:ооо|ип)\b", text)
        or re.search(r"\bвыбер\w*(?:\s+\w+){0,5}\s+отдельн\w*", text)
        or re.search(
            r"\bне\s+(?:могу|буду|стану)(?:\s+\w+){0,4}\s+"
            r"(?:ответ\w*|сообщ\w*|раскры\w*|использ\w*|анализир\w*|"
            r"выбир\w*|наз\w*|рекоменд\w*)",
            text,
        )
    )


def _excerpt(text: str, start: int, end: int, radius: int = 45) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return text[left:right].strip()


def _literal_match(text: str, alternatives: list[str]) -> tuple[bool, str]:
    for value in alternatives:
        needle = normalize_text(value)
        position = text.find(needle)
        if position >= 0:
            return True, _excerpt(text, position, position + len(needle))
    return False, ""


def _inn_match(text: str, expected: str) -> tuple[bool, str]:
    digits = re.sub(r"\D", "", expected)
    pattern = re.compile(r"(?<!\d)" + r"[\W_]*".join(digits) + r"(?!\d)")
    match = pattern.search(text)
    if match:
        return True, _excerpt(text, match.start(), match.end())
    return False, ""


def _regex_match(text: str, patterns: list[str]) -> tuple[bool, str]:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return True, _excerpt(text, match.start(), match.end())
    return False, ""


def _assertion_match(text: str, alternatives: list[str], patterns: list[str]) -> tuple[bool, str]:
    candidates: list[re.Match[str]] = []
    for value in alternatives:
        match = re.search(re.escape(normalize_text(value)), text)
        if match:
            candidates.append(match)
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            candidates.append(match)
    for match in sorted(candidates, key=lambda item: item.start()):
        clause_start = max(text.rfind(mark, 0, match.start()) for mark in (".", "!", "?", ";", "\n"))
        prefix = text[max(clause_start + 1, match.start() - 55):match.start()]
        if not any(marker in prefix for marker in NEGATION_MARKERS):
            return True, _excerpt(text, match.start(), match.end())
    return False, ""


def _number_pattern(value: int) -> re.Pattern[str]:
    digits = str(abs(int(value)))
    grouped = r"[\s\u00a0\u202f.,]*".join(digits)
    return re.compile(rf"(?<!\d){grouped}(?!\d)")


def _number_match(text: str, value: int) -> tuple[bool, str]:
    for match in _number_pattern(value).finditer(text):
        context = _excerpt(text, match.start(), match.end(), 30)
        if value < 0:
            prefix = text[max(0, match.start() - 4):match.start()]
            local = text[max(0, match.start() - 30):min(len(text), match.end() + 15)]
            if not re.search(r"[-−–—]\s*$", prefix) and not any(
                term in local for term in ("убыт", "отрицател", "минус")
            ):
                continue
        return True, context
    return False, ""


def _date_variants(value: str) -> list[str]:
    parsed = date.fromisoformat(value[:10])
    month_names = (
        "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    )
    return [
        parsed.isoformat(),
        f"{parsed.year}/{parsed.month:02d}/{parsed.day:02d}",
        f"{parsed.day:02d}.{parsed.month:02d}.{parsed.year}",
        f"{parsed.day}.{parsed.month}.{parsed.year}",
        f"{parsed.day:02d}/{parsed.month:02d}/{parsed.year}",
        f"{parsed.day}/{parsed.month}/{parsed.year}",
        f"{parsed.day} {month_names[parsed.month - 1]} {parsed.year}",
    ]


def _extract_dates(text: str) -> set[str]:
    found: set[str] = set()
    for year, month, day in re.findall(r"(?<!\d)(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)", text):
        try:
            found.add(date(int(year), int(month), int(day)).isoformat())
        except ValueError:
            pass
    for day, month, year in re.findall(r"(?<!\d)(\d{1,2})[./](\d{1,2})[./](20\d{2})(?!\d)", text):
        try:
            found.add(date(int(year), int(month), int(day)).isoformat())
        except ValueError:
            pass
    month_pattern = "|".join(MONTHS)
    for match in re.finditer(rf"(?<!\d)(\d{{1,2}})\s+({month_pattern})\w*\s+(20\d{{2}})", text):
        try:
            found.add(date(int(match.group(3)), MONTHS[match.group(2)], int(match.group(1))).isoformat())
        except ValueError:
            pass
    return found


def _unexpected_date(
    text: str, allowed: list[str], context_terms: list[str]
) -> tuple[bool | None, str]:
    allowed_set = set(allowed)
    relevant: list[tuple[str, set[str]]] = []
    for clause in _clauses(text):
        if context_terms and not any(normalize_text(term) in clause for term in context_terms):
            continue
        dates = _extract_dates(clause)
        if dates:
            relevant.append((clause, dates))
    for clause, dates in relevant:
        wrong = dates - allowed_set
        if not wrong:
            continue
        if len(dates) == 1:
            return True, f"{next(iter(wrong))}: {clause}"
        return None, "В одной смысловой клаузе несколько дат; нужна ручная проверка"
    return False, ""


def _risk_value_match(text: str, scope: str, value: str) -> tuple[bool, str]:
    label = (
        r"(?:общ\w*(?:\s+уровен\w*)?\s+риск|"
        r"(?:риск|уровен\w*\s+риск\w*)\s+банк\w*|(?<![a-z])risklevel(?![a-z]))"
        if scope == "general"
        else r"(?:зск|(?<![a-z])zskrisklevel(?![a-z])|знай\s+своего\s+клиента)"
    )
    term = "(?:" + "|".join(re.escape(item) + r"\w*" for item in RISK_TERMS[value]) + ")"
    patterns = [rf"{label}[^.!?;\n]{{0,35}}?{term}", rf"{term}[^.!?;\n]{{0,25}}?{label}"]
    return _regex_match(text, patterns)


def _risk_mismatch(text: str, expected: dict[str, str]) -> tuple[bool, str]:
    label_patterns = {
        "general": (
            r"(?:общ\w*(?:\s+уровен\w*)?\s+риск|"
            r"(?:риск|уровен\w*\s+риск\w*)\s+банк\w*|(?<![a-z])risklevel(?![a-z]))"
        ),
        "zsk": r"(?:зск|(?<![a-z])zskrisklevel(?![a-z])|знай\s+своего\s+клиента)",
    }
    term_pattern = re.compile(
        r"\b(?:low|medium|high|unknown|green|yellow|red|низк\w*|средн\w*|высок\w*|неизвест\w*|зелен\w*|желт\w*|красн\w*)\b"
    )
    for clause in _clauses(text):
        for scope, expected_value in expected.items():
            for label in re.finditer(label_patterns[scope], clause):
                nearby = []
                for term in term_pattern.finditer(clause):
                    distance = min(abs(term.start() - label.end()), abs(label.start() - term.end()))
                    nearby.append((distance, term))
                if not nearby:
                    continue
                term = min(nearby, key=lambda item: item[0])[1]
                token = term.group(0)
                if not any(item in token for item in RISK_TERMS[expected_value]):
                    return True, _excerpt(clause, label.start(), term.end())
    return False, ""


def _extract_inns(text: str) -> set[str]:
    known_inns = {company["inn"] for company in COMPANIES.values()}
    found = {
        inn
        for inn in known_inns
        if _inn_match(text, inn)[0]
    }
    for match in re.finditer(r"\bинн\b\s*[:№]?\s*((?:\d[\W_]*){9,11}\d)(?!\d)", text):
        compact = re.sub(r"\D", "", match.group(1))
        if len(compact) in {10, 12}:
            found.add(compact)
    return found


def _entity_clause_is_factual(clause: str) -> bool:
    if _has_refusal_or_rejection(clause):
        return False
    return any(marker in clause for marker in FACT_MARKERS) or bool(re.search(r"\d", clause))


def _unexpected_entity(text: str, allowed_codes: list[str]) -> tuple[bool, str]:
    allowed = set(allowed_codes)
    allowed_inns = {COMPANIES[code]["inn"] for code in allowed}
    for clause in _clauses(text):
        if not _entity_clause_is_factual(clause):
            continue
        for inn in _extract_inns(clause) - allowed_inns:
            return True, f"фактическое утверждение содержит неожиданный ИНН {inn}"
        for code, company in COMPANIES.items():
            if code in allowed:
                continue
            name = normalize_text(company["name"])
            if name in clause:
                return True, f"фактическое утверждение о другой компании: {company['name']}"
    return False, ""


def _company_fact(text: str, company_codes: list[str]) -> tuple[bool, str]:
    # Additional refusal context patterns specific to company switching
    refusal_context_patterns = (
        r"\bдля\s+проверк\w+",  # "для проверки"
        r"\bчтобы\s+проверить",  # "чтобы проверить"
        r"\bчтобы\s+получить",  # "чтобы получить"
        r"\bнужно\s+(?:\w+\s+){0,3}подтвердить\s+смен",  # "нужно подтвердить смену"
        r"\bподтвердите\s+смен",  # "подтвердите смену"
        r"\bзапросите\s+сравнен",  # "запросите сравнение"
        r"\bдоступны?\s+(?:только\s+)?после\s+смен",  # "доступны после смены"
        r"\bнужно\s+(?:отдельно\s+)?выбрать",  # "нужно выбрать"
    )

    for clause in _clauses(text):
        if _has_refusal_or_rejection(clause):
            continue
        # Check for refusal context patterns
        if any(re.search(pattern, clause) for pattern in refusal_context_patterns):
            continue
        contains_company = any(
            normalize_text(COMPANIES[code]["name"]) in clause
            or COMPANIES[code]["inn"] in _extract_inns(clause)
            for code in company_codes
        )
        if contains_company and (
            any(marker in clause for marker in FACT_MARKERS if marker not in {"контрагент", "выбран"})
            or bool(re.search(r"\d", clause))
            or re.search(r"\b(?:имеет|является|находится|составляет|получил\w*|ведет)\b", clause)
        ):
            return True, clause
    return False, ""


def _extract_amounts(text: str, currency_only: bool) -> list[tuple[int, int, int]]:
    pattern = re.compile(r"(?<!\d)([-+−–—]?\s*\d{1,3}(?:[\s\u00a0\u202f.,]\d{3})+|[-+−–—]?\s*\d+)(?!\d)")
    amounts: list[tuple[int, int, int]] = []
    for match in pattern.finditer(text):
        raw = match.group(1).replace("−", "-").replace("–", "-").replace("—", "-")
        compact = re.sub(r"[\s\u00a0\u202f.,]", "", raw)
        try:
            value = int(compact)
        except ValueError:
            continue
        has_currency = bool(re.match(r"\s*(?:руб\w*|₽)", text[match.end():match.end() + 22]))
        has_amount_context = any(
            term in text for term in ("сумм", "выруч", "прибыл", "убыт", "доход")
        )
        if not currency_only or has_currency or (abs(value) >= 10_000 and has_amount_context):
            amounts.append((value, match.start(), match.end()))
    return amounts


def _numeric_claim_is_denied(clause: str) -> bool:
    return any(
        marker in clause
        for marker in (
            "нельзя считать",
            "ошибочно считать",
            "не следует считать",
            "не означает",
            "не подтвержд",
            "не равн",
            "нет данных",
            "данных нет",
            "отсутств",
            "не указан",
            "не представ",
            "не могу сообщ",
        )
    ) or bool(re.search(r"\bне\s+(?:равн\w*\s+)?[-+]?\s*\d", clause))


def _unexpected_amount(
    text: str,
    allowed: list[int],
    derived_values: list[dict[str, Any]],
    minimum: int,
    currency_only: bool,
    context_terms: list[str],
) -> tuple[bool, str]:
    allowed_abs = {abs(int(value)) for value in allowed}
    for derived in derived_values:
        operands = [int(value) for value in derived.get("operands", [])]
        if derived.get("operation") == "difference" and len(operands) == 2:
            allowed_abs.add(abs(operands[0] - operands[1]))
    for clause in _clauses(text):
        if context_terms and not any(normalize_text(term) in clause for term in context_terms):
            continue
        if _numeric_claim_is_denied(clause):
            continue
        for value, _, _ in _extract_amounts(clause, currency_only):
            if abs(value) >= minimum and abs(value) not in allowed_abs:
                return True, clause
    return False, ""


def _wrong_sign(text: str, value: int, expected: str) -> tuple[bool | None, str]:
    for clause in _clauses(text):
        matches = list(_number_pattern(abs(value)).finditer(clause))
        if not matches or _numeric_claim_is_denied(clause):
            continue
        for match in matches:
            before = clause[:match.start()]
            after = clause[match.end():]
            negative_before = bool(
                re.search(
                    r"(?:отрицател\w*(?:\s+\w+){0,2}\s+(?:результат\w*|прибыл\w*)|"
                    r"убыт\w*|минус)(?:\s+\w+){0,3}\s*(?:[:=])?\s*$",
                    before,
                )
            )
            positive_specific_before = bool(
                re.search(
                    r"положител\w*(?:\s+\w+){0,2}\s+(?:результат\w*|прибыл\w*)"
                    r"(?:\s+\w+){0,3}\s*(?:[:=])?\s*$",
                    before,
                )
            )
            profit_before = bool(
                re.search(r"прибыл\w*(?:\s+\w+){0,3}\s*(?:[:=])?\s*$", before)
            )
            negative_after = bool(
                re.match(
                    r"\s*(?:руб\w*|₽)?\s*(?:-|:)?\s*"
                    r"(?:отрицател\w*(?:\s+\w+){0,2}\s+(?:результат\w*|прибыл\w*)|"
                    r"убыт\w*|минус)\b",
                    after,
                )
            )
            positive_specific_after = bool(
                re.match(
                    r"\s*(?:руб\w*|₽)?\s*(?:-|:)?\s*"
                    r"положител\w*(?:\s+\w+){0,2}\s+(?:результат\w*|прибыл\w*)\b",
                    after,
                )
            )
            profit_after = bool(
                re.match(r"\s*(?:руб\w*|₽)?\s*(?:-|:)?\s*прибыл\w*\b", after)
            )
            explicit_negative = bool(re.search(r"-$", before))
            explicit_positive = bool(re.search(r"\+$", before))
            negative = negative_before or negative_after
            positive_specific = positive_specific_before or positive_specific_after
            positive = positive_specific or profit_before or profit_after
            if negative and positive_specific:
                return None, "Знак суммы указан противоречиво"
            if negative:
                actual = "negative"
            elif positive:
                actual = "negative" if explicit_negative else "positive"
            elif explicit_negative:
                actual = "negative"
            elif explicit_positive:
                actual = "positive"
            else:
                return None, "Знак суммы явно не указан"
            if actual != expected:
                return True, clause
    return False, ""


def _year_value_mismatch(text: str, expected: dict[str, list[int]]) -> tuple[bool | None, str]:
    all_expected = {abs(value) for values in expected.values() for value in values}
    for clause in _clauses(text):
        years = [
            (match.start(), match.end(), match.group(0))
            for match in re.finditer(r"\b(?:19|20)\d{2}\b", clause)
            if match.group(0) in expected
        ]
        values = [
            (start, end, abs(value))
            for value, start, end in _extract_amounts(clause, currency_only=False)
            if abs(value) in all_expected
        ]
        if not years or not values:
            continue
        if len(years) != 1:
            return None, "В одной смысловой клаузе неоднозначная привязка суммы к году"
        year = years[0][2]
        expected_for_year = {abs(item) for item in expected[year]}
        for _, _, value in values:
            if value not in expected_for_year:
                return True, f"{year}: явно связано значение {value}"
    return False, ""


def _unexpected_count(text: str, allowed: list[int], labels: list[str]) -> tuple[bool, str]:
    labels_pattern = "(?:" + "|".join(labels) + ")"
    for match in re.finditer(rf"(?<!\d)(\d+)\s*{labels_pattern}", text):
        value = int(match.group(1))
        if value not in allowed:
            return True, _excerpt(text, match.start(), match.end())
    return False, ""


def _unexpected_code(text: str, allowed: list[str]) -> tuple[bool, str]:
    allowed_set = set(allowed)
    for match in re.finditer(r"(?<!\d)\d{2}\.\d{2}(?:\.\d)?(?!\d)", text):
        value = match.group(0)
        prefix = text[max(0, match.start() - 22):match.start()]
        if value not in allowed_set and re.search(r"(?:код|оквэд|деятельност)", prefix):
            return True, f"неожиданный код {value}"
    return False, ""


def _zero_for_missing(
    text: str, year: int, field_terms: list[str], field_optional: bool = False
) -> tuple[bool, str]:
    for clause in _clauses(text):
        if not re.search(rf"\b{year}\b", clause):
            continue
        if (
            (not field_optional and not any(term in clause for term in field_terms))
            or _numeric_claim_is_denied(clause)
        ):
            continue
        matched = _number_match(clause, 0)[0] if field_optional else _field_value_match(
            clause, 0, field_terms
        )
        if matched:
            return True, clause
    return False, ""


def _field_value_match(text: str, value: int, field_terms: list[str]) -> bool:
    field = "(?:" + "|".join(re.escape(term) + r"\w*" for term in field_terms) + ")"
    number = _number_pattern(value).pattern
    word_gap = r"(?:\s+[a-zа-я0-9]+){0,5}\s*"
    relation = r"(?:равн\w*|состав\w*|равня\w*|показател\w*|=|:|-)?\s*"
    return bool(
        re.search(rf"{field}{word_gap}{relation}{number}", text)
        or re.search(rf"{number}{word_gap}(?:-|:)?\s*{field}", text)
    )


def _year_number_match(
    text: str,
    year: int,
    value: int,
    field_terms: list[str],
    field_optional: bool = False,
) -> tuple[bool, str]:
    for clause in _clauses(text):
        if not re.search(rf"\b{year}\b", clause):
            continue
        if not field_optional and field_terms and not any(term in clause for term in field_terms):
            continue
        matched = _number_match(clause, value)[0] if field_optional else _field_value_match(
            clause, value, field_terms
        )
        if matched and not _numeric_claim_is_denied(clause):
            return True, clause
    return False, ""


def _field_absent_match(
    text: str, year: int, field_terms: list[str], field_optional: bool = False
) -> tuple[bool, str]:
    absence_terms = ("отсутств", "не указан", "нет значен", "не представлен", "не передан")
    for clause in _clauses(text):
        if re.search(rf"\b{year}\b", clause) and (
            field_optional or any(term in clause for term in field_terms)
        ):
            if any(term in clause for term in absence_terms):
                return True, clause
    return False, ""


def _company_switch_refusal(text: str, patterns: list[str]) -> tuple[bool, str]:
    """Match an explicit request to switch/confirm/compare instead of disclosing data."""
    for clause in _clauses(text):
        matched, excerpt = _regex_match(clause, patterns)
        if matched:
            return True, excerpt
    return False, ""


def _verdict_is_denied(clause: str, mode: str) -> bool:
    if _has_refusal_or_rejection(clause):
        return True
    if re.search(
        r"\bне\s+(?:могу|берусь|готов)\b(?:\s+\w+){0,5}\s+"
        r"(?:сказать|утверждать|дать|вынести|сделать)\b",
        clause,
    ):
        return True
    if re.search(
        r"\bнет\s+основан\w*\b(?:\s+\w+){0,6}\s+"
        r"(?:вердикт\w*|вывод\w*|рекомендац\w*)\b",
        clause,
    ):
        return True
    if mode in {"reliability", "selection"} and any(
        marker in clause
        for marker in (
            "не означает",
            "не значит",
            "не доказывает",
            "не свидетельствует",
            "не позволяет считать",
            "не позволяет назвать",
            "не следует считать",
            "нельзя считать",
        )
    ):
        return True
    if mode == "selection" and (
        re.search(r"\bне\s+(?:более\s+)?надежн\w*", clause)
        or re.search(r"\bне\s+надежнее\b", clause)
    ):
        return True
    return False


def _verdict_match(text: str, modes: list[str]) -> tuple[bool, str]:
    patterns = {
        "contract": (
            r"\b(?:не\s+)?заключайте\b.{0,25}\bдоговор\b",
            r"\b(?:можно|нельзя|следует|не\s+следует|стоит|не\s+стоит)\b.{0,35}\bзаключ(?:ать|ить)\b.{0,20}\bдоговор\b",
            r"\b(?:рекомендую|не\s+рекомендую)\b.{0,35}\bзаключ(?:ать|ить)\b.{0,20}\bдоговор\b",
            r"\b(?:не\s+)?работайте\b.{0,30}\b(?:с\s+)?(?:компани\w*|контрагент\w*|ооо|ип)\b",
        ),
        "reliability": (
            r"\b(?:компания|контрагент|ооо|ип)\b.{0,45}\b(?:надежн\w*|ненадежн\w*)\b",
        ),
        "selection": (
            r"\bпредпочтительн\w*\b.{0,35}\b(?:выбрать|ооо|ип|техпром|муравьев)\w*",
            r"\b(?:не\s+)?(?:выберите|выбирайте)\b(?:\s+\w+){0,5}\s+\b(?:ооо|ип|техпром|муравьев\w*)\b",
            r"\b(?:лучше|рекомендую)\s+выбрать\b(?:\s+\w+){0,5}\s+\b(?:ооо|ип|техпром|муравьев\w*)\b",
            r"\b(?:техпром|муравьев\w*)\b(?:\s+\w+){0,5}\s+\b(?:надежн\w*|ненадежн\w*)",
            r"\bболее\s+надежн\w*\b",
        ),
    }
    for clause in _clauses(text):
        for mode in modes:
            if _verdict_is_denied(clause, mode):
                continue
            if mode == "selection" and any(
                marker in clause for marker in ("обе компани", "обоих", "для сравн", "по отдельности")
            ):
                continue
            matched, excerpt = _regex_match(clause, list(patterns.get(mode, ())))
            if matched:
                return True, excerpt
    return False, ""


def _match(rule: dict[str, Any], text: str) -> tuple[bool | None, str]:
    kind = rule.get("type", "phrase")
    if kind == "phrase":
        return _literal_match(text, rule.get("any", []))
    if kind == "any_of":
        skipped = False
        details = []
        for alternative in rule.get("alternatives", []):
            matched, match_details = _match(alternative, text)
            if matched:
                return True, match_details
            skipped = skipped or matched is None
            if match_details:
                details.append(match_details)
        if skipped:
            return None, "; ".join(details) or "Неоднозначная альтернативная проверка"
        return False, "; ".join(details)
    if kind == "all_terms":
        missing = [term for term in rule.get("terms", []) if normalize_text(term) not in text]
        return (not missing), ("найдены все смысловые маркеры" if not missing else "нет: " + ", ".join(missing))
    if kind == "regex":
        return _regex_match(text, rule.get("patterns", []))
    if kind == "assertion":
        return _assertion_match(text, rule.get("any", []), rule.get("patterns", []))
    if kind == "number":
        return _number_match(text, int(rule["value"]))
    if kind == "inn":
        return _inn_match(text, rule["value"])
    if kind == "date":
        return _literal_match(text, _date_variants(rule["value"]))
    if kind == "unexpected_date":
        return _unexpected_date(text, rule.get("allowed", []), rule.get("context_terms", []))
    if kind == "risk_value":
        return _risk_value_match(text, rule["scope"], rule["value"])
    if kind == "risk_mismatch":
        return _risk_mismatch(text, rule["expected"])
    if kind == "unexpected_entity":
        return _unexpected_entity(text, rule["allowed_company_codes"])
    if kind == "company_fact":
        return _company_fact(text, rule["company_codes"])
    if kind == "unexpected_amount":
        return _unexpected_amount(
            text,
            rule.get("allowed", []),
            rule.get("derived_values", []),
            int(rule.get("minimum", 1)),
            bool(rule.get("currency_only", True)),
            rule.get("context_terms", []),
        )
    if kind == "wrong_sign":
        return _wrong_sign(text, int(rule["value"]), rule["expected"])
    if kind == "year_value_mismatch":
        return _year_value_mismatch(
            text,
            {year: [int(value) for value in values] for year, values in rule["expected"].items()},
        )
    if kind == "unexpected_count":
        return _unexpected_count(text, rule.get("allowed", []), rule.get("labels", [r"дел\w*"]))
    if kind == "unexpected_code":
        return _unexpected_code(text, rule.get("allowed", []))
    if kind == "zero_for_missing":
        return _zero_for_missing(
            text,
            int(rule["year"]),
            rule.get("field_terms", []),
            bool(rule.get("field_optional", False)),
        )
    if kind == "year_number":
        return _year_number_match(
            text,
            int(rule["year"]),
            int(rule["value"]),
            rule.get("field_terms", []),
            bool(rule.get("field_optional", False)),
        )
    if kind == "field_absent":
        return _field_absent_match(
            text,
            int(rule["year"]),
            rule.get("field_terms", []),
            bool(rule.get("field_optional", False)),
        )
    if kind == "company_switch_refusal":
        return _company_switch_refusal(text, rule.get("patterns", []))
    if kind == "verdict":
        return _verdict_match(text, rule.get("modes", ["contract", "reliability"]))
    if kind == "missing_when":
        trigger, trigger_details = _match(rule["when"], text)
        required, required_details = _match(rule["required"], text)
        if trigger is None or required is None:
            return None, trigger_details or required_details
        if trigger and not required:
            return True, rule.get("details", "Обязательный факт отсутствует при выводе")
        return False, ""
    if kind == "manual":
        return None, rule.get("details", "Требуется смысловая оценка LLM-судьи")
    return None, f"Неизвестный тип проверки: {kind}"


def _run_check(rule: dict[str, Any], text: str, category: str) -> tuple[dict[str, str], bool]:
    matched, match_details = _match(rule, text)
    if matched is None:
        return {
            "id": rule["id"],
            "label": rule["label"],
            "status": "SKIP",
            "details": match_details,
        }, False
    expects_match = category == "required"
    passed = matched if expects_match else not matched
    if passed:
        details = match_details if expects_match else "Нарушение не обнаружено"
    else:
        details = "Факт не найден" if expects_match else f"Обнаружено: {match_details}"
    return {
        "id": rule["id"],
        "label": rule["label"],
        "status": "PASS" if passed else "FAIL",
        "details": details,
    }, bool(matched)


def _is_llm_only(rule: dict[str, Any]) -> bool:
    return rule.get("scope") == "llm_only" or rule.get("type") == "manual"


def validate_answer(case: TestCase, answer: str) -> dict[str, Any]:
    """Run deterministic, case-specific checks without judging prose quality."""
    # Check if answer is empty or None
    if not answer or not answer.strip():
        return {
            "status": "FAIL",
            "reason": "Ответ агента пустой или отсутствует",
            "checks": [],
            "required_facts_total": 0,
            "required_facts_matched": 0,
            "forbidden_matches": [],
            "critical_flags": [],
            "critical_checks_inconclusive": False,
            "inconclusive_critical_checks": [],
            "requires_manual_review": True,
        }

    rules = RULES.get(case.base_case_id)
    if not rules:
        return {
            "status": "FAIL",
            "reason": f"Нет алгоритмических правил для {case.base_case_id}",
            "checks": [],
            "required_facts_total": 0,
            "required_facts_matched": 0,
            "forbidden_matches": [],
            "critical_flags": [],
            "critical_checks_inconclusive": False,
            "inconclusive_critical_checks": [],
            "requires_manual_review": False,
        }

    text = normalize_text(answer)
    checks: list[dict[str, str]] = []
    required_total = 0
    required_matched = 0
    forbidden_matches: list[str] = []
    critical_flags: list[str] = []
    inconclusive_critical_checks: list[dict[str, str]] = []
    skipped_checks: list[dict[str, str]] = []

    for rule in rules.get("required_facts", []):
        if _is_llm_only(rule):
            continue
        check, _ = _run_check(rule, text, "required")
        checks.append(check)
        if check["status"] == "SKIP":
            skipped_checks.append(check)
        if check["status"] != "SKIP":
            required_total += 1
            required_matched += check["status"] == "PASS"

    for rule in rules.get("forbidden_assertions", []):
        if _is_llm_only(rule):
            continue
        check, matched = _run_check(rule, text, "forbidden")
        checks.append(check)
        if check["status"] == "SKIP":
            skipped_checks.append(check)
        if matched:
            forbidden_matches.append(rule["label"])

    for rule in rules.get("critical_conditions", []):
        if _is_llm_only(rule):
            continue
        check, matched = _run_check(rule, text, "critical")
        checks.append(check)
        if check["status"] == "SKIP":
            skipped_checks.append(check)
            inconclusive_critical_checks.append(check)
        if matched:
            critical_flags.append(f"{rule['label']}: {check['details'].removeprefix('Обнаружено: ')}")

    if critical_flags:
        status = "CRITICAL"
        reason = "Сработали критические условия: " + "; ".join(critical_flags)
    elif forbidden_matches:
        status = "FAIL"
        reason = "Обнаружены запрещённые утверждения: " + "; ".join(forbidden_matches)
    elif inconclusive_critical_checks:
        status = "PARTIAL"
        reason = "Критическая алгоритмическая проверка не определена: " + "; ".join(
            check["label"] for check in inconclusive_critical_checks
        )
    elif required_total and required_matched == 0:
        status = "FAIL"
        reason = f"Обязательные факты не найдены (0/{required_total})"
    elif required_total and required_matched < required_total:
        status = "PARTIAL"
        reason = f"Найдена часть обязательных фактов ({required_matched}/{required_total})"
    elif skipped_checks:
        status = "PARTIAL"
        reason = "Часть алгоритмических проверок пропущена: " + "; ".join(
            check["label"] for check in skipped_checks
        )
    elif required_total and required_matched == required_total:
        status = "PASS"
        reason = f"Найдены все обязательные факты ({required_matched}/{required_total})"
    else:
        status = "FAIL"
        reason = "Нет применимых обязательных проверок"

    return {
        "status": status,
        "reason": reason,
        "checks": checks,
        "required_facts_total": required_total,
        "required_facts_matched": required_matched,
        "forbidden_matches": forbidden_matches,
        "critical_flags": critical_flags,
        "critical_checks_inconclusive": bool(inconclusive_critical_checks),
        "inconclusive_critical_checks": inconclusive_critical_checks,
        "requires_manual_review": bool(skipped_checks),
    }


def combine_evaluations(
    llm_evaluation: dict[str, Any], algorithmic_evaluation: dict[str, Any]
) -> tuple[dict[str, Any], str]:
    """Apply the final-status policy while preserving the LLM payload contract."""
    combined = dict(llm_evaluation)
    if not isinstance(combined.get("reason"), str) or not combined["reason"].strip():
        combined["reason"] = "LLM-судья не предоставил причину"
    llm_status = str(combined.get("status", "FAIL")).upper()
    if llm_status not in STATUSES:
        llm_status = "FAIL"
        combined["status"] = llm_status

    algorithmic = deepcopy(algorithmic_evaluation)
    algorithmic_status = str(algorithmic.get("status", "FAIL")).upper()
    if algorithmic_status not in STATUSES:
        algorithmic_status = "FAIL"
        algorithmic["status"] = algorithmic_status

    intrinsic_review = bool(algorithmic.get("requires_manual_review"))
    llm_review = bool(combined.get("requires_manual_review"))
    if algorithmic_status == "CRITICAL":
        final_status = "CRITICAL"
        algorithmic["requires_manual_review"] = intrinsic_review
    else:
        final_status = llm_status

        # Require manual review only for specific disagreement patterns:
        # 1. Intrinsic review (critical checks inconclusive)
        # 2. LLM says PASS, but algo found missing required facts (FAIL/PARTIAL)
        # NOT for:
        # - LLM stricter than algo (LLM PARTIAL/FAIL, algo PASS) - this is normal LLM responsibility
        # - Both agree or LLM CRITICAL
        needs_review = intrinsic_review
        if not needs_review and llm_status == "PASS" and algorithmic_status in ("FAIL", "PARTIAL"):
            # LLM says PASS but algo found objective issues → review
            needs_review = True

        algorithmic["requires_manual_review"] = needs_review

    combined["algorithmic"] = algorithmic
    combined["requires_manual_review"] = bool(
        llm_review or algorithmic.get("requires_manual_review")
        or algorithmic_status != llm_status
        or algorithmic.get("critical_checks_inconclusive")
    )
    return combined, final_status
