# Publication chain review v3 — resolved

Final read-only follow-up: the remaining frontend scientific-review consistency finding from v2 is resolved.

- The actual ReadingView call now receives stale={workspace.generated_is_stale || Boolean(workspace.manuscript.needs_scientific_review)}. Therefore a retained legacy generated version with no saved scientific stamp still passes a hold when pending scientific review is set.
- Manuscript types accept the actual boolean/0/1 flag shape. The shipped component test extracts the real parent expression and checks both true and1 hold values, while a separate existing ReadingView component check verifies stale=true disables publication. Existing SubmissionPanel stale=true coverage also verifies archive completion disabled. The parent reports eight component checks PASS; this review read their current source and did not rerun them.
- STALE completion now reads “历史归档 · 需要重新核对”, avoiding the incorrect assertion that the version itself necessarily changed after withdrawal/scientific hold.

The two backend v1 findings were resolved in v2. No remaining actionable issue from those three findings was found in the current reviewed files. This is not complete WF10/native/original118/final11/scientific acceptance. Prior reviews remain preserved.

No test, model, DB, UI, service or shared session operation was performed. Only this new report was written.

Current SHA256:

- studio-workspace.tsx: 4aebf157c44544a9528f44cd30739221a86d417ba08a84e605c222678f08e42c
- studio-types.ts: c01b0c0e177a0e15579654fd8b788dd6538e4d28b57980e9f06076f4265111d8
- studio-submission-publication.mjs: a624596c83ae66a3d42b1f5d03b50940d60f79f3162831dd75fc6c7cf9db2a76
