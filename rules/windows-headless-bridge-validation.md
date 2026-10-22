# Windows API bridge console validation

Use the existing headless Hermes Gateway launcher as a reference. An outer
hidden process or CREATE_NO_WINDOW flag alone does not prove descendants cannot
create a visible Windows Terminal. Record actual window show/hide events and
their owning console/process ancestry while exercising real JSON and SSE calls.

Do not wrap each structured-JSON CLI call directly in conhost: a terminal host
can echo input, merge stderr, inject VT escapes, and return its own exit status.
Host the service in a hidden console, retain explicit subprocess pipes, and
verify descendant console inheritance plus exact stdout, stderr and exit code.
The API adapter's private plugin namespace may inherit a verified invisible
console without modifying installed Hermes plugin files or global terminal settings.

The observed AGY CLI auto-update/version check launched a nested `agy --version`
with a visible terminal. API children use AGY_CLI_DISABLE_AUTO_UPDATE=true;
CLI updates remain a separate maintenance operation. Validate the installed
version rather than assuming this setting is supported by every future release.

Construct nested Python test snippets with repr(), not nested hand-escaped quote
strings. Preserve failed fixture output and fix the execution context; retain
the exact JSON/stdout/stderr/exit-code/console assertions.

An idle bridge socket snapshot is not a quiescent workload: a new request may
arrive during restart. Coordinate an explicit caller pause/drain for single-attempt
durable workloads. Preserve any failed run and all successful results; do not
delete a halted marker, reset an experiment, or claim uninterrupted execution.

Monitor the bridge and reverse tunnel separately using authenticated readiness.
A TCP listener or HTTP401 alone is insufficient. Never expose bearer tokens in
the dashboard catalog, status JSON, incident history or logs. Health probes must
not generate model calls.
