"""Original PDF body science; conditions remain separate pending actual association."""
from __future__ import annotations

from pathlib import Path
from typing import Annotated

import dspy
from dspy.utils.exceptions import AdapterParseError
from pydantic import BaseModel, ConfigDict, Field

from rstv4.skeleton_contract import Intent, SourceContractError, digest
from rstv4.skeleton_dspy import ReceiptLM, json_text, write_json
from rstv4.skeleton_mapped_review import UniqueKeyJSONAdapter
from rstv4.skeleton_original_pdf_table_science_v6 import (
    PDFLineDecision,
    complete_line_schema,
    target_line_domain,
    verify_footnote_anchor_ledger,
    verify_native_value_ledger,
)
from rstv4.skeleton_original_pdf_table_science_v6 import (
    source_values as qualified_source_values,
)
from rstv4.skeleton_pdf_numeric_source_v1 import validate_literal_scientific_evidence

PDF_TABLE_SCIENCE_VERSION = "original-pdf-body-science-full-source-compact-input-and-nonempty-schema-v8"
PDF_SCIENCE_CONTRACT = """
Extract complete independent scientific BODY assertions from the actual original PDF
target table and exact physical columns. Full original pages, complete original
footnotes and independently reviewed source-condition candidates remain supplied.
No parsed HTML, old body interpretation, learner output, grade or desired answer exists.

Each claim has one actual source_technology_header_id. State its original header name
exactly, and preserve the original parameter, all values, citation years, inequality,
modality, cell-versus-system basis, reference-power basis and actual value units in
statement and ordinary qualifications. Missing row units do not erase explicit value
units. Do not infer a missing unit from another value or scientific column. Wrapped
lines retain the original parameter/column until the original layout starts another.

Footnote conditions are distinct source-model scientific objects already retained in
original_pdf_condition_scope_candidate. Do not generate per-claim footnote fields or
copy those conditions into ordinary qualifications. Their exact original scientific
text remains preserved separately. A following independent association stage must
link every actual condition to its exact affected proposition and technology. This
body stage cannot make a qualified reference eligible. Read conditions as source
context, and retain unresolved_fields if they contradict body interpretation.

Use unique scientific reference_id aliases. Declare actual nonblank target
pdf_evidence_line_ids, including the original technology header and every wrapped line
needed for all scientific fields. Code derives source geometry and actual block ID only.
Do not generate a block_id, scientific correction or source quote. Every original
native numeric token, including citation years, must occur in a same-column unchanged
statement/ordinary qualification with its exact source line selected. Preserve lexical
numbers and punctuation without conversion. Numerical coverage is not semantic truth.

line_coverage has EXACTLY every supplied required_nonblank_line_coverage_ids key once,
and no blank or foreign key. Retain full target_table_line_ids and blank lines in source
context only. SCIENTIFIC_DATA must have actual body assertion support or an already
retained source-condition reference. HEADER_OR_STRUCTURE and BIBLIOGRAPHIC_METADATA
are nonassertive source context. UNRESOLVED explicitly retains missing interpretation;
do not mark substantive science as structure to pass a check. Preserve every actual
condition and its full original anchor/footer/definition source evidence separately.

The native quantity input retains every actual source quantity as an array; its exact
field order is declared in quantity_record_fields. All full original PDF lines and all
original condition scientific text, rationale, scope, prefix and actual evidence IDs
remain present. Only duplicated locator geometry is omitted from this model projection;
complete immutable source ledgers and geometry remain frozen for independent replay.
The technical body requires NONEMPTY claims and all actual quantities. Empty claims
with either scientific presence flag are invalid and never become source acceptance.

Return all declared top-level output fields and only those fields: claims,
line_coverage, contains_scientific_data, unresolved_fields. Independent review also
returns corrections. Do not return per-claim footnote_qualifications or old conditional
output formats. Scientific statements and qualifications stay exactly as generated.
"""


class PDFBodyClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    qualifications: list[str]
    intent: Intent
    source_technology_header_id: str = Field(min_length=1)
    pdf_evidence_line_ids: list[str] = Field(min_length=1)


class PDFTableAnnotation(dspy.Signature):
    original_pdf_lines: str = dspy.InputField()
    original_pdf_source_lineage: str = dspy.InputField()
    original_pdf_footnote_anchors: str = dspy.InputField()
    original_pdf_native_column_values: str = dspy.InputField()
    original_pdf_definition_fragments: str = dspy.InputField()
    original_pdf_condition_scope_candidate: str = dspy.InputField()
    target_table_line_ids: str = dspy.InputField()
    required_nonblank_line_coverage_ids: str = dspy.InputField()
    target_block_id: str = dspy.InputField()
    scientific_interpretation_contract: str = dspy.InputField()
    repair_feedback: str = dspy.InputField()
    claims: Annotated[list[PDFBodyClaim], Field(min_length=1)] = dspy.OutputField()
    line_coverage: dict[str, PDFLineDecision] = dspy.OutputField()
    contains_scientific_data: bool = dspy.OutputField()
    unresolved_fields: list[str] = dspy.OutputField()


class PDFTableReview(PDFTableAnnotation):
    draft_scientific_annotation: str = dspy.InputField()
    corrections: list[str] = dspy.OutputField()


PDFTableAnnotation = PDFTableAnnotation.with_instructions(PDF_SCIENCE_CONTRACT)
PDFTableReview = PDFTableReview.with_instructions(PDF_SCIENCE_CONTRACT + "\nIndependently "
    "reread every source column, value, unit, condition context and quantity. Return a "
    "complete source-justified replacement. The draft is a candidate, never authority.")


def source_values(pdf_context, target_ids, block_id, footnote_ledger, native_value_ledger,
                  definition_fragments, reviewed_scope):
    values = qualified_source_values(pdf_context, target_ids, block_id, footnote_ledger,
        native_value_ledger, definition_fragments, reviewed_scope)
    values.pop("original_condition_copy_literals")
    values["original_pdf_native_column_values"] = json_text({
        "source_pdf_sha256": native_value_ledger["source_pdf_sha256"],
        "technology_headers": [{key: item[key] for key in ["technology_header_id", "original_header_text", "header_line_id"]}
            for item in native_value_ledger["technology_headers"]],
        "quantity_record_fields": ["quantity_id", "source_line_id", "literal_numeric_token", "technology_header_id"],
        "original_numeric_tokens_in_scientific_columns": [[item[key] for key in
            ["quantity_id", "source_line_id", "literal_numeric_token", "technology_header_id"]]
            for item in native_value_ledger["original_numeric_tokens_in_scientific_columns"]],
        "scientific_fields_generated_or_changed": False})
    values["original_pdf_condition_scope_candidate"] = json_text({key: reviewed_scope[key] for key in
        ["condition_scopes", "unresolved_fields", "source_scope_protocol_eligible"]})
    values["original_pdf_definition_fragments"] = json_text({
        "source_pdf_sha256": definition_fragments["source_pdf_sha256"],
        "layout_text_sha256": definition_fragments["layout_text_sha256"],
        "fragments": [{key: item[key] for key in ["fragment_id", "marker", "quote", "original_definition_line_ids"]}
            for item in definition_fragments["fragments"]], "scientific_propositions_or_scopes_generated": False})
    values["scientific_interpretation_contract"] = PDF_SCIENCE_CONTRACT
    return values


def source_error_feedback(message: str) -> str:
    """Retain structural diagnostic without feeding back a partial raw response excerpt."""
    return message.split("\n\nAdapter ", 1)[0].split("\n\nLM Response:", 1)[0]


def source_condition_references(domain, footnotes, definition_fragments, reviewed_scope):
    fragments = {item["fragment_id"]: item for item in definition_fragments["fragments"]}
    scopes = reviewed_scope["condition_scopes"]
    if (set(scopes) != set(fragments) or reviewed_scope["source_scope_protocol_eligible"] is not True
            or reviewed_scope["unresolved_fields"]):
        raise SourceContractError("Complete eligible original condition candidate required")
    references = []
    for key, scope in scopes.items():
        marker = fragments[key]["marker"]
        if marker not in footnotes or scope["resolution"] != "RESOLVED":
            raise SourceContractError("Original source condition marker/resolution changed")
        note = footnotes[marker]
        selected = scope["pdf_evidence_line_ids"]
        required = {note["anchor_line_id"], note["marker_line_id"],
            *[line["line_id"] for line in note["definition_lines"]]}
        if (len(selected) != len(set(selected)) or not set(selected).issubset(domain)
                or not required.issubset(selected)):
            raise SourceContractError("Source condition lacks actual complete anchor/definition")
        references.append({"actual_condition_fragment_id": key, "actual_marker": marker,
            "unchanged_source_model_scope": scope, "actual_definition_fragment": fragments[key],
            "actual_pdf_evidence": [domain[line_id] for line_id in selected],
            "scientific_fields_changed": False, "body_association_complete": False})
    return references


def validate_pdf_science(output, pdf_context, target_ids, block_id, footnote_ledger,
                         native_value_ledger, definition_fragments, reviewed_scope):
    complete = target_line_domain(pdf_context, target_ids)
    domain = {key: value for key, value in complete.items() if value["text"].strip()}
    notes = {item["marker"]: item for item in verify_footnote_anchor_ledger(
        pdf_context, target_ids, footnote_ledger)}
    verify_native_value_ledger(pdf_context, target_ids, footnote_ledger, native_value_ledger)
    conditions = source_condition_references(domain, notes, definition_fragments, reviewed_scope)
    if set(output["line_coverage"]) != set(domain):
        raise SourceContractError("Every nonblank original PDF table line requires exactly one disposition")
    links = {key: [] for key in domain}
    condition_links = {key: [] for key in domain}
    for condition in conditions:
        for line in condition["actual_pdf_evidence"]:
            condition_links[line["line_id"]].append(condition["actual_condition_fragment_id"])
    claims, ids, locators, identities = [], set(), [], []
    for raw in output["claims"]:
        claim = PDFBodyClaim.model_validate(raw).model_dump()
        alias, selected = claim["reference_id"], claim["pdf_evidence_line_ids"]
        if alias in ids:
            raise SourceContractError("Original scientific body claim ID duplicated: " + alias)
        ids.add(alias)
        if len(selected) != len(set(selected)) or not set(selected).issubset(domain):
            raise SourceContractError("Scientific body evidence must select unique actual nonblank lines")
        for key in selected:
            links[key].append(alias)
        claims.append(claim)
        locators.append({"reference_id": alias, "pdf_evidence_locations": [domain[key] for key in selected],
            "scientific_fields_changed": False})
        identities.append({"reference_id": alias, "actual_target_block_id": block_id,
            "source_identity_generated_by_model": False, "scientific_fields_changed": False})
    # The unchanged numerical verifier reads an empty condition view only; no scientific text is added.
    numeric_view = [{**claim, "footnote_qualifications": {}} for claim in claims]
    if not isinstance(output["contains_scientific_data"], bool) or output["contains_scientific_data"] != bool(claims) or not claims:
        raise SourceContractError("Actual technical table requires nonempty scientific body assertions")
    numerical = validate_literal_scientific_evidence(numeric_view, pdf_context, native_value_ledger)
    coverage, unresolved = [], []
    for key, raw in output["line_coverage"].items():
        decision = PDFLineDecision.model_validate(raw).model_dump()
        if decision["disposition"] == "SCIENTIFIC_DATA" and not (links[key] or condition_links[key]):
            raise SourceContractError("Actual scientific line lacks body or source-condition support: " + key)
        if decision["disposition"] == "UNRESOLVED":
            unresolved.append(key)
            if links[key] or condition_links[key]:
                raise SourceContractError("Unresolved line cannot become resolved scientific support")
        coverage.append({"line_id": key, **decision,
            "body_reference_ids": links[key] if decision["disposition"] == "SCIENTIFIC_DATA" else [],
            "source_condition_fragment_ids": condition_links[key] if decision["disposition"] == "SCIENTIFIC_DATA" else []})
    if not isinstance(output["contains_scientific_data"], bool) or output["contains_scientific_data"] != bool(claims) or not claims:
        raise SourceContractError("Actual technical table requires nonempty scientific body assertions")
    if unresolved and not output["unresolved_fields"]:
        raise SourceContractError("Unresolved body source lines require retained scientific ambiguity")
    return {"claims": claims, "line_coverage": coverage, "source_block_identity_resolutions": identities,
        "source_line_locator_resolutions": locators, "native_numeric_source_proof": numerical,
        "unchanged_source_condition_references": conditions, "contains_scientific_data": True,
        "unresolved_fields": list(output["unresolved_fields"]),
        "pdf_body_source_protocol_eligible": not unresolved and not output["unresolved_fields"],
        "qualified_scientific_reference_eligible": False, "condition_association_complete": False,
        "parsed_cell_association_complete": False, "full_source_comparison_complete": False,
        **({"corrections": list(output["corrections"])} if "corrections" in output else {})}


class OriginalPDFTableScienceBuilder:
    def __init__(self, output: Path, *, actual_model: str):
        self.output = output
        self.lm = ReceiptLM("thinking", output / "teacher-lm", max_tokens=24000,
            required_actual_model=actual_model)

    def annotate(self, pdf_context, target_ids, block_id, footnote_ledger, native_value_ledger,
                 definition_fragments, reviewed_scope):
        args = (pdf_context, target_ids, block_id, footnote_ledger, native_value_ledger,
            definition_fragments, reviewed_scope)
        values = source_values(*args)
        schema = complete_line_schema(pdf_context, target_ids)
        signatures = {"PDF_ANNOTATION": PDFTableAnnotation.with_updated_fields("line_coverage", type_=schema),
            "PDF_INDEPENDENT_REVIEW": PDFTableReview.with_updated_fields("line_coverage", type_=schema)}
        key = digest({"version": PDF_TABLE_SCIENCE_VERSION, "inputs": values})
        record_path = self.output / "records" / (key + ".json")
        if record_path.exists():
            raise SourceContractError("Body science already completed; audit original evidence")
        stages = {}
        for name, signature in signatures.items():
            base = dict(values)
            if name == "PDF_INDEPENDENT_REVIEW":
                base["draft_scientific_annotation"] = json_text(stages["PDF_ANNOTATION"]["model_output"])
            predictor, attempts, feedback = dspy.Predict(signature), [], []
            for number in range(3):
                actual, raw = {**base, "repair_feedback": "\n".join(feedback)}, None
                try:
                    with dspy.context(lm=self.lm, adapter=UniqueKeyJSONAdapter()):
                        result = predictor(**actual)
                    raw = {"claims": [claim.model_dump() for claim in result.claims],
                        "line_coverage": result.line_coverage.model_dump(),
                        "contains_scientific_data": result.contains_scientific_data,
                        "unresolved_fields": list(result.unresolved_fields),
                        **({"corrections": list(result.corrections)} if name == "PDF_INDEPENDENT_REVIEW" else {})}
                    validated = validate_pdf_science(raw, *args)
                except (AdapterParseError, SourceContractError, ValueError, TypeError) as failure:
                    message = str(failure)[:2500]
                    attempts.append({"number": number + 1, "inputs": actual, "inputs_digest": digest(actual),
                        "model_output": raw, "protocol_error": message})
                    feedback.append(source_error_feedback(message))
                    write_json(self.output / "failures" / (key + "-" + name + ".json"), {"attempts": attempts})
                else:
                    stages[name] = {"inputs": actual, "inputs_digest": digest(actual), "model_output": raw,
                        "validated": validated, "rejected_attempts": attempts}
                    write_json(self.output / "stages" / key / (name + ".json"), stages[name])
                    break
            else:
                raise SourceContractError("Original PDF body own-protocol attempts exhausted: " + feedback[-1])
        record = {"version": PDF_TABLE_SCIENCE_VERSION, "input_digest": key, "inputs": values,
            "stages": stages, "reviewed": stages["PDF_INDEPENDENT_REVIEW"]["validated"],
            "candidate_access": False, "status": "BODY_SOURCE_CANDIDATE_PENDING_CONDITION_ASSOCIATION_AND_AUDIT"}
        write_json(record_path, record)
        return record
