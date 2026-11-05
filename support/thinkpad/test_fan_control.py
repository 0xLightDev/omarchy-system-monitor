import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class FanControlTest(unittest.TestCase):
    def run_helper(self, mode, enabled='N', busy=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parameter = root / 'parameter'
            parameter.write_text(enabled)
            fan = root / 'fan'
            fan.touch()
            log = root / 'calls'
            modprobe = root / 'modprobe'
            modprobe.write_text('#!/bin/bash\necho "$*" >> "$TEST_ROOT/calls"\n'
                                'if [[ "$1" == -r ]]; then exit "$BUSY"; fi\n'
                                'echo Y > "$TEST_ROOT/parameter"\n')
            modprobe.chmod(0o755)
            script = Path(__file__).with_name('fan-control').read_text()
            script = script.replace('/sys/module/thinkpad_acpi/parameters/fan_control', str(parameter))
            script = script.replace('/sys/module/thinkpad_acpi', directory)
            script = script.replace('/proc/acpi/ibm/fan', str(fan))
            result = subprocess.run(['bash', '-c', script, 'fan-control', mode],
                                    env={**os.environ, 'PATH': f'{directory}:/usr/bin',
                                         'TEST_ROOT': directory, 'BUSY': str(int(busy))},
                                    capture_output=True, text=True)
            return result, fan.read_text(), log.read_text() if log.exists() else ''

    def test_activation_and_modes(self):
        for mode, expected in [('enable', ''), ('max', 'level 7\n'),
                               ('auto', 'level auto\n'), ('full-speed', 'level full-speed\n')]:
            with self.subTest(mode=mode):
                result, fan, calls = self.run_helper(mode)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(fan, expected)
                self.assertEqual(calls, '-r thinkpad_acpi\nthinkpad_acpi fan_control=1\n')

    def test_enabled_driver_is_not_reloaded(self):
        result, fan, calls = self.run_helper('max', enabled='Y')
        self.assertEqual((result.returncode, fan, calls), (0, 'level 7\n', ''))

    def test_invalid_mode_has_no_side_effects(self):
        result, fan, calls = self.run_helper('invalid')
        self.assertEqual((result.returncode, fan, calls), (2, '', ''))

    def test_busy_driver_is_reported_without_writing_fan(self):
        result, fan, calls = self.run_helper('max', busy=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('driver is busy', result.stderr)
        self.assertEqual((fan, calls), ('', '-r thinkpad_acpi\n'))


if __name__ == '__main__':
    unittest.main()
