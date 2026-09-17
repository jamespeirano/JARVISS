"""Offline references, source integrity, and the chat-to-document contract."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarviss import library
from jarviss.assistant import messages
from jarviss.map_questions import answer_map
from jarviss.service import Service


class ReferenceTests(unittest.TestCase):
    def test_installed_sources_have_provenance_and_matching_hashes(self):
        identifiers = set()
        for doc in library.references():
            with self.subTest(document=doc['id']):
                self.assertNotIn(doc['id'], identifiers)
                identifiers.add(doc['id'])
                for key in ('publisher', 'date', 'reviewed', 'url', 'license', 'license_note'):
                    self.assertTrue(doc[key])
                self.assertTrue(doc['url'].startswith('https://'))
                self.assertEqual(hashlib.sha256(doc['text'].encode()).hexdigest(), doc['sha256'])
                self.assertEqual(len(doc['text'].split()), doc['words'])
                self.assertEqual(len(doc['sections']), len({s['id'] for s in doc['sections']}))
                self.assertTrue(all(s['heading'] and s['text'] for s in doc['sections']))
                if doc.get('pdf'):
                    data = Path(library.reference_pdf(doc['id'])).read_bytes()
                    self.assertTrue(data.startswith(b'%PDF'))
                    self.assertEqual(hashlib.sha256(data).hexdigest(), doc['pdf_sha256'])

    def test_read_search_and_retrieve_require_no_network(self):
        with patch('socket.socket', side_effect=AssertionError('Network forbidden')):
            result = library.search_references('bowline')
            self.assertTrue(any(r['id'] == 'army-rope' for r in result))
            for found in result:
                doc = library.reference_document(found['id'])
                self.assertIn(found['section'], {s['id'] for s in doc['sections']})
            passages = library.retrieve('How do I boil cloudy river water at 8000 feet?')
            self.assertTrue(any('3 minutes' in p['text'] for p in passages))
            for passage in passages:
                if passage.get('id'):
                    doc = library.reference_document(passage['id'])
                    section = next(s for s in doc['sections'] if s['id'] == passage['section'])
                    self.assertIn(passage['text'], section['text'])

    def test_conditions_and_units_survive_retrieval(self):
        for question, expected in [
            ('Can I put drinking water in a washed pesticide jug?', ['Never repurpose', 'pesticide']),
            ('How many drops of 6% bleach per gallon of clear drinking water?', ['8 drops', '30 minutes']),
            ('Can I run a generator in an open garage?', ['20 feet', 'garage']),
            ('How long is opened insulin good for?', ['no universal', '56 days']),
            ('Does a swollen can become safe after boiling?', ['Do not taste', 'boiling']),
        ]:
            with self.subTest(question=question):
                text = '\n'.join(p['text'] for p in library.retrieve(question)).lower()
                for fact in expected:
                    self.assertIn(fact.lower(), text)

    def test_acronyms_and_manual_wording_variants(self):
        for question, fact in [
            ('What does PASS mean for a fire extinguisher?', 'Pull'),
            ('How do I join two ropes of different thickness?', 'single sheet bend'),
            ('How do we prevent volunteer burnout?', 'stress'),
        ]:
            with self.subTest(question=question):
                self.assertIn(fact.lower(), '\n'.join(p['text'] for p in library.retrieve(question)).lower())

    def test_navigation_lessons_do_not_require_a_map_position(self):
        for question in ('What do tightly spaced contour lines mean for my route?',
                         'How do I use a compass to navigate around an obstacle?',
                         'How do I find the back azimuth for a bearing of 70 degrees?'):
            self.assertIsNone(answer_map(question, {}, None))
        self.assertIn('No offline map', answer_map('With my compass, give me directions to the nearest hospital', {}, None)[0])

    def test_source_links_survive_unrelated_sections_being_added(self):
        original = library.sections('## Water\nBoil.\n## Food\nKeep cold.')
        updated = library.sections('## Shelter\nKeep dry.\n## Water\nBoil.\n## Food\nKeep cold.')
        self.assertEqual([s['id'] for s in original], [s['id'] for s in updated[1:]])
        repeated = library.sections('## Notes\nOne.\n## Notes\nTwo.')
        self.assertNotEqual(repeated[0]['id'], repeated[1]['id'])

    def test_unknown_documents_and_paths_are_rejected(self):
        for identifier in ('../settings.json', '/etc/passwd', 'missing'):
            with self.assertRaises(ValueError):
                library.reference_document(identifier)
        with self.assertRaises(ValueError):
            library.reference_pdf('field-water')
        with patch('jarviss.library.reference_document', return_value={'pdf':'../private.pdf'}):
            with self.assertRaises(ValueError):
                library.reference_pdf('untrusted')

    def test_section_paths_distinguish_repeated_headings_without_changing_links(self):
        parts = library.sections('# Heat\n## Heatstroke\n### Symptoms\nConfusion.\n'
                                 '## Heat exhaustion\n### Symptoms\nHeavy sweating.')
        self.assertEqual([p['path'] for p in parts], [
            ['Heat', 'Heatstroke', 'Symptoms'], ['Heat', 'Heat exhaustion', 'Symptoms']])
        original = library.sections('### Symptoms\nConfusion.\n### Symptoms\nHeavy sweating.')
        self.assertEqual([p['id'] for p in parts], [p['id'] for p in original])

    def test_offline_editions_exclude_website_controls_and_keep_complete_advice(self):
        food = library.reference_document('fda-food-flood')
        self.assertEqual([s['heading'] for s in food['sections']], ['Before a Storm', 'During a Storm', 'After a Storm'])
        self.assertNotRegex(food['text'], r'WATCH|Get Assistance|Links for Consumer|1-888-SAFE')
        rope = library.reference_document('army-rope')
        self.assertIn('should have a basic knowledge of ropes and knots', rope['text'])
        medical = library.reference_document('cert-4')
        for number, part in enumerate(['Head', 'Neck', 'Shoulders', 'Chest', 'Arms', 'Abdomen', 'Pelvis', 'Legs'], 1):
            self.assertRegex(medical['text'], rf'(?m)^{number}\. {part}\b')

    def test_exact_model_manual_and_user_content_preserved(self):
        docs = [{'title':'UnknownPump ZQ77 manual', 'text':'Fault E04: inspect the blue inlet strainer.'},
                {'title':'AnotherPump X18 manual', 'text':'Fault E04: high motor temperature.'}]
        result = library.retrieve('UnknownPump ZQ77 shows E04', docs)
        self.assertEqual([r['title'] for r in result], ['UnknownPump ZQ77 manual'])
        self.assertFalse(library.retrieve('UnknownPump ZQ78 shows E04', docs))

    def test_chat_retains_reference_links_in_history_and_answer_event(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('jarviss.service.DATA', Path(folder)), patch('jarviss.service.ROOT', Path(folder)), patch('jarviss.service.emit') as emit:
                service = Service()
                try:
                    service.ready = True
                    with patch.object(service, 'catalog', return_value=None), patch.object(service.model, 'chat', return_value='Boil for three minutes.') as chat:
                        service.command('chat', {'text':'How do I boil river water at 7000 feet?'})
                    context = json.loads(chat.call_args.args[0][0]['content'].split('CONTEXT DATA:\n')[1])
                    refs = service.history[-1]['references']
                    self.assertTrue(refs)
                    self.assertTrue(all(any(d['title'] == r['title'] and d['heading'] == r['heading'] for d in context['local_documents']) for r in refs))
                    saved = json.loads((Path(folder) / 'conversation.json').read_text())
                    self.assertEqual(saved[-1]['references'], refs)
                    answers = [c.args[0]['data'] for c in emit.call_args_list if c.args[0]['event'] == 'answer']
                    self.assertEqual(answers[-1]['references'], refs)
                finally:
                    service.close()

    def test_deterministic_calculation_does_not_claim_document_support(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('jarviss.service.DATA', Path(folder)), patch('jarviss.service.ROOT', Path(folder)), patch('jarviss.service.emit'):
                service = Service()
                try:
                    with patch.object(service, 'catalog', return_value=None), patch.object(service.model, 'chat') as chat:
                        result = service.command('chat', {'text':'12 litres for 3 people using 2 litres each daily. How long will it last?'})
                    self.assertTrue(result.startswith('2 days'))
                    chat.assert_not_called()
                    self.assertEqual(service.history[-1]['references'], [])
                finally:
                    service.close()


if __name__ == '__main__':
    unittest.main()
