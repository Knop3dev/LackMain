# lackminer qbtc

Q-BTC miner for Windows, Linux and Hive OS. CPU mining and OpenCL GPU mining on AMD and NVIDIA.

**Pool:** [ashenward.ru/pool](https://ashenward.ru/pool/) · `stratum+ssl://ashenward.ru:3336`

## Download and start

Download the [latest release](https://github.com/Knop3dev/LackMain/releases/latest).

- Windows: extract the Windows archive and run `start-windows.cmd`.
- Linux: extract the Linux archive and run `bash start-linux.sh`.

Choose `pool`, select `gpu`, `cpu` or `cpu-gpu`, enter your public Q-BTC address and confirm the start. GPU is the default; CPU mining is enabled only when selected. GPU mode requires the manufacturer's OpenCL driver. CPU mode does not require a GPU. Pool mining does not require a local node.

LackPool requires **0.3.1 or newer** and TLS on port **3336**. The miner verifies the certificate chain and server name. It does not fall back to plaintext. Port 3334 is closed; update old pool URLs in saved settings and Hive OS Flight Sheets.

GPU:

```sh
lackminer-qbtc --pool stratum+ssl://ashenward.ru:3336 --user YOUR_QBTC_ADDRESS.gpu0 --device 0
```

CPU:

```sh
lackminer-qbtc --pool stratum+ssl://ashenward.ru:3336 --user YOUR_QBTC_ADDRESS.cpu --cpu --cpu-threads 4
```

On Windows use `lackminer-qbtc.exe`; on Linux use `./lackminer-qbtc`. `--password x` is optional. Press Ctrl+C to stop. Pool connections reconnect automatically.

### CPU + GPU

```sh
lackminer-qbtc --pool stratum+ssl://ashenward.ru:3336 --user YOUR_QBTC_ADDRESS.mixed --cpu-gpu --device 0 --cpu-threads 2 --cpu-intensity 50 --intensity 50
```

`--cpu-gpu` runs the selected OpenCL GPU (integrated or discrete) and CPU together on the pool. They share a connection and search separate nonce ranges. Logs and JSON statistics include separate CPU/GPU rates and a combined total. Combined mode uses the GPU share difficulty; CPU shares may arrive less frequently than in CPU-only mode, with the same work-based accounting.

`--cpu` uses only the CPU. Without either flag, only the GPU runs. `--cpu-threads N` sets the number of CPU mining threads. `--cpu-intensity 1..100` controls CPU work/pause time; `--intensity 1..100` independently controls GPU work/pause time. These settings are not wattage limits. CPU options apply to pool mining; SOLO remains GPU-only. Windows and Linux launchers save the selected mode and both intensities.

## Rewards

LackPool charges **1.5%** of each block reward, including transaction fees. There is **no additional 10% miner fee in pool mode**.

The pool uses **PPLNS**. Each block's distributable reward is divided over the latest accepted work, with a window equal to twice the expected work for a network block at that block's difficulty. Shares are weighted by difficulty; the oldest boundary share is counted partially. CPU miners receive easier shares with proportionally less weight. Blocks do not reset the window. During initial filling, the available work receives the full distributable reward. Your remaining work can earn rewards after disconnecting until newer work replaces it.

Rewards become spendable only after at least 100 blocks of coinbase maturity and canonical-chain verification. Automatic payouts start at **10 Q-BTC**. The operator pays network transaction fees from the pool fee reserve. Payouts may wait for sufficient fee reserve or confirmations. Orphaned blocks do not create spendable balances. Shares alone do not guarantee a reward.

All rewards initially arrive at the operator's pool wallet. The payout service transfers verified earnings to the address supplied by each miner. Check shares, balances and transaction IDs at [ashenward.ru/pool](https://ashenward.ru/pool/).

## GPU settings

`--list-devices` lists GPU indices. `--device N` selects one GPU. `--worksize 64|128|256`, `--batch N` and `--unroll 0|1` control OpenCL batching.

`--max-power W` is a measured-power protection threshold that pauses computation; it is not a hard board-power limit and brief overshoots are possible. `--power-limit W` requests a driver power limit where supported. `--power-percent P`, `--core-clock MHz`, `--memory-clock MHz`, `--fan PERCENT`, `--intensity 1..100`, `--max-temp C` and `--max-hotspot C` depend on driver support. Integrated GPUs can mine without temperature or power telemetry. The launchers default to driver-managed power (0); existing saved limits remain unchanged. Set the launcher power budget to 0 if your GPU has no power sensor. Explicit --max-power, --max-temp and --max-hotspot settings require their corresponding sensors. Loss of a monitored sensor pauses protected mining. Driver settings are restored on normal exit.

`--log-file miner.jsonl` records mining events. `--stats-file stats.json` provides current machine-readable statistics.

## Hive OS

Use an Ubuntu 22.04 or newer image with OpenCL drivers. Create a Custom miner Flight Sheet:

| Setting | Value |
| --- | --- |
| Name | `lackminer-qbtc` |
| Installation URL | [Hive OS archive](https://github.com/Knop3dev/LackMain/releases/download/v0.3.3/lackminer-qbtc-0.3.3-hiveos.tar.gz) |
| Wallet template | Your public Q-BTC address |
| Pool URL | `stratum+ssl://ashenward.ru:3336` |
| Extra config | `--devices all` |

All detected AMD/NVIDIA GPUs are used by default. Mixed workers are supported. Select cards with `--devices 0,1,2`. Each GPU has its own mining process, statistics and restart policy. Pool mode does not start a node. Use Hive OC profiles for farm clocks and fans.

## SOLO

```sh
lackminer-qbtc --solo --node http://127.0.0.1:24002 --user YOUR_QBTC_ADDRESS --device 0
```

SOLO retains the disclosed **10% developer fee**, separate from pool mode. The fee covers subsidy and transaction fees. The remaining 90% goes to the miner's address. Fee address: `qbtc10y29nvfuwyxfxhkl4yqkenw4u6hshsk9zgaf5ctz4zfpa2gxe45qtwawce`. If both addresses match, the full coinbase goes to that address.

Choose `solo` in the launcher to start the official local node. Hive SOLO uses an empty Pool URL. Reserve disk space for the node; mining pauses until local/public chain agreement is verified.

## Build

```sh
cargo build --release --locked
```

Windows AMD controls: `cmake -S gpu-control -B build/gpu-control`, then `cmake --build build/gpu-control --config Release`. Place `lackminer-gpu-control.exe` next to the miner. Dependency licenses are included in release archives.

---

## Русский

Майнер Q-BTC для Windows, Linux и Hive OS. Поддерживает CPU и AMD/NVIDIA через OpenCL.

Скачайте [последний релиз](https://github.com/Knop3dev/LackMain/releases/latest). На Windows запустите `start-windows.cmd`, на Linux — `bash start-linux.sh`. Выберите `pool`, затем `cpu` или `gpu`, укажите публичный адрес Q-BTC и подтвердите запуск.

Пул: **`stratum+ssl://ashenward.ru:3336`**. Статистика и баланс: **[ashenward.ru/pool](https://ashenward.ru/pool/)**. Локальная нода для пула не нужна.

GPU:

```sh
lackminer-qbtc --pool stratum+ssl://ashenward.ru:3336 --user YOUR_QBTC_ADDRESS.gpu0 --device 0
```

CPU:

```sh
lackminer-qbtc --pool stratum+ssl://ashenward.ru:3336 --user YOUR_QBTC_ADDRESS.cpu --cpu --cpu-threads 4
```

Схема — **PPLNS**: учитывается последняя работа в окне 2× ожидаемой работы на блок при его сложности. Вес шары зависит от сложности, граничная шара учитывается частично. После блока окно не сбрасывается; при первоначальном заполнении награда делится по имеющейся работе.

Комиссия пула — **1,5%**, дополнительных 10% в pool-режиме нет. Начисления становятся доступными после созревания награды и проверки основной цепи. Выплата — **от 10 Q-BTC** на адрес майнера; комиссию транзакции оплачивает оператор из резерва комиссии пула.

Для Hive OS укажите архив из таблицы выше, свой адрес в Wallet template и `stratum+ssl://ashenward.ru:3336` в Pool URL. Extra config: `--devices all`. Поддерживаются несколько GPU в одном воркере и смешанные AMD/NVIDIA.

В режиме SOLO сохраняется отдельная комиссия разработчика 10%. Для SOLO нужна синхронизированная локальная нода. `--max-power` ограничивает работу по показаниям датчика и допускает краткие превышения; аппаратное ограничение мощности задаётся отдельно при поддержке драйвера.

Встроенная графика может майнить без датчиков температуры и мощности. В стартовом скрипте значение мощности 0 оставляет управление драйверу; это настройка по умолчанию для новой конфигурации. Сохранённый лимит не меняется автоматически: при отсутствии датчика мощности выберите 0. Явно заданные `--max-power`, `--max-temp` и `--max-hotspot` требуют соответствующих датчиков. Защита по доступным температурным датчикам сохраняется.

### CPU и GPU одновременно

По умолчанию работает только GPU. `--cpu` включает только процессор; `--cpu-gpu` — процессор вместе с выбранной встроенной или дискретной OpenCL-картой. Совместный режим доступен на пуле, SOLO остаётся GPU-режимом.

```text
lackminer-qbtc.exe --pool stratum+ssl://ashenward.ru:3336 --user ВАШ_QBTC_АДРЕС.mixed --cpu-gpu --device 0 --cpu-threads 2 --cpu-intensity 50 --intensity 50
```

`--cpu-threads` задаёт число потоков процессора, `--cpu-intensity` — его долю времени вычислений, `--intensity` — долю времени GPU. Это не ограничение потребления в ваттах. CPU и GPU перебирают разные диапазоны nonce; скорости отображаются отдельно и суммарно. В совместном режиме сложность шар общая, как для GPU, поэтому процессор может отправлять их реже, чем при отдельном CPU-майнинге. Начисления по выполненной работе не меняются. В стартовых скриптах Windows/Linux можно выбрать `gpu`, `cpu` или `cpu-gpu`; выбор и настройки сохраняются.
