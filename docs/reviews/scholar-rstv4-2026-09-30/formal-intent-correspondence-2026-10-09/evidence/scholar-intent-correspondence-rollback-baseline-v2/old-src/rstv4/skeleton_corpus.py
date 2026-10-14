"""Prepare a reproducible paper-disjoint corpus from existing local parser artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from .parser_quality import normalize_mineru_result
from .skeleton_contract import build_document_context, chunk_document, digest


def _title_identity(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def prepare_corpus(
    source: Path, output: Path, *, seed: int = 20260930,
    train_count: int = 4, validation_count: int = 2, test_count: int = 10,
) -> dict[str, Any]:
    if min(train_count, validation_count) < 1 or test_count < 10:
        raise ValueError("Require nonempty train/validation and at least ten test papers")
    if (output / "manifest.json").exists():
        raise FileExistsError("Corpus already exists; use its frozen manifest or a new directory")
    pdfs = {_title_identity(path.stem): path for path in source.glob("*.pdf")}
    eligible, excluded = [], []
    for content in sorted((source / "pdfparser").glob("*/*_content_list.json")):
        name = content.stem.removesuffix("_content_list")
        pdf = pdfs.get(_title_identity(name))
        if pdf is None:
            excluded.append({"source": str(content), "reason": "NO_MATCHING_SOURCE_PDF"})
            continue
        markdown = content.with_name(name + ".md")
        if not markdown.is_file():
            excluded.append({"source": str(content), "reason": "MISSING_MARKDOWN"})
            continue
        items = json.loads(content.read_text(encoding="utf-8"))
        chars = sum(len(str(item.get("text") or "")) for item in items if isinstance(item, dict))
        if not 12000 <= chars <= 150000:
            excluded.append({"source": str(content), "reason": "OUTSIDE_ARTICLE_LENGTH_STRATUM"})
            continue
        eligible.append((content, markdown, pdf))
    rng = random.Random(seed)
    rng.shuffle(eligible)
    # The already-inspected baseline paper belongs in development, never the final test set.
    preferred = next((item for item in eligible if "Kuwait" in item[2].stem), None)
    if preferred:
        eligible.remove(preferred)
        eligible.insert(0, preferred)
    needed = train_count + validation_count + test_count
    documents = []
    used_titles, used_pdf_digests, used_dois = set(), set(), set()
    for content, markdown, pdf in eligible:
        try:
            pages = len(PdfReader(str(pdf), strict=False).pages)
            if not 4 <= pages <= 50:
                excluded.append({"source": str(content), "reason": "OUTSIDE_ARTICLE_PAGE_STRATUM"})
                continue
            title_identity = _title_identity(pdf.stem)
            pdf_digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
            if title_identity in used_titles or pdf_digest in used_pdf_digests:
                excluded.append({"source": str(content), "reason": "DUPLICATE_SOURCE"})
                continue
            normalized = normalize_mineru_result({"manifest": {
                "content_list_path": str(content), "markdown_path": str(markdown),
            }}, source_pdf_path=pdf)
            blocks = normalized["blocks"]
            front = " ".join(block["text"] for block in blocks[:10])
            match = re.search(r"10\.\d{4,9}/[^\s<>\"{}]+", front, re.IGNORECASE)
            doi = match.group(0).rstrip(".,);").casefold() if match else None
            if doi and doi in used_dois:
                excluded.append({"source": str(content), "reason": "DUPLICATE_FRONT_MATTER_DOI"})
                continue
            paper_id = "paper_" + digest(doi or title_identity)[:20]
            for block in blocks:
                block["block_id"] = f"{paper_id}:b{block['sequence']}"
            index = len(documents)
            split = "train" if index < train_count else (
                "validation" if index < train_count + validation_count else "test"
            )
            document = {
                "paper_id": paper_id, "title": pdf.stem, "doi_candidate": doi,
                "split": split, "pages": pages,
                "source_pdf": str(pdf), "source_content": str(content),
                "source_pdf_sha256": pdf_digest,
                "source_content_sha256": hashlib.sha256(content.read_bytes()).hexdigest(),
                "parser_quality": normalized["manifest"]["quality"], "blocks": blocks,
                "context": build_document_context(blocks, pdf.stem),
            }
            documents.append(document)
            used_titles.add(title_identity)
            used_pdf_digests.add(pdf_digest)
            if doi:
                used_dois.add(doi)
            print(f"{split}: {pdf.stem} ({len(blocks)} blocks)", flush=True)
            if len(documents) == needed:
                break
        except (OSError, ValueError, TypeError) as exc:
            excluded.append({"source": str(content), "reason": type(exc).__name__, "detail": str(exc)})
    if len(documents) != needed:
        raise ValueError(f"Only {len(documents)} of {needed} distinct papers could be prepared")
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": "paper-disjoint-v1", "seed": seed,
        "selection": "Fixed shuffled article-length stratum; preinspected Kuwait source in train",
        "limits": "Local research corpus; 4-50 page articles, 12000-150000 text characters",
        "counts": {"train": train_count, "validation": validation_count, "test": test_count},
        "eligible_artifacts": len(eligible), "excluded": excluded,
        "documents": [],
    }
    for document in documents:
        filename = document["paper_id"] + ".json"
        (output / filename).write_text(
            json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        manifest["documents"].append({
            key: value for key, value in document.items() if key not in {"blocks", "context"}
        } | {
            "file": filename, "body_blocks": len(document["blocks"]),
            "text_chars": sum(len(block["text"]) for block in document["blocks"]),
            "full_document_chunks": len(chunk_document(document["blocks"])),
        })
    manifest["manifest_digest"] = digest(manifest)
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--test-papers", type=int, default=10)
    args = parser.parse_args()
    result = prepare_corpus(args.source.resolve(), args.output.resolve(), test_count=args.test_papers)
    print(json.dumps({"counts": result["counts"], "manifest_digest": result["manifest_digest"]}))


if __name__ == "__main__":
    main()
