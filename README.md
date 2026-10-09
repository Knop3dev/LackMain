# lackminer qbtc

SOLO Q-BTC GPU miner for Windows, Linux and Hive OS. OpenCL backend for AMD and NVIDIA GPUs, with a local Q-BTC node.

**Developer fee: 10% of the full block reward, including transaction fees. The remaining 90% goes to your payout address.**

Fee address: `qbtc10y29nvfuwyxfxhkl4yqkenw4u6hshsk9zgaf5ctz4zfpa2gxe45qtwawce`.

## Download and start

Download your package from [Releases](https://github.com/Knop3dev/LackMain/releases/tag/v0.2.0).

- **Windows:** extract the archive and run `start-windows.cmd`.
- **Linux:** Ubuntu 22.04 or newer, the GPU vendor's OpenCL driver, `curl`, `tar` and `util-linux`. Extract the archive and run `bash start-linux.sh`.

Enter your public Q-BTC address, select a GPU and confirm startup. The launcher downloads the official Q-BTC node v2.5.0 with SHA-256 verification. Mining starts after the node synchronizes and its chain tip matches the explorer. Node data is stored alongside the miner; choose a disk with sufficient space. On Linux, use `LACKMINER_NODE_DIR` to select another directory.

With an existing local node:

```text
lackminer-qbtc --solo --node http://127.0.0.1:24002 --user YOUR_QBTC_ADDRESS --device 0 --max-power 120
```

Press `Ctrl+C` to stop the miner. The node stays running. Launchers restart the miner after an error with a 10-second delay.

## GPU settings

| Option | Purpose |
| --- | --- |
| `--list-devices` | List OpenCL devices and PCI addresses |
| `--device 0` | Select a GPU |
| `--max-power 120` | Pause above the measured power budget; resume below 95% |
| `--intensity 80` | Compute duty cycle, 1–100% |
| `--max-temp 80`, `--max-hotspot 80` | Temperature thresholds in °C; resume 5°C below the limit |
| `--power-limit W` | Driver power limit on NVIDIA and Linux AMD |
| `--power-percent P` | Windows AMD power limit adjustment in percent |
| `--core-clock MHz` | Windows AMD maximum clock; Linux AMD profile reduction; NVIDIA application clock |
| `--memory-clock MHz` | Linux AMD and NVIDIA, where supported |
| `--fan PERCENT` | Linux AMD fan control |
| `--worksize 128`, `--batch 16777216` | Workgroup size and nonce batch size |

`--max-power` uses GPU sensor readings and allows brief overshoots. It is not a hardware cap or wall power measurement. Windows AMD reports ASIC power. Default temperature limits are 80°C when sensors are available. Mining pauses if a required protection sensor becomes unavailable. Driver controls require supported hardware and permissions. Settings are restored on normal exit; an abrupt shutdown may require resetting the driver profile.

## Hive OS

Use an Ubuntu 22.04 or newer image with OpenCL drivers. In the Flight Sheet, choose Custom miner, name `lackminer-qbtc`, and use the [Hive OS package URL](https://github.com/Knop3dev/LackMain/releases/download/v0.2.0/lackminer-qbtc-0.2.0-hiveos.tar.gz). Wallet template: your public Q-BTC address. Leave Pool URL empty. Extra config: `--device 0 --max-power 120 --intensity 100`.

Use Hive OS OC profiles for clocks and fans. Each miner instance handles one GPU. Reserve disk space for the local node.

## Build

```text
cargo build --release --locked
```

Windows AMD helper: `cmake -S gpu-control -B build/gpu-control`, then `cmake --build build/gpu-control --config Release`. Place `lackminer-gpu-control.exe` next to the miner. The official ADLX SDK is downloaded at a pinned commit. Dependency licenses are included in release packages under `licenses/`.

---

## Русский

SOLO GPU-майнер Q-BTC для Windows, Linux и Hive OS. OpenCL: AMD и NVIDIA. Комиссия — 10% всей награды блока, включая комиссии транзакций. Остальные 90% поступают на указанный адрес. Комиссионный адрес: `qbtc10y29nvfuwyxfxhkl4yqkenw4u6hshsk9zgaf5ctz4zfpa2gxe45qtwawce`.

### Запуск

Windows: распакуйте архив на диск с местом для ноды и запустите `start-windows.cmd`.

Linux (Ubuntu 22.04 или новее): установите OpenCL-драйвер производителя, `curl`, `tar`, `util-linux`. Распакуйте архив и выполните `bash start-linux.sh`.

Введите публичный адрес Q-BTC, выберите GPU и подтвердите запуск. Локальная официальная нода v2.5.0 загружается с проверкой SHA-256. Майнинг начинается после проверки синхронизации и совпадения вершины цепочки с explorer. Данные ноды хранятся рядом с майнером; на Linux каталог можно задать через `LACKMINER_NODE_DIR`.

Прямой запуск с уже работающей локальной нодой:

```text
lackminer-qbtc --solo --node http://127.0.0.1:24002 --user YOUR_QBTC_ADDRESS --device 0 --max-power 120 --stats-file stats.json --log-file miner.jsonl
```

`Ctrl+C` останавливает майнер. Локальная нода продолжает синхронизацию. При ошибке интерактивные launchers повторяют запуск через 10 секунд.

### GPU

| Параметр | Назначение |
| --- | --- |
| `--list-devices` | OpenCL-устройства и PCI |
| `--max-power 120` | Пауза при превышении измеренного бюджета, возобновление ниже 95% |
| `--intensity 80` | Доля времени вычислений, 1–100% |
| `--max-temp 80`, `--max-hotspot 80` | Пауза при превышении, возобновление на 5°C ниже |
| `--power-limit W` | Аппаратный лимит: NVIDIA и Linux AMD, при поддержке драйвером |
| `--power-percent P` | Windows AMD: процент лимита драйвера |
| `--core-clock MHz` | Windows AMD: максимальная частота; Linux AMD: снижение профиля; NVIDIA: application clock |
| `--memory-clock MHz` | Linux AMD и NVIDIA, если поддерживается |
| `--fan PERCENT` | Linux AMD через sysfs |
| `--worksize 128`, `--batch 16777216` | Размер группы и пакет nonce |

`--max-power` регулирует загрузку по датчику и допускает кратковременное превышение. Это не аппаратный потолок и не потребление компьютера из розетки. Для Windows AMD показан ASIC power. Лимиты температуры по умолчанию 80°C, если датчик доступен. При потере используемого защитой датчика вычисления приостанавливаются. Аппаратные настройки восстанавливаются при штатном завершении; аварийное выключение может потребовать сброса профиля в драйвере.

### Hive OS

Используйте образ на Ubuntu 22.04 или новее и рабочий OpenCL-драйвер. В Flight Sheet выберите Custom miner, имя `lackminer-qbtc`, URL релизного `lackminer-qbtc-0.2.0-hiveos.tar.gz`. Wallet template — ваш публичный Q-BTC адрес, Pool URL не требуется. Extra config, например: `--device 0 --max-power 120 --intensity 100`. Частоты и вентилятор можно задать штатным OC-профилем Hive OS. Один экземпляр обслуживает одну GPU. Следите за свободным местом для локальной ноды.

### Сборка

```text
cargo build --release --locked
```

Windows AMD helper: `cmake -S gpu-control -B build/gpu-control`, затем `cmake --build build/gpu-control --config Release`. Поместите `lackminer-gpu-control.exe` рядом с основным exe. SDK ADLX загружается из официального репозитория по закреплённому commit. Лицензии зависимостей поставляются отдельно в `licenses/`.
