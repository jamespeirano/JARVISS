"""A case-insensitive checkout must retain the application's Python source."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class SourceDistributionTests(unittest.TestCase):
    def test_application_source_is_not_ignored_on_case_insensitive_filesystems(self):
        git = os.environ.get('GIT_EXECUTABLE') or shutil.which('git')
        if not git:
            self.skipTest('Git is required to check source distribution rules.')
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as temp:
            checkout = Path(temp)
            shutil.copyfile(root / '.gitignore', checkout / '.gitignore')
            subprocess.run([git, 'init', '--quiet', str(checkout)], check=True)
            (checkout / 'jarviss').mkdir()
            for name in ('__init__.py', 'service.py', 'setup.py'):
                (checkout / 'jarviss' / name).touch()
                result = subprocess.run(
                    [git, '-c', 'core.ignorecase=true', 'check-ignore', '--no-index',
                     '--quiet', 'jarviss/' + name], cwd=checkout, capture_output=True)
                self.assertEqual(result.returncode, 1,
                                 f'Application source is ignored: jarviss/{name}')


if __name__ == '__main__':
    unittest.main()
