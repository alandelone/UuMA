# W06 Held Jobs Triage Report (2026-11-04)

**Total Held Jobs (`NEEDS_HUMAN`):** 32  
**Database:** `C:/Users/Alandelone/CodeSpace_Local/RSTV4/data/catalog.db`  
**Inspected At:** 2026-11-04 13:53 MYT  

---

## Error Classification & Recovery Strategy

| Cluster / Error Signature | Task | Count | Priority & Strategy | Associated Work Item |
| :--- | :--- | :---: | :--- | :--- |
| **1. Dimension support state**<br>`Dimension must distinguish support, unknown and unassessed content` | `quick_read` | **10** | High value / P0. Pinned repair helpers exist in `catalog-48cece41023e`. Original 4 cases pinned; eligible for night admission or bounded recovery. | **W03** |
| **2. Theme-role quotation IDs**<br>`Synthesis evidence must identify supplied original quotations` | `initial_theme_role` | **2** | High value / P0. Exact 2 pinned cases: `catalogreadingjob_eae894b770`, `catalogreadingjob_cf93a4cfe6`. Prepared in `test_night_theme_combined_v664.py`. | **W04** |
| **3. Digest input coverage**<br>`Synthesis must cover every supplied input in order` | `initial_digest` | **2** | High value / P0. Exact 2 remaining cases: `catalogreadingjob_ea6fa5b6ee`, `catalogreadingjob_90a62402ae` (1 case already reconciled in v653). | **W05** |
| **4. Deep-read reason dimension binding**<br>`Reason must bind to a supported PaperSkeleton dimension` | `quick_read` | **4** | Requires inspecting source dimension profile binding; keep held until reviewed. | **W06 / W14** |
| **5. Synthesis dimension source observation**<br>`Dimensions must be source-backed observations` | `initial_synthesis` | **2** | Includes `fc39e8cd` (from v653) and `21ad44b4`. Contract requires source span evidence for synthesis claims. | **W06** |
| **6. Foreign / invalid selector mismatch**<br>`Source evidence refers to an unknown or foreign selector`<br>`Evidence must identify a source block and exact quotation` | `quick_read` | **3** | Parser-to-source geometry mismatch. Need exact source span validation. | **W06** |
| **7. Preview patch unverified**<br>`The patch model did not establish the original local signal` | `initial_preview_patch` | **2** | Historical preview repair was insufficient. | **W06** |
| **8. Malformed JSON / Non-object outputs**<br>`Model output is not a JSON object`<br>`Expecting property name enclosed in double quotes...` | Mixed (`quick_read`, `initial_digest`, `initial_json_recovery`) | **5** | Syntax parsing errors across model responses. Triage with json recovery parser. | **W06** |
| **9. Deep-read reason rationale completeness**<br>`Reason must explain evidence, purpose and expected additional value` | `quick_read` | **1** | Scientific rationale validation failure. | **W06 / W14** |
| **10. New dimension layer binding**<br>`New dimensions need a definition and PaperSkeleton layer bindings` | `quick_read` | **1** | Inferred dimension outside 22 standard profile layers. | **W06 / W13** |

---

## Action Plan

1. **W04 (2 cases) & W05 (2 cases)**: P0 target. Recoverable under `catalog-48cece41023e` via bounded admissions.
2. **W03 (10 cases)**: 4 pinned cases ready for night admission; expand helper to remaining 6 cases after verification.
3. **Other 16 cases**: Maintain explicit held status with accountable reasons; do not blanket-reset or let them block the 137 READY jobs.
