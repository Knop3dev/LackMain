import argparse, dataclasses, getpass, json, multiprocessing, pathlib, signal, sys, time
from config import VERSION, Settings, data_directory, load, save

def format_rate(value):
    for scale, label in [(1000000000.0, 'GH/s'), (1000000.0, 'MH/s'), (1000.0, 'kH/s'), (1, 'H/s')]:
        if value >= scale or scale == 1:
            return f'{value / scale:.3f} {label}'

def parser():
    p = argparse.ArgumentParser(prog='lackminer-lbtc', description='LBTC CPU and OpenCL miner')
    p.add_argument('--version', action='version', version=VERSION)
    p.add_argument('--config', type=pathlib.Path)
    p.add_argument('--address')
    p.add_argument('--mode', choices=['solo', 'pool'])
    p.add_argument('--node')
    p.add_argument('--devices', '--device', dest='devices', help='Comma-separated OpenCL IDs or all')
    p.add_argument('--no-gpu', action='store_true')
    p.add_argument('--cpu-workers', type=int)
    p.add_argument('--intensity', type=int)
    p.add_argument('--worksize', type=int)
    p.add_argument('--batch', type=int)
    p.add_argument('--max-temperature', type=int)
    p.add_argument('--max-hotspot', type=int)
    p.add_argument('--power-w', type=int)
    p.add_argument('--power-percent', type=int)
    p.add_argument('--core-mhz', type=int)
    p.add_argument('--memory-mhz', type=int)
    p.add_argument('--apply-tuning', action='store_true')
    p.add_argument('--wallet', type=pathlib.Path)
    p.add_argument('--key-prompt', action='store_true')
    p.add_argument('--panel', action='store_true')
    p.add_argument('--gui', action='store_true')
    p.add_argument('--port', type=int, default=8808)
    p.add_argument('--no-browser', action='store_true')
    p.add_argument('--start', action='store_true', help='Start mining when opening the local panel')
    p.add_argument('--list-devices', action='store_true')
    p.add_argument('--self-test', action='store_true')
    p.add_argument('--benchmark', action='store_true')
    p.add_argument('--seconds', type=float, default=10)
    return p

def main(argv=None):
    args = parser().parse_args(argv)
    from backend import list_devices, OpenCL
    devices = list_devices()
    if args.list_devices:
        print(json.dumps({'devices': devices, 'cpu_workers_available': multiprocessing.cpu_count()}, indent=2))
        return 0
    directory = args.config.parent if args.config else data_directory()
    path = args.config or directory / 'settings.json'
    settings = load(path)
    for name in ['address', 'mode', 'node', 'cpu_workers', 'intensity', 'worksize', 'batch', 'max_temperature', 'max_hotspot']:
        value = getattr(args, name)
        if value is not None:
            setattr(settings, name, value)
    if args.devices is not None:
        settings.devices = [x['id'] for x in devices] if args.devices == 'all' else [int(x.strip()) for x in args.devices.split(',')]
    if args.no_gpu:
        settings.devices = []
    if not devices and args.devices is None and (not settings.cpu_workers):
        settings.devices = []
        settings.cpu_workers = 1
    settings.validate()
    changes = {k: getattr(args, k) for k in ['power_w', 'power_percent', 'core_mhz', 'memory_mhz'] if getattr(args, k) is not None}
    if changes:
        for device in settings.devices:
            settings.tuning[str(device)] = {**settings.tuning.get(str(device), {}), **changes}
    settings.validate()
    if args.benchmark or args.self_test:
        if not 0.1 <= args.seconds <= 3600:
            raise ValueError('Benchmark duration must be 0.1..3600 seconds')
        from selftest import check, benchmark, example
        from cpu import scan
        from work_nonce import split_job
        head, tail = split_job(example())
        started = time.perf_counter()
        scan((head, tail, 10 ** 12, 20000, 0))
        cpu = 20000 / (time.perf_counter() - started)
        print(json.dumps({'CPU_reference_H_s': cpu}))
        for identifier in settings.devices:
            engine = OpenCL(device=identifier)
            try:
                count = check(engine)
                print(json.dumps({'device': identifier, 'self_test_nonces': count, 'result': 'PASS'}))
                if args.benchmark:
                    row = benchmark(engine, args.seconds, min(settings.worksize, engine.max_workgroup), settings.batch)
                    row['GPU_CPU_ratio'] = row['H_s'] / cpu
                    print(json.dumps(row))
            finally:
                engine.close()
        return 0
    from miner import Miner
    miner = Miner(settings, directory)
    if args.gui:
        from gui import Window
        Window(miner).run()
        return 0
    if args.panel:
        from dashboard import launch
        server, url = launch(miner, args.port, not args.no_browser)
        print(url, flush=True)
        if args.start:
            miner.start()
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            miner.stop()
            server.shutdown()
        return 0
    settings.validate(require_address=True)
    if args.apply_tuning:
        miner.apply_tuning()
    if settings.mode == 'solo':
        if args.key_prompt:
            miner.unlock(key_hex=getpass.getpass('LBTC private key (hidden, local only): '))
        elif args.wallet:
            miner.unlock(wallet_file=args.wallet, password=getpass.getpass('Wallet password: '))
        else:
            raise ValueError('SOLO needs --key-prompt, --wallet FILE, or unlock in --gui / --panel')
    miner.start()
    try:
        while miner.running() or (not miner.user_stopped and settings.auto_restart and (miner.stats['state'] == 'Error') and (len(miner.restart_history) < 3)):
            d = miner.snapshot()
            print(json.dumps({k: d[k] for k in ('state', 'hashrate', 'average_hashrate', 'accepted', 'rejected', 'stale', 'blocks', 'node_height', 'error')}), flush=True)
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    finally:
        failed = miner.stats['state'] == 'Error'
        miner.stop()
    return 1 if failed else 0
if __name__ == '__main__':
    multiprocessing.freeze_support()
    try:
        sys.exit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
