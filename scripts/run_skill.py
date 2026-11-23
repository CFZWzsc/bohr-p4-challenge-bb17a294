#!/usr/bin/env python3
"""Deterministic bilingual alignment / terminology / number audit helper.

Reads /input/case.json (or --case), writes /app/output/result.json (or --output).
Standard library only, no network. Preserves case_id and every original
output_contract field. The script does NOT machine-translate; target cells are
left pending until the calling agent fills them.
"""

import argparse
import hashlib
import json
import os
import re
import sys

SOURCE_KEYS = ("source_text", "source", "original_text", "text", "manuscript",
               "content", "input_text", "paper_text")
TARGET_KEYS = ("translation", "target_text", "translated_text", "output_text")
GLOSSARY_KEYS = ("glossary", "terminology", "term_base", "termbase", "terms")
LANG_KEYS = ("target_language", "language", "target_lang", "locale")

STOP_EN = {"this", "that", "these", "those", "with", "from", "were", "have",
           "been", "their", "which", "would", "could", "should", "using",
           "study", "results", "method", "methods", "table", "figure"}
STOP_ZH = {"我们", "本文", "研究", "结果", "方法", "可以", "以及", "通过", "进行",
           "一个", "这些", "那些", "由于", "因此", "其中", "对于", "如果", "但是"}


def load_case(path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def norm_space(text):
    return re.sub(r"\s+", " ", text or "").strip()


def sha256_text(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def read_if_path(value):
    if isinstance(value, str) and len(value) < 4096 and os.path.isfile(value.strip()):
        path = value.strip()
        if os.path.getsize(path) <= 2 * 1024 * 1024:
            try:
                with open(path, "r", encoding="utf-8-sig") as fh:
                    return fh.read(), path
            except (UnicodeDecodeError, OSError):
                return None, path
    return None, None


def find_value(obj, keys, path="case"):
    hits = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = "%s.%s" % (path, key)
            if "output_contract" in child:
                continue
            if str(key).lower() in keys:
                hits.append((child, value))
            hits.extend(find_value(value, keys, child))
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            hits.extend(find_value(value, keys, "%s[%d]" % (path, idx)))
    return hits


def resolve_text(hits):
    for _, value in hits:
        if isinstance(value, str):
            text, path = read_if_path(value)
            if text is not None:
                return text, path
            if len(value.strip()) >= 10:
                return value, None
        if isinstance(value, dict):
            for key in ("text", "content", "body", "value"):
                if isinstance(value.get(key), str) and len(value[key].strip()) >= 10:
                    return value[key], value.get("path")
    return None, None


def resolve_scalar(hits):
    for _, value in hits:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list) and value and isinstance(value[0], str):
            return value[0].strip()
    return None


def split_sections(text):
    sections, current, buf = [], "Front matter", []
    for line in text.splitlines():
        heading = re.match(r"^\s*(?:#{1,6}\s+|\d+(?:\.\d+)*\s+)(\S.*)$", line)
        if heading:
            if buf:
                sections.append((current, "\n".join(buf)))
                buf = []
            current = heading.group(1).strip()
        else:
            buf.append(line)
    if buf:
        sections.append((current, "\n".join(buf)))
    return sections or [("Body", text)]


def segment(text):
    segments = []
    pattern = re.compile(r"[^。！？!?\.]+(?:[。！？!?]|\.(?=\s|$))|[^。！？!?\.]+$")
    for section, block in split_sections(text):
        position = text.find(block)
        if position < 0:
            position = 0
        cursor = position
        for match in pattern.finditer(block):
            raw = match.group(0)
            if not raw.strip():
                continue
            start = cursor + match.start()
            segments.append({
                "segment_id": "S%03d" % (len(segments) + 1),
                "section": section,
                "char_start": start,
                "char_end": start + len(raw),
                "source": raw.strip(),
                "target": None,
                "status": "pending_translation",
            })
        cursor = position
    return segments


def extract_terms(text):
    candidates = {}
    for match in re.finditer(r"\b[A-Z]{2,6}\b", text):
        term = match.group(0)
        candidates[term] = candidates.get(term, 0) + 1
    for match in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b", text):
        term = norm_space(match.group(1))
        if len(term) > 6:
            candidates[term] = candidates.get(term, 0) + 1
    for match in re.finditer(r"\b[a-z][a-z\-]{4,}\b", text.lower()):
        term = match.group(0)
        if term not in STOP_EN:
            candidates[term] = candidates.get(term, 0) + 1
    for match in re.finditer(r"[\u4e00-\u9fff]{2,6}", text):
        term = match.group(0)
        if term not in STOP_ZH:
            candidates[term] = candidates.get(term, 0) + 1
    return sorted(
        [{"source": term, "occurrences": count} for term, count in candidates.items() if count >= 2],
        key=lambda item: (-item["occurrences"], item["source"]),
    )[:50]


def audit_numbers(text):
    pattern = re.compile(
        r"(?<![A-Za-z])"
        r"[0-9]+(?:[.,][0-9]+)?"
        r"(?:\s*[×x]\s*10\^?-?[0-9]+)?"
        r"(?:\s*(?:%|‰|mg|g|kg|ml|mL|L|mm|cm|m|km|s|ms|min|h|°C|K|Pa|kPa|MPa|"
        r"mol|mmol|μM|nM|M|Hz|kHz|MHz|GB|MB|kb|bp|Da|kDa|万|亿))?"
        r"(?![A-Za-z])"
    )
    results, seen = [], set()
    for match in pattern.finditer(text):
        value = match.group(0).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        results.append({
            "value": value,
            "char_start": match.start(),
            "char_end": match.end(),
            "context": norm_space(text[max(0, match.start() - 40):match.end() + 40]),
        })
    return results


def audit_citations(text):
    patterns = [
        r"\[\d+(?:\s*[-,–]\s*\d+)*\]",
        r"\([A-Z][A-Za-z\-]+(?:\s+(?:et\s+al\.?|and\s+[A-Z][A-Za-z\-]+))?,?\s*\d{4}[a-z]?\)",
        r"\b[A-Z][A-Za-z\-]+\s+et\s+al\.?",
        r"\{\\cite\{[^}]+\}\}",
        r"\\cite\{[^}]+\}",
    ]
    found = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            found.append({
                "marker": match.group(0),
                "char_start": match.start(),
                "char_end": match.end(),
            })
    found.sort(key=lambda item: item["char_start"])
    unique, seen = [], set()
    for item in found:
        key = (item["char_start"], item["char_end"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def semantic_markers(text):
    rules = {
        "negation": r"\b(?:not|no|never|none|neither|without)\b|不|无|未|非",
        "hedge": r"\b(?:may|might|could|suggest|suggests|likely|possibly|appears?|tends? to)\b|可能|或许|提示|倾向于",
        "causal": r"\b(?:because|causes?|leads? to|results? in|due to|therefore)\b|导致|引起|因此|由于",
        "limitation": r"\b(?:limitation|limited|only|except|however|although)\b|局限|仅|除外|然而|虽然",
    }
    hits = []
    for name, pattern in rules.items():
        for match in re.finditer(pattern, text, re.IGNORECASE):
            hits.append({"kind": name, "marker": match.group(0), "char_start": match.start()})
    return sorted(hits, key=lambda item: item["char_start"])


def glossary_check(text, target, glossary):
    checked = []
    for entry in glossary:
        source = entry.get("source") if isinstance(entry, dict) else None
        target_term = entry.get("target") if isinstance(entry, dict) else None
        if not source:
            continue
        occurrences = len(re.findall(re.escape(source), text, re.IGNORECASE))
        status = "not_observed" if occurrences == 0 else "observed"
        if target and target_term and status == "observed":
            if target_term not in target:
                status = "conflict"
        checked.append({
            "source": source,
            "target": target_term,
            "occurrences": occurrences,
            "status": status,
        })
    return checked


def collect_glossary(case):
    glossary = []
    for _, value in find_value(case, set(GLOSSARY_KEYS)):
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    glossary.append({"source": item.get("source") or item.get("term"),
                                     "target": item.get("target") or item.get("translation")})
                elif isinstance(item, str) and "=" in item:
                    source, target = item.split("=", 1)
                    glossary.append({"source": source.strip(), "target": target.strip()})
        elif isinstance(value, dict):
            for source, target in value.items():
                if isinstance(target, str):
                    glossary.append({"source": source, "target": target})
    return [g for g in glossary if g.get("source")]


# ------------------------------------------------------------- contract -----
def contract_top_fields(contract):
    if contract is None:
        return [], []
    if isinstance(contract, str):
        return [contract], []
    if isinstance(contract, list):
        names = []
        for entry in contract:
            if isinstance(entry, str):
                names.append(entry)
            elif isinstance(entry, dict):
                name = entry.get("name") or entry.get("field") or entry.get("key")
                if name:
                    names.append(str(name))
        return names, []
    if isinstance(contract, dict):
        unsupported = [k for k in ("anyOf", "allOf", "oneOf", "$ref", "patternProperties") if k in contract]
        if isinstance(contract.get("properties"), dict):
            return list(contract["properties"].keys()), unsupported
        nested = contract.get("fields")
        if isinstance(nested, list):
            return contract_top_fields(nested)[0], unsupported
        if isinstance(nested, dict):
            return list(nested.keys()), unsupported
        reserved = {"type", "required", "optional", "additionalProperties", "title",
                    "description", "version", "schema"}
        return [k for k in contract if k not in reserved and not str(k).startswith("$")], unsupported
    return [], []


ALIASES = {
    "case_id": "case_id", "task_id": "case_id", "challenge_id": "case_id",
    "status": "status", "run_status": "status", "summary": "summary",
    "segments": "segments", "alignment": "segments", "bilingual": "segments",
    "terminology": "terminology", "glossary": "terminology", "terms": "terminology",
    "numbers": "number_audit", "number_check": "number_audit", "numbers_audit": "number_audit",
    "citations": "citation_audit", "references": "citation_audit",
    "translation": "deliverable", "translated_text": "deliverable",
    "output": "deliverable", "result": "deliverable", "deliverable": "deliverable",
    "sources": "sources", "uncertainty": "uncertainty", "limitations": "limitations",
    "changes": "change_record", "change_log": "change_record",
}


def fill_contract(result, contract, payload):
    fields, unsupported = contract_top_fields(contract)
    preserved, unmapped = [], []
    for field in fields:
        if result.get(field) is not None:
            preserved.append(field)
            continue
        key = ALIASES.get(field.lower(), field.lower())
        if payload.get(key) is not None:
            result[field] = payload[key]
            preserved.append(field)
        else:
            result[field] = None
            unmapped.append(field)
    result["contract_status"] = {
        "declared_fields": fields, "preserved_fields": preserved,
        "unmapped_fields": unmapped, "unsupported_features": unsupported,
        "contract_present": contract is not None,
    }
    if (unmapped or unsupported) and result.get("status") == "completed":
        result["status"] = "partial"


def write_json(path, payload):
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


CASE_CANDIDATES = (
    "/input/case.json", "/app/input/case.json", "/app/work/case.json",
    "/app/case.json", "case.json", "input/case.json",
)


def discover_case(preferred):
    for path in (preferred,) + CASE_CANDIDATES:
        if path and os.path.isfile(path):
            return path
    for base in ("/input", "/app/input", "/app/work", "/app", "."):
        try:
            for name in sorted(os.listdir(base)):
                if name.lower().endswith(".json") and "case" in name.lower():
                    candidate = os.path.join(base, name)
                    if os.path.isfile(candidate):
                        return candidate
        except OSError:
            continue
    return preferred


def main():
    parser = argparse.ArgumentParser(description="Bilingual alignment helper")
    parser.add_argument("--case", default="/input/case.json")
    parser.add_argument("--output", "--out", default="/app/output/result.json")
    args = parser.parse_args()

    result = {
        "case_id": None, "status": "failed", "summary": {}, "segments": [],
        "terminology": [], "number_audit": [], "citation_audit": [],
        "semantic_boundaries": [], "deliverable": {}, "sources": [],
        "uncertainty": [], "change_record": [], "limitations": [],
    }
    case_path = discover_case(args.case)
    try:
        case = load_case(case_path)
    except (OSError, ValueError) as exc:
        result["limitations"].append("case_read_failed: %s" % type(exc).__name__)
        result["status"] = "partial"
        try:
            write_json(args.output, result)
        except OSError:
            pass
        return 0

    if not isinstance(case, dict):
        case = {"materials": case}
    result["case_id"] = case.get("case_id") or case.get("id") or case.get("challenge_id")
    contract = case.get("output_contract")

    source, source_path = resolve_text(find_value(case, set(SOURCE_KEYS)))
    target, target_path = resolve_text(find_value(case, set(TARGET_KEYS)))
    language = resolve_scalar(find_value(case, set(LANG_KEYS)))
    glossary = collect_glossary(case)

    if not source:
        result["status"] = "partial"
        result["limitations"].append("source_text_missing")
        result["uncertainty"].append({"item": "source", "detail": "no usable source text found"})
    else:
        result["status"] = "completed"
        segments = segment(source)
        result["segments"] = segments
        result["terminology"] = extract_terms(source)
        result["number_audit"] = audit_numbers(source)
        result["citation_audit"] = audit_citations(source)
        result["semantic_boundaries"] = semantic_markers(source)
        if glossary:
            result["terminology_glossary"] = glossary_check(source, target, glossary)
        if not language:
            result["uncertainty"].append({"item": "target_language", "detail": "unspecified"})

        rows = ["| ID | Section | Source | Target |", "|---|---|---|---|"]
        for item in segments:
            rows.append("| %s | %s | %s | _(pending)_ |" % (
                item["segment_id"], item["section"].replace("|", "/"),
                item["source"].replace("|", "/")))
        term_rows = ["| source | target | occurrences | status |", "|---|---|---|---|"]
        for item in result.get("terminology_glossary") or result["terminology"]:
            term_rows.append("| %s | %s | %s | %s |" % (
                item.get("source"), item.get("target") or "_(pending)_",
                item.get("occurrences"), item.get("status", "candidate")))
        result["deliverable"] = {
            "bilingual_table": "\n".join(rows),
            "terminology_sheet": "\n".join(term_rows),
            "translation_status": "pending" if not target else "supplied_target_present",
            "target_language": language,
        }
        result["sources"] = [
            {"role": "source_text", "path": source_path, "sha256": sha256_text(source),
             "chars": len(source)},
            {"role": "target_text", "path": target_path,
             "sha256": sha256_text(target) if target else None},
        ]
        result["summary"] = {
            "segments": len(segments),
            "terminology_candidates": len(result["terminology"]),
            "numbers": len(result["number_audit"]),
            "citations": len(result["citation_audit"]),
            "semantic_markers": len(result["semantic_boundaries"]),
            "translated_segments": 0 if not target else len(segments),
        }
        result["change_record"] = [
            {"action": "segment_source", "count": len(segments)},
            {"action": "extract_numbers", "count": len(result["number_audit"])},
            {"action": "extract_citations", "count": len(result["citation_audit"])},
        ]
        result["limitations"] = [
            "The script does not machine-translate; target cells remain pending until the agent fills them.",
            "Terminology candidates are frequency-based and are not authoritative discipline-specific translations.",
        ]

    payload = dict(result)
    try:
        fill_contract(result, contract, payload)
    except Exception as exc:  # never fail the run on contract quirks
        result["contract_status"] = {"declared_fields": [], "preserved_fields": [],
                                     "unmapped_fields": [], "unsupported_features": [],
                                     "contract_present": contract is not None,
                                     "contract_error": type(exc).__name__}
    if not result.get("case_id"):
        result["case_id"] = "unknown"
        result["status"] = "partial"
        result["limitations"].append("case_id_missing")
    try:
        write_json(args.output, result)
    except OSError as exc:
        sys.stderr.write("output_write_failed: %s\n" % type(exc).__name__)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # last-resort guard: always leave a readable result
        try:
            write_json("/app/output/result.json",
                       {"case_id": "unknown", "status": "partial",
                        "error": type(exc).__name__,
                        "limitations": ["unhandled_exception"]})
        except OSError:
            pass
        sys.exit(0)
