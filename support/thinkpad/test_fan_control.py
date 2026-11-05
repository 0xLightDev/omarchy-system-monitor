import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class FanControlTest(unittest.TestCase):
    def run_helper(self, mode, enabled='N', busy=False, fan_present=True,
                   fail_configured_load=False, model_version='ThinkPad T530'):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parameter = root / 'parameter'
            parameter.write_text(enabled)
            dmi = root / 'product_version'
            dmi.write_text(model_version)
            fan = root / 'fan'
            if fan_present:
                fan.touch()
            log = root / 'calls'
            modprobe = root / 'modprobe'
            modprobe.write_text('#!/bin/bash\necho "$*" >> "$TEST_ROOT/calls"\n'
                                'if [[ "$1" == -r ]]; then exit "$BUSY"; fi\n'
                                'if [[ "$1" == thinkpad_acpi && "${2:-}" == fan_control=1 && "$FAIL_CONFIGURED_LOAD" == 1 ]]; then exit 1; fi\n'
                                'echo Y > "$TEST_ROOT/parameter"\n')
            modprobe.chmod(0o755)
            script = Path(__file__).with_name('fan-control').read_text()
            script = script.replace('/usr/bin/modprobe', str(modprobe))
            script = script.replace('/sys/class/dmi/id/product_version', str(dmi))
            script = script.replace('/sys/module/thinkpad_acpi/parameters/fan_control', str(parameter))
            script = script.replace('/sys/module/thinkpad_acpi', directory)
            script = script.replace('/proc/acpi/ibm/fan', str(fan))
            result = subprocess.run(['bash', '-c', script, 'fan-control', mode],
                                    env={**os.environ, 'PATH': f'{directory}:/usr/bin',
                                         'TEST_ROOT': directory, 'BUSY': str(int(busy)),
                                         'FAIL_CONFIGURED_LOAD': str(int(fail_configured_load))},
                                    capture_output=True, text=True)
            return result, fan.read_text() if fan.exists() else None, log.read_text() if log.exists() else ''

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

    def test_non_t530_hardware_is_rejected_before_driver_changes(self):
        result, fan, calls = self.run_helper('max', model_version='ThinkPad X1 Carbon')
        self.assertEqual(result.returncode, 1)
        self.assertIn('only supported on ThinkPad T530', result.stderr)
        self.assertEqual((fan, calls), ('', ''))

    def test_busy_driver_is_reported_without_writing_fan(self):
        result, fan, calls = self.run_helper('max', busy=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('driver is busy', result.stderr)
        self.assertEqual((fan, calls), ('', '-r thinkpad_acpi\n'))

    def test_missing_fan_interface_is_reported(self):
        result, fan, calls = self.run_helper('max', enabled='Y', fan_present=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn('fan control is unavailable', result.stderr)
        self.assertEqual((fan, calls), (None, ''))

    def test_failed_configured_module_load_does_not_write_fan(self):
        result, fan, calls = self.run_helper('max', fail_configured_load=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Could not load the ThinkPad fan driver', result.stderr)
        self.assertEqual((fan, calls), ('', '-r thinkpad_acpi\nthinkpad_acpi fan_control=1\nthinkpad_acpi\n'))


if __name__ == '__main__':
    unittest.main()
