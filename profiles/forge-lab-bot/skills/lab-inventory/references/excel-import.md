# Excel inventory and order-history import

First classify the workbook. A physical-count workbook can seed inventory after review. A purchase
or marketplace-order workbook is procurement evidence only and must not seed stock.

## Order-history workbook

1. Call `inventory_preview_or_import_order_workbook` with `commit=false`.
2. Show status/category filters, closed-row exclusions, listing-unit quantities, unresolved identities,
   and the workbook hash. Never sum repeated order-level paid amounts per line.
3. Commit the purchase-history staging only after approval. This writes no inventory events and
   changes no balance.
4. Use `inventory_list_purchase_history` and eSchematic search to review identities. Attach an ID with
   `inventory_resolve_purchase_history_line` only after it exists in the configured catalog.
5. Treat package descriptions such as `100个` as a conversion review. `商品数量 = 1` means one
   purchased listing unit until the user confirms the contained unit count.
6. Receive only a physically counted and inspected quantity into a known location.

## Physical-count workbook

1. Inspect sheet names, headers, formulas, merged cells, units, duplicates, and blank/summary rows.
2. Propose an explicit mapping for component identity, quantity, location, condition, supplier/lot,
   and notes. Do not guess unresolved component IDs.
3. Resolve each row to a canonical eSchematic `component_id`. Keep ambiguous rows in review.
4. Convert accepted rows to normalized JSON with a stable `source_key`, such as
   `workbook-hash:sheet:row`.
5. Call `inventory_preview_or_import_legacy_rows` with `commit=false` and show counts, unresolved
   rows, locations, and proposed quantities.
6. Commit only after the user approves the preview. The stable source key prevents duplicate import.

Each committed row becomes a provenance-bearing legacy `RECEIVE` event. Corrections after import
must be new `ADJUST` events; never edit the original event or overwrite a balance.
