"""Model recommendations must not count shared graphics memory twice."""
import unittest
from unittest.mock import patch

from jarviss import hardware
from jarviss.hardware import GIB, gb, recommend

MODELS = [{'id':'compact', 'memory_gib':5}, {'id':'balanced', 'memory_gib':8}, {'id':'advanced', 'memory_gib':21}]


def machine(memory, available, gpus=(), unified=False):
    return {'memory':memory*GIB, 'available':available*GIB, 'unified':unified, 'gpus':list(gpus)}


class RecommendTests(unittest.TestCase):
    def test_no_gpu_uses_ram_budget_only(self):
        rows, selected = recommend(MODELS, machine(16, 12))
        self.assertEqual(selected, 'balanced')
        self.assertEqual([r['fits'] for r in rows], [True, True, False])
        self.assertEqual(rows[0]['reason'], 'Uses the CPU; replies may be slower.')

    def test_discrete_gpu_memory_is_extra(self):
        gpu = {'name':'NVIDIA GeForce RTX 4090', 'total':24*GIB, 'available':24*GIB, 'shared':False}
        rows, selected = recommend(MODELS, machine(16, 10, [gpu]))
        self.assertEqual(selected, 'advanced')
        self.assertTrue(all(r['accelerated'] for r in rows))

    def test_integrated_gpu_heap_is_host_ram(self):
        # 5 GiB free RAM cannot hold a 5 GiB model however large the Iris heap claims to be.
        gpu = {'name':'Intel(R) Iris(R) Xe Graphics', 'total':8*GIB, 'available':8*GIB, 'shared':True}
        rows, selected = recommend(MODELS, machine(16, 5, [gpu]))
        self.assertIsNone(selected)
        self.assertEqual(rows[0]['reason'], 'Close other apps or choose a smaller model.')
        rows, selected = recommend(MODELS, machine(16, 12, [gpu]))
        self.assertEqual(selected, 'balanced')
        self.assertFalse(rows[1]['accelerated'])
        self.assertEqual(rows[1]['reason'], 'Uses shared graphics memory; replies may be slower.')

    def test_apple_unified_memory_is_accelerated(self):
        rows, selected = recommend(MODELS, machine(36, 30, unified=True))
        self.assertEqual(selected, 'advanced')
        self.assertTrue(all(r['accelerated'] for r in rows))

    def test_threshold_edge(self):
        # budget = min(available, 80% of memory) - 2 GiB must reach the model size exactly.
        self.assertEqual(recommend(MODELS, machine(32, 7))[1], 'compact')
        self.assertIsNone(recommend(MODELS, machine(32, 6.99))[1])
        gpu = {'name':'NVIDIA GeForce RTX 3060', 'total':12*GIB, 'available':8/.9*GIB, 'shared':False}
        self.assertEqual(recommend(MODELS, machine(8, 4, [gpu]))[1], 'balanced')
        self.assertIsNone(recommend(MODELS, machine(8, 3.99, [gpu]))[1])


class InspectTests(unittest.TestCase):
    def test_vulkan_uma_flag_and_names_mark_shared_adapters(self):
        listing = ('ggml_vulkan: Found 2 Vulkan devices:\n'
                   'ggml_vulkan: 0 = NVIDIA GeForce RTX 3060 (NVIDIA) | uma: 0 | fp16: 1 | warp size: 32\n'
                   'ggml_vulkan: 1 = Custom Adapter (Mesa) | uma: 1 | fp16: 1 | warp size: 32\n'
                   'Available devices:\n'
                   '  Vulkan0: NVIDIA GeForce RTX 3060 (12288 MiB, 11000 MiB free)\n'
                   '  Vulkan1: Custom Adapter (16384 MiB, 16000 MiB free)\n'
                   '  Vulkan2: AMD Radeon(TM) Graphics (8192 MiB, 8000 MiB free)\n')
        result = type('Result', (), {'stdout':listing, 'stderr':'', 'returncode':0})()
        with patch('jarviss.hardware.shutil.which', return_value=None), patch('jarviss.assets.find_server', return_value='llama-server'), \
             patch('jarviss.hardware.subprocess.run', return_value=result), patch('jarviss.hardware.platform.system', return_value='Windows'):
            gpus = hardware.inspect()['gpus']
        self.assertEqual([(g['name'], g['shared']) for g in gpus],
                         [('NVIDIA GeForce RTX 3060', False), ('Custom Adapter', True), ('AMD Radeon(TM) Graphics', True)])

    def test_free_disk_is_the_smaller_of_data_and_temp_volumes(self):
        usage = {'D:': type('Usage', (), {'free':50*GIB})(), 'C:': type('Usage', (), {'free':3*GIB})()}
        with patch('jarviss.hardware.ROOT', 'D:'), patch('jarviss.hardware.tempfile.gettempdir', return_value='C:'), \
             patch('jarviss.hardware.shutil.disk_usage', side_effect=usage.__getitem__):
            self.assertEqual(hardware.free_disk(), 3*GIB)

    def test_gb_matches_setup_page_formatting(self):
        self.assertEqual(gb(2*GIB), '2.1 GB')
        self.assertEqual(gb(16551316384), '16.6 GB')


if __name__ == '__main__':
    unittest.main()
