from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from rstv4.paper_parser import MinerUParser
from rstv4.parser_quality import normalize_mineru_result


def _result(tmp_path: Path, items: list[dict]) -> dict:
    markdown = tmp_path / "paper.md"
    content_list = tmp_path / "paper_content_list.json"
    markdown.write_text("# A paper\n\nBody content", encoding="utf-8")
    content_list.write_text(json.dumps(items), encoding="utf-8")
    return {
        "manifest": {
            "markdown_path": str(markdown),
            "content_list_path": str(content_list),
        },
        "blocks": [],
        "references": [],
    }


def test_conclusion_and_bibliography_keep_locations(tmp_path: Path) -> None:
    items = [
        {"type": "text", "text_level": 1, "text": "Introduction", "page_idx": 0},
        {"type": "text", "text": "A detailed method and result. " * 5, "page_idx": 0},
        {"type": "text", "text_level": 1, "text": "Conclusions", "page_idx": 1},
        {"type": "text", "text": "The conclusion remains available as evidence. " * 3,
         "page_idx": 1},
        {"type": "text", "text_level": 1, "text": "Bibliography", "page_idx": 2},
        {"type": "text", "text": "[1] First cited work. [2] Second cited work.",
         "page_idx": 2},
        {"type": "text", "text": "There are no conflicts of interest.", "page_idx": 3},
    ]

    parsed = normalize_mineru_result(_result(tmp_path, items))

    assert any("conclusion remains" in block["text"] for block in parsed["blocks"])
    assert {block["page_number"] for block in parsed["blocks"]} == {1, 2, 4}
    assert [ref["page_number"] for ref in parsed["references"]] == [3, 3]
    assert len(parsed["references"]) == 2
    assert parsed["blocks"][-1]["section"] == "Back matter"
    assert parsed["blocks"][0]["location"]["content_index"] == 0
    assert parsed["manifest"]["quality"]["reference_heading_found"] is True


def test_empty_body_cannot_be_published(tmp_path: Path) -> None:
    items = [{"type": "text", "text_level": 1, "text": "Bibliography", "page_idx": 0},
             {"type": "text", "text": "[1] Reference only.", "page_idx": 0}]

    with pytest.raises(ValueError, match="too little readable body"):
        normalize_mineru_result(_result(tmp_path, items))


def test_embedded_reference_heading_is_split_from_first_entry(tmp_path: Path) -> None:
    items = [
        {"type": "text", "text": "The study reports a substantial body of findings. " * 5,
         "page_idx": 0},
        {"type": "text", "text": "Journal footer\nReferences\n[1] First work. [2] Next work.",
         "page_idx": 1},
    ]

    parsed = normalize_mineru_result(_result(tmp_path, items))

    assert parsed["manifest"]["quality"]["reference_heading_found"] is True
    assert [entry["raw_text"] for entry in parsed["references"]] == [
        "[1] First work.", "[2] Next work.",
    ]
    assert any(block["text"] == "Journal footer" for block in parsed["blocks"])


def test_years_inside_reference_do_not_create_new_entries(tmp_path: Path) -> None:
    items = [
        {"type": "text", "text": "A substantial source body. " * 6, "page_idx": 0},
        {"type": "text", "text_level": 1, "text": "Literature Cited", "page_idx": 1},
        {"type": "text", "text": "1. First author 2020. Results from 2019.\n"
         "2. Second author 2021. Further work.", "page_idx": 1},
    ]

    parsed = normalize_mineru_result(_result(tmp_path, items))

    assert len(parsed["references"]) == 2


def test_unnumbered_bibliography_lines_are_separate_entries(tmp_path: Path) -> None:
    items = [
        {"type": "text", "text": "A substantial source body. " * 6, "page_idx": 0},
        {"type": "text", "text_level": 1, "text": "Bibliography", "page_idx": 1},
        {"type": "text", "text": (
            "Alpha, A. 2020. A long first cited work in an academic journal.\n"
            "Beta, B. 2021. A long second cited work in another journal.\n"
            "Gamma, G. 2022. A long third cited work in a book."
        ), "page_idx": 1},
    ]

    parsed = normalize_mineru_result(_result(tmp_path, items))

    assert len(parsed["references"]) == 3
    assert parsed["references"][1]["raw_text"].startswith("Beta, B.")


def test_citation_instruction_and_disclaimer_are_back_matter(tmp_path: Path) -> None:
    items = [
        {"type": "text", "text": "A substantial source body. " * 6, "page_idx": 0},
        {"type": "text", "text_level": 1, "text": "References", "page_idx": 1},
        {"type": "text", "text": "1. Alpha, A. 2020. A cited article.", "page_idx": 1},
        {"type": "text", "text": "How to cite this article: Source details.", "page_idx": 1},
        {"type": "text", "text": "Disclaimer/Publisher's Note: The views are the authors'.",
         "page_idx": 2},
    ]

    parsed = normalize_mineru_result(_result(tmp_path, items))

    assert len(parsed["references"]) == 1
    assert any(block["section"] == "Back matter" for block in parsed["blocks"])


def test_reference_pages_align_to_physical_pdf_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    items = [
        {"type": "text", "text": "A substantial source body. " * 6, "page_idx": 0},
        {"type": "text", "text_level": 1, "text": "References", "page_idx": 1},
        {"type": "text", "text": (
            "[1] Alpha authors comparative photovoltaic deployment in rural villages. "
            "[2] Beta authors advanced battery optimization using simulated microgrids."
        ), "page_idx": 1},
    ]
    source_pages = (
        "An introduction to the research and the methods used.\f"
        "Alpha authors comparative photovoltaic deployment in rural villages.\f"
        "Beta authors advanced battery optimization using simulated microgrids.\f"
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_, **__: subprocess.CompletedProcess([], 0, stdout=source_pages.encode()),
    )

    parsed = normalize_mineru_result(
        _result(tmp_path, items), source_pdf_path=tmp_path / "source.pdf"
    )

    assert [ref["page_number"] for ref in parsed["references"]] == [2, 3]
    assert parsed["references"][1]["location"]["mineru_page_number"] == 2
    assert parsed["manifest"]["quality"]["reference_page_alignment"]["corrected"] == 1


def test_ambiguous_reference_page_is_not_claimed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    items = [
        {"type": "text", "text": "A substantial source body. " * 6, "page_idx": 0},
        {"type": "text", "text_level": 1, "text": "References", "page_idx": 1},
        {"type": "text", "text": "[1] Alpha authors comparative photovoltaic deployment in rural villages.",
         "page_idx": 1},
    ]
    repeated = "Alpha authors comparative photovoltaic deployment in rural villages."
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_, **__: subprocess.CompletedProcess(
            [], 0, stdout=f"Body.\f{repeated}\f{repeated}\f".encode()
        ),
    )

    parsed = normalize_mineru_result(
        _result(tmp_path, items), source_pdf_path=tmp_path / "source.pdf"
    )

    assert parsed["references"][0]["page_number"] is None
    assert parsed["manifest"]["quality"]["reference_page_alignment"]["ambiguous"] == 1


def test_tables_equations_and_figure_captions_remain_document_blocks(tmp_path: Path) -> None:
    items = [
        {"type": "text", "text": "The paper reports detailed findings. " * 5,
         "page_idx": 0},
        {"type": "table", "table_caption": ["Table 1. Generation"],
         "table_body": "<table><tr><td>Solar</td><td>244</td></tr></table>",
         "page_idx": 1},
        {"type": "equation", "text": "$$ E = mc^2 $$", "page_idx": 1},
        {"type": "image", "img_caption": ["Figure 1. System diagram"],
         "img_path": "images/figure1.jpg", "page_idx": 2},
    ]

    parsed = normalize_mineru_result(_result(tmp_path, items))

    assert [block["block_type"] for block in parsed["blocks"]] == [
        "TEXT", "TABLE_HTML", "EQUATION_LATEX", "FIGURE_CAPTION",
    ]
    assert "Solar" in parsed["blocks"][1]["text"]
    assert parsed["blocks"][1]["page_number"] == 2
    assert parsed["blocks"][3]["location"]["artifact_image_path"] == "images/figure1.jpg"
    assert parsed["manifest"]["quality"]["table_blocks"] == 1


def test_source_numbered_reference_gap_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    items = [
        {"type": "text", "text": "A substantial source body. " * 6, "page_idx": 0},
        {"type": "text", "text_level": 1, "text": "References", "page_idx": 1},
        {"type": "text", "text": " ".join(
            f"[{number}] Author {number}. A detailed renewable energy research paper."
            for number in (1, 2, 3, 4, 6, 7)
        ), "page_idx": 1},
    ]
    source = "Body.\fReferences\n" + "\n".join(
        f"[{number}] Author {number}. A detailed renewable energy research paper."
        for number in range(1, 8)
    ) + "\f"
    monkeypatch.setattr(
        subprocess, "run",
        lambda argv, **__: subprocess.CompletedProcess(
            [], 0,
            stdout=(source.split("\f", 1)[1] if "-f" in argv else source).encode(),
        ),
    )

    parsed = normalize_mineru_result(
        _result(tmp_path, items), source_pdf_path=tmp_path / "source.pdf"
    )

    assert parsed["manifest"]["quality"]["reference_page_alignment"][
        "missing_source_numbered_references"
    ] == [5]


def test_mineru_retries_use_fresh_output_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RSTV4_MINERU_ARTIFACT_ROOT", str(tmp_path / "m"))
    parser = MinerUParser(tmp_path)
    monkeypatch.setattr(parser, "check", lambda: {"available": True})
    source_pdf = tmp_path / "a very long source title.pdf"
    source_pdf.write_bytes(b"%PDF-1.4\nsource identity\n%%EOF")
    outputs: list[Path] = []
    staged_sources: list[Path] = []
    stages: list[str] = []

    def fake_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        output = Path(argv[argv.index("--output") + 1])
        staged_source = Path(argv[argv.index("--pdf") + 1])
        outputs.append(output)
        staged_sources.append(staged_source)
        stage = argv[argv.index("--stage") + 1]
        stages.append(stage)
        assert staged_source.name == "source.pdf"
        assert staged_source.read_bytes() == source_pdf.read_bytes()
        assert len(str(output / "source" / "images" / ("f" * 64 + ".jpg"))) < 240
        output.mkdir(parents=True, exist_ok=True)
        if stage == "analyze":
            (output / "model.json").write_text("[]", encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, stdout=str(output / "model.json") + "\n")
        assert (output / "model.json").is_file()
        manifest = output / "rstv4-parse-result.json"
        data = _result(
            output,
            [{"type": "text", "text": "A complete source paragraph. " * 5,
              "page_idx": 0}],
        )
        manifest.write_text(json.dumps(data), encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, stdout=str(manifest) + "\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    first = parser.parse(source_pdf, tmp_path / "deep" / "parse")
    parser.parse(source_pdf, tmp_path / "deep" / "parse")

    assert stages == ["analyze", "materialize", "analyze", "materialize"]
    assert outputs[0] == outputs[1]
    assert outputs[0] != outputs[2]
    assert all(path.parent.parent == parser.artifact_root for path in outputs)
    assert all(not source.exists() for source in staged_sources)
    assert first["manifest"]["source_pdf_path"] == str(source_pdf.resolve())


def test_mineru_analysis_crash_stops_before_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RSTV4_MINERU_ARTIFACT_ROOT", str(tmp_path / "m"))
    parser = MinerUParser(tmp_path)
    monkeypatch.setattr(parser, "check", lambda: {"available": True})
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    stages: list[str] = []
    staged_paths: list[Path] = []

    def crash(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        stages.append(argv[argv.index("--stage") + 1])
        staged_paths.append(Path(argv[argv.index("--pdf") + 1]))
        return subprocess.CompletedProcess(argv, 3221225477, stderr="c10.dll access violation")

    monkeypatch.setattr(subprocess, "run", crash)
    with pytest.raises(RuntimeError, match="MinerU analyze exited with code 3221225477"):
        parser.parse(pdf, tmp_path / "requested")

    assert stages == ["analyze"]
    assert all(not path.exists() for path in staged_paths)
