# Use-case verification

Scope: every item in [survival-use-cases.md](survival-use-cases.md).

## Practical scenarios

- **Water:** Chat or Docs → Water. Contamination guidance; fuel-contaminated water must not be presented as safe after boiling.
- **Food:** Chat or Food after a power cut. Uses time and temperature; no smell test.
- **Equipment warning:** Add the exact manual, then ask about the model and code. Missing manuals must prompt for information.
- **Parts:** Paste labels into Chat. Compare supplied voltage, chemistry and limits; missing specifications are unknown.
- **Toilets:** Toilets without water guide; tailor the plan to people and available supplies.
- **Building:** Check a building guide; immediate danger requires leaving, not remote certification.
- **Translation:** Paste the label and target language into Chat. Preserve numbers, units and warnings.
- **Repairs:** Add a manual and describe tools and symptoms. Request one check at a time.
- **Growing:** Garden records, seed packets, local observations and imported regional guides.
- **Meeting:** People records, actual radio manuals, check-in times and local messages.
- **Priorities:** Today records and saved supplies/power; observed weather and available daylight.

## Additional uses

- **Supplies:** Amount ÷ daily group use; edit and restart persistence. The earliest shortage is considered across the whole inventory.
- **Daily planning:** Now / Today / Later, owner, due date and dependencies.
- **Navigation:** City/state → street/landmark → confirm point. Nearby resources, route miles and Back / Next directions.
- **Power:** Device watts × hours; usable battery capacity and solar assumptions; explicit shortfall and battery-only duration.
- **Library:** Search bundled guides, pasted text and readable PDFs. Retrieve relevant passages into Chat.
- **Equipment repair:** Exact-manual retrieval; refuse to substitute another model's fault code.
- **Food production:** Seed inventory, planting and harvest estimates, observations and preservation references.
- **Community:** Skills, resources, needs, responsibilities and meeting points.
- **Communication:** Two authenticated browser clients exchange messages over a local HTTP board, including automatic receipt and a phone-sized screen. No internet relay.
- **Logging:** Observed / Reported / Assumption / Decision remain distinct.
- **Education:** Short lessons, translation, speech recognition and spoken replies.
- **Rebuilding:** Repair tasks, materials, dependencies, owners and maintenance dates.

## Evidence

**74 backend tests pass.** They cover calculations, validation, persistence, model-specific manual retrieval, PDF extraction, state boundaries, route failures, stale-location races, hardware recommendations, setup resumption and operation recovery. Electron tests exercise the actual forms and controls with isolated user data.

Chat layout checks pass at 1024, 1440 and 2240 pixels wide. They verify the stacked heading and shortcuts, adjacent message box, keyboard focus after choosing a shortcut, conversation and clear transitions, and layouts with the voice panel open or closed. Screenshots were visually inspected at desktop and small-window sizes.

`tests/verify_all_states.py` completed **102 real offline walks across all 50 states and DC**. Each complete route was checked against Census state boundaries. Additional routes include Philadelphia → New York and Los Angeles → New York. This samples coverage; it does not prove every road is passable.

`tests/voice_integration.py` passed neural synthesis, three speech-recognition fixtures, start/pause cycles, spoken pause, playback/resume, missing-device handling and the physical speaker-to-microphone test. The full model-to-voice conversation completed in 6.96 seconds and returned to listening. A native telemetry shutdown crash was reproduced, fixed by disabling the uploader before runtime initialization, and the complete conversation then exited cleanly.

The earlier `tests/verify_use_cases.py` run exercised 23 questions against the original, unmodified Qwen model with isolated equipment manuals and planning records, followed by focused retests. Those final reviewed answers passed their scenario criteria; 13 also had automated content checks. Final answers were at most 84 words, with a median response time of 8.91 seconds on this Mac. These results do not qualify replacement models.

The tests caught and corrected stale stock overriding new amounts, irrelevant manuals retrieved for shared fault codes, unnecessary procedure details, and overly long daily plans. Current user quantities now suppress older stock estimates for that answer; saved records remain unchanged.

Local evidence: `local-data/use-case-review.json`, `state-verification/results.json`, `voice-verification.json` and `voice-roundtrip.json`. Synthetic equipment manuals test retrieval and model behavior; they are not installed as real equipment guidance. Successful generation alone is not counted as a semantic pass.

## New setup and model checks

The new setup checks available RAM, graphics memory and storage; verifies pinned model file hashes; handles pause/restart/retry; and tests model and voice engines before reporting ready. UI checks cover recommendations, model selection, low storage, two window sizes, reload during download, completion, and preservation of conversation history. A running model is not rejected because its own graphics memory is occupied.

The unsigned Apple silicon app passed `electron/tests/packaged-setup.cjs` using isolated records and real cached datasets: full setup, a model translation, voice-engine initialization, map rendering and a real walking route. The app used its bundled Python and four native engines, with no separate runtime installation; external renderer HTTP requests were blocked and none occurred. This cached-data test is separate from the real checksum-verified model downloads and does not simulate every interruption in a fresh nationwide basemap transfer.

Each catalog model was downloaded and exercised on all 23 questions. Gemma 4 E2B and E4B missed cases: repeated questions, omitted saved meeting points or precautions, and unreliable equipment/food-preservation advice. Their limitations are shown when selected. Hardware fit is not a quality pass.

The Qwen 3.8 27B abliterated model correctly handled the core water, food, evacuation, manual, translation, supply and record questions in this run. Review still found an unnecessary inferred battery charging voltage, a long gardening answer, and extra assumptions in daily planning. This is not an all-cases quality pass or a claim of emergency reliability.

Results: `local-data/setup-model-compact.json`, `setup-model-balanced.json` and `setup-model-advanced.json`. Those local files contain isolated test fixtures, not the user's records. Model generations are probabilistic; the setup's first-response test checks operability only.

## Repeat setup checks

Run `node electron/tests/setup.cjs` for isolated wizard checks. Set `TEST_PACKAGED` to the built application executable and run `node electron/tests/packaged-setup.cjs` for real cached-data/model/voice/map integration. The latter requires downloaded catalog models, voice files and the US dataset, and uses the model recommended for available memory at test time. Set `JARVIS_TEST_MODEL` and `JARVIS_TEST_RESULTS` to repeat a catalog model's use cases.

```sh
python -m unittest discover -s tests -p 'test_*.py' -v
node electron/tests/atlas-protocol.cjs
node electron/tests/atlas.cjs
node electron/tests/operations.cjs
node electron/tests/planner.cjs
node electron/tests/board.cjs
node electron/tests/smoke.cjs
python -m tests.verify_use_cases
python -m tests.verify_all_states
python -m tests.voice_integration
```

Model answers remain probabilistic. These checks verify the recorded scenarios, not medical judgment, structural inspection, current road conditions or arbitrary equipment compatibility. Exact manuals, labels and local observations still come from the user.
