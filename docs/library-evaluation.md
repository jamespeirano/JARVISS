# Offline library evaluation — September 17, 2026

The larger library improves access to source material. It does **not** make a small model reliably correct. Incorrect answers remained even when the right passage was supplied.

## What was tested

- Three pinned abliterated models from `resources/model-catalog.json`: Gemma E2B, Gemma E4B and Qwen 27B. Downloaded weights matched the catalog SHA-256 values.
- 36 initial questions per model, both without library context and with the previous application context: 216 answers.
- Expanded questions cover water, food storage and preservation, medicine labels, first aid, sanitation, growing food, power, shelter, navigation, rope, teamwork, fire and rescue. The main scenario set contains 84 questions, run on each model. A second set adds 24 condition and wording variations and repeats 10 observed failure cases.
- Variations change quantities, elevation, elapsed time, missing facts, conflicting observations, wording and spoken-answer requests. Supply calculations distinguish group consumption from per-person consumption.
- Smaller prompt/context experiments were also evaluated. Shortening the prompt sometimes invented an equipment-code meaning and did not consistently fix food advice. Those prompt changes were discarded.

The default system and voice prompts and model weights were retained. No refusal categories were added. Changes concentrate on source content, retrieval, source links and application behavior.

## Findings that drove the library

**Water:** Unassisted answers confused what filters remove, gave inconsistent disinfectant quantities or suggested reusing chemical containers. Added source conditions for boiling elevation, bleach concentration, filtration limits and food-safe storage containers. Fuel/chemical contamination is different from microbial contamination.

**Food:** Unassisted answers sometimes relied on smell, proposed rescuing overnight rice or soup by reheating, confused ordinary best-by dates with infant-formula use-by dates, or allowed a boiling-water process for plain green beans. Added CDC, FDA and USDA guidance with temperatures, time limits, container conditions and preservation-method limitations.

**Medicine:** Model memory cannot establish a new expiration date or an opened product's usable period. Insulin formulations and containers differ; freezing changes the question. Added product-label examples, conditions and limits of stockpile-extension studies. A label for another product is not a substitute for the user's label.

**Shelter and navigation:** Older field manuals contained useful detail but sometimes retrieved unrelated procedures. Models also calculated reverse bearings incorrectly and confused north references. Added specific field chapters on bearings, grid/true/magnetic north, complete obstacle detours, ground insulation, ventilation and avoiding fast-water crossings. Original illustrated manual chapters remain available to read and export.

**Teamwork:** Broad disaster-psychology passages displaced practical questions about records, shift fatigue or a small team's priorities. Added a short field chapter connecting those questions to the detailed FEMA CERT material.

**Equipment:** An unfamiliar code such as E04 is not enough to identify a fault. Exact-model matching remains required for imported manuals. Smaller prompt experiments that guessed fault meanings were rejected.

## Remaining answer problems

- **Gemma E2B:** Repeated failures included treating expired infant formula as an ordinary quality-date issue, suggesting an unsuitable canning method, omitting burn cooling and asking for a location instead of explaining a general skill. Some repetitions improved; that inconsistency is itself a limitation.
- **Gemma E4B:** Usually handled the core questions better, but still mixed up canned-food storage categories, added unnecessary questions and miscalculated compass bearings before the focused navigation chapter was added.
- **Qwen 27B:** Performed better on these examples, but still made assumptions, omitted qualifications or retrieved an unrelated passage. It sometimes referred users to phone services despite the scenario having no communications.
- Reference buttons identify the passages supplied to the model. They do not certify that its answer follows them. Read the linked section for conditions, units and exceptions.
- Long saved context can crowd out an answer, especially in non-English text. The app now counts tokens with the loaded model, reserves output space and removes old exchanges first. If the remaining question, facts and sources do not fit, it reports that limitation rather than silently truncating them.

These are qualitative software evaluations, not clinical review, survival training certification or a guarantee of accuracy. A successful generation, correct keyword or passing software test is not an answer-quality pass. The questions used during development are not an independent benchmark, and generation at temperature 0.25 can vary between runs.

## Reproduce the checks

Install the contributor environment and download the catalog models through Setup. Each run uses temporary synthetic records and blocks external `urllib` requests during inference; the local inference server remains reachable. Models run one at a time.

```sh
python -m tests.evaluate_knowledge --mode raw --model all --output local-data/raw-new.jsonl
python -m tests.evaluate_knowledge --mode app --model all --output local-data/app-new.jsonl
python -m tests.evaluate_knowledge --mode app --model all --cases tests/scenarios/variations.json --output local-data/variations-new.jsonl
python -m tests.verify_use_cases
```

The JSONL rows retain the question, expected facts, actual answer, model hash, selected passages and payload hash. `judgment: not_reviewed` is deliberate: review every answer against its sources before assigning a result. Supply arithmetic may run directly in code. This evaluator does not replace full-service map, audio or installer tests.

Scenario files: [core questions](../tests/scenarios/knowledge.json), [manual questions](../tests/scenarios/manuals.json), [further variations](../tests/scenarios/variations.json). Sources and redistribution details: [library catalog](reference-library.md).

## Application checks

- 121 backend tests passed, including source integrity, saved reference links, section hierarchy, source-text formatting and long-context handling.
- Desktop checks exercised setup, maps, planner, messages, documents, delayed responses and voice failures/retry. Full-screen map entry and exit, cross-page voice generation indicators, document search, persisted links, canceled exports and attributed text/PDF exports passed.
- Real map data produced 102 sampled walking routes across all 50 states and DC. This checks sampled graph connections, not road access, water quality or current conditions.
- Real local speech synthesis and recognition completed six digital round trips with two distinct voices and the spoken stop command. This did not use a physical microphone or speakers and does not establish audio-device compatibility.
- Installer-specific results belong with the release checksums. The new builds still need signature, packaged first-launch and setup integration checks; earlier VM results do not automatically certify a new binary.

### Reader usability checks

All 38 documents were opened with networking blocked and no model loaded. The reader tests compare the visible words and quantities against every bundled section. They cover search and retry, PDF filtering, saved chat links, highlighted sections, return focus and scroll position, export cancellation, literal untrusted text, missing PDFs, stale links and late or reordered responses.

The actual Chromium PDF viewer was checked at each illustrated chapter's cover, first, middle and last source pages. Reopening another page in the same PDF originally left the viewer on page 1; each open now reloads the local PDF at the requested page. A short final section also keeps its selection after a jump, even when it cannot scroll to the top.

The section menu stays in the app and supports arrow keys, Home/End, Escape and leaving by keyboard. Layout checks use 1024- and 1440-pixel windows at 100%, 125% and 150% zoom, plus paths containing spaces and non-ASCII characters. The Mac and Windows PR jobs run this suite. These are source-app tests; the packaged-app check separately verifies setup, bundled text, reader assets and a real illustrated PDF page.

## Public-source review

The reachable history was scanned for credentials and reviewed for environment files, private keys, private documents, home paths and personal records. No secret findings were observed. Matches for personal email addresses were public third-party license credits; required attribution remains intact. Commit author names and GitHub no-reply addresses are public Git metadata.

The publication check now rejects `.env.*` files as well as `.env`, except the deliberate `.env.example` template. Signing credentials remain outside the repository and CI. This is a scan of the available repository history, not a guarantee about deleted remote objects, forks or external caches.
