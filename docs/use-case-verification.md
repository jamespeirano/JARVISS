# Testing and known limitations

The scenarios are listed in [survival use cases](survival-use-cases.md). Test the user's result, not just whether an answer appeared.

## What to check

- **Setup:** download → install → open → setup → Ready offline. No terminal or separate runtime installs. Check pause, retry, low storage, missing files and model recommendations.
- **Maps:** city/street/landmark → confirm position → nearest resource → walking miles and directions. Check compound questions, ambiguous places, changed positions, disconnected routes and unrelated chat preserving a route.
- **Answers:** clear, brief and grounded in supplied facts. Check explicit supply calculations, missing daily use, group versus per-person rates, exact equipment manuals and relevant guide retrieval.
- **Plan and Docs:** save, edit, delete and restart; verify supplies, tasks, power, garden, people, observations and imported documents.
- **Voice:** listen, transcribe, answer, play audio and resume. Check pause, missing devices and model failures.
- **Group messages:** two clients on the same local network, authentication, receipt and phone layout.
- **Offline:** disconnect the network after setup; verify model, maps, routes and saved references.

## Automated checks

```sh
python -m unittest discover -s tests -p 'test_*.py' -v
python scripts/check_publication.py
node --test electron/tests/startup.cjs
node electron/tests/atlas-protocol.cjs
npm run build:map --prefix electron
```

For UI changes, run the relevant desktop tests:

```sh
node electron/tests/setup.cjs
node electron/tests/atlas.cjs
node electron/tests/operations.cjs
node electron/tests/planner.cjs
node electron/tests/board.cjs
node electron/tests/smoke.cjs
```

These use isolated test records. Full-map integration tests skip when downloaded data is absent. Passing unit tests alone does not validate installers or model answers.

## Real data, models and installers

- `python -m tests.verify_all_states`: real offline routes using downloaded US map/routing data.
- `python -m tests.verify_use_cases`: model answers using synthetic records; review the responses against each scenario. Set `JARVIS_TEST_MODEL` and `JARVIS_TEST_RESULTS` to choose a catalog model and result file.
- `python -m tests.verify_short_answers`: a small real-model check, including explicit supply calculations.
- `python -m tests.voice_integration`: real voice tests; see [voice](voice.md).
- `node scripts/check_installed_ui.cjs /path/to/executable`: packaged first launch with empty data and an OS-only PATH.
- `TEST_PACKAGED` plus `node electron/tests/packaged-setup.cjs`: integration using real cached models, voice and maps. This does not replace a fresh-download test.

Keep each result tied to its source revision, installer checksum, platform and model. Reuse evidence only for unchanged behavior. Rebuilt installers still need signature and startup checks. Changes to setup, dependencies or packaging need clean-machine checks.

See [the detailed library evaluation](library-evaluation.md) for source-driven model tests, remaining mistakes and reproduction commands.

## Recorded results and limits

Earlier map testing sampled **102 offline walks across all 50 states and DC**, plus cross-state and long-distance routes. This does not prove every road is connected or passable.

The clean Mac test completed GUI setup and answered with the network disconnected. The clean Windows test remains in progress; release reports record its final status separately. Neither establishes performance on every computer.

Catalog-model testing found mistakes in smaller Gemma models and extra assumptions or verbose answers in Qwen. Hardware fit and setup's first response check establish operability, not answer quality. Simple explicit supply arithmetic runs in code; other calculations can still be wrong.

Routes use recorded geography. They do not confirm open facilities, supplies, passable roads or safe drinking water. A path near a river may end on a bridge; water access and current flow remain unverified. National routing data omits street names.

Group messages are not encrypted. Live microphone accuracy, long-running reliability and emergency advice require separate evaluation. Use exact manuals, labels and local observations; do not treat a generated answer as an inspection.
