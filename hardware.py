import json, os, pathlib, re, shutil, subprocess, sys, threading, time

def command(args):
    flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    result = subprocess.run(args, capture_output=True, text=True, timeout=10, **flags)
    if result.returncode:
        raise RuntimeError('GPU driver refused the requested setting')
    return result.stdout

def number(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

class Hardware:

    def __init__(self):
        self.lock = threading.RLock()
        self.cache = {}
        self.restore_actions = []
        self.adl = None
        self.helpers = []

    def read(self, device):
        pci = device.get('pci')
        if not pci:
            return {}
        with self.lock:
            cached = self.cache.get(pci)
            if cached and time.monotonic() - cached[0] < 1:
                return cached[1]
            result = {}
            try:
                if 'NVIDIA' in device['vendor'].upper() and shutil.which('nvidia-smi'):
                    fields = ['temperature.gpu', 'utilization.gpu', 'power.draw', 'clocks.gr', 'clocks.mem', 'fan.speed']
                    text = command(['nvidia-smi', '-i', pci, '--query-gpu=' + ','.join(fields), '--format=csv,noheader,nounits'])
                    result = dict(zip(['temperature_c', 'utilization_percent', 'power_w', 'core_mhz', 'memory_mhz', 'fan_percent'], [number(x.strip()) for x in text.strip().split(',')]))
                elif os.name == 'nt' and ('AMD' in device['vendor'].upper() or 'ADVANCED MICRO' in device['vendor'].upper()):
                    if self.adl is None:
                        from adl import ADL
                        self.adl = ADL()
                    result = self.adl.read(pci)
                elif sys.platform.startswith('linux'):
                    base = pathlib.Path('/sys/bus/pci/devices') / pci
                    paths = list((base / 'hwmon').glob('hwmon*'))
                    if paths:
                        hw = paths[0]
                        for file, key, scale in [('temp1_input', 'temperature_c', 1000), ('temp2_input', 'hotspot_c', 1000), ('power1_average', 'power_w', 1000000.0), ('freq1_input', 'core_mhz', 1000000.0), ('freq2_input', 'memory_mhz', 1000000.0), ('fan1_input', 'fan_rpm', 1)]:
                            try:
                                result[key] = int((hw / file).read_text()) / scale
                            except (OSError, ValueError):
                                pass
                    try:
                        result['utilization_percent'] = int((base / 'gpu_busy_percent').read_text())
                    except (OSError, ValueError):
                        pass
            except Exception:
                result = {}
            self.cache[pci] = (time.monotonic(), result)
            return result

    def apply(self, devices, tuning):
        with self.lock:
            if self.restore_actions or self.helpers:
                raise ValueError('Restore previous tuning before applying another profile')
            mapped = {str(d['id']): d for d in devices}
            try:
                for identifier, values in tuning.items():
                    requested = {k: v for k, v in values.items() if v is not None}
                    if not requested:
                        continue
                    d = mapped.get(str(identifier))
                    if not d or not d.get('pci'):
                        raise ValueError('Cannot safely map this GPU to the driver')
                    pci = d['pci']
                    vendor = d['vendor'].upper()
                    if 'NVIDIA' in vendor:
                        if requested.get('fan_percent'):
                            raise ValueError('Fan tuning is unavailable through nvidia-smi')
                        if requested.get('power_percent') is not None:
                            raise ValueError('Use watts for NVIDIA power limits')
                        if 'power_w' in requested:
                            text = command(['nvidia-smi', '-i', pci, '--query-gpu=power.limit,power.min_limit,power.max_limit', '--format=csv,noheader,nounits'])
                            current, low, high = map(float, text.strip().split(','))
                            wanted = requested['power_w']
                            if not low <= wanted <= high:
                                raise ValueError('Power limit outside the driver range')
                            self.restore_actions.append(('command', ['nvidia-smi', '-i', pci, '-pl', str(current)]))
                            command(['nvidia-smi', '-i', pci, '-pl', str(wanted)])
                        for field, switch, reset in [('core_mhz', '-lgc', '-rgc'), ('memory_mhz', '-lmc', '-rmc')]:
                            if field in requested:
                                wanted = requested[field]
                                self.restore_actions.append(('command', ['nvidia-smi', '-i', pci, reset]))
                                command(['nvidia-smi', '-i', pci, switch, f'{wanted},{wanted}'])
                    elif os.name == 'nt':
                        sensor = self.read(d)
                        if 'adl_index' not in sensor:
                            raise ValueError('AMD driver mapping is unavailable')
                        exe = pathlib.Path(getattr(sys, '_MEIPASS', pathlib.Path(__file__).parent)) / 'lackminer-amd-control.exe'
                        if not exe.exists():
                            raise ValueError('AMD tuning helper is unavailable in this build')
                        args = [str(exe), '--adl-index=' + str(sensor['adl_index'])]
                        for key, flag in [('core_mhz', 'core'), ('memory_mhz', 'memory'), ('power_percent', 'power')]:
                            if key in requested:
                                args.append('--' + flag + '=' + str(requested[key]))
                        if requested.get('fan_percent'):
                            raise ValueError('Fan tuning is managed by AMD Software')
                        if len(args) == 2:
                            continue
                        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                        self.helpers.append(process)
                        reply = process.stdout.readline()
                        if not reply or not json.loads(reply).get('applied'):
                            raise RuntimeError('AMD driver refused the profile')
                    elif sys.platform.startswith('linux'):
                        base = pathlib.Path('/sys/bus/pci/devices') / pci
                        hw = list((base / 'hwmon').glob('hwmon*'))
                        if not hw:
                            raise ValueError('AMD hwmon is unavailable')
                        if 'power_percent' in requested:
                            raise ValueError('Use watts for Linux power limits')
                        if 'power_w' in requested:
                            path = hw[0] / 'power1_cap'
                            low = int((hw[0] / 'power1_cap_min').read_text())
                            high = int((hw[0] / 'power1_cap_max').read_text())
                            value = requested['power_w'] * 1000000
                            if not low <= value <= high:
                                raise ValueError('Power limit outside the driver range')
                            self.write(path, str(value))
                        if 'core_mhz' in requested or 'memory_mhz' in requested:
                            path = base / 'pp_od_clk_voltage'
                            text = path.read_text()
                            changes = []
                            original = []
                            for field, section, letter, bound in [('core_mhz', 'OD_SCLK', 's', 'SCLK'), ('memory_mhz', 'OD_MCLK', 'm', 'MCLK')]:
                                if field not in requested:
                                    continue
                                block = re.search(section + ':\\s*\\n(.*?)(?=\\n[A-Z_]+:|\\Z)', text, re.S)
                                states = re.findall('(\\d+):\\s*(\\d+)M[hH]z', block.group(1) if block else '')
                                bounds = re.search('\\b' + bound + ':\\s*(\\d+)M[hH]z\\s+(\\d+)M[hH]z', text)
                                if not states or not bounds:
                                    raise ValueError('Driver does not expose a supported clock range')
                                low, high = map(int, bounds.groups())
                                wanted = requested[field]
                                if not low <= wanted <= high:
                                    raise ValueError('Clock outside the driver range')
                                index, old = states[-1]
                                original.append(f'{letter} {index} {old}')
                                changes.append(f'{letter} {index} {wanted}')
                            self.write(base / 'power_dpm_force_performance_level', 'manual')
                            self.restore_actions.append(('od', path, original))
                            for value in changes:
                                path.write_text(value)
                            path.write_text('c')
                        if 'fan_percent' in requested:
                            self.write(hw[0] / 'pwm1_enable', '1')
                            self.write(hw[0] / 'pwm1', str(round(requested['fan_percent'] * 255 / 100)))
                    else:
                        raise ValueError('GPU tuning is unavailable on this platform')
            except Exception:
                self.restore()
                raise

    def write(self, path, value):
        previous = path.read_text()
        self.restore_actions.append(('file', path, previous))
        path.write_text(value)

    def restore(self):
        with self.lock:
            errors = []
            for p in self.helpers:
                try:
                    p.stdin.write('restore\n')
                    p.stdin.flush()
                    if p.wait(timeout=10):
                        errors.append('AMD driver restore needs attention')
                except Exception:
                    errors.append('AMD driver restore needs attention')
            self.helpers = []
            for action in reversed(self.restore_actions):
                try:
                    if action[0] == 'command':
                        command(action[1])
                    elif action[0] == 'od':
                        for value in action[2]:
                            action[1].write_text(value)
                        action[1].write_text('c')
                    else:
                        action[1].write_text(action[2])
                except Exception:
                    errors.append('Previous GPU setting could not be restored')
            self.restore_actions = []
            if errors:
                raise RuntimeError('; '.join(errors))
