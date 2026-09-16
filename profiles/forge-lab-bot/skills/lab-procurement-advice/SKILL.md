---
name: lab-procurement-advice
description: Analyze BOM shortages against lab inventory, compare multi-platform sourcing options, and generate procurement advice.
---

# Lab Procurement Advice

The `lab-procurement-advice` skill assists engineers in identifying component shortages and evaluating sourcing alternatives.

## Core Invariants

- **Advice, Not Autonomous Purchase**: Lab_Bot generates comparison data, price snapshots, and purchase advice; actual payment/ordering remains with the user.
- **CopyCat & UI Automation Scope**: Orchestrator-coordinated CopyCat or computer UI control may be used to expand search terms and overcome stealth web crawling hurdles on dynamic storefronts, but is strictly restricted from making payments or executing checkouts.
- **Federated Sourcing**: Search terms expand from canonical MPNs and verified aliases across approved distributors (LCSC, 1688, Taobao, etc.).
- **Traceable Snapshots**: Vendor listings, prices, and URLs are timestamped observations, not timeless facts.

## Tool Routing

- **BOM Shortage Analysis**: `lab_analyze_bom` (resolves design BOM against eSchematic and checks stock shortages).
- **Shortage Ingestion**: `procurement_create_requirements_from_shortages` (explicitly converts BOM shortages into tracked requirements).
- **Requirements Management**: `procurement_create_requirement`, `procurement_list_requirements`.
- **Search Term Expansion**: `procurement_expand_terms` (retrieves aliases and raw material alternatives), `procurement_save_term_rule`.
- **Live Chrome Crawling (Taobao & 1688)**:
  - `procurement_check_crawler_status`: checks Chrome executable, user profile directory, and session persistence.
  - `procurement_auto_search_and_evaluate`: drives local Chrome session to search Taobao & 1688, handles sliders/login with human-in-the-loop, harvests live offers, and computes 3-strategy evaluation.
- **Offer Ingestion**: `procurement_parse_offer_snippet` (extracts price, shop, and shipping from pasted links/text), `procurement_record_offers`, `procurement_list_offers`.
- **Multi-Strategy Sourcing**: `procurement_evaluate_sourcing` (compares Lowest Landed Cost, Single-Shop Bundle, and First-Principles DIY).
- **Order Handoff & Receiving**: `procurement_confirm_order` (marks requirements as ORDERED and generates draft `purchase_lots`), followed by `inventory_receive` upon parcel arrival.
- **Stock Availability Verification**: `inventory_get_balances`.

