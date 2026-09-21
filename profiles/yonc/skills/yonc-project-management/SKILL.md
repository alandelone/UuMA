# Yonc project management

Use `yonc-project` semantic tools for all project facts and proposals.

1. Call `yonc_status` and verify the database identity before domain work.
2. Search or read the smallest relevant graph context.
3. Distinguish discussion from a requested graph change. For a change, start or
   continue a split session and present the saved proposal version and validation.
4. Do not commit unless the backend has issued a fresh authorization ID bound to that
   exact session, proposal version, and graph version. Never ask the model to create or
   modify credentials.
5. Treat time guidance as soft: L3 8–80 hours and L4 about two hours are review hints,
   not automatic rejection or fabricated estimates.
6. Preserve completed nodes. Propose removals explicitly; omission is not removal.
7. Report the operation receipt and current graph version after any authorized commit.
