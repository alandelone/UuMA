from __future__ import annotations

import os
import uuid
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


class GrobidReferenceParser:
    """Optional isolated GROBID fallback used only for reference extraction."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.environ.get("GROBID_URL") or "").rstrip("/")

    @property
    def available(self) -> bool:
        return bool(self.base_url)

    def extract(self, pdf: str | Path, *, timeout_seconds: int = 300) -> list[dict[str, Any]]:
        if not self.available:
            return []
        boundary = f"rstv4-{uuid.uuid4().hex}"
        content = Path(pdf).read_bytes()
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="input"; filename="paper.pdf"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        request = urllib.request.Request(
            f"{self.base_url}/api/processReferences",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            root = ET.fromstring(response.read())
        references = []
        for index, node in enumerate(root.findall(".//{*}biblStruct")):
            text = " ".join(" ".join(node.itertext()).split())
            doi_node = node.find(".//{*}idno[@type='DOI']")
            if text:
                references.append(
                    {
                        "raw_text": text,
                        "doi": (
                            doi_node.text.strip()
                            if doi_node is not None and doi_node.text
                            else None
                        ),
                        "location": {"source": "grobid", "index": index},
                    }
                )
        return references
