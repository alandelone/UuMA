"""Scientific table annotation from original PDF, before parsed-cell association."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Literal

import dspy
from dspy.utils.exceptions import AdapterParseError
from pydantic import BaseModel, ConfigDict, Field, create_model

from rstv4.skeleton_contract import Intent, SourceContractError, digest
from rstv4.skeleton_dspy import ReceiptLM, json_text, write_json
from rstv4.skeleton_mapped_review import UniqueKeyJSONAdapter
from rstv4.skeleton_scientific_table_reference_v8 import indexed_original_pdf_lines

PDF_TABLE_SCIENCE_VERSION = "source-only-original-pdf-science-before-parsed-cell-association-v1"
PDF_SCIENCE_CONTRACT = """
Extract the complete scientific content of the identified original PDF table, solely
from actual original_pdf_lines and target_table_line_ids. All lines are exact original
text preserving physical columns, whitespace, wrapped continuations and footnotes.
The full original pages are supplied as neighboring context. Extract ONLY the target
table. Parsed HTML and historical model interpretations are deliberately unavailable
at this scientific stage. No learner output, grade or desired scientific answer exists.

Read the parameter, stated unit and technology column in the ORIGINAL layout. A row
may continue across several physical lines; a continuation retains its original row
and column until the original PDF starts the next parameter. Preserve every material
value, cited source, baseline, modality, condition, comparison, inequality and footnote.
Do not silently assign missing units. Keep cell versus system efficiency distinct.
Footnote conditions belong in qualifications of all affected actual assertions.
Use independent scientific propositions, not a generic table description. Never guess
ambiguous scientific scope: explicitly retain it in unresolved_fields and coverage.

Each claim declares unique actual pdf_evidence_line_ids supporting all its scientific
fields. Do not reproduce quotes or calculate offsets. Code resolves ONLY source
geometry; it never rewrites scientific statements, qualifications or intent. Use unique
claim aliases r1,r2,... and the exact target block_id. An actual line may support
multiple claims. Include original header/unit/footnote lines needed by each claim.

line_coverage requires every nonblank target-table line exactly once. Each value has
only disposition and rationale. SCIENTIFIC_DATA includes actual quantities, properties,
conditions and scientific footnotes, and must support an actual extracted assertion.
HEADER_OR_STRUCTURE and BIBLIOGRAPHIC_METADATA describe only actual nonassertive source.
UNRESOLVED is explicit incomplete scientific interpretation. Every disposition must
be source justified. Complete source coverage is mandatory. Do not clear an ambiguity
by inventing an assertion or marking substantive science as structure.
"""


class PDFScientificClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference_id: str = Field(min_length=1)
    block_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    qualifications: list[str]
    intent: Intent
    pdf_evidence_line_ids: list[str] = Field(min_length=1)


class PDFLineDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disposition: Literal["SCIENTIFIC_DATA", "HEADER_OR_STRUCTURE", "BIBLIOGRAPHIC_METADATA", "UNRESOLVED"]
    rationale: str = Field(min_length=1)


class PDFTableAnnotation(dspy.Signature):
    original_pdf_lines: str = dspy.InputField()
    original_pdf_source_lineage: str = dspy.InputField()
    target_table_line_ids: str = dspy.InputField()
    target_block_id: str = dspy.InputField()
    scientific_interpretation_contract: str = dspy.InputField()
    repair_feedback: str = dspy.InputField()
    claims: list[PDFScientificClaim] = dspy.OutputField()
    line_coverage: dict[str, PDFLineDecision] = dspy.OutputField()
    contains_scientific_data: bool = dspy.OutputField()
    unresolved_fields: list[str] = dspy.OutputField()


class PDFTableReview(PDFTableAnnotation):
    draft_scientific_annotation: str = dspy.InputField()
    corrections: list[str] = dspy.OutputField()


PDFTableAnnotation = PDFTableAnnotation.with_instructions(PDF_SCIENCE_CONTRACT)
PDFTableReview = PDFTableReview.with_instructions(
    PDF_SCIENCE_CONTRACT + "\nIndependently re-read every target line and physical column. "
    "Correct unsupported scope, omitted values or footnotes using only the original PDF. "
    "Return a complete replacement scientific annotation and source-justified corrections. "
    "The draft is a candidate, never an authority.")


def target_line_domain(pdf_context: dict, target_ids: list[str]) -> dict[str, dict]:
    lines = indexed_original_pdf_lines(pdf_context["layout_text"])
    actual_ids = [line["line_id"] for line in lines]
    if (not target_ids or len(target_ids) != len(set(target_ids))
            or not set(target_ids).issubset(actual_ids)):
        raise SourceContractError("Original PDF table requires unique actual target line IDs")
    positions = [actual_ids.index(key) for key in target_ids]
    if positions != list(range(positions[0], positions[-1] + 1)):
        raise SourceContractError("Original PDF table target must retain its entire consecutive source range")
    return {line["line_id"]: line for line in lines if line["line_id"] in target_ids}


def complete_line_schema(pdf_context: dict, target_ids: list[str]) -> type[BaseModel]:
    return create_model("AllActualNonblankPDFTableLines", __config__=ConfigDict(extra="forbid"),
        **{key: (PDFLineDecision, Field(description=line["text"]))
           for key, line in target_line_domain(pdf_context, target_ids).items() if line["text"].strip()})


def source_values(pdf_context: dict, target_ids: list[str], block_id: str) -> dict:
    target_line_domain(pdf_context, target_ids)
    return {"original_pdf_lines": json_text([{key: line[key] for key in ("line_id", "text")}
                                             for line in indexed_original_pdf_lines(pdf_context["layout_text"])]),
            "original_pdf_source_lineage": json_text({key: value for key, value in pdf_context.items()
                                                       if key not in {"layout_text", "indexed_layout_lines"}}),
            "target_table_line_ids": json_text(target_ids), "target_block_id": block_id,
            "scientific_interpretation_contract": PDF_SCIENCE_CONTRACT}


def validate_pdf_science(output: dict, pdf_context: dict, target_ids: list[str], block_id: str) -> dict:
    domain = target_line_domain(pdf_context, target_ids)
    required = {key for key, line in domain.items() if line["text"].strip()}
    if set(output["line_coverage"]) != required:
        raise SourceContractError("Every nonblank original PDF table line must have exactly one disposition")
    claims, locators, ids = [], [], set()
    links = {key: [] for key in required}
    for raw in output["claims"]:
        claim = PDFScientificClaim.model_validate(raw).model_dump()
        alias = claim["reference_id"]
        selected = claim["pdf_evidence_line_ids"]
        if alias in ids or claim["block_id"] != block_id:
            raise SourceContractError("Original PDF scientific claim ID duplicate or foreign block")
        ids.add(alias)
        if len(selected) != len(set(selected)) or not set(selected).issubset(required):
            raise SourceContractError("Original PDF scientific evidence must be unique nonblank target lines")
        for key in selected:
            links[key].append(alias)
        claims.append(claim)
        locators.append({"reference_id": alias, "pdf_evidence_locations": [
            {"line_id": key, "quote": domain[key]["text"], "start": domain[key]["start"], "end": domain[key]["end"],
             "original_pdf_layout_digest": digest(pdf_context["layout_text"])} for key in selected],
            "model_scientific_fields_changed": False})
    coverage, unresolved = [], []
    for key, raw in output["line_coverage"].items():
        decision = PDFLineDecision.model_validate(raw).model_dump()
        if decision["disposition"] == "SCIENTIFIC_DATA" and not links[key]:
            raise SourceContractError("Actual scientific PDF line lacks extracted claim support: " + key)
        if decision["disposition"] == "UNRESOLVED":
            unresolved.append(key)
            if links[key]:
                raise SourceContractError("Unresolved PDF scientific line cannot be claimed as resolved support")
        coverage.append({"line_id": key, **decision,
                         "reference_ids": links[key] if decision["disposition"] == "SCIENTIFIC_DATA" else []})
    contains = output["contains_scientific_data"]
    if not isinstance(contains, bool) or contains != bool(claims):
        raise SourceContractError("Original PDF scientific presence must agree with actual extracted assertions")
    if not claims:
        raise SourceContractError("This actual technical table requires scientific extraction, not zero-claim structure")
    if unresolved and not output["unresolved_fields"]:
        raise SourceContractError("Unresolved scientific PDF lines require explicit scientific omissions")
    return {"claims": claims, "line_coverage": coverage, "source_line_locator_resolutions": locators,
            "contains_scientific_data": contains, "unresolved_fields": list(output["unresolved_fields"]),
            "pdf_scientific_coverage_eligible": not unresolved and not output["unresolved_fields"],
            "parsed_cell_association_complete": False, "full_source_comparison_complete": False,
            **({"corrections": copy.deepcopy(output["corrections"])} if "corrections" in output else {})}


class OriginalPDFTableScienceBuilder:
    def __init__(self, output: Path, *, actual_model: str) -> None:
        self.output = output
        self.lm = ReceiptLM("thinking", output / "teacher-lm", max_tokens=24000,
                            required_actual_model=actual_model)

    def annotate(self, pdf_context: dict, target_ids: list[str], block_id: str) -> dict:
        values = source_values(pdf_context, target_ids, block_id)
        schema = complete_line_schema(pdf_context, target_ids)
        signatures = {"PDF_ANNOTATION": PDFTableAnnotation.with_updated_fields("line_coverage", type_=schema),
                      "PDF_INDEPENDENT_REVIEW": PDFTableReview.with_updated_fields("line_coverage", type_=schema)}
        key = digest({"version": PDF_TABLE_SCIENCE_VERSION, "inputs": values})
        record_path = self.output / "records" / (key + ".json")
        if record_path.exists():
            raise SourceContractError("Original PDF science probe already completed; audit existing evidence")
        stages = {}
        for name, signature in signatures.items():
            base = dict(values)
            if name == "PDF_INDEPENDENT_REVIEW":
                base["draft_scientific_annotation"] = json_text(stages["PDF_ANNOTATION"]["model_output"])
            predictor, failures, attempts = dspy.Predict(signature), [], []
            for number in range(3):
                actual = {**base, "repair_feedback": "\n".join(failures)}
                raw = None
                try:
                    with dspy.context(lm=self.lm, adapter=UniqueKeyJSONAdapter()):
                        result = predictor(**actual)
                    raw = {"claims": [claim.model_dump() for claim in result.claims],
                           "line_coverage": result.line_coverage.model_dump(),
                           "contains_scientific_data": result.contains_scientific_data,
                           "unresolved_fields": list(result.unresolved_fields),
                           **({"corrections": list(result.corrections)} if name == "PDF_INDEPENDENT_REVIEW" else {})}
                    validated = validate_pdf_science(raw, pdf_context, target_ids, block_id)
                    stages[name] = {"inputs": actual, "inputs_digest": digest(actual), "model_output": raw,
                                    "validated": validated, "rejected_attempts": attempts}
                    write_json(self.output / "stages" / key / (name + ".json"), stages[name])
                    break
                except (AdapterParseError, SourceContractError, ValueError, TypeError) as error:
                    message = str(error)[:2500]
                    attempts.append({"number": number + 1, "inputs": actual, "inputs_digest": digest(actual),
                                     "model_output": raw, "protocol_error": message})
                    failures.append(message)
                    write_json(self.output / "failures" / (key + "-" + name + ".json"), {"attempts": attempts})
            else:
                raise SourceContractError("Original PDF science own-protocol stage exhausted: " + failures[-1])
        record = {"version": PDF_TABLE_SCIENCE_VERSION, "input_digest": key, "inputs": values, "stages": stages,
                  "reviewed": stages["PDF_INDEPENDENT_REVIEW"]["validated"], "candidate_access": False,
                  "status": "ORIGINAL_PDF_SCIENCE_CANDIDATE_PENDING_PARSED_CELL_ASSOCIATION_AND_AUDIT"}
        write_json(record_path, record)
        return record
