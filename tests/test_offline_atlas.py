import unittest
from pathlib import Path
from unittest.mock import patch
from jarviss.maps import OfflineMap, build_pack, matches_place
from jarviss.map_questions import answer_map, parse_question
from jarviss.atlas import MapCatalog, TileArchive
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

    def test_find_drinking_water(self):
        self.assertEqual(parse_question('Where can I find drinking water?')['target'],'drinking water')
        self.assertIsNotNone(self.answer('Where can I find drinking water?')[1])

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
        text,new=self.answer('Give me directions',route)
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
            self.assertTrue(all(r['source']=='offline basemap' for r in rows))
            pharmacy=archive.nearest([30.2672,-97.7431],'pharmacy',3)
            self.assertTrue(pharmacy)
            self.assertTrue(all('pharmacy' in (r['category']+r['name']).lower() for r in pharmacy))


if __name__=='__main__':unittest.main()
