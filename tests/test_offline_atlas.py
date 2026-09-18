import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from jarviss.maps import OfflineMap, build_pack, matches_place
from jarviss.map_questions import answer_map, parse_question
from jarviss.atlas import MapCatalog, TileArchive, feature_key
from tests.test_core import fixture


class RoutingTests(unittest.TestCase):
    def test_middle_of_long_segment(self):
        p=fixture();p['nodes']={'a':[40,-74.008],'b':[40,-73.992]}
        p['roads']=[{'nodes':['a','b'],'walkable':True,'name':'Long Road'}]
        route=OfflineMap(p).route([40,-74.002],[40,-73.998])
        self.assertLess(route['start_gap_m'],1)
        self.assertAlmostEqual(route['distance_m'],341,delta=2)
        self.assertIn('east',route['steps'][0]['instruction'])

    def test_mid_segment_reverse_oneway_denied(self):
        p=fixture();p['roads'][0]['oneway']='yes'
        with self.assertRaisesRegex(ValueError,'No connected'):
            OfflineMap(p).route([40,-73.9992],[40,-73.9998])

    def test_turns_have_leg_lengths(self):
        p=fixture();p['roads']=[{'nodes':['1','2'],'name':'First Road','walkable':True},
            {'nodes':['2','3'],'name':'Second Road','walkable':True}]
        route=OfflineMap(p).route(p['nodes']['1'],p['nodes']['3'])
        self.assertEqual(len(route['steps']),2)
        self.assertEqual(route['steps'][1]['action'],'Turn left')
        self.assertEqual(route['steps'][1]['road'],'Second Road')
        self.assertIn('miles',route['steps'][1]['instruction'])

    def test_node_access_restriction_not_crossed(self):
        p=fixture();p['blocked_nodes']=['2']
        self.assertNotIn('2',OfflineMap(p).graph)
        with self.assertRaises(ValueError): OfflineMap(p).route(p['nodes']['1'],p['nodes']['3'])

    def test_intersection_only_joins_shared_osm_nodes(self):
        p=fixture();p['roads']=[{'nodes':['1','2'],'name':'First Road','walkable':True},
            {'nodes':['2','3'],'name':'Second Road','walkable':True}]
        area=OfflineMap(p)
        self.assertEqual(area.resolve_location('First Rd and Second Road')['point'],p['nodes']['2'])
        p['roads'][1]['nodes']=['4','5']
        with self.assertRaisesRegex(ValueError,'No shared intersection'):
            OfflineMap(p).resolve_location('First Road and Second Road')

    def test_road_name_without_position_asks_cross_street(self):
        with self.assertRaisesRegex(ValueError,'cross street'):
            OfflineMap(fixture()).resolve_location('Park Path')

    def test_nearby_saved_position_resolves_road(self):
        found=OfflineMap(fixture()).resolve_location('Park Path',[40,-74])
        self.assertEqual(found['point'],[40,-74])
        self.assertIn('confirm',found['location_note'])

    def test_water_category_does_not_promise_drinkability(self):
        self.assertFalse(matches_place({'kind':'untreated water','category':'water','name':'Lake'},'drinking water'))
        self.assertTrue(matches_place({'kind':'water','category':'drinking_water','name':'Tap'},'drinking water'))
        self.assertTrue(matches_place({'kind':'untreated water','category':'stream','name':'Creek'},'water'))
        self.assertFalse(matches_place({'kind':'medical','category':'pharmacy','name':'Drugstore'},'hospital'))

    def test_standing_water_matches_by_name_within_its_group(self):
        self.assertTrue(matches_place({'kind':'water','name':'Rowan Pond'},'pond'))
        self.assertTrue(matches_place({'kind':'water','name':'Unnamed water'},'water source'))
        self.assertFalse(matches_place({'kind':'restaurant','category':'restaurant','name':'Pond Cafe'},'pond'))

    def test_resource_names_do_not_override_recorded_categories(self):
        for query,category,name in [
            ('hospital','pet','LiveWell Animal Hospital'),
            ('hospital','memorial','Former Hospital'),
            ('pharmacy','restaurant','Old Pharmacy Cafe'),
            ('river','restaurant','River Cafe'),
        ]:
            with self.subTest(query=query,category=category):
                place={'kind':category,'category':category,'name':name}
                self.assertFalse(matches_place(place,query))
                self.assertTrue(matches_place(place,name))


class QuestionTests(unittest.TestCase):
    def setUp(self):
        self.area=OfflineMap(fixture());self.profile={'lat':40,'lon':-74}

    def answer(self,q,previous=None):
        with patch('socket.socket',side_effect=AssertionError('Network forbidden')):
            return answer_map(q,self.profile,self.area,previous)

    def test_distance_phrasings(self):
        for q in ['How many miles to Recorded fountain?','How far is Recorded fountain?',
                  "I'm on Park Path. How do I get to Recorded fountain?",
                  'Give me directions to Recorded fountain']:
            with self.subTest(q=q):
                text,route=self.answer(q)
                self.assertIsNotNone(route,text);self.assertIn('miles',text)
                self.assertIn('Park Path',text)

    def test_water_source_alias_finds_recorded_water(self):
        for question in ['what is the nearest water source','Where is the closest water source?']:
            with self.subTest(question=question):
                text,route=self.answer(question)
                self.assertIsNotNone(route,text);self.assertEqual(route['destination'],'Recorded fountain')
                self.assertIn('Do not assume water is safe',text)

    def test_find_drinking_water(self):
        self.assertEqual(parse_question('Where can I find drinking water?')['target'],'drinking water')
        self.assertIsNotNone(self.answer('Where can I find drinking water?')[1])

    def test_running_water_finds_a_waterway_and_routes_offline(self):
        pack=fixture()
        pack['places'] += [
            {'id':'pond','name':'Nearby pond','kind':'untreated water','category':'pond','point':[40,-73.999]},
            {'id':'stream','name':'Recorded creek','kind':'untreated water','category':'stream','point':[40.001,-73.999]}]
        self.area=OfflineMap(pack)
        for question in ['Hey, how do I get to the closest running water?',
                         "I'm on Park Path. Where is the nearest flowing water?",
                         'Where is the nearest running water and how do I walk there?',
                         'Where is the nearest running water, and can you give me directions?',
                         'Where is the closest running water? Give me directions to it.',
                         'Where is the nearest running water from here?',
                         'Where is the closest running water near me?',
                         'Where is the nearest running water and how do I walk there/']:
            with self.subTest(question=question):
                text,route=self.answer(question)
                self.assertIsNotNone(route,text)
                self.assertEqual(route['destination'],'Recorded creek')
                self.assertIn('Park Path',text)
                self.assertIn('miles',text)
                self.assertIn('Current flow is unknown',text)
                self.assertNotIn('Nearby pond',text)
                self.assertNotIn('Recorded fountain',text)
                self.assertIn('Access to the water is unverified', text)
                self.assertIn('bridge', route['destination_note'])

    def test_named_origin_and_directions_are_separate_from_resource(self):
        for question in [
            "I'm at Recorded fountain. Where is the nearest water and how do I walk there?",
            'Where is the nearest water near Recorded fountain, and how far is it?',
            'Where is the closest water to Recorded fountain and give me directions',
            'From Recorded fountain to the nearest water, please',
        ]:
            with self.subTest(question=question):
                intent = parse_question(question)
                self.assertEqual(intent['origin'], 'Recorded fountain')
                self.assertEqual(intent['target'], 'water')
                text, route = answer_map(question, {}, self.area)
                self.assertIsNotNone(route, text)
                self.assertEqual(route['origin'], self.area.pack['places'][0]['point'])

    def test_named_origin_does_not_silently_fall_back_to_saved_position(self):
        text, route = self.answer('Where is the nearest water near Atlantis and how do I walk there?')
        self.assertIsNone(route)
        self.assertNotIn('Mapped walk', text)

    def test_place_names_with_and_are_preserved(self):
        self.assertEqual(parse_question('Directions to Bread and Water Cafe')['target'], 'Bread and Water Cafe')
        self.assertEqual(parse_question("I'm on First Road and Second Street. Where is the nearest water?")['origin'], 'First Road and Second Street')

    def test_running_water_does_not_substitute_a_tap(self):
        text,route=self.answer('Where is the closest running water?')
        self.assertIsNone(route)
        self.assertIn('No “running water” records',text)

    def test_nearest_hospital_routes_to_human_hospital(self):
        pack=fixture()
        pack['places'] += [
            {'id':'vet','name':'Animal Hospital','kind':'veterinary','category':'veterinary','point':[40,-73.9995]},
            {'id':'memorial','name':'Former Hospital','kind':'memorial','category':'memorial','point':[40,-73.999]},
            {'id':'hospital','name':'Recorded General Hospital','kind':'medical','category':'hospital','point':[40.001,-73.999]}]
        self.area=OfflineMap(pack)
        text,route=self.answer('Where is the nearest hospital?')
        self.assertIsNotNone(route,text)
        self.assertEqual(route['destination'],'Recorded General Hospital')
        self.assertNotIn('Animal Hospital',text)
        self.assertNotIn('Former Hospital',text)

    def test_arbitrary_category_does_not_fall_through_to_model(self):
        text,route=self.answer('Where is the nearest bicycle repair shop?')
        self.assertIn('No “bicycle repair shop” records',text);self.assertIsNone(route)

    def test_unrelated_request_is_not_map_intent(self):
        self.assertIsNone(self.answer('How should I ration my stored water?'))

    def test_missing_origin_and_destination_ask(self):
        text,_=answer_map("I'm on Park Path. How do I get to Recorded fountain?",{},self.area)
        self.assertIn('cross street',text)
        self.assertIn('Which destination',self.answer('Give me directions')[0])

    def test_followup_uses_previous_destination(self):
        _,route=self.answer('nearest water')
        for question in ['Give me directions', 'How do I walk there?', 'How far is it?']:
            with self.subTest(question=question):
                text,new=self.answer(question,route)
                self.assertEqual(new['destination'],'Recorded fountain')
                self.assertIn('miles',text)

    def test_followup_retains_explicit_origin(self):
        previous={'destination':'Recorded fountain','destination_point':[40.001,-73.999],
                  'origin':[40,-73.9995],'destination_kind':'water'}
        _,route=self.answer('Give me directions',previous)
        self.assertEqual(route['origin'],previous['origin'])

    def test_unknown_named_destination_does_not_invent(self):
        text,route=self.answer('How many miles to Atlantis?')
        self.assertIn('No “Atlantis” records',text);self.assertIsNone(route)

    def test_duplicate_names_are_not_silently_chosen(self):
        p=fixture();p['places'].append(dict(p['places'][0],id='second',point=[40.002,-74]))
        text,route=answer_map('Directions to Recorded fountain',self.profile,OfflineMap(p))
        self.assertIn('Several records',text);self.assertIsNone(route)

    def test_generic_road_cannot_overwrite_saved_position(self):
        text,route=self.answer("I'm on this road. How do I get to water?")
        self.assertIsNone(route);self.assertEqual(self.profile,{'lat':40,'lon':-74})

    def test_basemap_never_invents_walking_topology(self):
        catalog=MapCatalog()
        with self.assertRaisesRegex(ValueError,'US offline directions are not installed'):
            catalog.route([40,-74],[40.01,-74])

    def test_idless_features_keep_one_identity_across_tile_clips(self):
        from shapely.geometry import LineString
        whole=LineString([(-97.7512,30.2703),(-97.7412,30.2713)])
        clipped=LineString([(-97.7511996,30.2703001),(-97.7412,30.2713)])
        self.assertEqual(feature_key('Shoal Creek','untreated water',whole),feature_key('shoal creek','untreated water',clipped))
        self.assertNotEqual(feature_key('Shoal Creek','untreated water',whole),feature_key('Waller Creek','untreated water',whole))
        self.assertNotEqual(feature_key('Shoal Creek','untreated water',whole),feature_key('Shoal Creek','road',whole))

    def test_empty_query_returns_resources_only(self):
        pack=fixture();pack['places']+=[{'id':'node/8','name':'Post box','kind':'post box','point':[40,-74]},
                                        {'id':'node/9','name':'Bin','kind':'waste basket','category':'waste_basket','point':[40,-74]},
                                        {'id':'node/10','name':'Shop','kind':'supermarket','category':'supermarket','point':[40,-74]}]
        self.assertEqual([p['id'] for p in OfflineMap(pack).nearest([40,-74])],['node/10','node/3','node/5'])
        self.assertEqual([p['id'] for p in OfflineMap(pack).nearest([40,-74],'post box')],['node/8'])
        self.assertFalse(matches_place({'id':'tile/pois/1','name':'Post box','kind':'post box','category':'post_box'},''))
        self.assertTrue(matches_place({'id':'tile/pois/2','name':'Creek','kind':'untreated water','category':'stream'},''))
        archive=SimpleNamespace(pack={},contains=lambda p:True,nearest=lambda point,query='',limit=8:[])
        self.assertEqual([p['id'] for p in MapCatalog([OfflineMap(pack)],archive).nearest([40,-74])],['node/10','node/3','node/5'])

    def test_catalog_merges_a_pack_place_with_its_basemap_copy(self):
        copy={'id':'tile/pois/1','name':'Recorded Fountain','kind':'untreated water','point':[40.0015,-73.999],'distance_m':170}
        other={'id':'tile/pois/2','name':'Recorded Fountain','kind':'untreated water','point':[40.004,-73.999],'distance_m':445}
        archive=SimpleNamespace(pack={},contains=lambda p:True,nearest=lambda point,query='',limit=8:[copy,other])
        rows=MapCatalog([OfflineMap(fixture())],archive).nearest([40,-74],'water')
        self.assertEqual([r['id'] for r in rows],['node/3','tile/pois/2'])


class RealArchiveTests(unittest.TestCase):
    @unittest.skipUnless(Path('local-maps/us-z15.pmtiles').exists(),'Local US archive not installed')
    def test_real_archive_search_without_network(self):
        with patch('socket.socket',side_effect=AssertionError('Network forbidden')):
            archive=TileArchive('local-maps/us-z15.pmtiles')
            self.assertTrue(archive.contains([30.2672,-97.7431]))
            self.assertFalse(archive.contains([30,-140]))
            self.assertTrue(archive.contains([51.88,-176.6581]))
            rows=archive.nearest([30.2672,-97.7431],'water',3)
            self.assertTrue(rows)
            self.assertTrue(all(r['distance_m']<=5000 for r in rows))
            waterways=archive.nearest([30.2672,-97.7431],'running water',3)
            self.assertTrue(waterways)
            self.assertTrue(all(r['category'] in ('river','stream','spring') for r in waterways))
            self.assertTrue(all(r['source']=='offline basemap' for r in rows))
            pharmacy=archive.nearest([30.2672,-97.7431],'pharmacy',3)
            self.assertTrue(pharmacy)
            self.assertTrue(all('pharmacy' in (r['category']+r['name']).lower() for r in pharmacy))


if __name__=='__main__':unittest.main()
