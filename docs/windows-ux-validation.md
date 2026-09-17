# Windows 0.2.3 UX follow-up

## Fixed

- **Pause stays reachable.** Use View setup in the header or Settings → Model after leaving the wizard.
- **Chat starts sooner.** Setup checks the model and voice before downloading maps. Chat can run while maps download. Pausing or a map failure keeps the checked model available, including after restarting the app.
- **Search covers the library.** Imported files and built-in guides appear with matching reference passages. Unrelated cards stay hidden. The PDF filter excludes text-only documents.
- **Progress is readable.** Component names replace filenames. Transfer counters use decimal GB/MB, percentage, speed and an estimated time when available. Map tool logs and terminal formatting stay out of the UI. Verification is shown separately.
- **Remaining downloads reflect saved work.** Model partials and completed/partial routing files reduce the estimate. An unfinished basemap still restarts; the pause message explains this.
- **Map readiness is explicit.** Search waits for map data and offers View setup instead of suggesting a different town.
- **Directions keep the destination name.** The popup passes its name through to the route title; unnamed points retain a generic label.

No model, prompt, dependency or signing changes.

## Validation

Local tests on macOS, against this source revision:

- New regression tests fail on the pre-fix source for inaccessible Pause, imported-document search, model-first chat, map readiness, destination naming and remaining model bytes.
- 130 Python tests pass, including real local map/route integration. Tests cover overlapping chat and failed map downloads, pause/restart, corrupt downloads, literal names, Windows UTF-8 progress and verification before publishing files.
- Electron checks cover startup, operations, chat/voice indicators, planner, two-client local board, layout, setup, documents/PDFs and real offline maps. Setup now also runs in Windows and Mac PR CI.
- Real downloaded data: 50 states plus D.C., two walking routes per jurisdiction (102 routes). Python network calls blocked. This is not a physical route survey or an OS-level network-disconnection test.
- Real Gemma model: answered an imported manual question while map setup was pending, remained running after Pause, and completed setup on resume using existing files with external Python HTTP blocked. Test records were isolated from the user's library.
- Full Git history secret scan and publication-boundary checks: no credentials detected. Signing remains outside public PR workflows.

## Limits and follow-up

- These are source regression checks, not a new signed-installer or clean-Windows-machine acceptance run. The supplied Windows report establishes that the existing 0.2.3 installer completed setup; a new installer needs its own smoke test before release.
- The native Windows installer already shows a progress bar. Its disabled Cancel/Close buttons during file installation are expected. This change does not customize NSIS or add an unreliable installation ETA.
- An existing six-question answer spot check passed four deterministic calculations. The compact model's two free-form answers missed their review targets: a vague follow-up about water usage, and an unsupported numerical claim in a heat-loss explanation. Successful generation is not an advice-quality pass. Model and prompt files are unchanged.
- Audio controls and lifecycle regressions are covered; no new Windows acoustic or microphone-hardware test is claimed. The packaged audio test requires a newly built executable and is outside this source-only pass.
