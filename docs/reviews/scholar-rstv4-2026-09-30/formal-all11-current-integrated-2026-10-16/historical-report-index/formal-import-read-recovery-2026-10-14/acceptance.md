# Native review import and read recovery — 2026-10-14

This continuation closes the four-format native import/readback subset and a real frontend error-state defect. **G11, the original 118 requirements, and final combined 11-group acceptance remain incomplete.** G01–G10 have separate sealed software-group evidence; that does not prove the full original requirements or scientific quality.

## Result and repair

Before the repair, a failed initial comments/rounds request left empty arrays visible as “尚未导入审稿意见” and offered “建立第1轮” even though three rounds existed. Network failure itself did not replace a backend baseline: existing server guards protect duplicate rounds and fixed versions. The precise intermittent IAB transport cause remains unproved.

The workspace now distinguishes loading, failed, and confirmed reads. It retains last-read rows, selected round, local import draft and edited preview; labels stale data; hides the false empty statement; and provides “重新读取意见与轮次”. Creation and import confirmation require a confirmed read, including handler guards. Only the latest request may commit results. Successful create/import acknowledgments survive failed subsequent reads, so retry performs GET rather than repeating a saved operation. Existing source/history content and pending local previews are retained.

## Actual native acceptance

The owned copy `scui-native-import-n01cagy6` retains the original manuscript v5 / author r62. Native round3 explicitly fixes v5/r62. TXT (UTF-8 BOM), Markdown, DOCX and text PDF were chosen through the actual browser file chooser and explicitly confirmed once: A207–A210. TXT preview preserved a paragraph's internal line break, edited only the first item, excluded the second, and was first cancelled. Cancellation preserved all109 tables exactly; reselecting the same file restored the original preview. Four persisted cards retain separate original/edited text, filenames, batch IDs, original positions and full extracted import text, including the unselected TXT item. No manuscript location or change link was guessed.

After the repair, native reload displays the actual three rounds and A207–A210. Each original-source card was expanded and read back. A controlled tab-scoped network block then failed a warm refresh: actual old data and the two-item local preview remained, with explicit error and disabled confirmation. Removing the temporary block and pressing the retry recovered the same data and preview with four GET requests, zero POST requests. The temporary block was cleared in `finally`; no browser setting remains changed. The throwaway local preview was cancelled without import. See `proof/14-*`, `15-*`, `16-*`.

Independent data audit preserves all206 prior comment rows byte-for-byte as serialized fields, both prior rounds/baselines, versions, jobs, model records, source/response/change histories and schema. Exactly four comment rows and one round/baseline were appended. Four pre-existing paper sample cache entries refreshed document_revision39→62 and created_at only; candidate IDs/query/sample_json and the other16 cache rows remain exact. These are disclosed derived-cache updates, not changes to author/source/history data. Original G09 source files and database SHA remain exact.

## Verification

- Isolated production build passed; original source tree and dist remained unchanged during building. Source and compiled files are separately hashed.
- Scoped frontend lint and three existing import-preview unit cases passed.
- Eight browser regression cases passed: separate cold comments/rounds failures, genuine empty reads, warm failure retaining edited preview, saved create/import followed by failed reload, and late old empty/error results. Every API route was mocked, so these tests created no real collection, import, model or database mutation.
- First regression run retained six strict-locator failures: identical text occurs in the visible edited paragraph and collapsed original provenance. Assertions were scoped to the unique semantic opinion article's edited paragraph; no behavior assertion was removed. The original failing run and traces remain in the evidence.
- Twenty-five actual backend round/baseline/import contract tests passed in36.13s. The historical1078-test suite predates these latest changes; final current-source combined regression is still required.

## BibTeX subset and outstanding work

From the real Writing Track scope, the actual file chooser read the sealed324-byte `references.bib` locally. The textbox contains the exact text apart from native CRLF→LF textarea normalization; it reports two entries/one DOI and explicitly says the file was not uploaded. Network observation proves no POST on selection. Choosing an actual5,000,001-byte file rejected it without replacing the prior input or uploading data. “检查输入” sent only the declared JSON preview request, reported one existing paper/one reusable PDF, and created no Collection or task. All109 database tables/schema/rows stayed exact. **AC03 slow-read/stale-read behavior is still unverified; AC03 is not marked complete.**

GPU attempts3/4/5 are terminal failures with no published parse; the CPU retry has never run. Latest read-only `nvidia-smi` returned255, “Failed to initialize NVML: Unknown Error”. Windows device enumeration separately reports RTX4070Ti StatusOK/error0. Those observations do not establish why CUDA/NVML is unhealthy. Commit pressure has improved from the prior failure context but current full GPU success is unproved. No driver/global config/security/pagefile change, unrelated process kill, model replay or attempt6 was performed. Keep G11 parser recovery, the remaining original118 items, and the actual final11-group flow open.

The shared mission remains verification/pending_review. Prior HONC/scientific history and failures are preserved. No external scientific approval, publication, messages or gate transition occurred.
