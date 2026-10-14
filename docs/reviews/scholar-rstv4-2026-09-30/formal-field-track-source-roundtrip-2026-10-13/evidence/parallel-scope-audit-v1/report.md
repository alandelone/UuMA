# G10 independent source and scope audit

Completed 2026-10-13T05:34:18.731Z. This is a read-only API and frozen-source audit, not the complete native G10 acceptance.

## Verified

- Current fixed Energy Snapshot is v1 SEALED. All snapshot fields and its whole frozen manifest match the prepared baseline exactly; digest_matches and members_match are true. Ten membership rows match the baseline.
- All seven separate semantic kinds retain every baseline record field, original reference, role, conditions and qualifications. Each current software interpretation explicitly reports scientific_approval=false.
- Two raw source units, parsed layers, original text, page 3 / Introduction / sequence 1, Paper IDs, PaperVersion IDs and Skeleton IDs match the baseline. Every referenced offset reproduces the full original quote.
- Eleven read-only discussion context requests verify the seven fixed semantic records, their exact source versions and selected snapshot digest, genuine Other metadata, explicit cross-Field rejection and independent Track scope. The route uses ResearchDiscussions.context -> _read mode=ro -> resolve_context. No message was submitted.
- Other's sources, evidence, Builds, Snapshots, candidates, semantic objects/runs, Tracks, citations, reviews and projection jobs are actually empty. Energy Snapshot ownership in Other returns 404; Energy semantic selection in Other returns 404; an unknown Snapshot returns 404.
- Track remains ACTIVE / MAPPED / revision 1, with its baseline core fields preserved. At the observed GET it lists the Energy Snapshot as available, while adoptions, adopted_snapshots, nodes and evidence remain empty. Available does not claim adopted.

## Limits and remaining coverage

- The imported legacy software fixture has null file_version_id, parse_run_id, PDF digest and parsed digest. This does not prove actual PDF parsing identity or a downloadable source PDF. Main acceptance must use other evidence for those requirements.
- Conditions and qualifications are empty arrays in this fixture. Preservation passes; nonempty-condition coverage is not proved by this run. Source raw wording “under dry conditions” remains exact.
- These are expressly software fixture interpretations, not scientific approval or judgments about the example paper.
- The parent agent owns native Field -> Snapshot -> Track -> manuscript -> source round trips, possible authorized mutations, narrow-screen checks and the final G10 completion judgment. No browser operation, writer, migration, seeding, model call, service restart, full regression or gate transition was performed here.
- Observations are timestamped per response. No whole-database unchanged claim is made during concurrent authorized parent UI actions.

## Evidence

Baseline SHA-256: 90345354d25ef34f6a73cf76e5dd5900661eedc151bfac32b960425a6732de8a.

receipt.json contains exact IDs, source hashes, route timestamps and limitations. Six GET response files and eleven context response files preserve full payloads. Four *.source.txt files preserve the inspected current source. verify.mjs independently rechecks saved evidence against the hashed baseline and has executed with PASS (7 kinds, 2 units, 6 GET responses, 11 contexts).
