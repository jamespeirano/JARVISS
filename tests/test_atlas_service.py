import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from jarviss.service import Service
from jarviss.storage import write_json
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

    def test_basemap_size_that_disagrees_with_its_record_is_reported_at_startup(self):
        maps=self.data/'local-maps';maps.mkdir();target=maps/'us-z15.pmtiles';target.write_bytes(b'x'*10)
        archive=Mock(path=target,pack={'label':'US','bounds':[24,-125,50,-66],'center':[37,-95]})
        with patch('jarviss.service.TileArchive',return_value=archive),patch('jarviss.service.LocationIndex'):
            for size,expected in ((20,'download record'),(10,None)):
                write_json(maps/'manifest.json',{'file':target.name,'size_bytes':size,'sha256':'0'*64})
                state=self.service().state()
                self.assertEqual(state['basemap']['label'],'US')
                if expected:self.assertIn(expected,state['mapError']);self.assertIn('Check setup',state['mapError'])
                else:self.assertIsNone(state['mapError'])

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

    def test_failed_map_request_keeps_route_and_changing_position_clears_route(self):
        service=self.service();self.import_area(service,fixture())
        service.command('set_map_position',{'lat':40,'lon':-74})
        service.command('chat',{'text':'nearest water'});route=service.route;self.assertIsNotNone(route)
        # Directions in use survive an unsuccessful lookup; only a new successful answer replaces them.
        service.command('chat',{'text':'nearest spacesuit'});self.assertEqual(service.route,route)
        service.command('route',{'point':[40.001,-73.999],'name':'Fountain corner'});self.assertEqual(service.route['destination'],'Fountain corner')
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

    def test_earlier_search_results_stay_routable_until_the_map_changes(self):
        service=self.service();self.import_area(service,fixture())
        service.command('set_map_position',{'lat':40,'lon':-74})
        found=service.command('nearest',{'query':'water'})[0]
        service.command('nearest',{'query':'medical'})
        self.assertEqual(service.command('route',{'id':found['id']})['destination'],'Recorded fountain')
        service.command('use_basemap',{})
        with self.assertRaisesRegex(ValueError,'Search again'):
            service.command('route',{'id':found['id']})

    def test_routable_places_are_capped(self):
        service=self.service();self.import_area(service,fixture())
        service.command('set_map_position',{'lat':40,'lon':-74})
        catalog=service.catalog()
        for batch in range(20):
            with patch.object(catalog,'nearest',return_value=[{'id':f'node/{batch}-{i}','name':'x','kind':'water','point':[40,-74]} for i in range(30)]), \
                 patch.object(service,'catalog',return_value=catalog):
                service.command('nearest',{'query':'water'})
        self.assertEqual(len(service.places_by_id),300)
        self.assertIn('node/19-29',service.places_by_id);self.assertNotIn('node/0-0',service.places_by_id)

    def test_map_swap_during_routing_rejects_the_old_result(self):
        service=self.service();self.import_area(service,fixture())
        service.command('set_map_position',{'lat':40,'lon':-74})
        started=threading.Event();release=threading.Event();failures=[]
        def route(*_):
            started.set()
            if not release.wait(5):raise RuntimeError('Test did not release routing')
            return {'distance_m':100,'steps':[]}
        catalog=Mock();catalog.route.side_effect=route
        def run():
            try:service.command('route',{'point':[40.001,-74]})
            except Exception as e:failures.append(e)
        with patch.object(service,'catalog',return_value=catalog):
            worker=threading.Thread(target=run);worker.start()
            try:
                self.assertTrue(started.wait(3))
                service.command('use_basemap',{})
            finally:release.set();worker.join(5)
        self.assertEqual(len(failures),1);self.assertIn('map changed',str(failures[0]))
        self.assertIsNone(service.route)

    def test_close_waits_for_a_running_operation_and_stops_the_router(self):
        service=self.service();self.services.remove(service)
        service.us_router=Mock()
        service.lock.acquire()
        threading.Timer(0.4,service.lock.release).start()
        started=time.monotonic();service.close()
        self.assertGreaterEqual(time.monotonic()-started,0.35)
        service.us_router.close.assert_called_once()

    def test_concurrent_situation_and_position_saves_keep_both_on_disk(self):
        service=self.service();failures=[]
        def situations():
            for i in range(25):service.command('save_profile',{'situation':f'S{i}','supplies':'water','location_text':'Austin'})
        def positions():
            for i in range(25):service.command('set_map_position',{'lat':30+i*.001,'lon':-97.7})
        def guard(fn):
            try:fn()
            except Exception as e:failures.append(e)
        threads=[threading.Thread(target=guard,args=(fn,)) for fn in (situations,positions)]
        for t in threads:t.start()
        for t in threads:t.join(10)
        self.assertEqual(failures,[])
        saved=json.loads((self.data/'profile.json').read_text(encoding='utf-8'))
        self.assertEqual(saved,service.profile)
        self.assertEqual(saved['situation'],'S24');self.assertEqual(saved['supplies'],'water')
        self.assertIn(saved.get('lat'),[30+i*.001 for i in range(25)])


if __name__=='__main__':unittest.main()
