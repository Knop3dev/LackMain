import dataclasses, json, os, pathlib, sys, tempfile
from urllib.parse import urlparse
from wallet import valid_address
VERSION = '0.1.0'

def data_directory():
    override = os.environ.get('LACKMINER_DATA')
    if override:
        return pathlib.Path(override)
    if sys.platform == 'win32':
        base = pathlib.Path(os.environ.get('LOCALAPPDATA', pathlib.Path.home()))
    elif sys.platform == 'darwin':
        base = pathlib.Path.home() / 'Library/Application Support'
    else:
        base = pathlib.Path(os.environ.get('XDG_DATA_HOME', pathlib.Path.home() / '.local/share'))
    return base / 'lackminer-lbtc'

@dataclasses.dataclass
class Settings:
    address: str = ''
    mode: str = 'solo'
    node: str = 'https://latebitcoiners.com'
    devices: list = dataclasses.field(default_factory=lambda: [0])
    cpu_workers: int = 0
    worksize: int = 128
    batch: int = 1048576
    intensity: int = 80
    max_temperature: int = 80
    max_hotspot: int = 85
    auto_restart: bool = True
    tuning: dict = dataclasses.field(default_factory=dict)

    def validate(self, require_address=False):
        if self.address and (not valid_address(self.address)):
            raise ValueError('Invalid LBTC address checksum')
        if require_address and (not self.address):
            raise ValueError('Set your LBTC payout address')
        if self.mode not in ('solo', 'pool'):
            raise ValueError('Choose solo or pool')
        parsed = urlparse(self.node)
        if parsed.username or parsed.password or parsed.query or parsed.fragment or (parsed.path not in ('', '/')):
            raise ValueError('Use a node origin without credentials or a path')
        if parsed.scheme != 'https' and (not (parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost', '::1'))):
            raise ValueError('Remote nodes require HTTPS')
        if not isinstance(self.devices, list) or any((type(x) is not int or x < 0 for x in self.devices)) or len(set(self.devices)) != len(self.devices):
            raise ValueError('Invalid device selection')
        if type(self.cpu_workers) is not int or not 0 <= self.cpu_workers <= 256:
            raise ValueError('CPU workers must be 0..256')
        if not self.devices and (not self.cpu_workers):
            raise ValueError('Select a GPU or at least one CPU worker')
        if self.worksize not in (32, 64, 128, 256):
            raise ValueError('Workgroup must be 32, 64, 128 or 256')
        if type(self.batch) is not int or not self.worksize <= self.batch <= 16777216 or self.batch % self.worksize:
            raise ValueError('Batch must be divisible by workgroup, at most 16777216')
        if type(self.intensity) is not int or not 1 <= self.intensity <= 100:
            raise ValueError('Intensity must be 1..100')
        if not 40 <= self.max_temperature <= 85 or not 40 <= self.max_hotspot <= 100:
            raise ValueError('Invalid thermal limits')
        if type(self.auto_restart) is not bool or not isinstance(self.tuning, dict):
            raise ValueError('Invalid settings')
        for device, values in self.tuning.items():
            if not str(device).isdigit() or not isinstance(values, dict):
                raise ValueError('Invalid tuning device')
            for field, value in values.items():
                if field not in ('power_w', 'power_percent', 'core_mhz', 'memory_mhz', 'fan_percent'):
                    raise ValueError('Unknown tuning field')
                if value is not None and (type(value) is not int or (not -50 <= value <= 50 if field == 'power_percent' else not 1 <= value <= 10000) or (field == 'fan_percent' and value > 100)):
                    raise ValueError('Invalid tuning value')
        return self

def load(path):
    path = pathlib.Path(path)
    if not path.exists():
        return Settings()
    value = json.loads(path.read_text(encoding='utf8'))
    known = {f.name for f in dataclasses.fields(Settings)}
    if set(value) - known:
        raise ValueError('Unknown configuration fields')
    return Settings(**value).validate()

def save(path, settings):
    settings.validate()
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.settings-')
    try:
        with os.fdopen(fd, 'w', encoding='utf8') as f:
            json.dump(dataclasses.asdict(settings), f, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
