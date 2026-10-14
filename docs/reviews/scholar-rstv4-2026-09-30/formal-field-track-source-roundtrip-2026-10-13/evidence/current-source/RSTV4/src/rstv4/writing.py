from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class OutlineSection:
    heading: str
    subheading: str | None
    points: list[str]


class OutlineParser:
    """Parses hierarchical markdown outline into structured sections and points."""

    @staticmethod
    def parse(content: str) -> list[OutlineSection]:
        main_heading_pattern = r"^###?\s+(.*?)$"
        bullet_pattern = r"^\s*[-*]\s+(.*)$"

        lines = content.splitlines()
        sections: list[OutlineSection] = []
        current_heading = "Main"
        current_subheading: str | None = None
        current_points: list[str] = []

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            heading_match = re.match(main_heading_pattern, line_str)
            if heading_match:
                if current_points:
                    sections.append(
                        OutlineSection(
                            heading=current_heading,
                            subheading=current_subheading,
                            points=current_points,
                        )
                    )
                    current_points = []
                current_heading = heading_match.group(1).strip()
                current_subheading = None
                continue

            bullet_match = re.match(bullet_pattern, line_str)
            if bullet_match:
                point_text = bullet_match.group(1).strip()
                current_points.append(point_text)

        if current_points:
            sections.append(
                OutlineSection(
                    heading=current_heading,
                    subheading=current_subheading,
                    points=current_points,
                )
            )

        return sections


class CitationVerifier:
    """Validates citation references in generated text against real evidence."""

    @staticmethod
    def verify(text: str, valid_citation_keys: set[str]) -> dict[str, Any]:
        """Finds all citations in format [@key] or [key] and checks if they exist."""
        # Find citations like [@doi:xxx] or [@paper_123] or [ev_123]
        citations_found = set(re.findall(r"\[@?([a-zA-Z0-9_:./-]+)\]", text))

        valid = citations_found.intersection(valid_citation_keys)
        invalid = citations_found - valid_citation_keys

        return {
            "all_citations": sorted(citations_found),
            "valid_citations": sorted(valid),
            "invalid_citations": sorted(invalid),
            "is_resolvable": not invalid,
        }


class ManuscriptCompiler:
    """Compiles Research Blueprint and section text into a unified manuscript."""

    @staticmethod
    def compile_markdown(
        title: str,
        abstract: str,
        sections: list[dict[str, str]],
        references: list[dict[str, Any]],
    ) -> str:
        lines: list[str] = [f"# {title}", "", "## Abstract", "", abstract.strip(), ""]

        for sec in sections:
            sec_title = sec.get("title", "Section")
            sec_content = sec.get("content", "").strip()
            lines.extend([f"## {sec_title}", "", sec_content, ""])

        if references:
            lines.extend(["## References", ""])
            for idx, ref in enumerate(references, 1):
                authors = ", ".join(ref.get("authors", [])) or "Unknown Authors"
                year = ref.get("published_year") or "n.d."
                ref_title = ref.get("title", "Untitled")
                doi = ref.get("doi")
                doi_str = f" DOI: https://doi.org/{doi}" if doi else ""
                lines.append(f"{idx}. {authors} ({year}). *{ref_title}*.{doi_str}")
            lines.append("")

        return "\n".join(lines)
