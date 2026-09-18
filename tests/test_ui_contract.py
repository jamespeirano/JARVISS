"""State fields and commands the desktop renderer relies on."""
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from jarviss import library, maps
from jarviss.assistant import messages
from jarviss.service import Service
from jarviss.storage import read_json, write_json
from tests.test_core import fixture


class UIContractTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        for target in ('service.DATA', 'service.ROOT', 'setup.DATA', 'setup.ROOT', 'library.DATA'):
            self.stack.enter_context(patch(f'jarviss.{target}', self.root))
        for module in ('service', 'setup'): self.stack.enter_context(patch(f'jarviss.{module}.MODELS', self.root/'models'))
        self.events = self.stack.enter_context(patch('jarviss.service.emit'))
        self.service = Service()
        self.addCleanup(self.stack.close)
        self.addCleanup(self.service.close)
        self.addCleanup(maps.set_units, 'imperial')

    def test_state_lists_documents_lightly_and_serves_one_with_sections(self):
        self.service.command('import_note', {'title':'Pump manual', 'text':'## Priming\nFill the bowl.'})
        state = self.service.state()
        self.assertEqual(state['documents'], [{'title':'Pump manual', 'kind':'note', 'imported_at':state['documents'][0]['imported_at'], 'words':5}])
        (self.root/'Pump.PDF').write_bytes(b'%PDF-1.4 garbage'); (self.root/'notes.md').write_text('Prime the pump first.')
        with self.assertRaisesRegex(ValueError, 'could not be read'): self.service.command('import_document', {'path':str(self.root/'Pump.PDF')})
        self.service.command('import_document', {'path':str(self.root/'notes.md')})
        self.assertEqual({d['title']:d['kind'] for d in self.service.state()['documents']}, {'Pump manual':'note', 'notes.md':'text'})
        self.assertEqual([library.document_kind(t) for t in ('manual.pdf', 'Manual.PDF', 'a.txt', 'a.md', 'Pump manual', 'v1.2 notes')], ['pdf', 'pdf', 'text', 'text', 'note', 'note'])
        self.service.command('library_delete', {'title':'notes.md'})
        self.assertEqual(self.service.command('document', {'title':'Pump manual'})['sections'][0]['heading'], 'Priming')
        self.assertEqual(self.service.command('library_rename', {'title':'Pump manual', 'new_title':'Pump'}), 'Pump')
        self.assertTrue(self.service.command('library_delete', {'title':'Pump'}))
        self.assertEqual(self.service.state()['documents'], [])

    def test_quick_prompts_paths_and_setup_skip(self):
        state = self.service.state()
        self.assertEqual(len(state['quick_prompts']), 6)
        self.assertEqual(state['quick_prompts'][0]['label'], 'Water')
        self.assertTrue(all(set(p) == {'label', 'prompt'} and p['prompt'].strip() and 0 < len(p['label']) <= 28 for p in state['quick_prompts']))
        self.assertEqual(state['paths'], {'data':str(self.root), 'logs':str(self.root/'service.log')})
        self.assertFalse(state['setup']['skipped'])
        self.assertTrue(self.service.command('setup_skip', {})['skipped'])
        self.assertTrue(self.service.state()['setup']['skipped']); self.assertTrue(read_json(self.root/'setup.json', {})['skipped'])
        self.assertEqual(self.service.state()['setup']['percent'], 0)

    def test_units_setting_drives_distances_in_map_answers(self):
        area = self.root/'area.json'; write_json(area, fixture())
        self.service.command('import_map', {'path':str(area)})
        self.service.command('set_map_position', {'lat':40, 'lon':-74})
        prompts = {k:self.service.settings[k] for k in ('system_prompt', 'voice_prompt', 'voice_max_sentences', 'voice_max_tokens', 'text_max_tokens')}
        self.assertEqual(self.service.settings['units'], 'imperial')
        self.assertIn('miles', self.service.command('chat', {'text':'How far is Recorded fountain?'}))
        with self.assertRaisesRegex(ValueError, 'imperial or metric'): self.service.command('prompt_settings', {**prompts, 'units':'furlongs'})
        self.assertEqual(self.service.command('prompt_settings', {**prompts, 'units':'metric'})['units'], 'metric')
        self.assertEqual(read_json(self.root/'settings.json', {})['units'], 'metric')
        answer = self.service.command('chat', {'text':'How far is Recorded fountain?'})
        self.assertNotIn('miles', answer); self.assertRegex(answer, r'\d+ m')
        self.assertEqual(maps.format_distance(2500), '2.50 km (2,500 m)'); self.assertEqual(maps.format_distance(80), '80 m')
        self.assertIn('kilometers', messages({'lat':40, 'lon':-74}, [], 'Hi', self.service.catalog(), None, self.service.settings)[0]['content'])
        self.assertEqual(Service().settings['units'], 'metric'); self.assertEqual(maps.UNITS['value'], 'metric')

    def test_search_results_carry_distance_text_in_the_current_units(self):
        area = self.root/'area.json'; write_json(area, fixture())
        self.service.command('import_map', {'path':str(area)})
        self.service.command('set_map_position', {'lat':40, 'lon':-74})
        prompts = {k:self.service.settings[k] for k in ('system_prompt', 'voice_prompt', 'voice_max_sentences', 'voice_max_tokens', 'text_max_tokens')}
        for units, pattern in (('imperial', r'^0\.\d\d miles \(\d+ m\)$'), ('metric', r'^\d+ m$')):
            self.service.command('prompt_settings', {**prompts, 'units':units})
            for rows in (self.service.command('nearest', {'query':'water'}), self.service.command('search_locations', {'query':'Recorded fountain', 'near':[40, -74]})):
                self.assertEqual(rows[0]['name'], 'Recorded fountain'); self.assertRegex(rows[0]['distance_text'], pattern)
                self.assertEqual(rows[0]['distance_text'], maps.format_distance(rows[0]['distance_m']))


if __name__ == '__main__': unittest.main()
