"""Bounded, source-linked synthesis after KAG graph retrieval."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import defaultdict
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .kag_adapter import OpenSpgKagBackend
from .knowledge_models import (
    AnswerCitation,
    KnowledgeAnswer,
    ReasoningMode,
    ReasoningStep,
    ReasoningTraceRecord,
    SatisfactionLevel,
)
from .knowledge_service import KnowledgeService
from .orbit_discovery import DiscoveryArtifact, artifact_is_relevant, artifact_priority

LOGGER = logging.getLogger(__name__)


class OrbitCompactSynthesizer:
    """Use KAG retrieval, then synthesize only from bounded canonical source excerpts."""

    @staticmethod
    def _answer_focus_terms(question: str) -> tuple[str, ...]:
        if any(term in question for term in ("缓苗", "成活率", "病害管理")):
            return (
                "缓苗", "移栽", "成活", "病害", "恢复", "定植", "伤根", "分株后",
                "transplant", "survival", "establishment", "disease", "recovery",
            )
        if any(term in question for term in ("喷雾间隔", "喷头", "雾化间隔")):
            return ("喷雾", "喷头", "喷嘴", "雾化", "营养液", "参数", "misting", "nozzle")
        return ()

    def __init__(self, knowledge: KnowledgeService, backend: OpenSpgKagBackend) -> None:
        self.knowledge = knowledge
        self.backend = backend

    def answer(self, question: str, **kwargs: Any) -> dict[str, Any]:
        response = self.backend.retrieve_context(question)
        refs = {str(ref) for ref in response.get("result_refs") or []}
        snippets = self._snippets(question, refs)
        watermark = int(self.knowledge.projection_health()["watermark"])
        trace = ReasoningTraceRecord(
            question=question,
            requested_mode=kwargs.get("requested_mode", ReasoningMode.SIMPLE),
            selected_mode=ReasoningMode.SIMPLE,
            steps=[ReasoningStep(
                step=1, operator="SEMANTIC", query=question,
                result_refs=sorted(refs),
                summary="OpenSPG KAG graph/vector retrieval; source-linked compact synthesis.",
            )],
            projection_watermark=watermark,
            degraded=False,
        )
        self.knowledge.record_reasoning_trace(trace, actor_id=kwargs.get("actor_id", "wisdom-oldman"))
        if not snippets:
            return KnowledgeAnswer(
                answer="目前没有直接相关、可追溯的证据足以回答这个问题。",
                satisfaction_level=SatisfactionLevel.INSUFFICIENT,
                satisfaction_rationale="Graph retrieval found no suitable canonical source excerpt.",
                reasoning_trace_id=trace.reasoning_trace_id,
                selected_mode=ReasoningMode.SIMPLE,
                runtime_status="KAG",
                projection_watermark=watermark,
            ).model_dump(mode="json")

        try:
            points = self._generate(question, snippets)
        except (ValueError, RuntimeError) as exc:
            LOGGER.warning(
                "Synthesis model generation failed for question %r (%s); treating as insufficient evidence",
                question,
                exc,
            )
            points = []
        by_key = {item["key"]: item for item in snippets}
        paragraphs: list[str] = []
        citations: dict[str, AnswerCitation] = {}
        for point in points[:12]:
            if not isinstance(point, dict):
                continue
            text = str(point.get("text") or "").strip()[:1200]
            keys = [key for key in point.get("sources", []) if key in by_key]
            if not text or not keys:
                continue
            focus_terms = self._answer_focus_terms(question)
            if focus_terms and not any(term in text.casefold() for term in focus_terms):
                continue
            if any(term in question for term in ("喷雾间隔", "喷头", "雾化间隔")) and not any(
                term in text.casefold() for term in ("气雾", "雾培", "气培", "fogoponic", "aeroponic")
            ):
                continue
            certainty = str(point.get("certainty") or "evidence").casefold()
            prefix = "暂定解释：" if certainty == "inference" else ""
            links = []
            for key in dict.fromkeys(keys):
                item = by_key[key]
                citation = AnswerCitation(
                    source_id=item["source_id"], document_id=item["document_id"],
                    chunk_id=item["chunk_id"], locator=item["locator"],
                    location=item["location"],
                )
                citations[item["chunk_id"]] = citation
                locator = item["locator"]
                page = re.search(r"\bpages? (\d+)\b", item["location"])
                if page and item["media_type"] == "application/pdf":
                    locator += f"#page={page.group(1)}"
                links.append(f"[{key}]({locator})")
            paragraphs.append(f"{prefix}{text} {' '.join(links)}")
        if not paragraphs:
            return KnowledgeAnswer(
                answer="已检索的摘录尚不足以形成可核查的直接回答。",
                satisfaction_level=SatisfactionLevel.INSUFFICIENT,
                satisfaction_rationale="The model returned no source-linked points.",
                reasoning_trace_id=trace.reasoning_trace_id,
                selected_mode=ReasoningMode.SIMPLE,
                runtime_status="KAG",
                projection_watermark=watermark,
            ).model_dump(mode="json")
        answer = "\n\n".join(paragraphs)
        return KnowledgeAnswer(
            answer=answer,
            citations=list(citations.values()),
            conditions=[
                "结论仅适用于引文明确描述的品种、环境和栽培系统；未验证参数不可直接套用，候选知识仍待审核。"
            ],
            satisfaction_level=SatisfactionLevel.PROVISIONAL,
            satisfaction_rationale=(
                "KAG located canonical records; each published point names an allowed source excerpt."
            ),
            reasoning_trace_id=trace.reasoning_trace_id,
            selected_mode=ReasoningMode.SIMPLE,
            runtime_status="KAG",
            projection_watermark=watermark,
        ).model_dump(mode="json")

    def _snippets(self, question: str, graph_refs: set[str]) -> list[dict[str, str]]:
        sources = self.knowledge.list_records("source", limit=500)["records"]
        documents = self.knowledge.list_records("document", limit=1000)["records"]
        chunks = self.knowledge.list_records("chunk", limit=5000)["records"]
        latest = {}
        for document in documents:
            source_id = document["source_id"]
            if source_id not in latest or document["version"] > latest[source_id]["version"]:
                latest[source_id] = document
        by_document: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for chunk in chunks:
            by_document[chunk["document_id"]].append(chunk)
        ranked = []
        crop_terms = (
            "青葱", "香葱", "小葱", "scallion", "green onion", "bunching onion",
            "welsh onion", "allium fistulosum", "onions, green bunching",
        ) if any(name in question for name in ("青葱", "香葱", "小葱")) else ()
        for source in sources:
            source_id = source["source_id"]
            document = latest.get(source_id)
            artifact = DiscoveryArtifact(
                locator=source["locator"], title=source["title"], provider="canonical",
                snippet=" ".join(
                    chunk["text"][:500]
                    for chunk in by_document.get(document["document_id"], [])[:8]
                ) if document else "",
            )
            if not document or not artifact_is_relevant(question, artifact):
                continue
            if crop_terms and not any(term in source["title"].casefold() for term in crop_terms):
                continue
            host = urlparse(source["locator"]).hostname or ""
            if host.endswith(("douban.com", "reddit.com", "quora.com", "zhihu.com")):
                continue
            authority = 3 if host.endswith((".edu", ".gov", ".edu.cn", ".gov.cn")) else 0
            if "journal" in host or "scientiae" in host:
                authority += 2
            if host.endswith("douban.com"):
                authority -= 4
            ranked.append((artifact_priority(question, artifact) + authority, source, document))
        ranked.sort(key=lambda row: row[0], reverse=True)

        chosen: list[dict[str, str]] = []
        for _, source, document in ranked[:6]:
            candidates = by_document.get(document["document_id"], [])
            candidates.sort(key=lambda chunk: (
                int(chunk["chunk_id"] in graph_refs) * 5
                + int(chunk["ordinal"] < 4) * 2
                + sum(term in chunk["text"].casefold() for term in (
                    "scallion", "green onion", "allium fistulosum", "青葱", "分株", "气雾",
                    "fogoponic", "aeroponic", "tillering", "results", "conclusion",
                )),
                -int(chunk["ordinal"]),
            ), reverse=True)
            selected = []
            seen_pages: set[int] = set()
            for chunk in candidates:
                page = re.search(r"\bpages? (\d+)\b", chunk.get("location") or "")
                page_number = int(page.group(1)) if page else None
                if page_number is not None and page_number in seen_pages:
                    continue
                selected.append(chunk)
                if page_number is not None:
                    seen_pages.add(page_number)
                if len(selected) >= 4:
                    break
            if len(selected) < 4:
                selected.extend(chunk for chunk in candidates if chunk not in selected)
            for chunk in selected[:4]:
                location = chunk.get("location") or ""
                metadata = source.get("metadata") or {}
                if metadata.get("not_full_text") and metadata.get("source_location"):
                    location = (
                        f"{metadata['source_location']} (verified abstract paraphrase); "
                        f"{location}"
                    )
                chosen.append({
                    "key": f"S{len(chosen) + 1}",
                    "source_id": source["source_id"],
                    "document_id": document["document_id"],
                    "chunk_id": chunk["chunk_id"],
                    "title": source["title"],
                    "locator": source["locator"],
                    "location": location,
                    "media_type": document.get("media_type") or "",
                    "text": chunk["text"][:1100],
                })
                if len(chosen) >= 12:
                    return chosen
        return chosen

    @staticmethod
    def _parse_synthesis_points(content: str) -> list[dict[str, Any]] | None:
        if not content or not content.strip():
            return None
        cleaned = content.strip()
        if "```" in cleaned:
            m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
            if m:
                cleaned = m.group(1).strip()
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start >= 0 and end > start:
            candidate = cleaned[start:end + 1]
            for attempt_cand in (
                candidate,
                re.sub(r",\s*([}\]])", r"\1", candidate),
                re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", candidate),
            ):
                try:
                    data = json.loads(attempt_cand, strict=False)
                    if isinstance(data, dict):
                        pts = data.get("points")
                        if isinstance(pts, list):
                            if not pts:
                                return []
                            valid = [p for p in pts if isinstance(p, dict)]
                            if valid:
                                return valid
                        if (
                            data.get("evidence_gap")
                            or data.get("gap")
                            or data.get("evidence_gaps")
                        ):
                            return []
                except (json.JSONDecodeError, ValueError):
                    continue
        points: list[dict[str, Any]] = []
        pat1 = re.compile(
            r'\{\s*"text"\s*:\s*"(?P<text>[\s\S]*?)"\s*,\s*"sources"\s*:\s*\[(?P<sources>[\s\S]*?)\]'
            r'(?:\s*,\s*"certainty"\s*:\s*"(?P<certainty>[\s\S]*?)")?\s*\}'
        )
        for m in pat1.finditer(cleaned):
            t = m.group("text").replace('\\"', '"').strip()
            srcs = [
                s.strip().strip('"\'')
                for s in m.group("sources").split(",")
                if s.strip().strip('"\'')
            ]
            cert = (m.group("certainty") or "evidence").strip()
            if t and srcs:
                points.append({"text": t, "sources": srcs, "certainty": cert})
        if points:
            return points
        pat2 = re.compile(
            r'\{\s*"sources"\s*:\s*\[(?P<sources>[\s\S]*?)\]\s*,\s*"text"\s*:\s*"(?P<text>[\s\S]*?)"'
            r'(?:\s*,\s*"certainty"\s*:\s*"(?P<certainty>[\s\S]*?)")?\s*\}'
        )
        for m in pat2.finditer(cleaned):
            t = m.group("text").replace('\\"', '"').strip()
            srcs = [
                s.strip().strip('"\'')
                for s in m.group("sources").split(",")
                if s.strip().strip('"\'')
            ]
            cert = (m.group("certainty") or "evidence").strip()
            if t and srcs:
                points.append({"text": t, "sources": srcs, "certainty": cert})
        if points:
            return points
        return None

    @staticmethod
    def _generate(question: str, snippets: list[dict[str, str]]) -> list[dict[str, Any]]:
        base_url = os.environ.get("OPENAI_BASE_URL", "").rstrip("/")
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
        primary_model = os.environ.get("UUMA_KAG_LLM_MODEL")
        if not base_url or not api_key or not primary_model:
            raise RuntimeError("Compact research synthesis model is not configured.")
        fallback_model = os.environ.get("UUMA_KAG_LLM_FALLBACK_MODEL") or "gemini-3.8-flash"
        last_failure = "invalid JSON"
        timeout = int(os.environ.get("UUMA_SYNTHESIS_TIMEOUT", "240"))
        max_attempts = max(2, int(os.environ.get("UUMA_SYNTHESIS_ATTEMPTS", "3")))
        compact_plan = [False] + [True] * (max_attempts - 1)
        for attempt_idx, compact in enumerate(compact_plan):
            selected = snippets[:6] if compact else snippets
            context = "\n\n".join(
                f"{item['key']} | {item['title']} | {item['location']}\n{item['text']}"
                for item in selected
            )
            limit = 5 if compact else 8
            prompt = (
                f"Return a JSON object with at most {limit} concise, sourced research points "
                "that directly answer the exact question, not adjacent topics. "
                "Every points[].text MUST be fluent Simplified Chinese. "
                "Use only the excerpts. Distinguish direct evidence from an inference, preserve "
                "species and cultivation-system conditions, and do not invent equipment settings. "
                "If the excerpts do not answer the requested parameter, duration, survival, or "
                "disease question, state that specific evidence gap instead of listing general "
                "growth or cultivation findings. "
                "Never claim the entire literature lacks a fact just because these excerpts omit it; "
                "say 'the reviewed sources/abstract do not specify it'. "
                "Do not say an abstract explicitly states that a parameter is absent; omission "
                "from an excerpt is not an explicit claim in the original source. "
                "Schema: {\"points\":[{\"text\":\"one finding under 180 Chinese characters\","
                "\"sources\":[\"S1\"],\"certainty\":\"evidence\"}]}. "
                "Every point must cite an excerpt key. Use certainty=inference only for a "
                "clearly labelled inference. Output nothing outside JSON. "
                f"Question: {question}\n\nExcerpts:\n{context}"
            )
            current_model = (
                fallback_model
                if (attempt_idx == len(compact_plan) - 1 and primary_model != fallback_model)
                else primary_model
            )
            payload: dict[str, Any] = {
                "model": current_model,
                "messages": [
                    {"role": "system", "content": "你是中文研究写作者。只输出合法 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
                "max_tokens": 3000 if compact else 3600,
            }
            request = Request(
                base_url + "/chat/completions",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Authorization": "Bearer " + api_key,
                    "Content-Type": "application/json",
                    "X-Hermes-Agent": "wisdom-oldman",
                },
            )
            try:
                with urlopen(request, timeout=timeout) as response:
                    result = json.load(response)
            except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                last_failure = type(exc).__name__
                time.sleep(1)
                continue
            raw_content = result["choices"][0]["message"].get("content") or ""
            content = (
                "".join(
                    str(part.get("text") or "") if isinstance(part, dict) else str(part)
                    for part in raw_content
                )
                if isinstance(raw_content, list) else str(raw_content)
            )
            points = OrbitCompactSynthesizer._parse_synthesis_points(content)
            if points is not None:
                return points
            last_failure = "malformed JSON or missing source-linked points"
        raise ValueError(
            f"The synthesis model did not return source-linked JSON after "
            f"{len(compact_plan)} attempts: {last_failure}."
        )
