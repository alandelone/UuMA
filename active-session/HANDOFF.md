# Session Handoff

## Current position

# Session Handoff

## Current position

2026-10-22 read-only Telegram Brainstormer and Observatory architecture review. Mission remains verification with stage-gates/04-verification-report.md pending_review; no gate transition. Traced owner-authorized Telegram DM through uuma_brainstormer_commands, loopback /api/v1/navigation, BrainstormerNavigation, and BrainstormerStore. Canonical project/topic/question/assumption/evidence/decision/checkpoint graph lives in Brainstormer project state JSON; navigation binding and transport receipts use the deployment-configured navigation database. Observatory reads the canonical graph read-only but presents separate aggregate/topic/item views. Existing question DAG, subquestions, dependencies, readiness/blocking, assumptions, evidence, decisions and checkpoints are available. Telegram currently lists and switches topics, while /brainstorm prints a shallow summary from raw objects: at most five titles per category, 3500-character truncation, no issue-tree/detail navigation, and it ignores returned decision_map readiness/tree data. The pause phrases display the latest saved checkpoint; they do not create a dedicated user-summary checkpoint. The decision summary filter should be reviewed because it labels non-rejected and non-superseded decision objects as confirmed without checking an approved status. Recommendations are to retain /topics for top-level topic selection, expose issue-tree and detail navigation, surface ready/blocked counts and evidence links, provide explicit checkpoint saving, and separate proposed from approved decisions. No implementation or tests were run. The existing dirty worktree and unrelated user changes were preserved.

## Previous handoff preserved verbatim

# Session Handoff

## Current position

Reviewed the current Wisdom-Oldman design and implementation: documented sufficiency criteria, the four search tiers and providers, durable Orbit polling, knowledge ingestion/projection, and answer generation. Found that KAG bridge responses omit satisfaction_level, while the adapter defaults it to PROVISIONAL and OrbitRunner's satisfaction assessor passes it through.

## Known dead ends

No code changes or tests were needed. CodeGraph was exhausted after two calls; the remaining uncovered code paths were checked with session-wrapped source reads.

## Next action

Provide the user a Chinese architecture explanation, distinguish policy from implemented stop scoring, explain the async background search loop and clarify that 'Delicious' is not a configured provider; it may mean ChatGPT Deep Research.


## Known dead ends

None observed. No production topic contents, live Telegram conversation, or active topic binding was inspected; findings are from current source and repository docs.

## Next action

Present the architecture and prioritized Telegram UX proposal to the user; wait for their chosen scope before implementing changes.


## Request continued on 2026-10-22

The user is validating Scholar Bot and RSTV4 and asked to recover prior requests, map the live architecture, and proceed through these checks: Catalog search and download of one paper; related-paper discovery through DOI/VIA and references toward main-line papers; the Research Overview real Field/Topic/Track and remembered facet; paper-to-KAG/FieldKG map and the paper-to-Skeleton transformation; Writing Studio Track/Paper creation, the intended dropdown or draft-generation action, and adding figures and tables. Treat “VIA” and “drop down” as user wording that may need later clarification; current working interpretation is DOI/reference discovery and producing a draft.

The pre-task handoff now being preserved contains the 2026-10-22 Telegram Brainstormer/Observatory architecture review and embeds an earlier Wisdom-Oldman review. Preserve that full current handoff verbatim above this continuation; it includes the Wisdom search tiers/providers, Orbit polling, ingestion/projection, answer generation, satisfaction_level default, and the “Delicious” provider clarification.

## Live architecture and verification evidence

- Live Scholar Catalog is at `http://127.0.0.1:8875`. Its Research Overview API returns empty real fields, topics, field-topic links, tracks, questions, manuscripts, collections, and jobs. The visible Solar Energy/Solar Nowcasting tree is explicitly labeled a layout demo and is not written to Catalog. FieldKG map view says no Field. Catalog Filter is a separate paper metadata/status rule builder; it is not a populated Research Overview topic facet.
- Live Catalog local title filter successfully found exactly one paper: “Reliability Predictors for Solar Irradiance Satellite-Based Forecast”, DOI `10.3390/en13215566`. The live API summary is 1,197 visible papers; a prior raw-table count was 3,177. Current list SQL excludes quarantined rows, likely explaining the difference; exact quarantine count was not established.
- Live Collection Start is disabled until a real Topic/Track is selected. The Collection backend also requires a real Field ID. No real Field/Topic/Track currently exists, so no main-Catalog collection or download was started and no placeholder research hierarchy was created.
- Completed a real single-paper download and Catalog registration in a separate ignored scratch root only: `.uuma-local/scholar-single-paper-download-20261022/`. It used DOI resolution through the worker, then downloaded the publisher PDF from MDPI’s `mdpi-res.com` PDF CDN, registered it through `AcquisitionService.register_pdf`, and queried `/api/catalog/papers/query` with `TestClient`. Result: 29,709,412 bytes; SHA-256 `f5be8962c3babd251305af40c8f15f492df65d02da8573afb24d31f459bbb2d2`; identity status `VERIFIED`; search total 1; search PDF status `VERIFIED`. Evidence summary is `.uuma-local/scholar-single-paper-download-20261022/result.json`; source PDF and scripts remain in that isolated ignored directory. Main Catalog was untouched.
- Automated Unpaywall discovery was not verified: neither `UNPAYWALL_EMAIL` nor `CROSSREF_EMAIL` is configured. The canonical `www.mdpi.com/.../pdf` endpoint returned HTTP 403; the publisher CDN URL returned HTTP 200 with a valid PDF. The scratch test therefore verifies DOI metadata resolution, publisher PDF download, identity verification/registration, and Catalog search, but does not prove the Unpaywall auto-locate step or the live main-Catalog UI end to end.
- Collection seed entry points in code: DOI, BibTeX, query terms, and selecting existing Catalog papers. Local PDF-directory import is a separate service path. Query-term search fans out to Crossref, OpenAlex, Semantic Scholar, arXiv, Europe PMC, DataCite, and OpenAIRE. DOI metadata resolution order is Crossref, DataCite, OpenAlex, then OpenAIRE. PDF acquisition supports verified registered-PDF reuse, Unpaywall OA lookup/download (plus configured command adapters), and browser-assisted publisher handoff; local PDF import is a separate route. Parsed references resolve by DOI when present; DOI-less references use strict Crossref bibliographic matching and bounded OpenAIRE/OpenAlex fallback. Current evidence does not show forward-citation search or ranking/selecting “main-line/seminal” papers.
- The FieldKG used by Scholar is separate from the healthy Wisdom KAG at port 8891. RSTV4 defaults Scholar’s FieldKG bridge to port 8892; no active bridge was found. The local Catalog has zero FieldKG builds, snapshots, or projection outbox rows. Do not route Scholar to Wisdom KAG: project/schema are distinct.
- Intended paper-to-graph path from RSTV4 design: immutable PaperVersion → PaperSkeleton L1–L4 with source-grounded units/propositions/relations/intents/role → Evidence Candidates → human accept/reject/review → Evidence with source location/digest plus candidate gaps → sealed FieldKG snapshot version → explicit Track adoption. Current verification did not execute this path. The 2026-10-19 Flash 3.8 continuation report remains partial: 10 papers, 1,286 blocks, 126 windows; 31 windows succeeded and 95 failed. Three complete skeletons (PTHP/URB/fridge; 279 blocks) were saved through the native pipeline using cache adoption, not a successful fresh model-call rerun. No main Catalog write; the FieldKG consumer still needs the atomic L3 intent array adaptation. Full 10-paper semantic correctness and independent review were not established. Detailed report: `docs/reviews/scholar-rstv4-2026-09-30/flash38-text-to-skeleton-2026-10-19/result.md`.
- Writing Studio runs at `http://127.0.0.1:3000` and gets Tracks/manuscripts from the RSTV4 Studio API (normally port 8874). Live page shows no Tracks and 0 manuscripts; Track dropdown says create a Track in Scholar first; `＋ 新 Paper` is disabled. No manuscript exists to exercise Generate.
- Code supports a structured editor (sections, paragraph groups, paragraphs, intent/thought blocks), template sample/preview/adoption from Skeleton, `Generate` as a revision-bound durable job, generated-version reading, citations, and manuscript assets. Figure/table picker accepts PNG/JPG/JPEG/SVG/CSV/XLSX/MD; upload attaches an asset to a paragraph; generated display renders figures and table previews. These are code-path findings only; no live Studio generation or upload was run because no Track/manuscript exists.
- Existing RSTV4 and Writing Studio working-tree changes are user changes. They were preserved. No product source or main database was edited in this session.

## Next review sequence

1. Select or create the real Field/Topic/Track to use for the main Catalog single-paper run. Then repeat the exact single-paper DOI test through the live UI, observe metadata resolution, OA locate/browser fallback, PDF verification, and Catalog search.
2. Use that Track to test parsed reference expansion, resolve-by-DOI and DOI-less matching, then determine whether forward-citation/core-paper discovery exists or requires implementation.
3. With a real Field, inspect the FieldKG map API, confirm PaperVersion/Skeleton L1–L4 source links, review Evidence Candidates, and test snapshot/adoption without skipping human review. Do not connect to Wisdom KAG.
4. With a real Track, create one Writing Studio Paper, inspect Track/template dropdowns, add one figure and one table, generate a draft/version, and check citations and generated assets.
5. Keep mission stage at `verification`, gate `stage-gates/04-verification-report.md`, status `pending_review`; no gate transition was made.


## Known dead ends

The live main Catalog cannot start a collection without a real Field and Topic/Track. Unpaywall auto-location remains unverified because no contact email is configured and the canonical MDPI endpoint returned 403; a publisher CDN PDF was successfully downloaded and registered only in the isolated scratch Catalog. FieldKG bridge and Writing Studio generation remain unverified because no real Field/Track exists.

## Next action

Ask the user to select or approve a real Field/Topic/Track for the live single-paper collection run. Then continue the requested checks in order: reference expansion and core-paper discovery; FieldKG map and review/snapshot/adoption; Writing Studio Paper, figure/table upload, and Generate. Keep verification gate pending_review.
