import sys
import os
import ctypes
import threading
import re
import subprocess
import json
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

GITHUB_REPO = "valentinpo/registry-cleaner"

def run_as_admin():
    if ctypes.windll.shell32.IsUserAnAdmin() == 0:
        script = os.path.abspath(sys.argv[0])
        params = ' '.join(sys.argv[1:])
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}" {params}', None, 1)
        sys.exit()

class RegistryCleanerGUI:
    VERSION = "3.3.0"
    
    def __init__(self, root):
        self.root = root
        self.root.title(f"Очистка реестра Windows v{self.VERSION}")
        self.root.geometry("950x720")
        self.root.minsize(850, 600)
        
        self.backup_file = None
        self.current_problems = []  # (type, data, tree_iid)
        self.is_dark_theme = True
        self.is_scanning = False
        self.is_downloading = False
        
        self.setup_ui()
        self.setup_theme(dark=True)
        
        if not self.is_admin():
            messagebox.showwarning("Внимание", "Для работы с реестром запустите программу от имени Администратора!")
            
        self.log_message("🔧 Программа запущена. Разработано: Валентин и Михаил Полуяхтовы")
        self.log_message("️ Перед очисткой рекомендуется создать точку восстановления системы.")

    def is_admin(self):
        try: return os.getuid() == 0
        except AttributeError: return ctypes.windll.shell32.IsUserAnAdmin() != 0

    def setup_theme(self, dark=True):
        style = ttk.Style()
        style.theme_use('clam')
        if dark:
            self.root.configure(bg='#1e1e1e')
            style.configure('.', background='#1e1e1e', foreground='#e0e0e0', fieldbackground='#2b2b2b')
            style.configure('TFrame', background='#1e1e1e')
            style.configure('TButton', background='#3a3a3a', foreground='#ffffff', borderwidth=1, font=('Segoe UI', 9))
            style.map('TButton', background=[('active', '#4d4d4d'), ('pressed', '#2a2a2a')])
            style.configure('TLabel', background='#1e1e1e', foreground='#e0e0e0')
            style.configure('TRadiobutton', background='#1e1e1e', foreground='#e0e0e0')
            style.configure('TCheckbutton', background='#1e1e1e', foreground='#e0e0e0')
            style.configure('Header.TLabel', font=('Segoe UI', 10, 'bold'), foreground='#4fc3f7')
            style.configure('Credits.TLabel', font=('Segoe UI', 9), foreground='#757575')
            
            style.configure('Treeview', background='#252525', foreground='#d4d4d4', fieldbackground='#252525', font=('Consolas', 9))
            style.configure('Treeview.Heading', background='#3a3a3a', foreground='#ffffff', font=('Segoe UI', 9, 'bold'))
            style.map('Treeview', background=[('selected', '#4d4d4d')], foreground=[('selected', '#ffffff')])
            style.configure('Treeview.Treeview', rowheight=24)
            
            if hasattr(self, 'log_text'): self.log_text.config(bg='#252525', fg='#d4d4d4', insertbackground='#ffffff')
            if hasattr(self, 'credits_label'): self.credits_label.configure(foreground='#757575')
        else:
            self.root.configure(bg='#f5f5f5')
            style.theme_use('default')
            style.configure('Treeview', background='#ffffff', foreground='#212121', fieldbackground='#ffffff', font=('Consolas', 9))
            style.configure('Treeview.Heading', background='#e0e0e0', foreground='#212121', font=('Segoe UI', 9, 'bold'))
            style.map('Treeview', background=[('selected', '#cce5ff')], foreground=[('selected', '#004085')])
            
            if hasattr(self, 'log_text'): self.log_text.config(bg='#ffffff', fg='#212121', insertbackground='#000000')
            if hasattr(self, 'credits_label'): self.credits_label.configure(foreground='#666666')
        self.root.update_idletasks()

    def toggle_theme(self):
        self.is_dark_theme = not self.is_dark_theme
        self.setup_theme(dark=self.is_dark_theme)
        self.log_message("🎨 Тема изменена на: " + ("Тёмная" if self.is_dark_theme else "Светлая"))

    def setup_ui(self):
        menubar = tk.Menu(self.root)
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="📜 Что нового (Release Notes)", command=self.show_release_notes)
        help_menu.add_command(label="Проверить обновления", command=self.check_updates)
        help_menu.add_separator()
        help_menu.add_command(label="О программе", command=self.show_about)
        menubar.add_cascade(label="Справка", menu=help_menu)
        self.root.config(menu=menubar)

        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(control_frame, text="🛡️ Точка восстановления", command=self.create_restore_point).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Создать бэкап", command=self.backup_registry).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Сканировать", command=self.start_scan).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Очистить выбранные", command=self.clean_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Очистить всё", command=self.clean_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Восстановить бэкап", command=self.restore_registry_backup).pack(side=tk.LEFT, padx=5)
        
        self.theme_btn = ttk.Button(control_frame, text="🌙 Тема", command=self.toggle_theme)
        self.theme_btn.pack(side=tk.RIGHT, padx=5)

        mode_frame = ttk.Frame(main_frame)
        mode_frame.pack(anchor=tk.W, pady=(0, 5))
        self.scan_mode_var = tk.StringVar(value="max")
        ttk.Radiobutton(mode_frame, text="⚡ Быстрое", variable=self.scan_mode_var, value="fast").pack(side=tk.LEFT)
        ttk.Radiobutton(mode_frame, text="🔍 Глубокое", variable=self.scan_mode_var, value="deep").pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(mode_frame, text="🚀 Максимальное", variable=self.scan_mode_var, value="max").pack(side=tk.LEFT)

        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.pack(fill=tk.X, pady=5)

        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        columns = ("type", "key", "name", "value", "status")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=12)
        self.tree.heading("type", text="Тип ошибки")
        self.tree.heading("key", text="Раздел реестра")
        self.tree.heading("name", text="Параметр")
        self.tree.heading("value", text="Значение / Ссылка")
        self.tree.heading("status", text="Статус")
        
        self.tree.column("type", width=90, anchor="center")
        self.tree.column("key", width=280)
        self.tree.column("name", width=130)
        self.tree.column("value", width=280)
        self.tree.column("status", width=80, anchor="center")
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.log_text = scrolledtext.ScrolledText(main_frame, height=6, wrap=tk.WORD, font=('Consolas', 9))
        self.log_text.pack(fill=tk.X, pady=5)

        self.stats_label = ttk.Label(main_frame, text="Готово к работе. Выберите режим и запустите сканирование.", 
                                     font=('Segoe UI', 10), style='Header.TLabel')
        self.stats_label.pack(fill=tk.X, pady=5)

        self.credits_label = ttk.Label(main_frame, text="© Разработано: Валентин и Михаил Полуяхтовы", 
                                       font=('Segoe UI', 9), style='Credits.TLabel')
        self.credits_label.pack(fill=tk.X, pady=(5, 0))

    # 📜 RELEASE NOTES
    def _clean_markdown(self, text):
        if not text: return "Нет описания."
        text = re.sub(r'^(#{1,6})\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'__(.+?)__', r'\1', text)
        text = re.sub(r'_(.+?)_', r'\1', text)
        text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
        text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)
        return text.strip()

    def show_release_notes(self):
        def fetch_thread():
            try:
                api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
                req = urllib.request.Request(api_url, headers={'User-Agent': 'RegistryCleaner'})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                tag = data.get('tag_name', 'Unknown')
                body = data.get('body', 'Нет описания.')
                cleaned = self._clean_markdown(body)
                self.root.after(0, lambda: self._display_release_notes(tag, cleaned))
            except Exception as e:
                self.root.after(0, lambda: self._display_release_notes("Ошибка", f"Не удалось загрузить заметки:\n{e}"))
        threading.Thread(target=fetch_thread, daemon=True).start()

    def _display_release_notes(self, tag, text):
        win = tk.Toplevel(self.root)
        win.title(f"📜 Release Notes ({tag})")
        win.geometry("580x480")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()
        win.geometry("+{}+{}".format(self.root.winfo_rootx() + 200, self.root.winfo_rooty() + 100))

        bg = '#1e1e1e' if self.is_dark_theme else '#ffffff'
        fg = '#d4d4d4' if self.is_dark_theme else '#212121'
        win.configure(bg=bg)

        frame = ttk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        ttk.Label(frame, text=f"Версия: {tag}", font=('Segoe UI', 11, 'bold')).pack(anchor=tk.W)
        ttk.Separator(frame, orient='horizontal').pack(fill=tk.X, pady=5)

        txt = scrolledtext.ScrolledText(frame, wrap=tk.WORD, font=('Consolas', 9), height=18, state=tk.DISABLED)
        txt.pack(fill=tk.BOTH, expand=True, pady=5)
        txt.configure(bg='#252525' if self.is_dark_theme else '#ffffff', fg=fg, insertbackground=fg)
        txt.config(state=tk.NORMAL)
        txt.insert(tk.END, text)
        txt.config(state=tk.DISABLED)

        ttk.Button(frame, text="Закрыть", command=win.destroy).pack(pady=5)

    def show_about(self):
        about_win = tk.Toplevel(self.root)
        about_win.title("О программе")
        about_win.geometry("480x360")
        about_win.resizable(False, False)
        about_win.transient(self.root)
        about_win.grab_set()
        about_win.geometry("+{}+{}".format(self.root.winfo_rootx() + 250, self.root.winfo_rooty() + 150))
        if self.is_dark_theme: about_win.configure(bg='#1e1e1e')
        else: about_win.configure(bg='#ffffff')

        frame = ttk.Frame(about_win)
        frame.pack(expand=True, fill=tk.BOTH, padx=20, pady=20)
        ttk.Label(frame, text="🛠 Очистка реестра Windows", font=('Segoe UI', 14, 'bold')).pack(pady=10)
        ttk.Label(frame, text=f"Версия: {self.VERSION}").pack()
        ttk.Label(frame, text="Разработчики: Валентин и Михаил Полуяхтовы").pack(pady=2)
        ttk.Label(frame, text="© 2026 Все права защищены", foreground='gray').pack(pady=5)
        ttk.Label(frame, text="Таблица результатов, точка восстановления,\nавтообновление и просмотр Release Notes.\n\n⚠️ Всегда делайте бэкап перед очисткой!", justify=tk.CENTER).pack(pady=10)
        ttk.Button(frame, text="Закрыть", command=about_win.destroy).pack(pady=5)

    def create_restore_point(self):
        if not messagebox.askyesno("Подтверждение", "Создать точку восстановления системы?\nЭто займёт 10-30 секунд и потребует прав администратора."):
            return
        self.log_message("🛡️ Создание точки восстановления...")
        self.progress.start()
        def restore_thread():
            try:
                cmd = 'powershell -Command "Checkpoint-Computer -Description \'RegistryCleaner_AutoRestore\' -RestorePointType \'MODIFY_SETTINGS\'"'
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
                if result.returncode == 0:
                    self.root.after(0, lambda: self.log_message("✅ Точка восстановления создана успешно!"))
                else:
                    self.root.after(0, lambda: self.log_message(f"⚠️ Ошибка: {result.stderr.strip()}"))
                    self.root.after(0, lambda: self.log_message("💡 Включите защиту системы: ПКМ на Этот компьютер → Свойства → Защита системы → Включить"))
            except subprocess.TimeoutExpired:
                self.root.after(0, lambda: self.log_message("⏳ Превышено время ожидания. Попробуйте позже."))
            except Exception as e:
                self.root.after(0, lambda: self.log_message(f"❌ Ошибка: {e}"))
            finally:
                self.root.after(0, lambda: self.progress.stop())
        threading.Thread(target=restore_thread, daemon=True).start()

    def parse_version(self, v):
        return tuple(map(int, re.findall(r'\d+', str(v))[:3]))

    def check_updates(self):
        if not GITHUB_REPO or GITHUB_REPO == "your-username/registry-cleaner":
            messagebox.showwarning("Настройка", "Укажите ваш GitHub репозиторий в переменной GITHUB_REPO в коде.")
            return
        def update_thread():
            self.log_message("🌐 Проверка обновлений...")
            try:
                api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
                req = urllib.request.Request(api_url, headers={'User-Agent': 'RegistryCleaner'})
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode('utf-8'))
                remote_version = data.get("tag_name", "0.0.0").lstrip('v')
                download_url = None
                for asset in data.get("assets", []):
                    if asset["name"].endswith(".exe"):
                        download_url = asset["browser_download_url"]
                        break
                if not download_url:
                    self.root.after(0, lambda: self.log_message("❌ Не найден .exe файл в последнем релизе."))
                    return
                if self.parse_version(remote_version) > self.parse_version(self.VERSION):
                    size_mb = data["assets"][0].get("size", 0) / (1024*1024)
                    self.root.after(0, lambda: self.log_message(f"📦 Доступна новая версия: v{remote_version} ({size_mb:.1f} MB)"))
                    if messagebox.askyesno("Обновление", f"Доступна версия {remote_version}.\nСкачать и установить?"):
                        self.root.after(0, lambda: self.download_update(download_url, remote_version))
                else:
                    self.root.after(0, lambda: self.log_message("✅ У вас установлена последняя версия."))
            except Exception as e:
                self.root.after(0, lambda: self.log_message(f"❌ Ошибка проверки обновлений: {e}"))
        threading.Thread(target=update_thread, daemon=True).start()

    def download_update(self, url, version):
        if self.is_downloading: return
        self.is_downloading = True
        self.progress['mode'] = 'determinate'
        self.progress['value'] = 0
        self.log_message("⬇️ Загрузка новой версии...")
        current_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        temp_exe = os.path.join(current_dir, f"registry_cleaner_v{version}.exe")
        def dl_thread():
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'RegistryCleaner'})
                with urllib.request.urlopen(req, timeout=120) as response:
                    total = response.length
                    if total < 0: total = 10_000_000
                    downloaded = 0
                    with open(temp_exe, 'wb') as f:
                        while True:
                            chunk = response.read(16384)
                            if not chunk: break
                            f.write(chunk)
                            downloaded += len(chunk)
                            percent = min(100, int((downloaded / total) * 100))
                            self.root.after(0, lambda p=percent: self.progress.config(value=p))
                if os.path.getsize(temp_exe) < 1000000:
                    raise Exception("Файл загружен не полностью")
                self.root.after(0, lambda: self.log_message("✅ Загрузка завершена. Применяю обновление..."))
                self.root.after(0, lambda: self.apply_update(temp_exe))
            except Exception as e:
                self.root.after(0, lambda: self.log_message(f"❌ Ошибка загрузки: {e}"))
                self.root.after(0, lambda: setattr(self, 'is_downloading', False))
                self.root.after(0, lambda: self.progress.config(mode='indeterminate', value=0))
                if os.path.exists(temp_exe):
                    try: os.remove(temp_exe)
                    except: pass
        threading.Thread(target=dl_thread, daemon=True).start()

    def apply_update(self, new_path):
        current_exe = os.path.abspath(sys.argv[0])
        batch_path = os.path.join(os.path.dirname(current_exe), "update_self.bat")
        current_pid = os.getpid()
        with open(batch_path, 'w', encoding='cp1251') as f:
            f.write('@echo off\n')
            f.write('echo 🔄 Обновление системы...\n')
            f.write('timeout /t 5 /nobreak >nul\n')
            f.write(f'taskkill /F /PID {current_pid} >nul 2>&1\n')
            f.write('timeout /t 2 /nobreak >nul\n')
            f.write(':retry_del\n')
            f.write(f'del /f /q "{current_exe}" 2>nul\n')
            f.write(f'if exist "{current_exe}" (timeout /t 2 /nobreak >nul & goto retry_del)\n')
            f.write(f'move /y "{new_path}" "{current_exe}"\n')
            f.write(f'start "" "{current_exe}"\n')
            f.write('timeout /t 2 /nobreak >nul\n')
            f.write(f'del /f /q "%~f0"\n')
        subprocess.Popen(['cmd', '/c', batch_path], creationflags=subprocess.CREATE_NO_WINDOW)
        self.log_message("🔄 Обновление применяется. Программа закроется...")
        time.sleep(1)
        os._exit(0)

    def get_scan_paths(self, mode):
        base = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce",
            r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Run",
            r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\RunOnce",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        ]
        deep = base + [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved",
        ]
        maximum = deep + [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
            r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\App Paths",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Browser Helper Objects",
            r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Explorer\Browser Helper Objects",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\ShellExecuteHooks",
            r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Explorer\ShellExecuteHooks",
            r"SOFTWARE\Microsoft\Shared Tools\MSConfig\startupreg",
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\FontLink\SystemLink",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Fonts",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Help",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunServices",
        ]
        return {"fast": base, "deep": deep, "max": maximum}.get(mode, base)

    def log_message(self, message):
        self.log_text.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def parse_key_path(self, full_path):
        import winreg as reg
        if full_path.startswith("HKEY_LOCAL_MACHINE\\"):
            return reg.HKEY_LOCAL_MACHINE, full_path[len("HKEY_LOCAL_MACHINE\\"):]
        elif full_path.startswith("HKEY_CURRENT_USER\\"):
            return reg.HKEY_CURRENT_USER, full_path[len("HKEY_CURRENT_USER\\"):]
        return reg.HKEY_LOCAL_MACHINE, full_path

    def backup_registry(self):
        import winreg as reg
        self.log_message("Создание резервной копии HKLM...")
        try:
            self.backup_file = f"registry_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.reg"
            result = subprocess.run(['reg', 'export', 'HKLM', self.backup_file, '/y'], capture_output=True, text=True, shell=True)
            if result.returncode == 0: self.log_message(f"✅ Бэкап создан: {self.backup_file}")
            else: self.log_message(f"❌ Ошибка бэкапа: {result.stderr}")
        except Exception as e: self.log_message(f"❌ Критическая ошибка: {e}")

    def restore_registry_backup(self):
        if not self.backup_file or not os.path.exists(self.backup_file):
            messagebox.showerror("Ошибка", "Файл резервной копии не найден!")
            return
        if messagebox.askyesno("Подтверждение", "Восстановить реестр из бэкапа?\nЭто перезапишет текущие данные!"):
            try:
                self.log_message("Восстановление реестра...")
                result = subprocess.run(['reg', 'import', self.backup_file], capture_output=True, text=True, shell=True)
                if result.returncode == 0: self.log_message("✅ Реестр успешно восстановлен!")
                else: self.log_message(f"❌ Ошибка восстановления: {result.stderr}")
            except Exception as e: self.log_message(f"❌ Ошибка: {e}")

    def key_exists(self, full_key_path):
        import winreg as reg
        try:
            hkey, sub_key = self.parse_key_path(full_path)
            reg.OpenKey(hkey, sub_key, 0, reg.KEY_READ)
            return True
        except Exception: return False

    def extract_registry_path(self, value):
        match = re.search(r'(HKEY_(?:LOCAL_MACHINE|CURRENT_USER)\\[^\\]*(?:\\[^\\]*)*)', value)
        return match.group(1) if match else None

    def find_invalid_registry_references(self, key_path):
        import winreg as reg
        invalid_refs = []
        try:
            hkey, sub_key = self.parse_key_path(key_path)
            key = reg.OpenKey(hkey, sub_key, 0, reg.KEY_READ)
            i = 0
            while True:
                try:
                    name, value, _ = reg.EnumValue(key, i)
                    if isinstance(value, str) and 'HKEY_' in value:
                        ref_key = self.extract_registry_path(value)
                        if ref_key and not self.key_exists(ref_key):
                            invalid_refs.append((key_path, name, value, ref_key))
                    i += 1
                except OSError: break
            reg.CloseKey(key)
        except Exception: pass
        return invalid_refs

    def find_invalid_paths(self, key_path):
        import winreg as reg
        invalid_entries = []
        try:
            hkey, sub_key = self.parse_key_path(key_path)
            key = reg.OpenKey(hkey, sub_key, 0, reg.KEY_READ)
            i = 0
            while True:
                try:
                    name, value, _ = reg.EnumValue(key, i)
                    if isinstance(value, str) and ('exe' in value.lower() or 'dll' in value.lower()):
                        clean_path = value.strip().strip('"').split(' ')[0]
                        if not os.path.exists(clean_path):
                            invalid_entries.append((key_path, name, value))
                    i += 1
                except OSError: break
            reg.CloseKey(key)
        except Exception: pass
        return invalid_entries

    def start_scan(self):
        import winreg as reg
        if self.is_scanning:
            messagebox.showwarning("Внимание", "Сканирование уже запущено. Дождитесь завершения.")
            return
        self.is_scanning = True
        self.current_problems.clear()
        self.tree.delete(*self.tree.get_children())
        self.log_message("🔍 Начало сканирования...")
        self.progress.start()
        self.stats_label.config(text="Сканирование...")
        def scan_thread():
            mode = self.scan_mode_var.get()
            locations = self.get_scan_paths(mode)
            total = len(locations)
            found = 0
            for idx, loc in enumerate(locations, 1):
                self.root.after(0, lambda l=loc, i=idx, t=total: self.log_message(f"📂 [{i}/{t}] Сканирование: {l}"))
                try:
                    refs = self.find_invalid_registry_references(loc)
                    for r in refs:
                        iid = self.root.after(0, lambda k=r[0], n=r[1], v=r[3]: self.tree.insert("", "end", values=("Invalid Ref", k, n, v, "⚠️")))
                        self.current_problems.append(("Invalid Ref", r, iid))
                        found += 1
                    paths = self.find_invalid_paths(loc)
                    for p in paths:
                        iid = self.root.after(0, lambda k=p[0], n=p[1], v=p[2]: self.tree.insert("", "end", values=("Invalid Path", k, n, v, "📁")))
                        self.current_problems.append(("Invalid Path", p, iid))
                        found += 1
                except Exception: pass
            self.is_scanning = False
            self.root.after(0, lambda: self.finish_scan(found))
        threading.Thread(target=scan_thread, daemon=True).start()

    def finish_scan(self, count):
        self.progress.stop()
        self.stats_label.config(text=f"✅ Сканирование завершено. Найдено проблем: {count}")
        self.log_message(f"📊 Итог: найдено {count} записей с ошибками.")

    def clean_selected(self):
        selected_iids = self.tree.selection()
        if not selected_iids:
            messagebox.showinfo("Информация", "Выберите записи в таблице для удаления.")
            return
        if messagebox.askyesno("Подтверждение", f"Удалить {len(selected_iids)} выбранных записей?\nРекомендуется сначала создать точку восстановления!"):
            self.log_message("🧹 Начало очистки выбранных...")
            self.progress.start()
            def clean_thread():
                deleted = 0
                for iid in selected_iids:
                    prob = next((p for p in self.current_problems if p[2] == iid), None)
                    if not prob: continue
                    prob_type, prob_data = prob[0], prob[1]
                    try:
                        key_path, name = prob_data[0], prob_data[1]
                        import winreg as reg
                        hkey, sub_key = self.parse_key_path(key_path)
                        key = reg.OpenKey(hkey, sub_key, 0, reg.KEY_SET_VALUE)
                        reg.DeleteValue(key, name)
                        reg.CloseKey(key)
                        deleted += 1
                        self.root.after(0, lambda k=key_path, n=name: self.log_message(f"🗑️ Удалено: {k}\\{n}"))
                    except Exception as e:
                        self.root.after(0, lambda k=key_path, n=name, e=e: self.log_message(f"❌ Ошибка удаления {k}\\{n}: {e}"))
                for iid in selected_iids:
                    self.root.after(0, lambda i=iid: self.tree.delete(i))
                self.current_problems = [p for p in self.current_problems if p[2] not in selected_iids]
                self.root.after(0, lambda: self.finish_clean(deleted))
            threading.Thread(target=clean_thread, daemon=True).start()

    def clean_all(self):
        if not self.current_problems:
            messagebox.showinfo("Информация", "Проблемы не найдены. Сначала выполните сканирование.")
            return
        if messagebox.askyesno("Подтверждение", f"Удалить все {len(self.current_problems)} записи?\nРекомендуется сначала создать точку восстановления!"):
            self.log_message("🧹 Начало полной очистки...")
            self.progress.start()
            def clean_thread():
                deleted = 0
                all_iids = [p[2] for p in self.current_problems]
                for prob_type, prob_data, iid in self.current_problems:
                    try:
                        key_path, name = prob_data[0], prob_data[1]
                        import winreg as reg
                        hkey, sub_key = self.parse_key_path(key_path)
                        key = reg.OpenKey(hkey, sub_key, 0, reg.KEY_SET_VALUE)
                        reg.DeleteValue(key, name)
                        reg.CloseKey(key)
                        deleted += 1
                        self.root.after(0, lambda k=key_path, n=name: self.log_message(f"🗑️ Удалено: {k}\\{n}"))
                    except Exception as e:
                        self.root.after(0, lambda k=key_path, n=name, e=e: self.log_message(f"❌ Ошибка удаления {k}\\{n}: {e}"))
                self.root.after(0, lambda: [self.tree.delete(i) for i in all_iids])
                self.current_problems.clear()
                self.root.after(0, lambda: self.finish_clean(deleted))
            threading.Thread(target=clean_thread, daemon=True).start()

    def finish_clean(self, deleted):
        self.progress.stop()
        self.stats_label.config(text=f"🧹 Очистка завершена. Удалено: {deleted}")
        self.log_message(f"✅ Готово. Удалено записей: {deleted}")
        messagebox.showinfo("Успех", f"Очистка завершена.\nУдалено: {deleted}")

if __name__ == "__main__":
    import urllib.request
    import winreg as reg
    run_as_admin()
    root = tk.Tk()
    app = RegistryCleanerGUI(root)
    root.mainloop()