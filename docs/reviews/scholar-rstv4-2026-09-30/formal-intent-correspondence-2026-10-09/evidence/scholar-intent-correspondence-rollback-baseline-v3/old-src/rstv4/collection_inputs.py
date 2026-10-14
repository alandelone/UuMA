"""Validate Collection inputs without creating papers, files, or jobs."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

DOI = re.compile(r"10\.\d{4,9}/\S+", re.IGNORECASE)
PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)


def normalize_input_doi(value: str) -> str:
    value = PREFIX.sub("", value.strip()).rstrip(".,;").casefold()
    while value.endswith(")") and value.count(")") > value.count("("):
        value = value[:-1]
    return value


def bibtex_records(text: str) -> list[dict[str, str]]:
    """Read common literal BibTeX; reject incomplete or unresolved macro values."""
    records = []
    cursor = 0
    while cursor < len(text):
        if text[cursor].isspace():
            cursor += 1
            continue
        if text[cursor] == "%":
            end = text.find("\n", cursor)
            cursor = len(text) if end < 0 else end + 1
            continue
        start = cursor
        header = re.match(r"@([A-Za-z]+)\s*([{(])", text[cursor:])
        if not header:
            raise ValueError("BibTeX contains unreadable content or an incomplete entry")
        kind, opener = header.groups()
        cursor += header.end()
        closer = "}" if opener == "{" else ")"
        if kind.casefold() in {"comment", "preamble", "string"}:
            raise ValueError("Please use literal BibTeX records without @string/@preamble/@comment")
        key = re.match(r"\s*[^,{}()\s]+\s*,", text[cursor:])
        if not key:
            raise ValueError("BibTeX entry needs a citation key and comma")
        cursor += key.end()
        fields = {}
        while True:
            while cursor < len(text) and (text[cursor].isspace() or text[cursor] == ","):
                cursor += 1
            if cursor >= len(text):
                raise ValueError("BibTeX entry is incomplete")
            if text[cursor] == closer:
                cursor += 1
                break
            field = re.match(r"([A-Za-z][\w-]*)\s*=\s*", text[cursor:])
            if not field:
                raise ValueError("BibTeX field is incomplete")
            name = field.group(1).casefold()
            cursor += field.end()
            if cursor >= len(text):
                raise ValueError("BibTeX field has no value")
            value_start = cursor
            if text[cursor] in '{"':
                value_opener = text[cursor]
                value_closer = "}" if value_opener == "{" else '"'
                cursor += 1
                value_start = cursor
                depth = 1
                while cursor < len(text):
                    char = text[cursor]
                    if char == "\\":
                        cursor += 2
                        continue
                    if value_opener == "{" and char == "{":
                        depth += 1
                    elif char == value_closer:
                        depth -= 1
                        if depth == 0:
                            break
                    cursor += 1
                if cursor >= len(text):
                    raise ValueError("BibTeX field value is incomplete")
                value = text[value_start:cursor]
                cursor += 1
            else:
                number = re.match(r"\d+", text[cursor:])
                if not number:
                    raise ValueError("Unresolved BibTeX macros must be replaced with literal values")
                value = number.group()
                cursor += number.end()
            fields[name] = " ".join(value.split())
            while cursor < len(text) and text[cursor].isspace():
                cursor += 1
            if cursor >= len(text) or text[cursor] not in (",", closer):
                raise ValueError("BibTeX fields must be separated by commas")
        if not fields.get("title") and not fields.get("doi"):
            raise ValueError("Each BibTeX record needs a title or DOI")
        fields["_raw"] = text[start:cursor]
        records.append(fields)
    return records


def prepare_inputs(dois: list[str], bibtex: str | None, queries: list[str], *, allow_catalog_only: bool = False) -> dict[str, Any]:
    if len((bibtex or "").encode("utf-8")) > 5_000_000:
        raise ValueError("BibTeX exceeds the 5 MB limit")
    seeds: dict[str, dict[str, Any]] = {}
    normalized_dois = set()
    duplicates = 0
    records = bibtex_records(bibtex or "")
    for raw, kind, identity in (
        [(raw, "DOI", {"doi": raw}) for raw in dois]
        + [(entry["_raw"], "BIBTEX", {k: v for k, v in entry.items() if k != "_raw"})
           for entry in records]
    ):
        doi = normalize_input_doi(identity.get("doi", ""))
        if (kind == "DOI" or identity.get("doi")) and not DOI.fullmatch(doi):
            raise ValueError(f"Invalid DOI: {identity['doi']}")
        if doi:
            identity["doi"] = doi
            normalized_dois.add(doi)
            key = f"doi:{doi}"
        else:
            key = "bib:" + hashlib.sha256(json.dumps([
                " ".join(identity.get("title", "").casefold().split()),
                identity.get("author"), identity.get("year"),
            ], ensure_ascii=False).encode()).hexdigest()
        if key in seeds:
            duplicates += 1
            continue
        seeds[key] = {"kind": kind, "raw": raw, "normalized": doi or key, "identity": identity}
    unique_queries = list(dict.fromkeys(query.strip() for query in queries))
    if any(not 3 <= len(query) <= 1000 for query in unique_queries):
        raise ValueError("Each search query must contain 3–1000 characters")
    if not seeds and not unique_queries and not allow_catalog_only:
        raise ValueError("At least one DOI, BibTeX record, or search query is required")
    return {
        "seeds": list(seeds.values()), "queries": unique_queries,
        "counts": {"unique_dois": len(normalized_dois), "bibtex_entries": len(records),
                   "unique_seeds": len(seeds), "queries": len(unique_queries),
                   "duplicate_inputs": duplicates + len(queries) - len(unique_queries)},
    }
