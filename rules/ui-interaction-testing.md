# Browser focus and action testing

For standalone Studio prototypes, verify action clicks both from neutral focus and directly after
editing or undoing inside a text field. Browser focusout occurs before click; a blur handler must
not replace the receiving panel and detach the impending click target. Prefer targeted updates
or skip that redraw when focus moves into the panel. Do not add artificial blur steps to a test
just to hide a lost-click defect.

Use a fresh isolated browser context and synthetic source/import data; never clear the user's
browser profile or point tests at production services. After a fix, run the focused interaction
contract and the full relevant prototype regression suite. Keep repository mission gates unchanged.
