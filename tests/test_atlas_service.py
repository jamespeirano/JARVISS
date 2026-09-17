import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from jarviss.service import Service
from tests.test_core import fixture


class AtlasServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.data=Path(self.temp.name)
        self.patches=[patch('jarviss.service.DATA',self.data),patch('jarviss.service.ROOT',self.data),
                      patch('jarviss.service.model_path',side_effect=lambda x:self.data/x),patch('jarviss.service.emit')]
        for p in self.patches:p.start()
        self.services=[]

    def tearDown(self):
        for service in self.services:service.close()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def service(self):
        service=Service();self.services.append(service);return service

    def import_area(self,service,pack):
        p=self.data/'import.json';p.write_text(json.dumps(pack));service.command('import_map',{'path':str(p)})

    def test_packs_and_selected_position_survive_restart(self):
        service=self.service();first=fixture();self.import_area(service,first)
        second=fixture();second['bounds']=[39.98,-74.02,40.02,-73.98]
        self.import_area(service,second)
        service.command('set_map_position',{'lat':40,'lon':-74})
        restarted=self.service()
        self.assertEqual(len(restarted.state()['routingPacks']),2)
        self.assertEqual(restarted.profile['lat'],40)
        with patch('socket.socket',side_effect=AssertionError('Network forbidden')):
            answer=restarted.command('chat',{'text':'How many miles to Recorded fountain?'})
        self.assertIn('Mapped walk',answer);self.assertIn('miles',answer)
        self.assertFalse(restarted.ready)
        self.assertEqual(restarted.route['destination'],'Recorded fountain')

    def test_failed_map_request_clears_route_and_changing_position_clears_route(self):
        service=self.service();self.import_area(service,fixture())
        service.command('set_map_position',{'lat':40,'lon':-74})
        service.command('chat',{'text':'nearest water'});self.assertIsNotNone(service.route)
        service.command('chat',{'text':'nearest spacesuit'});self.assertIsNone(service.route)
        service.command('chat',{'text':'nearest water'});self.assertIsNotNone(service.route)
        service.command('set_map_position',{'lat':40.0001,'lon':-74});self.assertIsNone(service.route)

    def test_unrelated_answers_keep_the_displayed_route(self):
        service=self.service();self.import_area(service,fixture())
        service.command('set_map_position',{'lat':40,'lon':-74})
        service.command('chat',{'text':'nearest water'})
        route=service.route
        for ready in (False, True):
            with self.subTest(model_ready=ready), patch('jarviss.service.emit') as emit, \
                 patch('jarviss.service.reference_answer',return_value=('Use dry clothes.',None)), \
                 patch.object(service.model,'chat',return_value='Use dry clothes.'):
                service.ready=ready
                service.command('chat',{'text':'Why do wet clothes feel colder in wind?'})
                answer_event=next(c.args[0] for c in emit.call_args_list if c.args[0]['event']=='answer')
                self.assertEqual(answer_event['data']['route'],route)
                self.assertEqual(service.route,route)
        answer=service.command('chat',{'text':'How do I walk there?'})
        self.assertIn('Recorded fountain',answer)
        with patch.object(service.model,'chat') as chat, patch('jarviss.service.emit') as emit:
            answer=service.command('chat',{'text':'I have 12 litres for 3 people. Each uses 2 litres per day. How many days will it last?'})
            self.assertTrue(answer.startswith('2 days.'))
            chat.assert_not_called()
            answer_event=next(c.args[0] for c in emit.call_args_list if c.args[0]['event']=='answer')
            self.assertEqual(answer_event['data']['route'],route)

    def test_water_access_note_matches_map_button_and_chat(self):
        pack=fixture();pack['places'][0].update(kind='untreated water',category='stream')
        service=self.service();self.import_area(service,pack)
        service.command('set_map_position',{'lat':40,'lon':-74})
        place=service.command('nearest',{'query':'running water'})[0]
        selected=service.command('route',{'id':place['id']})
        service.command('chat',{'text':'Where is the nearest running water and how do I walk there?'})
        self.assertEqual(service.route['destination_note'],selected['destination_note'])
        service.command('chat',{'text':'Give me directions'})
        self.assertEqual(service.route['destination_note'],selected['destination_note'])

    def test_location_discovery_does_not_assign_a_default_or_save_search_centers(self):
        service=self.service()
        self.assertNotIn('lat',service.state()['profile'])
        self.assertFalse((self.data/'profile.json').exists())
        self.import_area(service,fixture())
        rows=service.command('search_locations',{'query':'Recorded fountain','near':[40,-74]})
        self.assertEqual(rows[0]['name'],'Recorded fountain')
        self.assertNotIn('lat',service.state()['profile'])
        self.assertFalse((self.data/'profile.json').exists())
        service.command('set_map_position',{'lat':rows[0]['point'][0],'lon':rows[0]['point'][1]})
        self.assertTrue((self.data/'profile.json').exists())

    def test_stale_search_result_cannot_route_to_a_different_place(self):
        service=self.service();self.import_area(service,fixture())
        service.command('set_map_position',{'lat':40,'lon':-74})
        found=service.command('nearest',{'query':'water'})[0]
        service.command('nearest',{'query':'medical'})
        with self.assertRaisesRegex(ValueError,'Search again'):
            service.command('route',{'id':found['id']})


if __name__=='__main__':unittest.main()
