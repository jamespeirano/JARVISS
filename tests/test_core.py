import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from jarviss.maps import OfflineMap, coordinate, build_pack, distance
from jarviss.assistant import map_answer, messages
from jarviss.assets import extract
from jarviss.library import retrieve


def fixture():
    return {'version': 1, 'center': [40.0, -74.0], 'bounds': [39.99, -74.01, 40.01, -73.99],
            'downloaded_at': '2026-09-13T00:00:00Z',
            'nodes': {'1': [40.0, -74.0], '2': [40.0, -73.999], '3': [40.001, -73.999],
                      '4': [40.006, -73.995], '5': [40.007, -73.995]},
            'roads': [{'nodes': ['1', '2', '3'], 'name': 'Park Path', 'walkable': True},
                      {'nodes': ['4', '5'], 'name': 'Separate Path', 'walkable': True}],
            'places': [{'id': 'node/3', 'name': 'Recorded fountain', 'kind': 'water', 'point': [40.001, -73.999]},
                       {'id': 'node/5', 'name': 'Recorded clinic', 'kind': 'medical', 'point': [40.007, -73.995]}]}


class MapTests(unittest.TestCase):
    def test_distance(self):
        self.assertAlmostEqual(distance((0, 0), (0, 1)), 111195, delta=10)

    def test_coordinates_reject_nan_and_overflow(self):
        for lat, lon in [('nan', 0), (0, 'inf'), (91, 0), (0, 181), ('', 2)]:
            with self.assertRaises(ValueError): coordinate(lat, lon)

    def test_route_uses_connected_graph_offline(self):
        with patch('socket.socket', side_effect=AssertionError('Network forbidden')):
            route = OfflineMap(fixture()).route((40, -74), (40.001, -73.999))
            self.assertEqual(route['roads'], ['Park Path'])
            self.assertEqual(len(route['points']), 3)
            self.assertGreater(route['distance_m'], 190)
            self.assertLess(route['distance_m'], 200)

    def test_no_route_between_disconnected_components(self):
        with self.assertRaisesRegex(ValueError, 'No connected'):
            OfflineMap(fixture()).route((40, -74), (40.007, -73.995))

    def test_outside_map(self):
        with self.assertRaisesRegex(ValueError, 'outside'):
            OfflineMap(fixture()).route((39, -74), (40.001, -73.999))

    def test_private_and_motorway_excluded(self):
        raw = {'elements': [{'type': 'node', 'id': 1, 'lat': 40, 'lon': -74},
                             {'type': 'node', 'id': 2, 'lat': 40.001, 'lon': -74},
                             {'type': 'way', 'id': 3, 'nodes': [1, 2], 'tags': {'highway': 'motorway'}},
                             {'type': 'way', 'id': 4, 'nodes': [1, 2], 'tags': {'highway': 'path', 'access': 'private'}}]}
        pack = build_pack(raw, [40, -74], [39.99, -74.01, 40.01, -73.99], 1)
        self.assertFalse(OfflineMap(pack).graph)

    def test_missing_node_does_not_create_shortcut(self):
        pack = fixture()
        pack['roads'] = [{'nodes': ['1', 'missing', '3'], 'walkable': True, 'name': 'Broken'}]
        self.assertFalse(OfflineMap(pack).graph)

    def test_oneway_foot_is_respected(self):
        pack = fixture(); pack['roads'][0]['oneway'] = 'yes'
        with self.assertRaisesRegex(ValueError, 'No connected'):
            OfflineMap(pack).route((40.001, -73.999), (40, -74))

    def test_nearest_reply_is_grounded_and_qualified(self):
        result = map_answer('Where is the closest water?', {'lat': 40, 'lon': -74}, OfflineMap(fixture()))
        self.assertIn('Recorded fountain', result[0])
        self.assertIn('straight-line', result[0])
        self.assertIn('Do not assume water is safe', result[0])
        self.assertIsNotNone(result[1])

    def test_missing_map_does_not_invent_locations(self):
        text, route = map_answer('nearest hospital', {'lat': 40, 'lon': -74}, None)
        self.assertIn('No offline map', text)
        self.assertIsNone(route)


class ContextTests(unittest.TestCase):
    def test_personal_context_and_references_reach_model(self):
        with patch('jarviss.assistant.retrieve', return_value=[]):
            result = messages({'supplies': '4 liters, one person'}, [], 'What first?')
        self.assertIn('4 liters', result[0]['content'])
        self.assertIn('Choose what comes first', result[0]['content'])
        self.assertNotIn('"question":', result[0]['content'])
        self.assertNotIn('"prompt":', result[0]['content'])
        self.assertEqual(result[-1]['content'], 'What first?')

    def test_reference_retrieval(self):
        docs = [{'title': 'filter.md', 'imported_at': 'today', 'text': 'Replace the ceramic water filter cartridge.'},
                {'title': 'bike.md', 'imported_at': 'today', 'text': 'Inflate the bicycle tire.'}]
        found = retrieve('water filter', docs)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['title'], 'filter.md')

    def test_archive_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            archive = Path(root) / 'test.zip'
            with zipfile.ZipFile(archive, 'w') as z: z.writestr('../outside.txt', 'bad')
            with self.assertRaises(ValueError): extract(archive, Path(root) / 'out')
            self.assertFalse((Path(root) / 'outside.txt').exists())


if __name__ == '__main__':
    unittest.main()
