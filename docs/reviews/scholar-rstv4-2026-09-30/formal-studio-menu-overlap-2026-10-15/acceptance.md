# Studio menu overlap — repaired and natively verified

The previous actual menu placed Move and Delete at the same absolute coordinates.
Read-only DOM hit testing proved the Move center hit Delete, and two unintended
software-only deletions were natively undone. The two-file repair now places each
menu's actions in one positioned grid and makes buttons ordinary grid children.
Move/Delete handlers, object identities and author persistence rules are unchanged.
All five menu kinds are covered: Thought, Intent, Paragraph, Section and Group.

One real new Vinext production build succeeded in14.34seconds with a512MiB Node
limit and one worker thread. The prior source/build was preserved. Exactly two of
91 frontend files changed; the other89 and all311 backend files stayed byte-exact.
Git preserved Windows CRLF while the candidate uses LF: both raw hashes and the
exact declared byte transformation are retained. The initial SHA and path-classifier
audit failures are kept; no patch or successful build was replayed for receipts.

Native geometric tests passed for all five kinds at measured1280px and760px widths:
each action had positive bounds, action rectangles did not overlap, and the center
hit the intended button. Pointer Move opened the actual move-selection dialog and
cancelled without changing any of110 tables. An earlier viewport-override attempt
left innerWidth1280; those five extra observations are explicitly not counted as
narrow tests. The supported tab developer viewport then measured760, and all five
cases were rerun. Both overrides were cleared; measured width returned1280.

An explicit pointer Delete removed only the declared fictional slot2 paragraph at
author81→82. Native Undo restored the entire author document exactly at83. Only five
declared author/history tables changed. All generated versions, calls, jobs,
artifacts, checks and source/material records stayed exact. Keyboard Enter still
opens the same Move dialog. No models, new generated versions or workers ran.

Eight existing frontend suites passed: block-controls, blocks, structure, hierarchy,
undo-history, template-placement, correspondence and response-review. No new tests
that merely mirror JSX wrappers were added. The unchanged backend1130-test result
was retained rather than rerun for this frontend-only fix. Full final same-source11
acceptance remains required after the remaining product work.

The new build reused the preserved complex fixture at v6/author81; after the
reversible delete/Undo it is author83 with identical author content. Existing A212
check remains STALE because generated input is79. No gate or scientific approval
was advanced. Exact owned services were stopped, ports8877/58989 released, roots
retained. User8891 and original Studio/GPU/QuickRead services were untouched.

This report closes the observed menu-overlap defect only. Pure layout generation,
typed positive structure/source/material attribution, reverse Thought/Intent
navigation and the full original118/final11 workflow remain incomplete.
