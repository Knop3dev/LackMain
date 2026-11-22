import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    def run_launcher(self, saved_power=None, answer=''):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            if os.name == 'nt':
                script = (ROOT / 'start-windows.ps1').read_text().replace("'lackminer-qbtc.exe'", "'mock.ps1'")
                (root / 'start-windows.ps1').write_text(script)
                (root / 'mock.ps1').write_text("ConvertTo-Json -InputObject @($args) -Compress | Add-Content -LiteralPath (Join-Path $PSScriptRoot 'calls.jsonl'); $global:LASTEXITCODE=0\n")
                if saved_power is not None:
                    (root / 'miner-config.json').write_text(json.dumps({'max_power': saved_power}))
                answers = ['', '', 'test-wallet', '', answer, '', '', 'YES']
                entries = ','.join("'" + a + "'" for a in answers)
                (root / 'run.ps1').write_text("$global:answers=[System.Collections.Generic.Queue[string]]::new(); @(" + entries + ") | ForEach-Object {$global:answers.Enqueue($_)}; function Read-Host {param($Prompt) $global:answers.Dequeue()}; & (Join-Path $PSScriptRoot 'start-windows.ps1')\n")
                command = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(root / 'run.ps1')]
                result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=20)
            else:
                (root / 'start-linux.sh').write_text((ROOT / 'start-linux.sh').read_text())
                (root / 'lackminer-qbtc').write_text("#!/usr/bin/env python3\nimport json,sys\nwith open('calls.jsonl','a') as f:f.write(json.dumps(sys.argv[1:])+'\\n')\n")
                (root / 'lackminer-qbtc').chmod(0o755)
                if saved_power is not None:
                    (root / 'miner-config.txt').write_text('\n0\n' + str(saved_power) + '\n')
                result = subprocess.run(['bash', 'start-linux.sh'], cwd=root, input='\n\ntest-wallet\n\n' + answer + '\n\n\nYES\n', capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            calls = [json.loads(line) for line in (root / 'calls.jsonl').read_text().splitlines()]
            return next(call for call in calls if '--pool' in call)

    def test_first_start_does_not_require_power_sensor(self):
        self.assertNotIn('--max-power', self.run_launcher())

    def test_saved_limit_is_preserved(self):
        args = self.run_launcher(120)
        self.assertEqual(args[args.index('--max-power') + 1], '120')

    def test_user_can_disable_saved_limit(self):
        self.assertNotIn('--max-power', self.run_launcher(120, '0'))


if __name__ == '__main__':
    unittest.main()
