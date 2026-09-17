# Offline field library

Open **Docs**, then **Read full document**. The complete text appears in one reader; **Jump to section** moves within it. In chat, click a **Reference passage** to open and highlight the section supplied to the model. **Back to chat** returns to the conversation.

Choose **Illustrated PDFs** to find the three shelter, navigation and rope chapters. **Open illustrated PDF** opens the complete excerpt in a separate app window. **View illustrated page** opens the page for the selected section. **Save PDF** and **Save text (.md)** export copies; saving is not required to read them.

The library is bundled with the app. Reading, searching, asking about a passage and exporting work offline. No account or separate download is required.

## What's included

38 documents, about 105,000 words:

- Navigation bearings, north references, river obstacles, water sources, boiling, filters, disinfection and storage.
- Food temperatures, outages, storage periods, canning and drying.
- Medicine expiration, storage damage, opened products and insulin labels.
- Heat, cold, burns, bleeding, hygiene and waste.
- Growing food: planning plus tomato, bean, potato, basil and radish profiles.
- Generator placement, carbon monoxide, batteries and power calculations.
- Army manual chapters on shelter, clothing, navigation, knots and rope, including illustrated PDFs.
- Seven FEMA CERT chapters on preparedness, team organization, first actions and continued care, disaster stress, fire and utilities, and light search and rescue.

The original short checklists remain under **Using JARVISS**. Imported equipment manuals remain separate and retain their original rights.

## Sources and reuse

Each entry in [the catalog](../resources/references/catalog.json) records its publisher, edition, URL, review date, license basis, text hash and word count. PDF excerpts also record a file hash and original page range. Source and reuse details are visible inside each document.

- **CDC, FDA, USDA and FEMA:** selected federal publication text. Images, logos and third-party tables are excluded from these text editions. The government-work basis applies to qualifying U.S. federal works, not everything on a government website. See [17 U.S.C. §105](https://www.copyright.gov/title17/92chap1.html#105).
- **FEMA CERT:** selected chapters of the August 2019 Participant Manual, published by FEMA and archived by the [U.S. Government Publishing Office](https://www.govinfo.gov/app/details/GOVPUB-HS5_100-PURL-gpo185734). Class exercises and references to communications may assume resources unavailable during an extended outage.
- **Army ATP 3-50.21:** shelter, navigation and rope chapters from the September 18, 2018 edition. The publication states that public distribution is unlimited. The illustrated excerpts retain the original cover and page numbers. [Official publication](https://armypubs.army.mil/epubs/DR_pubs/DR_a/pdf/web/ARN12086_ATP%203-50x21%20FINAL%20WEB%202.pdf).
- **JARVISS field chapters:** original MIT-licensed summaries of cited factual guidance. University Extension, AHA, MedlinePlus and manufacturer labels are linked for attribution; their copyrighted handbooks and full pages are not redistributed. Do not infer a right to copy those publications from their being free to read online.

No agency endorses JARVISS. Original publications retain their edition dates; a retrieval date does not make an older procedure current. Detailed source text is included so people can inspect its conditions and context themselves.

## How answers use the library

Retrieval selects a few relevant passages within the model's limited context window. It does not load the entire library into every answer. Current field chapters and agency guidance take priority over broad older manuals. Some older references remain browsable but are excluded from automatic retrieval; the catalog marks those entries `searchable: false`.

The buttons below an answer identify passages actually supplied to the model. They are not a claim that every sentence in its answer is supported by each passage. A model can still misread a source or omit a condition. Open the section to check quantities, temperatures, timing and applicability. Tables and illustrations are not reproduced in the text-only editions; use the illustrated PDFs where provided.

## Updating or contributing a reference

1. Find a primary source and establish redistribution rights. Free access alone is insufficient.
2. Retain the edition, conditions, units and relevant exceptions. Avoid extracting a dose or table cell without its heading and qualifications.
3. Add the local document and its provenance to the catalog. Keep third-party notices. Recalculate SHA-256 and word count.
4. Test retrieval with different phrasings, conflicting facts, missing information and questions outside the document's coverage.
5. Check the answer against the source, then click its passage in Docs. Confirm search, restart and export with networking disabled.

Run `python -m unittest tests.test_references -v` for source integrity and reference-link tests, `node electron/tests/feedback.cjs` for chat citations, and `node electron/tests/references.cjs` for the reader, search, PDF pages, navigation and failure recovery. Clinical accuracy requires qualified review beyond software tests.
