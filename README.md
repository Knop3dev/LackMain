# lackminer LBTC

CPU and OpenCL miner for [Late Bitcoiners](https://latebitcoiners.com/). SOLO, official HTTPS pool, desktop GUI and optional local web panel.

[Русская инструкция](README.ru.md) · [Downloads](https://github.com/Knop3dev/LackMain/releases/tag/lbtc-v0.1.0)

## Start

**Windows:** extract the archive and open `lackminer-lbtc-gui.exe`. Enter your LBTC address, choose SOLO or Pool, select devices and save. Unlock your wallet locally for SOLO; pool mining only needs a public address. Press **Start mining**.

**Linux:** extract the archive, run `chmod +x lackminer-lbtc lackminer-lbtc-gui`, then open `./lackminer-lbtc-gui` or use the command line.

**macOS:** choose Intel or Apple Silicon and open the GUI app. The application is unsigned; approval may be required in Privacy & Security. GPU support depends on the OpenCL devices exposed by macOS. CPU mining does not require OpenCL. Clock and power controls are unavailable on macOS.

## Commands

```sh
lackminer-lbtc --list-devices
lackminer-lbtc --mode pool --address YOUR_LBTC_ADDRESS --devices all
lackminer-lbtc --mode solo --address YOUR_LBTC_ADDRESS --devices 0,1 --key-prompt
lackminer-lbtc --mode pool --address YOUR_LBTC_ADDRESS --no-gpu --cpu-workers 4
lackminer-lbtc --panel
```

Replace `YOUR_LBTC_ADDRESS` with your address. Instead of `--key-prompt`, use `--wallet /path/to/wallet.json` for an encrypted official wallet file. Passwords and private keys are requested locally, never passed as command-line arguments or saved by the miner. Unlocking is required after process restart.

Add `--cpu-workers` to a GPU command to use both. Workers search separate nonce ranges; all results use the same CPU verification. There is no additional miner fee.

The panel listens on `127.0.0.1:8808` and waits for a Start command. `--panel --start` explicitly starts a configured pool miner. Do not expose this port directly to the Internet; use an SSH tunnel.

## GPU settings

Driver settings remain unchanged on startup. Blank tuning fields mean **keep the driver setting**. Saved tuning is not applied automatically. Use **Save & apply** in the GUI or `--apply-tuning` in the CLI.

| Option | Meaning |
| --- | --- |
| `--devices 0,1` / `all` | OpenCL device selection |
| `--intensity 80` | Work/idle pacing, 1–100% |
| `--worksize 128` | Workgroup: 32, 64, 128 or 256 |
| `--batch 1048576` | Nonces per GPU dispatch |
| `--power-w 120` | NVIDIA/Linux driver power cap; telemetry-based pause where a cap is unavailable |
| `--power-percent -10` | AMD Windows driver power adjustment |
| `--core-mhz VALUE` | Requested core clock |
| `--memory-mhz VALUE` | Requested memory clock |
| `--max-temperature 80` | Pause at this GPU temperature, when a sensor is available |
| `--max-hotspot 85` | Pause at this hotspot temperature, when a sensor is available |

Windows AMD uses the official ADLX SDK; NVIDIA uses `nvidia-smi`; Linux AMD uses sysfs. Unsupported controls return an error. Driver permissions may be required. Voltage is not adjusted. Memory clock units follow the driver's convention. Restore returns NVIDIA locked clocks to driver management and restores captured AMD settings. A telemetry-based pause is not a physical board power limiter. Hardware telemetry is shown only when available.

OpenCL 1.2 devices are discovered without a model whitelist. AMD/NVIDIA require their vendor's OpenCL driver; Intel and Apple devices may also be listed. The startup self-test checks digest equality and strict target comparison. Enumeration alone does not prove that a driver can compile the kernel. Other hardware requires on-device verification.

## SOLO and pool

SOLO signs blocks locally and submits them over HTTPS. Coinbase pays the configured address plus the founder output required by the current node policy.

Pool mode follows the official v67 HTTPS API: `/api/pool/info` and `/api/pool/share`. The pool supplies its reward address and share factor; the participant address is included in the coinbase memo. The pool handles block signing, accounting and payouts. View rewards and withdraw on [the official pool page](https://latebitcoiners.com/pool/). No Stratum URL is used. Pool connectivity requires these official endpoints to be available.

Network timing and eligibility rules are respected. A ready solution waits for its permitted submission time, so current hashrate can be zero while a block is prepared. More hashrate does not guarantee winning every block. A pending SOLO solution is retained through restart and checked against the current parent. Automatic recovery is limited to three restarts in ten minutes.

## Hive OS

Create a Custom miner flight sheet:

| Field | Value |
| --- | --- |
| Miner name | `lackminer-lbtc` |
| Installation URL | `https://github.com/Knop3dev/LackMain/releases/download/lbtc-v0.1.0/lackminer-lbtc-0.1.0-hiveos.tar.gz` |
| Wallet template | Your LBTC address |
| Pool URL | Leave empty |
| Extra config | `pool` or `solo` |

Pool mode starts all detected GPUs. Hive OS manages the rig's clocks; the miner applies no tuning automatically. SOLO requires a local unlock through the panel: use `ssh -L 8808:127.0.0.1:8808 user@rig`, then open `http://127.0.0.1:8808`. A rig restart locks the SOLO wallet again. Private keys do not belong in flight sheets.

The Linux build targets glibc 2.31 or newer. Compatible OpenCL drivers are required.

## Build and test

Python 3.12+:

```sh
pip install -r requirements.txt pyinstaller==6.16.0
python -m unittest discover -s tests -v
```

On Windows, first build the AMD helper with `cmake -S native -B build/native` and `cmake --build build/native --config Release`. Then run `python tools/package.py`. Linux GUI builds need Tk installed. GitHub Actions builds Windows x64, Linux x64, macOS Intel and Apple Silicon from the same source.

`--self-test` checks an installed OpenCL driver. `--benchmark --seconds 30` measures actual nonce searches and a CPU reference on synthetic work without submitting blocks or shares.

Configuration and runtime data stay in the current user's application-data directory. Use `--config FILE` to choose another location.

## License

Includes modified LBTC reference code under the [Community Software License](LICENSE.txt). Windows archives include the AMD ADLX SDK license.
