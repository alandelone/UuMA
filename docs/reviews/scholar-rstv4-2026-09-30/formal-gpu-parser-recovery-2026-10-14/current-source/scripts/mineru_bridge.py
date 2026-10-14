from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path


def install_transformers_compatibility() -> None:
    """Map imports moved across supported Transformers releases."""
    from transformers import modeling_utils, pytorch_utils

    for name in (
        "apply_chunking_to_forward",
        "find_pruneable_heads_and_indices",
        "prune_linear_layer",
    ):
        if not hasattr(modeling_utils, name) and hasattr(pytorch_utils, name):
            setattr(modeling_utils, name, getattr(pytorch_utils, name))


def install_ocr_device_compatibility() -> None:
    """Keep Paddle OCR on the device selected by the MinerU configuration."""
    from magic_pdf.libs.config_reader import get_device

    if str(get_device()).casefold().startswith("cuda"):
        return
    from magic_pdf.model.sub_modules import model_init

    original = model_init.ModifiedPaddleOCR

    def configured_ocr(*args: object, **kwargs: object) -> object:
        kwargs["use_gpu"] = False
        return original(*args, **kwargs)

    model_init.ModifiedPaddleOCR = configured_ocr


def install_checkpoint_memory_compatibility() -> None:
    """Map existing checkpoint storage when this isolated run opts in."""
    if os.environ.get("RSTV4_MINERU_MMAP_WEIGHTS") != "1":
        return
    import torch

    original = torch.load

    def mapped_load(file: object, *args: object, **kwargs: object) -> object:
        if isinstance(file, (str, os.PathLike)) and "mmap" not in kwargs:
            path = Path(file)
            if path.is_file() and zipfile.is_zipfile(path):
                kwargs["mmap"] = True
        return original(file, *args, **kwargs)

    torch.load = mapped_load


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--legacy-root", required=True)
    parser.add_argument("--method", choices=("auto", "ocr", "txt"), default="auto")
    parser.add_argument("--stage", choices=("analyze", "materialize"), default="materialize")
    args = parser.parse_args()

    legacy_root = Path(args.legacy_root).resolve()
    sys.path.insert(0, str(legacy_root))
    install_transformers_compatibility()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    model_path = output / "model.json"
    if args.stage == "analyze":
        install_checkpoint_memory_compatibility()
        install_ocr_device_compatibility()
        from magic_pdf.config.enums import SupportedPdfParseMethod
        from magic_pdf.data.data_reader_writer import FileBasedDataReader, FileBasedDataWriter
        from magic_pdf.data.dataset import PymuDocDataset
        from magic_pdf.model.doc_analyze_by_custom_model import doc_analyze

        dataset = PymuDocDataset(FileBasedDataReader("").read(str(Path(args.pdf).resolve())))
        pdf_type = (
            dataset.classify()
            if args.method == "auto"
            else SupportedPdfParseMethod(args.method)
        )
        print(f"RSTV4_STAGE analyze_start type={pdf_type}", file=sys.stderr, flush=True)
        inference = dataset.apply(doc_analyze, ocr=(pdf_type == SupportedPdfParseMethod.OCR))
        inference.dump_model(FileBasedDataWriter(str(output)), model_path.name)
        print("RSTV4_STAGE model_written", file=sys.stderr, flush=True)
        print(model_path)
        return 0

    if not model_path.is_file():
        raise RuntimeError("MinerU analysis artifact is missing")
    from magic_pdf.operators.models import InferenceResult
    from paperpool.workers import pdf_parser_worker
    from paperpool.workers.content_refiner_worker import refine_content_list

    model_data = json.loads(model_path.read_text(encoding="utf-8"))
    if not isinstance(model_data, list) or not model_data:
        raise RuntimeError("MinerU analysis artifact is empty or invalid")

    def cached_analysis(dataset: object, **_: object) -> InferenceResult:
        # The legacy worker ignores model_json_path and reruns every model. Keep its
        # parsing and artifact pipeline while supplying the saved MinerU inference.
        return InferenceResult(model_data, dataset)

    pdf_parser_worker.doc_analyze = cached_analysis
    print("RSTV4_STAGE parse_start", file=sys.stderr, flush=True)
    markdown_path = pdf_parser_worker.pdf_parse_main(
        str(Path(args.pdf).resolve()),
        parse_method=args.method,
        output_dir=str(output),
        is_draw_visualization_bbox=False,
    )
    print("RSTV4_STAGE parser_returned", file=sys.stderr, flush=True)
    if not markdown_path:
        raise RuntimeError("MinerU did not publish a Markdown artifact")
    markdown = Path(markdown_path)
    content_list = markdown.with_name(f"{markdown.stem}_content_list.json")
    if not markdown.is_file() or not content_list.is_file():
        raise RuntimeError("MinerU artifact set is incomplete")
    refined = refine_content_list(str(content_list))
    print("RSTV4_STAGE refined", file=sys.stderr, flush=True)
    blocks = []
    for index, item in enumerate(refined["pp_txt_dict"]):
        text = str(item.get("raw_text") or item.get("text") or "").strip()
        if text:
            blocks.append(
                {
                    "sequence": index,
                    "page_number": item.get("page_idx"),
                    "section": item.get("section"),
                    "block_type": "TEXT",
                    "text": text,
                    "location": {"source": "mineru_content_list", "seq_idx": index},
                }
            )
    references = [
        {"raw_text": text, "location": {"source": "mineru_references", "index": index}}
        for index, text in enumerate(refined["ref_raw"])
        if str(text).strip()
    ]
    result = {
        "parser": "MinerU/magic-pdf",
        "parser_version": "1.2.2",
        "manifest": {
            "markdown_path": str(markdown),
            "content_list_path": str(content_list),
            "artifacts_complete": True,
        },
        "blocks": blocks,
        "references": references,
        "abstract": refined["pp_abstract"],
    }
    manifest_path = output / "rstv4-parse-result.json"
    temporary = manifest_path.with_suffix(".partial")
    temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    temporary.replace(manifest_path)
    print("RSTV4_STAGE manifest_written", file=sys.stderr, flush=True)
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
