# lackminer qbtc

SOLO GPU-майнер Q-BTC для Windows, Linux и Hive OS. OpenCL: AMD и NVIDIA. Комиссия — 10% всей награды блока, включая комиссии транзакций. Остальные 90% поступают на указанный адрес. Комиссионный адрес: `qbtc10y29nvfuwyxfxhkl4yqkenw4u6hshsk9zgaf5ctz4zfpa2gxe45qtwawce`.

## Запуск

Windows: распакуйте архив на диск с местом для ноды и запустите `start-windows.cmd`.

Linux (Ubuntu 22.04 или новее): установите OpenCL-драйвер производителя, `curl`, `tar`, `util-linux`. Распакуйте архив и выполните `bash start-linux.sh`.

Введите публичный адрес Q-BTC, выберите GPU и подтвердите запуск. Локальная официальная нода v2.5.0 загружается с проверкой SHA-256. Майнинг начинается после проверки синхронизации и совпадения вершины цепочки с explorer. Данные ноды хранятся рядом с майнером; на Linux каталог можно задать через `LACKMINER_NODE_DIR`.

Прямой запуск с уже работающей локальной нодой:

```text
lackminer-qbtc --solo --node http://127.0.0.1:24002 --user YOUR_QBTC_ADDRESS --device 0 --max-power 120 --stats-file stats.json --log-file miner.jsonl
```

`Ctrl+C` останавливает майнер. Локальная нода продолжает синхронизацию. При ошибке интерактивные launchers повторяют запуск через 10 секунд.

## GPU

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

## Проверка

```text
lackminer-qbtc --self-test --device 0
lackminer-qbtc --benchmark --device 0 --seconds 30 --cpu-threads 8 --max-power 120
lackminer-qbtc --tune --device 0 --seconds 10 --max-power 120
```

Self-test сравнивает 12 288 CPU/GPU хешей и 12 граничных проверок target. Подтверждение локальной ноды сохраняется в `evidence/solo`; оно не гарантирует включение блока в итоговую цепочку или созревание coinbase. Синхронизация может временно приостанавливать работу. Повторный запуск восстанавливает процесс, но не гарантирует доход.

## Hive OS

Используйте образ на Ubuntu 22.04 или новее и рабочий OpenCL-драйвер. В Flight Sheet выберите Custom miner, имя `lackminer-qbtc`, URL релизного `lackminer-qbtc-0.2.0-hiveos.tar.gz`. Wallet template — ваш публичный Q-BTC адрес, Pool URL не требуется. Extra config, например: `--device 0 --max-power 120 --intensity 100`. Частоты и вентилятор можно задать штатным OC-профилем Hive OS. Один экземпляр обслуживает одну GPU. Следите за свободным местом для локальной ноды.

## Сборка

```text
cargo build --release --locked
cargo test --locked
```

Windows AMD helper: `cmake -S gpu-control -B build/gpu-control`, затем `cmake --build build/gpu-control --config Release`. Поместите `lackminer-gpu-control.exe` рядом с основным exe. SDK ADLX загружается из официального репозитория по закреплённому commit. Лицензии зависимостей поставляются отдельно в `licenses/`.

Открытые исходники допускают изменение комиссии: гарантировать её неизменность в сторонней пересобранной версии технически невозможно.
