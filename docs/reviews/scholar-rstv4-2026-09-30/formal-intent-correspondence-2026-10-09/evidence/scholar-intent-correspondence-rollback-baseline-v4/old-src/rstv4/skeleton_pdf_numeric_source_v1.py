"""Original PDF column/token geometry and literal claim evidence, not science inference."""
from __future__ import annotations

import copy
import re

from rstv4.skeleton_contract import SourceContractError
from rstv4.skeleton_pdf_footnote_anchors_v1 import normalized_anchor_text

NUMERIC_SOURCE_VERSION = "original-pdf-literal-numeric-evidence-and-declared-single-column-v1"
NUMERIC_PATTERN = re.compile(r"\d+(?:[.,]\d+)*")


def numeric_tokens(text: str) -> set[str]:
    """Keep lexical source numbers unchanged; no unit or numeric value conversion."""
    return {match.group() for match in NUMERIC_PATTERN.finditer(text)}


def verify_native_value_ledger(pdf_context: dict, target_ids: list[str],
                               footnote_ledger: dict, ledger: dict) -> dict:
    if (ledger["source_pdf_sha256"] != pdf_context["source_pdf_sha256"]
            or ledger["layout_text_sha256"] != pdf_context["layout_text_sha256"]
            or ledger["target_table_line_ids"] != target_ids
            or ledger["scientific_fields_generated_or_changed"] is not False
            or ledger["learner_or_expected_scientific_values_used"] is not False):
        raise SourceContractError("Native numerical source ledger lineage/isolation changed")
    lines = {line["line_id"]: line for line in pdf_context["indexed_layout_lines"]}
    columns = ledger["technology_headers"]
    column_ids = [column["technology_header_id"] for column in columns]
    if (not columns or len(column_ids) != len(set(column_ids))
            or len({column["header_line_id"] for column in columns}) != 1):
        raise SourceContractError("Native scientific column header domain empty/ambiguous")
    header_id = columns[0]["header_line_id"]
    actual_names = re.split(r"\s{2,}", lines[header_id]["text"].strip())[2:]
    if actual_names != [column["original_header_text"] for column in columns]:
        raise SourceContractError("Native scientific column names differ from original source")
    if [column["native_header_bbox"]["x0"] for column in columns] != sorted(
            column["native_header_bbox"]["x0"] for column in columns):
        raise SourceContractError("Native scientific column order changed")
    footer_position = min(target_ids.index(note["marker_line_id"])
                          for note in footnote_ledger["source_footnotes"])
    body = [lines[key] for key in target_ids[target_ids.index(header_id):footer_position]
            if lines[key]["text"].strip()]
    rows = ledger["original_table_body_rows"]
    if [row["source_line"] for row in rows] != body:
        raise SourceContractError("Native numerical ledger omitted/reordered original body line")
    expected = []
    for row in rows:
        words = row["native_words"]
        if (not words or [word["x0"] for word in words] != sorted(word["x0"] for word in words)
                or normalized_anchor_text(" ".join(word["text"] for word in words))
                != normalized_anchor_text(row["source_line"]["text"])):
            raise SourceContractError("Native numerical words differ from unchanged source body")
        for word_number, word in enumerate(words, 1):
            physical = [column for index, column in enumerate(columns)
                if column["native_header_bbox"]["x0"] - 2 <= word["x0"]
                and (index == len(columns) - 1
                     or word["x0"] < columns[index + 1]["native_header_bbox"]["x0"] - 2)]
            if not physical:
                continue
            if len(physical) != 1:
                raise SourceContractError("Native numerical word scientific column ambiguous")
            for number, match in enumerate(NUMERIC_PATTERN.finditer(word["text"]), 1):
                expected.append({
                    "quantity_id": row["source_line"]["line_id"] + ":W" + str(word_number)
                    + ":N" + str(number),
                    "source_line_id": row["source_line"]["line_id"],
                    "literal_numeric_token": match.group(), "native_word_text": word["text"],
                    "native_word_token_start": match.start(), "native_word_token_end": match.end(),
                    "technology_header_id": physical[0]["technology_header_id"],
                    "native_word_bbox": {key: word[key] for key in ["x0", "x1", "top", "bottom"]},
                })
    if expected != ledger["original_numeric_tokens_in_scientific_columns"]:
        raise SourceContractError("Native quantity/column/token ledger is incomplete or changed")
    return copy.deepcopy(ledger)


def native_value_projection(ledger: dict) -> dict:
    return {
        "source_pdf_sha256": ledger["source_pdf_sha256"],
        "technology_headers": [{key: column[key] for key in
            ["technology_header_id", "original_header_text", "header_line_id"]}
            for column in ledger["technology_headers"]],
        "original_numeric_tokens_in_scientific_columns": [{key: token[key] for key in
            ["quantity_id", "source_line_id", "literal_numeric_token", "technology_header_id"]}
            for token in ledger["original_numeric_tokens_in_scientific_columns"]],
        "scientific_fields_generated_or_changed": False,
    }


def validate_literal_scientific_evidence(claims: list[dict], pdf_context: dict,
                                        ledger: dict) -> dict:
    lines = {line["line_id"]: line for line in pdf_context["indexed_layout_lines"]}
    columns = {column["technology_header_id"]: column for column in ledger["technology_headers"]}
    links = {token["quantity_id"]: [] for token in ledger["original_numeric_tokens_in_scientific_columns"]}
    for claim in claims:
        alias = claim["reference_id"]
        chosen = claim["source_technology_header_id"]
        selected = claim["pdf_evidence_line_ids"]
        if chosen not in columns:
            raise SourceContractError("Scientific claim declares foreign original technology column: " + alias)
        column = columns[chosen]
        if column["header_line_id"] not in selected:
            raise SourceContractError("Scientific claim omits its actual technology header evidence: " + alias)
        ordinary = " ".join([claim["statement"], *claim["qualifications"]])
        names = [column["original_header_text"] for column in columns.values()
                 if re.search(r"(?<!\w)" + re.escape(column["original_header_text"]) + r"(?!\w)", ordinary)]
        if names != [column["original_header_text"]]:
            raise SourceContractError("Scientific claim must state exactly its one actual technology column: "
                                      + alias + ": " + repr(names))
        science = " ".join([ordinary, *[value["qualification"]
                             for value in claim["footnote_qualifications"].values()]])
        selected_numeric = numeric_tokens(" ".join(lines[key]["text"] for key in selected))
        unsupported = numeric_tokens(science) - selected_numeric
        if unsupported:
            raise SourceContractError("Scientific claim numbers lack their declared original PDF evidence: "
                                      + alias + ": " + repr(sorted(unsupported)))
        ordinary_numeric = numeric_tokens(ordinary)
        for token in ledger["original_numeric_tokens_in_scientific_columns"]:
            if (token["technology_header_id"] == chosen and token["source_line_id"] in selected
                    and token["literal_numeric_token"] in ordinary_numeric):
                links[token["quantity_id"]].append(alias)
    missing = [key for key, aliases in links.items() if not aliases]
    if missing:
        raise SourceContractError("Actual native numerical tokens lack same-column scientific claim evidence: "
                                  + repr(missing))
    return {"literal_numeric_source_links": links, "scientific_fields_generated_or_changed": False,
            "numeric_coverage_proves_semantic_scope": False}
