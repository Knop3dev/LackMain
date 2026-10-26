# lackminer qbtc

Q-BTC miner for Windows, Linux and Hive OS. CPU mining and OpenCL GPU mining on AMD and NVIDIA.

**Pool:** [ashenward.ru/pool](https://ashenward.ru/pool/) · `stratum+tcp://ashenward.ru:3334`

## Download and start

Download the [latest release](https://github.com/Knop3dev/LackMain/releases/latest).

- Windows: extract the Windows archive and run `start-windows.cmd`.
- Linux: extract the Linux archive and run `bash start-linux.sh`.

Choose `pool`, select `cpu` or `gpu`, enter your public Q-BTC address and confirm the start. GPU mode requires the manufacturer's OpenCL driver. CPU mode does not require a GPU. Pool mining does not require a local node.

GPU:

```sh
lackminer-qbtc --pool stratum+tcp://ashenward.ru:3334 --user YOUR_QBTC_ADDRESS.gpu0 --device 0 --max-power 170
```

CPU:

```sh
lackminer-qbtc --pool stratum+tcp://ashenward.ru:3334 --user YOUR_QBTC_ADDRESS.cpu --cpu --cpu-threads 4
```

On Windows use `lackminer-qbtc.exe`; on Linux use `./lackminer-qbtc`. `--password x` is optional. Press Ctrl+C to stop. Pool connections reconnect automatically.

## Rewards

LackPool charges **1.5%** of each block reward, including transaction fees. There is **no additional 10% miner fee in pool mode**.

The pool uses PROP: each round's distributable reward is divided by accepted work, weighted by share difficulty. CPU miners receive easier shares; their shares do not count as equal work to harder GPU shares. Each round ends when the pool finds a block.

Rewards become spendable only after at least 100 blocks of coinbase maturity and canonical-chain verification. Automatic payouts start at **10 Q-BTC**. The operator pays network transaction fees from the pool fee reserve. Payouts may wait for sufficient fee reserve or confirmations. Orphaned blocks do not create spendable balances. Shares alone do not guarantee a reward.

All rewards initially arrive at the operator's pool wallet. The payout service transfers verified earnings to the address supplied by each miner. Check shares, balances and transaction IDs at [ashenward.ru/pool](https://ashenward.ru/pool/).

## GPU settings

`--list-devices` lists GPU indices. `--device N` selects one GPU. `--worksize 64|128|256`, `--batch N` and `--unroll 0|1` control OpenCL batching.

`--max-power W` is a measured-power protection threshold that pauses computation; it is not a hard board-power limit and brief overshoots are possible. `--power-limit W` requests a driver power limit where supported. `--power-percent P`, `--core-clock MHz`, `--memory-clock MHz`, `--fan PERCENT`, `--intensity 1..100`, `--max-temp C` and `--max-hotspot C` depend on driver support. Required sensor loss pauses protected mining. Driver settings are restored on normal exit.

`--log-file miner.jsonl` records mining events. `--stats-file stats.json` provides current machine-readable statistics.

## Hive OS

Use an Ubuntu 22.04 or newer image with OpenCL drivers. Create a Custom miner Flight Sheet:

| Setting | Value |
| --- | --- |
| Name | `lackminer-qbtc` |
| Installation URL | [Hive OS archive](https://github.com/Knop3dev/LackMain/releases/download/v0.3.0/lackminer-qbtc-0.3.0-hiveos.tar.gz) |
| Wallet template | Your public Q-BTC address |
| Pool URL | `stratum+tcp://ashenward.ru:3334` |
| Extra config | `--devices all --max-power 170` |

All detected AMD/NVIDIA GPUs are used by default. Mixed workers are supported. Select cards with `--devices 0,1,2`. Each GPU has its own mining process, statistics and restart policy. Pool mode does not start a node. Use Hive OC profiles for farm clocks and fans.

## SOLO

```sh
lackminer-qbtc --solo --node http://127.0.0.1:24002 --user YOUR_QBTC_ADDRESS --device 0 --max-power 170
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

Пул: **`stratum+tcp://ashenward.ru:3334`**. Статистика и баланс: **[ashenward.ru/pool](https://ashenward.ru/pool/)**. Локальная нода для пула не нужна.

GPU:

```sh
lackminer-qbtc --pool stratum+tcp://ashenward.ru:3334 --user YOUR_QBTC_ADDRESS.gpu0 --device 0 --max-power 170
```

CPU:

```sh
lackminer-qbtc --pool stratum+tcp://ashenward.ru:3334 --user YOUR_QBTC_ADDRESS.cpu --cpu --cpu-threads 4
```

Комиссия пула — **1,5%**, дополнительных 10% в pool-режиме нет. Награда распределяется пропорционально подтверждённой работе с учётом сложности шар. Начисления становятся доступными после созревания награды и проверки основной цепи. Выплата — **от 10 Q-BTC** на адрес майнера; комиссию транзакции оплачивает оператор из резерва комиссии пула.

Для Hive OS укажите архив из таблицы выше, свой адрес в Wallet template и `stratum+tcp://ashenward.ru:3334` в Pool URL. Extra config: `--devices all --max-power 170`. Поддерживаются несколько GPU в одном воркере и смешанные AMD/NVIDIA.

В режиме SOLO сохраняется отдельная комиссия разработчика 10%. Для SOLO нужна синхронизированная локальная нода. `--max-power` ограничивает работу по показаниям датчика и допускает краткие превышения; аппаратное ограничение мощности задаётся отдельно при поддержке драйвера.
