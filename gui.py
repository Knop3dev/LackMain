import dataclasses, json, threading, tkinter as tk
from tkinter import ttk, messagebox, filedialog
from config import VERSION
TEXT = {'en': {'title': 'Mining', 'start': 'Start mining', 'stop': 'Stop', 'save': 'Save settings', 'address': 'Payout address', 'mode': 'Mode', 'node': 'Node HTTPS', 'devices': 'GPU IDs, comma separated', 'cpu': 'CPU workers', 'intensity': 'Intensity %', 'worksize': 'Workgroup', 'batch': 'Batch', 'temp': 'GPU stop °C', 'hotspot': 'Hotspot stop °C', 'restart': 'Restart after an error', 'wallet': 'Local wallet', 'key': 'Private key · RAM only', 'file': 'Encrypted wallet file', 'password': 'Wallet password', 'browse': 'Browse', 'unlock': 'Unlock', 'lock': 'Lock', 'settings': 'Mining settings', 'tuning': 'GPU tuning', 'logs': 'Log', 'gpu': 'GPU ID', 'power_w': 'Power W', 'power_percent': 'AMD Windows power %', 'core_mhz': 'Core MHz', 'memory_mhz': 'Memory MHz', 'apply': 'Save & apply', 'restore': 'Restore settings', 'stock': 'Blank values keep driver settings. Tuning is never applied automatically.', 'panel': 'Open local panel', 'confirm': 'Apply these settings to the selected GPU?', 'locked': 'Locked', 'unlocked': 'Unlocked'}, 'ru': {'title': 'Майнинг', 'start': 'Начать майнинг', 'stop': 'Остановить', 'save': 'Сохранить настройки', 'address': 'Адрес выплат', 'mode': 'Режим', 'node': 'Нода HTTPS', 'devices': 'GPU ID через запятую', 'cpu': 'Потоки CPU', 'intensity': 'Интенсивность %', 'worksize': 'Рабочая группа', 'batch': 'Размер пакета', 'temp': 'Пауза GPU при °C', 'hotspot': 'Пауза Hotspot при °C', 'restart': 'Перезапуск после ошибки', 'wallet': 'Локальный кошелёк', 'key': 'Приватный ключ · только в памяти', 'file': 'Зашифрованный файл кошелька', 'password': 'Пароль кошелька', 'browse': 'Выбрать', 'unlock': 'Разблокировать', 'lock': 'Заблокировать', 'settings': 'Настройки майнинга', 'tuning': 'Настройки GPU', 'logs': 'Журнал', 'gpu': 'GPU ID', 'power_w': 'Потребление, Вт', 'power_percent': 'AMD Windows питание %', 'core_mhz': 'Ядро, МГц', 'memory_mhz': 'Память, МГц', 'apply': 'Сохранить и применить', 'restore': 'Восстановить', 'stock': 'Пустые поля сохраняют настройки драйвера. Автоприменения разгона нет.', 'panel': 'Открыть локальную панель', 'confirm': 'Применить эти параметры для выбранной карты?', 'locked': 'Заблокирован', 'unlocked': 'Разблокирован'}}

class Window:

    def __init__(self, miner):
        self.m = miner
        self.root = tk.Tk()
        self.root.title('lackminer LBTC ' + VERSION)
        self.root.geometry('1050x810')
        self.root.minsize(840, 650)
        self.root.configure(bg='#10161e')
        self.language = 'en'
        self.labels = []
        self.variables = {}
        self.server = None
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', background='#151e29', foreground='#e5edf7', fieldbackground='#0e151e', font=('Segoe UI', 10))
        style.configure('TButton', padding=9)
        style.configure('TNotebook.Tab', padding=(18, 10))
        style.configure('Treeview', rowheight=28, background='#151e29', fieldbackground='#151e29', foreground='#e5edf7')
        style.map('TButton', background=[('active', '#354453')])
        style.map('TNotebook.Tab', background=[('selected', '#334354')])
        outer = ttk.Frame(self.root, padding=20)
        outer.pack(fill='both', expand=True)
        top = ttk.Frame(outer)
        top.pack(fill='x')
        ttk.Label(top, text='lackminer  /  LBTC', font=('Segoe UI', 21, 'bold')).pack(side='left')
        ttk.Button(top, text='EN / RU', command=self.translate).pack(side='right')
        self.summary = ttk.Label(outer, text='Stopped', font=('Segoe UI', 13))
        self.summary.pack(anchor='w', pady=16)
        actions = ttk.Frame(outer)
        actions.pack(fill='x', pady=(0, 16))
        for key, fn in [('start', self.start), ('stop', lambda: self.background(self.m.stop)), ('panel', self.panel)]:
            self.button(actions, key, fn).pack(side='left', padx=(0, 10))
        self.tree = ttk.Treeview(outer, columns=('device', 'rate', 'temperature', 'power', 'load'), show='headings', height=4)
        for key, title, width in [('device', 'Device', 300), ('rate', 'H/s', 160), ('temperature', '°C / Hotspot', 145), ('power', 'W', 110), ('load', 'GPU %', 90)]:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, stretch=True)
        self.tree.pack(fill='x', pady=(0, 18))
        tabs = ttk.Notebook(outer)
        tabs.pack(fill='both', expand=True)
        settings = ttk.Frame(tabs, padding=16)
        tuning = ttk.Frame(tabs, padding=16)
        logs = ttk.Frame(tabs, padding=10)
        for frame, key in [(settings, 'settings'), (tuning, 'tuning'), (logs, 'logs')]:
            tabs.add(frame, text=TEXT['en'][key])
            self.labels.append((lambda text, f=frame: tabs.tab(f, text=text), key))
        left = ttk.Frame(settings)
        right = ttk.Frame(settings)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 20))
        right.grid(row=0, column=1, sticky='nsew')
        settings.columnconfigure(0, weight=1)
        settings.columnconfigure(1, weight=1)
        cfg = dataclasses.asdict(miner.settings)
        for i, (field, key) in enumerate([('address', 'address'), ('mode', 'mode'), ('node', 'node'), ('devices', 'devices'), ('cpu_workers', 'cpu'), ('intensity', 'intensity'), ('worksize', 'worksize'), ('batch', 'batch')]):
            self.label(left, key).grid(row=i, column=0, sticky='w', pady=5)
            value = ','.join(map(str, cfg[field])) if field == 'devices' else str(cfg[field])
            v = tk.StringVar(value=value)
            self.variables[field] = v
            entry = ttk.Combobox(left, textvariable=v, values=['solo', 'pool'], state='readonly') if field == 'mode' else ttk.Entry(left, textvariable=v)
            entry.grid(row=i, column=1, sticky='ew', pady=5, padx=(12, 0))
        left.columnconfigure(1, weight=1)
        for i, (field, key) in enumerate([('max_temperature', 'temp'), ('max_hotspot', 'hotspot')]):
            self.label(left, key).grid(row=8 + i, column=0, sticky='w', pady=5)
            v = tk.StringVar(value=str(cfg[field]))
            self.variables[field] = v
            ttk.Entry(left, textvariable=v).grid(row=8 + i, column=1, sticky='ew', padx=(12, 0), pady=5)
        self.restart = tk.BooleanVar(value=cfg['auto_restart'])
        check = ttk.Checkbutton(left, text=TEXT['en']['restart'], variable=self.restart)
        check.grid(row=10, column=0, columnspan=2, sticky='w', pady=8)
        self.labels.append((lambda text: check.configure(text=text), 'restart'))
        self.button(left, 'save', self.save).grid(row=11, column=0, columnspan=2, sticky='ew', pady=8)
        self.label(right, 'wallet').pack(anchor='w', pady=(0, 10))
        self.wallet_state = ttk.Label(right, text='Locked')
        self.wallet_state.pack(anchor='w')
        self.label(right, 'key').pack(anchor='w', pady=(12, 3))
        self.key = tk.StringVar()
        ttk.Entry(right, textvariable=self.key, show='●').pack(fill='x')
        self.label(right, 'file').pack(anchor='w', pady=(12, 3))
        self.file = tk.StringVar()
        ttk.Entry(right, textvariable=self.file).pack(fill='x')
        self.button(right, 'browse', lambda: self.file.set(filedialog.askopenfilename())).pack(anchor='e', pady=4)
        self.label(right, 'password').pack(anchor='w', pady=(6, 3))
        self.password = tk.StringVar()
        ttk.Entry(right, textvariable=self.password, show='●').pack(fill='x')
        self.button(right, 'unlock', self.unlock).pack(fill='x', pady=(12, 4))
        self.button(right, 'lock', lambda: self.background(self.m.lock_wallet)).pack(fill='x')
        self.label(tuning, 'stock', wraplength=850).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 18))
        self.tuning_vars = {}
        for row, key in enumerate(['gpu', 'power_w', 'power_percent', 'core_mhz', 'memory_mhz'], 1):
            self.label(tuning, key).grid(row=row, column=0, sticky='w', pady=6)
            v = tk.StringVar(value='0' if key == 'gpu' else '')
            self.tuning_vars[key] = v
            ttk.Entry(tuning, textvariable=v, width=28).grid(row=row, column=1, sticky='ew', padx=20)
        self.button(tuning, 'apply', self.apply_tuning).grid(row=6, column=0, pady=18)
        self.button(tuning, 'restore', lambda: self.background(self.m.hardware.restore)).grid(row=6, column=1, pady=18)
        self.log_widget = tk.Text(logs, bg='#10161e', fg='#b8c8db', font=('Consolas', 10), wrap='word', relief='flat')
        self.log_widget.pack(fill='both', expand=True)
        try:
            self.device_list = miner.devices()
        except Exception:
            self.device_list = []
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh()

    def label(self, parent, key, **kwargs):
        widget = ttk.Label(parent, text=TEXT[self.language][key], **kwargs)
        self.labels.append((lambda text, w=widget: w.configure(text=text), key))
        return widget

    def button(self, parent, key, command):
        widget = ttk.Button(parent, text=TEXT[self.language][key], command=command)
        self.labels.append((lambda text, w=widget: w.configure(text=text), key))
        return widget

    def translate(self):
        self.language = 'ru' if self.language == 'en' else 'en'
        for setter, key in self.labels:
            setter(TEXT[self.language][key])

    def background(self, fn):

        def work():
            try:
                fn()
            except Exception as e:
                self.root.after(0, lambda message=str(e): messagebox.showerror('lackminer', message))
        threading.Thread(target=work, daemon=True).start()

    def save(self):
        try:
            value = {k: v.get().strip() for k, v in self.variables.items()}
            value['devices'] = [int(x.strip()) for x in value['devices'].split(',') if x.strip()]
            for k in ['cpu_workers', 'intensity', 'worksize', 'batch', 'max_temperature', 'max_hotspot']:
                value[k] = int(value[k])
            value['auto_restart'] = self.restart.get()
            self.m.configure(value)
            return True
        except Exception as exc:
            messagebox.showerror('lackminer', str(exc))
            return False

    def start(self):
        if self.save():
            self.background(self.m.start)

    def unlock(self):
        if not self.save():
            return
        values = {'key_hex': self.key.get() or None, 'wallet_file': self.file.get() or None, 'password': self.password.get() or None}
        self.key.set('')
        self.password.set('')
        self.background(lambda: self.m.unlock(**values))

    def apply_tuning(self):
        if not messagebox.askyesno('GPU', TEXT[self.language]['confirm']):
            return
        try:
            device = str(int(self.tuning_vars['gpu'].get()))
            values = {k: int(v.get()) if v.get().strip() else None for k, v in self.tuning_vars.items() if k != 'gpu'}
            self.m.configure({'tuning': {**self.m.settings.tuning, device: values}})
            self.background(self.m.apply_tuning)
        except Exception as exc:
            messagebox.showerror('lackminer', str(exc))

    def panel(self):
        from dashboard import launch
        if self.server is None:
            self.server, _ = launch(self.m, 0)
        else:
            import webbrowser
            webbrowser.open('http://127.0.0.1:' + str(self.server.server_port) + '/')

    def refresh(self):
        from main import format_rate
        d = self.m.snapshot()
        self.summary.configure(text=d['state'] + '  ·  ' + format_rate(d['hashrate']) + '  ·  Accepted ' + str(d['accepted']) + '  ·  Blocks ' + str(d['blocks']) + ('  ·  ' + str(d['error']) if d['error'] else ''))
        self.wallet_state.configure(text=TEXT[self.language]['unlocked' if d['unlocked'] else 'locked'])
        self.tree.delete(*self.tree.get_children())
        rows = {str(x['id']): {} for x in self.device_list}
        rows.update(d['devices'])
        for identifier, row in rows.items():
            name = 'CPU' if identifier == 'cpu' else next((x['name'] for x in self.device_list if str(x['id']) == identifier), 'GPU ' + identifier)
            self.tree.insert('', 'end', values=('[' + identifier + '] ' + name, format_rate(row.get('hashrate', 0) if d['state'] == 'Mining' else 0), str(row.get('temperature_c', '—')) + ' / ' + str(row.get('hotspot_c', '—')), row.get('power_w', '—'), row.get('utilization_percent', '—')))
        self.log_widget.configure(state='normal')
        self.log_widget.delete('1.0', 'end')
        self.log_widget.insert('1.0', '\n'.join((time_string(x['time']) + '  ' + x['message'] for x in d['logs'])))
        self.log_widget.configure(state='disabled')
        self.root.after(1000, self.refresh)

    def close(self):
        try:
            self.m.stop()
        except Exception as exc:
            messagebox.showerror('lackminer', str(exc))
            return
        if self.server:
            self.server.shutdown()
        self.root.destroy()

    def run(self):
        self.root.mainloop()

def time_string(stamp):
    import datetime
    return datetime.datetime.fromtimestamp(stamp).strftime('%H:%M:%S')
