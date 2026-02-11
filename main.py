# Author: Sean
# Email: fishis@126.com

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
from smb.SMBConnection import SMBConnection
from nmb.NetBIOS import NetBIOS
import socket
import os
import platform
import tempfile
import subprocess
import time
import datetime

import sys

import json
from PIL import Image
import pystray

# Branding Configuration
APP_TITLE = "云铠智能办公扫描客户端"
APP_VERSION = "1.3"
APP_ICON_NAME = "app_icon.ico"
COMPANY_NAME = "云铠智能办公"

class DownloadHistory:
    def __init__(self, config_dir):
        self.history_file = os.path.join(config_dir, "download_history.json")
        self.history = {}
        self.load()

    def load(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
            except Exception as e:
                print(f"Failed to load history: {e}")
                self.history = {}

    def save(self):
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Failed to save history: {e}")

    def get_today_key(self):
        return datetime.date.today().isoformat()

    def is_downloaded(self, filename):
        today = self.get_today_key()
        return filename in self.history.get(today, [])

    def add_record(self, filename):
        today = self.get_today_key()
        if today not in self.history:
            self.history[today] = []
        if filename not in self.history[today]:
            self.history[today].append(filename)
            self.save()

    def clean_old_records(self, days_to_keep=30):
        # Optional: Clean records older than X days
        pass

class RemoteBrowserDialog(tk.Toplevel):
    def __init__(self, parent, conn, title="选择远程文件夹"):
        super().__init__(parent)
        self.conn = conn
        self.title(title)
        self.geometry("600x400")
        self.result_path = None
        
        # Center window
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        self.geometry(f"+{parent_x + 50}+{parent_y + 50}")

        self.setup_ui()
        self.load_shares()

    def setup_ui(self):
        # Top Path
        self.path_var = tk.StringVar(value="")
        ttk.Label(self, text="当前路径:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        ttk.Label(self, textvariable=self.path_var, font=("", 10, "bold")).pack(anchor=tk.W, padx=10, pady=(0, 5))
        
        # Treeview
        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree = ttk.Treeview(frame, columns=("Type",), show="tree", yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.tree.yview)
        
        self.tree.bind("<Double-1>", self.on_double_click)
        
        # Buttons
        btn_frame = ttk.Frame(self, padding="10")
        btn_frame.pack(fill=tk.X)
        
        ttk.Button(btn_frame, text="返回上一级", command=self.go_back).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="确定选择此目录", command=self.confirm_selection).pack(side=tk.RIGHT, padx=5)

    def load_shares(self):
        self.current_share = None
        self.current_path = ""
        self.path_var.set("\\\\Server")
        
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        try:
            shares = self.conn.listShares()
            for share in shares:
                if not share.isSpecial and '$' not in share.name:
                    self.tree.insert("", "end", text=share.name, values=("Share",), iid=share.name)
        except Exception as e:
            messagebox.showerror("错误", f"无法获取共享列表: {e}")

    def load_path(self, share, path):
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        try:
            files = self.conn.listPath(share, path)
            for f in files:
                if f.filename in ['.', '..']: continue
                if f.isDirectory:
                    self.tree.insert("", "end", text=f.filename, values=("Dir",))
        except Exception as e:
            messagebox.showerror("错误", f"无法获取目录列表: {e}")

    def on_double_click(self, event):
        item_id = self.tree.selection()[0]
        item = self.tree.item(item_id)
        name = item['text']
        
        if self.current_share is None:
            self.current_share = name
            self.current_path = ""
            self.path_var.set(f"\\\\Server\\{name}")
            self.load_path(self.current_share, "")
        else:
            if self.current_path:
                self.current_path += f"/{name}"
            else:
                self.current_path = name
            
            display_path = self.current_path.replace('/', '\\')
            self.path_var.set(f"\\\\Server\\{self.current_share}\\{display_path}")
            self.load_path(self.current_share, self.current_path)

    def go_back(self):
        if self.current_share is None:
            return
            
        if not self.current_path:
            self.load_shares()
        else:
            if '/' in self.current_path:
                self.current_path = self.current_path.rsplit('/', 1)[0]
            else:
                self.current_path = ""
            
            display_path = self.current_path.replace('/', '\\')
            self.path_var.set(f"\\\\Server\\{self.current_share}\\{display_path}")
            self.load_path(self.current_share, self.current_path)

    def confirm_selection(self):
        if self.current_share:
            full_path = f"{self.current_share}/{self.current_path}" if self.current_path else self.current_share
            self.result_path = full_path
            self.destroy()
        else:
            messagebox.showwarning("提示", "请选择一个共享文件夹或子文件夹")

class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, app, config):
        super().__init__(parent)
        self.app = app
        self.config = config
        self.title("设置")
        self.geometry("500x450")
        self.resizable(False, False)
        
        # Center window
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        self.geometry(f"+{parent_x + (parent_w - 500)//2}+{parent_y + (parent_h - 450)//2}")

        self.setup_ui()

    def setup_ui(self):
        frame = ttk.Frame(self, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)

        # 1. Automation Switch
        self.auto_enabled = tk.BooleanVar(value=self.config.get("auto_download_enabled", False))
        ttk.Checkbutton(frame, text="启用自动监控下载", variable=self.auto_enabled).grid(row=0, column=0, sticky=tk.W, pady=(0, 2))
        
        # 1.1 Check Interval
        sub_frame = ttk.Frame(frame)
        sub_frame.grid(row=1, column=0, sticky=tk.W, pady=(0, 10))
        ttk.Label(sub_frame, text="检测间隔(秒):").pack(side=tk.LEFT)
        self.interval_var = tk.IntVar(value=self.config.get("check_interval", 60))
        ttk.Entry(sub_frame, textvariable=self.interval_var, width=5).pack(side=tk.LEFT, padx=5)

        # 2. Source Path (Server)
        ttk.Label(frame, text="服务器源路径 (共享名/文件夹):").grid(row=2, column=0, sticky=tk.W, pady=(5, 0))
        src_frame = ttk.Frame(frame)
        src_frame.grid(row=3, column=0, sticky=tk.W, pady=(0, 10))
        
        self.source_path_var = tk.StringVar(value=self.config.get("auto_source_path", ""))
        ttk.Entry(src_frame, textvariable=self.source_path_var, width=40).pack(side=tk.LEFT)
        ttk.Button(src_frame, text="选择...", command=self.choose_source_path).pack(side=tk.LEFT, padx=5)
        ttk.Label(frame, text="例如: scanning/pending (不用带 \\\\IP)").grid(row=4, column=0, sticky=tk.W, pady=(0, 10), padx=5)

        # 3. Local Path
        ttk.Label(frame, text="本地保存路径:").grid(row=5, column=0, sticky=tk.W, pady=(5, 0))
        path_frame = ttk.Frame(frame)
        path_frame.grid(row=6, column=0, sticky=tk.W, fill=tk.X)
        
        self.local_path_var = tk.StringVar(value=self.config.get("auto_local_path", ""))
        ttk.Entry(path_frame, textvariable=self.local_path_var, width=40).pack(side=tk.LEFT)
        ttk.Button(path_frame, text="选择...", command=self.choose_local_path).pack(side=tk.LEFT, padx=5)

        # 4. Other Options
        self.del_after = tk.BooleanVar(value=self.config.get("delete_after_download", False))
        ttk.Checkbutton(frame, text="下载后自动删除服务器文件", variable=self.del_after).grid(row=7, column=0, sticky=tk.W, pady=(15, 5))

        self.auto_start = tk.BooleanVar(value=self.config.get("auto_start_enabled", False))
        ttk.Checkbutton(frame, text="开机自动启动软件", variable=self.auto_start).grid(row=8, column=0, sticky=tk.W, pady=5)
        
        self.skip_today = tk.BooleanVar(value=self.config.get("skip_downloaded_today", True))
        ttk.Checkbutton(frame, text="跳过今日已下载过的文件", variable=self.skip_today).grid(row=9, column=0, sticky=tk.W, pady=5)

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=10, column=0, pady=20)
        ttk.Button(btn_frame, text="保存", command=self.save_settings).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(side=tk.LEFT, padx=10)

    def choose_local_path(self):
        path = filedialog.askdirectory()
        if path:
            self.local_path_var.set(path)

    def choose_source_path(self):
        if not self.app.conn:
            messagebox.showwarning("未连接", "请先在主界面连接服务器，才能浏览远程文件夹。\n或者您也可以手动输入路径。")
            return
            
        dlg = RemoteBrowserDialog(self, self.app.conn)
        self.wait_window(dlg)
        if dlg.result_path:
            self.source_path_var.set(dlg.result_path)

    def save_settings(self):
        # Update config in app
        new_conf = {
            "auto_download_enabled": self.auto_enabled.get(),
            "check_interval": self.interval_var.get(),
            "auto_source_path": self.source_path_var.get().strip(),
            "auto_local_path": self.local_path_var.get().strip(),
            "delete_after_download": self.del_after.get(),
            "auto_start_enabled": self.auto_start.get(),
            "skip_downloaded_today": self.skip_today.get()
        }
        
        self.app.update_settings(new_conf)
        self.destroy()



class SMBBrowserApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_TITLE} {APP_VERSION}")
        self.root.geometry("800x600")
        
        # Style
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        self.conn = None
        self.current_share = None
        self.current_path = ""
        self.file_list = []
        
        # Config path in user home directory
        self.config_dir = os.path.join(os.path.expanduser("~"), ".yunkai_smb_client")
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)
        self.config_file = os.path.join(self.config_dir, "config.json")
        
        # Init Download History
        self.history = DownloadHistory(self.config_dir)
        
        # App Configuration Dict
        self.app_config = {}

        # For thread safety in UI updates
        self.lock = threading.Lock()
        
        # Default download path (Desktop)
        self.download_save_path = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Desktop"))
        
        self.setup_ui()
        self.setup_menu()
        self.load_config()
        self.start_automation_thread()
        
        # System Tray Protocol
        self.root.protocol('WM_DELETE_WINDOW', self.on_closing)

    def resource_path(self, relative_path):
        """ Get absolute path to resource, works for dev and for PyInstaller """
        try:
            # PyInstaller creates a temp folder and stores path in _MEIPASS
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def setup_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="选项", menu=help_menu)
        help_menu.add_command(label="设置", command=self.show_settings)
        help_menu.add_separator()
        help_menu.add_command(label="关于", command=self.show_about)

    def show_about(self):
        # Create a custom TopLevel window
        about_window = tk.Toplevel(self.root)
        about_window.title("关于")
        about_window.geometry("320x480")
        about_window.resizable(False, False)
        about_window.configure(bg='white')  # White background
        
        # Center the window
        self.root.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 160
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 240
        about_window.geometry(f"+{x}+{y}")

        # Main container with white background
        container = tk.Frame(about_window, bg='white', padx=20, pady=20)
        container.pack(fill=tk.BOTH, expand=True)

        # Title
        tk.Label(container, text=APP_TITLE, font=("Helvetica", 18, "bold"), bg='white', fg='#333333').pack(pady=(10, 5))
        tk.Label(container, text=f"v{APP_VERSION}", font=("Helvetica", 12), bg='white', fg='#888888').pack(pady=(0, 20))
        
        # Info card
        info_frame = tk.Frame(container, bg='#f5f5f5', padx=15, pady=10) # Light gray bg for info
        info_frame.pack(fill=tk.X, pady=(0, 20))
        
        tk.Label(info_frame, text="作者：Sean", font=("Helvetica", 11), bg='#f5f5f5', fg='#333333').pack(anchor='w')
        tk.Label(info_frame, text="邮箱：fishis@126.com", font=("Helvetica", 11), bg='#f5f5f5', fg='#333333').pack(anchor='w')
        
        # QR Code Image Section
        try:
            # Use resource_path helper for PyInstaller compatibility
            img_path = self.resource_path("wechat_qr.png")
            
            if os.path.exists(img_path):
                # Load image
                original_image = tk.PhotoImage(file=img_path)
                
                # Auto-resize logic (simple subsample)
                w = original_image.width()
                h = original_image.height()
                
                # Target width ~200px
                target_w = 200
                if w > target_w:
                    factor = int(w / target_w)
                    if factor < 1: factor = 1
                    about_window.image = original_image.subsample(factor, factor)
                else:
                    about_window.image = original_image
                
                img_label = tk.Label(container, image=about_window.image, bg='white')
                img_label.pack(pady=5)
                
                tk.Label(container, text="扫一扫添加微信", font=("Helvetica", 10), bg='white', fg='#666666').pack(pady=(5, 0))
            else:
                 tk.Label(container, text="(未找到名片图片)", bg='white', fg='#999').pack(pady=20)
                
        except Exception as e:
            print(f"Error loading image: {e}")
            tk.Label(container, text="(图片加载失败: 格式不支持?)", bg='white', fg='red').pack(pady=20)
            
        # Close button styled
        tk.Button(container, text="关闭", command=about_window.destroy, 
                  highlightbackground='white').pack(side=tk.BOTTOM, pady=(10, 0))

    def setup_ui(self):
        # Top Frame: Connection Settings
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(fill=tk.X)
        
        # Grid layout for top frame
        ttk.Label(top_frame, text="服务器地址:").grid(row=0, column=0, padx=5, sticky=tk.W)
        self.server_ip = tk.StringVar()
        ttk.Entry(top_frame, textvariable=self.server_ip, width=15).grid(row=0, column=1, padx=5)
        
        ttk.Label(top_frame, text="端口:").grid(row=0, column=2, padx=5, sticky=tk.W)
        self.port = tk.StringVar(value="445")
        ttk.Entry(top_frame, textvariable=self.port, width=6).grid(row=0, column=3, padx=5)

        ttk.Label(top_frame, text="用户:").grid(row=0, column=4, padx=5, sticky=tk.W)
        self.username = tk.StringVar(value="guest")
        ttk.Entry(top_frame, textvariable=self.username, width=12).grid(row=0, column=5, padx=5)
        
        ttk.Label(top_frame, text="密码:").grid(row=0, column=6, padx=5, sticky=tk.W)
        self.password = tk.StringVar()
        ttk.Entry(top_frame, textvariable=self.password, show="*", width=12).grid(row=0, column=7, padx=5)
        
        self.connect_btn = ttk.Button(top_frame, text="连接", command=self.start_connect_thread)
        self.connect_btn.grid(row=0, column=8, padx=5)

        ttk.Button(top_frame, text="配置", command=self.show_settings, width=6).grid(row=0, column=9, padx=5)

        # Middle Frame: File Browser
        mid_frame = ttk.Frame(self.root, padding="10")
        mid_frame.pack(fill=tk.BOTH, expand=True)

        # Toolbar
        toolbar = ttk.Frame(mid_frame)
        toolbar.pack(fill=tk.X, pady=(0, 5))
        
        self.back_btn = ttk.Button(toolbar, text="返回", state=tk.DISABLED, command=self.go_back)
        self.back_btn.pack(side=tk.LEFT)
        
        self.refresh_btn = ttk.Button(toolbar, text="刷新", state=tk.DISABLED, command=self.on_refresh)
        self.refresh_btn.pack(side=tk.LEFT, padx=5)
        
        self.path_label = ttk.Label(toolbar, text="未连接", anchor="w")
        self.path_label.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        # Download Path Selection Frame
        dl_frame = ttk.Frame(mid_frame)
        dl_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(dl_frame, text="下载保存位置:").pack(side=tk.LEFT, padx=(0, 5))
        self.dl_path_entry = ttk.Entry(dl_frame, textvariable=self.download_save_path)
        self.dl_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(dl_frame, text="选择...", command=self.choose_dl_path, width=8).pack(side=tk.LEFT)

        # Treeview for files
        columns = ("Size", "Type")
        
        # Container for tree and scrollbar
        tree_frame = ttk.Frame(mid_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        # Scrollbar first (packed right)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="tree headings", yscrollcommand=scrollbar.set)
        
        self.tree.heading("#0", text="名称", anchor="w")
        self.tree.heading("Size", text="大小")
        self.tree.heading("Type", text="类型")
        
        self.tree.column("#0", width=400)
        self.tree.column("Size", width=100)
        self.tree.column("Type", width=100)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar.config(command=self.tree.yview)
        
        self.tree.bind("<Double-1>", self.on_double_click)

        # Bottom Frame: Actions
        bottom_frame = ttk.Frame(self.root, padding="10")
        bottom_frame.pack(fill=tk.X)
        
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(bottom_frame, textvariable=self.status_var).pack(side=tk.LEFT)
        
        # Actions Selection
        # Actions Selection
        action_frame = ttk.Frame(bottom_frame)
        action_frame.pack(side=tk.RIGHT)

        self.btn_delete = ttk.Button(action_frame, text="仅删除", state=tk.DISABLED, command=lambda: self.execute_action("仅删除"))
        self.btn_delete.pack(side=tk.LEFT, padx=5)
        
        self.btn_download = ttk.Button(action_frame, text="仅下载", state=tk.DISABLED, command=lambda: self.execute_action("仅下载"))
        self.btn_download.pack(side=tk.LEFT, padx=5)

        self.btn_down_del = ttk.Button(action_frame, text="下载并删除", state=tk.DISABLED, command=lambda: self.execute_action("下载并删除"))
        self.btn_down_del.pack(side=tk.LEFT, padx=5)

    def choose_dl_path(self):
        path = filedialog.askdirectory(initialdir=self.download_save_path.get())
        if path:
            self.download_save_path.set(path)

    def load_config(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    self.app_config = json.load(f)
            else:
                 self.app_config = {}
            
            # Apply to UI vars
            self.server_ip.set(self.app_config.get("ip", ""))
            self.port.set(self.app_config.get("port", "445"))
            self.username.set(self.app_config.get("user", "guest"))
            self.password.set(self.app_config.get("password", ""))
            
            saved_path = self.app_config.get("download_path", "")
            if saved_path and os.path.exists(saved_path):
                self.download_save_path.set(saved_path)
                
            # Automation defaults if missing
            if "auto_download_enabled" not in self.app_config: self.app_config["auto_download_enabled"] = False
            if "check_interval" not in self.app_config: self.app_config["check_interval"] = 60
            if "auto_source_path" not in self.app_config: self.app_config["auto_source_path"] = ""
            if "auto_local_path" not in self.app_config: self.app_config["auto_local_path"] = ""
            if "delete_after_download" not in self.app_config: self.app_config["delete_after_download"] = False
            if "auto_start_enabled" not in self.app_config: self.app_config["auto_start_enabled"] = False
            if "skip_downloaded_today" not in self.app_config: self.app_config["skip_downloaded_today"] = True
            
        except Exception as e:
            print(f"Failed to load config: {e}")
            self.app_config = {}

    def save_config(self):
        try:
            # Update basic config from UI
            self.app_config["ip"] = self.server_ip.get()
            self.app_config["port"] = self.port.get()
            self.app_config["user"] = self.username.get()
            self.app_config["password"] = self.password.get()
            self.app_config["download_path"] = self.download_save_path.get()
            
            with open(self.config_file, 'w') as f:
                json.dump(self.app_config, f)
        except Exception as e:
            print(f"Failed to save config: {e}")

    def update_status(self, msg):
        self.root.after(0, lambda: self.status_var.set(msg))

    def show_error(self, title, msg):
        self.root.after(0, lambda: messagebox.showerror(title, msg))

    def start_connect_thread(self):
        self.connect_btn.config(state=tk.DISABLED)
        self.update_status("正在连接...")
        threading.Thread(target=self.connect, daemon=True).start()

    def connect(self):
        addr_input = self.server_ip.get().strip()
        user_port_str = self.port.get().strip()
        user = self.username.get().strip()
        password = self.password.get().strip()
        
        if not addr_input:
            self.show_error("错误", "请输入服务器地址")
            self.update_status("就绪")
            self.root.after(0, lambda: self.connect_btn.config(state=tk.NORMAL))
            return

        # Resolve hostname to IP if needed
        real_ip = addr_input
        try:
            # Check if it's already an IP
            socket.inet_aton(addr_input)
        except socket.error:
            # Not an IP, try to resolve
            try:
                self.update_status(f"正在解析主机名 {addr_input}...")
                real_ip = socket.gethostbyname(addr_input)
                self.update_status(f"主机名已解析: {addr_input} -> {real_ip}")
            except Exception as e:
                 print(f"DNS Resolution failed: {e}")
                 # Continue anyway, pysmb/socket might handle it or fail later
                 pass

        ports_to_try = []
        if user_port_str:
            p = int(user_port_str)
            ports_to_try.append(p)
            # If user left it as default 445, also try 139 as fallback
            if p == 445:
                ports_to_try.append(139)
        else:
            ports_to_try = [445, 139]

        client_name = socket.gethostname()
        
        # Try to resolve NetBIOS name once
        # Prepare list of remote names to try
        remote_names = []
        try:
            # Use the resolved IP for NetBIOS query
            self.update_status(f"正在解析 NetBIOS 名称 {real_ip}...")
            nb = NetBIOS()
            resolved = nb.queryIPForName(real_ip, port=137, timeout=2)
            nb.close()
            if resolved:
                remote_names.append(resolved[0])
        except:
            pass 
        
        # Always add fallback *SMBSERVER if not already present
        if "*SMBSERVER" not in remote_names:
            remote_names.append("*SMBSERVER")

        # Ensure client_name is valid for NetBIOS (max 15 chars)
        if not client_name:
            client_name = "SMBClient"
        # Take first part of FQDN and truncate
        client_name = client_name.split('.')[0]
        if len(client_name) > 15:
            client_name = client_name[:15]
            
        success = False
        errors = {}

        for port in ports_to_try:
            port_success = False
            for r_name in remote_names:
                try:
                    self.update_status(f"正在尝试连接 {real_ip}:{port} (Name: {r_name})...")
                    
                    is_direct = (port == 445)
                    self.conn = SMBConnection(
                        user, 
                        password, 
                        client_name, 
                        r_name, 
                        use_ntlm_v2=True,
                        sign_options=2,
                        is_direct_tcp=is_direct
                    )
                    
                    if self.conn.connect(real_ip, port, timeout=5):
                        success = True
                        port_success = True
                        self.update_status(f"已连接到 {real_ip} 端口 {port}")
                        
                        # Update the UI port to show what actually worked
                        self.root.after(0, lambda p=port: self.port.set(str(p)))
                        break # Break remote_names loop
                    else:
                        # Don't record error yet, try next name
                         errors[f"{port}-{r_name}"] = "认证失败"
                except Exception as e:
                    errors[f"{port}-{r_name}"] = str(e)
                    print(f"Failed on port {port} name {r_name}: {e}")
                    self.conn = None
            
            if port_success:
                break # Break ports loop
        
        if success:
            # Save successful connection details
            self.save_config()
            try:
                self.update_status("正在列出共享...")
                shares = self.conn.listShares()
                self.root.after(0, lambda: self.show_shares(shares))
                
                # Determine protocol version for display
                protocol_ver = "SMB2/3" if self.conn.isUsingSMB2 else "SMB1"
                self.update_status(f"已连接到 {real_ip} (协议: {protocol_ver})")
            except Exception as e:
                self.show_error("列出共享错误", str(e))
                self.update_status("已连接 (获取列表失败)")
        else:
            # Construct a detailed error message
            error_details = "\n".join([f"端口 {p}: {e}" for p, e in errors.items()])
            self.show_error("连接错误", f"无法连接到 {real_ip}.\n\n错误详情:\n{error_details}")
            self.update_status("连接失败")
            self.conn = None
        
        self.root.after(0, lambda: self.connect_btn.config(state=tk.NORMAL))

    def show_shares(self, shares):
        self.current_share = None
        self.current_path = ""
        self.path_label.config(text=f"\\\\{self.server_ip.get()}")
        self.back_btn.config(state=tk.DISABLED)
        self.refresh_btn.config(state=tk.NORMAL)
        self.btn_delete.config(state=tk.DISABLED)
        self.btn_download.config(state=tk.DISABLED)
        self.btn_down_del.config(state=tk.DISABLED)
        
        # Clear tree
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        for share in shares:
            # Filter special shares, those containing '$', and 'Distribute'
            if share.isSpecial:
                continue
            if '$' in share.name:
                continue
            if share.name.lower() == 'distribute':
                continue
                
            self.tree.insert("", "end", text=share.name, values=("共享文件夹", "文件夹"), iid=share.name)
        
    def on_double_click(self, event):
        item_id = self.tree.selection()[0]
        item = self.tree.item(item_id)
        name = item['text']
        i_type = item['values'][1]
        
        if i_type == "文件夹" or self.current_share is None:
            self.enter_directory(name)
        else:
            self.open_file(name)

    def open_file(self, filename):
        threading.Thread(target=self.perform_file_open, args=(filename,), daemon=True).start()

    def perform_file_open(self, filename):
        try:
            self.update_status(f"正在准备预览 {filename}...")
            
            path_to_file = filename
            if self.current_path:
                path_to_file = f"{self.current_path}/{filename}"
            
            # 使用临时目录的子目录作为缓存
            temp_dir = tempfile.gettempdir()
            cache_dir = os.path.join(temp_dir, "smb_browser_cache")
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir, exist_ok=True)
            
            save_path = os.path.join(cache_dir, filename)
            
            # 下载文件
            with open(save_path, 'wb') as f:
                self.conn.retrieveFile(self.current_share, path_to_file, f)
            
            self.update_status(f"正在打开 {filename}...")
            
            # Windows 下打开文件
            os.startfile(save_path)
                
            self.update_status(f"已打开 {filename}")
            
        except Exception as e:
            self.show_error("预览错误", f"无法打开文件: {str(e)}")
            self.update_status("预览失败")

    def enter_directory(self, name):
        if self.current_share is None:
            self.current_share = name
            self.current_path = ""
        else:
            if self.current_path:
                 self.current_path = f"{self.current_path}/{name}"
            else:
                 self.current_path = name

        self.update_status(f"正在列出 {self.current_path}...")
        threading.Thread(target=self.list_files, daemon=True).start()

    def list_files(self):
        try:
            files = self.conn.listPath(self.current_share, self.current_path)
            self.root.after(0, lambda: self.update_file_list(files))
        except Exception as e:
            self.show_error("列出文件错误", str(e))
            # Revert path change if failed
            # (Simple logic: just don't update list for now)
            self.update_status("列出文件失败")

    def update_file_list(self, files):
        # Update breadcrumb
        display_path = f"\\\\{self.server_ip.get()}\\{self.current_share}"
        if self.current_path:
             path_backslashes = self.current_path.replace('/', '\\')
             display_path += f"\\{path_backslashes}"
        self.path_label.config(text=display_path)
        
        self.path_label.config(text=display_path)
        
        self.back_btn.config(state=tk.NORMAL)
        self.refresh_btn.config(state=tk.NORMAL)
        self.btn_delete.config(state=tk.NORMAL)
        self.btn_download.config(state=tk.NORMAL)
        self.btn_down_del.config(state=tk.NORMAL)
        
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        for f in files:
            if f.filename in ['.', '..']:
                continue
            
            ftype = "文件夹" if f.isDirectory else "文件"
            size = f"{f.file_size / 1024:.1f} KB" if not f.isDirectory else ""
            
            # Simple icon differentiation by type text
            self.tree.insert("", "end", text=f.filename, values=(size, ftype))

    def go_back(self):
        if not self.current_share:
            return
            
        if not self.current_path:
            # Go back to share list
            self.update_status("正在返回共享列表...")
            threading.Thread(target=self.refresh_shares, daemon=True).start()
        else:
            # Go up one directory
            if '/' in self.current_path:
                self.current_path = self.current_path.rsplit('/', 1)[0]
            else:
                self.current_path = ""
            
            self.update_status(f"正在列出 {self.current_path}...")
            threading.Thread(target=self.list_files, daemon=True).start()

    def refresh_shares(self):
        try:
            shares = self.conn.listShares()
            self.root.after(0, lambda: self.show_shares(shares))
        except Exception as e:
             self.show_error("连接错误", str(e))

    def on_refresh(self):
        if self.conn is None:
            return

        if self.current_share is None:
            self.update_status("正在刷新共享列表...")
            threading.Thread(target=self.refresh_shares, daemon=True).start()
        else:
            self.update_status(f"正在刷新...")
            threading.Thread(target=self.list_files, daemon=True).start()

    def execute_action(self, mode):
        selected_items = self.tree.selection()
        if not selected_items:
            return

        # mode passed as argument
        
        # 收集所有选中的文件（忽略文件夹） -> This comment is outdated
        files_to_process = []
        has_folder = False
        for iid in selected_items:
            item = self.tree.item(iid)
            if item['values'][1] == "文件夹":
                has_folder = True
            files_to_process.append(item['text'])
        
        if not files_to_process:
            msg = "未选择文件。"
            messagebox.showinfo("提示", msg)
            return

        # 仅删除模式
        if mode == "仅删除":
            if not messagebox.askyesno("确认删除", f"确定要永久删除选中的 {len(files_to_process)} 个文件/文件夹吗？\n此操作不可恢复！"):
                return
            threading.Thread(target=self.perform_delete_only, args=(files_to_process,), daemon=True).start()
            return

        # 下载模式 (仅下载 或 下载并删除)
        delete_after = (mode == "下载并删除")
        
        # removed folder check warning
        
        # 获取保存路径
        target_dir = self.download_save_path.get().strip()
        if not target_dir:
            # Fallback to desktop if empty
            target_dir = os.path.join(os.path.expanduser("~"), "Desktop")
            self.download_save_path.set(target_dir)

        if not os.path.exists(target_dir):
            try:
                os.makedirs(target_dir)
            except Exception as e:
                 messagebox.showerror("错误", f"无法创建保存目录: {target_dir}\n{str(e)}")
                 return

        # 如果只包含一个文件
        if len(files_to_process) == 1:
            filename = files_to_process[0]
            # No dialog, use target_dir directly
            threading.Thread(target=self.perform_download_single, args=(filename, target_dir, delete_after), daemon=True).start()
        else:
            # 批量操作
            # No dialog, use target_dir
            threading.Thread(target=self.perform_download_batch, args=(files_to_process, target_dir, delete_after), daemon=True).start()

    def perform_delete_only(self, files):
        success_count = 0
        total = len(files)
        errors = []

        for index, filename in enumerate(files, 1):
            try:
                self.update_status(f"正在删除 ({index}/{total}): {filename}...")
                path_to_file = filename
                if self.current_path:
                    path_to_file = f"{self.current_path}/{filename}"
                
                is_directory = False
                try:
                    attr = self.conn.getAttributes(self.current_share, path_to_file)
                    is_directory = attr.isDirectory
                except:
                    pass

                if is_directory:
                    self.delete_directory_recursive(self.current_share, path_to_file)
                else:
                    self.conn.deleteFiles(self.current_share, path_to_file)
                
                success_count += 1
            except Exception as e:
                errors.append(f"{filename}: {str(e)}")
        
        self.update_status(f"删除完成。成功: {success_count}/{total}")
        
        # Refresh list if any success
        if success_count > 0:
            self.list_files()
            
        if errors:
            report = f"删除完成。\n成功: {success_count}\n失败: {len(errors)}\n\n错误详情:\n" + "\n".join(errors[:5])
            self.root.after(0, lambda: messagebox.showwarning("删除报告", report))
        else:
             self.root.after(0, lambda: messagebox.showinfo("成功", f"成功删除 {success_count} 个文件。"))

    def perform_download_single(self, filename, target_dir, delete_after):
        try:
            self.update_status(f"正在下载 {filename}...")
            path_to_file = filename
            if self.current_path:
                path_to_file = f"{self.current_path}/{filename}"
            
            save_path = os.path.join(target_dir, filename)
            
            is_directory = False
            try:
                attr = self.conn.getAttributes(self.current_share, path_to_file)
                is_directory = attr.isDirectory
            except:
                pass

            if is_directory:
                self.download_directory_recursive(self.current_share, path_to_file, save_path)
            else:
                with open(save_path, 'wb') as f:
                    self.conn.retrieveFile(self.current_share, path_to_file, f)
            
            msg = f"下载完成: {save_path}"
            if delete_after:
                if is_directory:
                    # Directory delete not fully safe/implemented recursively here yet for delete-after
                    msg += "\n(文件夹删除暂不支持，请手动删除)"
                else:
                    self.update_status(f"下载完成，正在删除 {filename}...")
                    self.conn.deleteFiles(self.current_share, path_to_file)
                    msg += "\n并已成功从服务器删除。"
                    # Refresh file list
                    self.list_files()
            
            self.update_status(f"处理完成: {filename}")
            self.root.after(0, lambda: messagebox.showinfo("成功", msg))
        except Exception as e:
            self.show_error("操作错误", str(e))
            self.update_status("操作失败")

    def download_directory_recursive(self, share, remote_path, local_path):
        if not os.path.exists(local_path):
            os.makedirs(local_path)
            
        # List contents of the remote directory
        try:
            items = self.conn.listPath(share, remote_path)
            for item in items:
                if item.filename in ['.', '..']:
                    continue
                
                remote_item_path = os.path.join(remote_path, item.filename).replace('\\', '/')
                local_item_path = os.path.join(local_path, item.filename)
                
                if item.isDirectory:
                    self.download_directory_recursive(share, remote_item_path, local_item_path)
                else:
                    with open(local_item_path, 'wb') as f:
                        self.conn.retrieveFile(share, remote_item_path, f)
        except Exception as e:
            print(f"Error downloading directory {remote_path}: {e}")
            raise e

    def delete_directory_recursive(self, share, remote_path):
        # List contents
        try:
            items = self.conn.listPath(share, remote_path)
            for item in items:
                if item.filename in ['.', '..']:
                    continue
                
                item_path = os.path.join(remote_path, item.filename).replace('\\', '/')
                
                if item.isDirectory:
                    self.delete_directory_recursive(share, item_path)
                else:
                    self.conn.deleteFiles(share, item_path)
            
            # After emptying, delete the directory itself
            self.conn.deleteDirectory(share, remote_path)
        except Exception as e:
            print(f"Error deleting directory {remote_path}: {e}")
            raise e

    def perform_download_batch(self, files, target_dir, delete_after):
        success_count = 0
        total = len(files)
        errors = []

        for index, filename in enumerate(files, 1):
            try:
                self.update_status(f"正在处理 ({index}/{total}): {filename}...")
                path_to_file = filename
                if self.current_path:
                    path_to_file = f"{self.current_path}/{filename}"
                
                save_path = os.path.join(target_dir, filename)
                
                # Check if it's a directory (we need to know if the selected item is a dir)
                # We can check self.file_list if we stored it, or just try/except or check via listPath?
                # A simple way is to check the tree item values again or just try to download as file and fail?
                # Better: In execute_action we know if it is a folder. But here we just have filenames.
                # We should probably pass the type or reference to the item.
                # However, the treeview has the type.
                
                # Let's check attributes of the file first to know if it is a directory.
                # Since we already have the file list in the tree, we can assume the user input 'files' came from the tree.
                # But 'files' argument here is just a list of strings (filenames).
                # We need to re-fetch attributes or assume.
                
                # To be robust, let's get attributes.
                # But wait, 'files' are from tree selection.
                # We can pass a list of (filename, is_dir) tuples instead of just strings?
                # That would require changing execute_action packing.
                pass 
                
                # RE-IMPLEMENTATION BELOW will handle checking via `getAttributes` or just try/except.
                # Actually, `files` passed into this function are just names. 
                # Let's change the logic in `execute_action` to pass (name, is_dir) tuples or just check here.
                # Checking here is safer.
                
                is_directory = False
                try:
                    # Get attributes to check if directory
                    attr = self.conn.getAttributes(self.current_share, path_to_file)
                    is_directory = attr.isDirectory
                except:
                    # If we can't get attributes, maybe it doesn't exist? verify via listing?
                    # Or just assume file.
                    pass

                if is_directory:
                    self.download_directory_recursive(self.current_share, path_to_file, save_path)
                else:
                    with open(save_path, 'wb') as f:
                        self.conn.retrieveFile(self.current_share, path_to_file, f)
                
                # Delete if requested, ONLY after successful download
                if delete_after:
                     if is_directory:
                         # Recursive delete for directory?
                         # For now, let's SKIP deleting directories to be safe as per plan.
                         # Or we can try to delete. `deleteDirectory` only works on empty.
                         pass
                     else:
                        self.conn.deleteFiles(self.current_share, path_to_file)
                
                success_count += 1
            except Exception as e:
                errors.append(f"{filename}: {str(e)}")

        status_msg = f"批量处理完成。成功: {success_count}/{total}"
        if errors:
             status_msg += f" 失败: {len(errors)}"
        
        self.update_status(status_msg)
        
        if success_count > 0 and delete_after:
            self.list_files()

        report = f"处理完成。\n成功: {success_count}\n失败: {len(errors)}"
        if errors:
            report += "\n\n错误详情 (前5个):\n" + "\n".join(errors[:5])
        
        self.root.after(0, lambda: messagebox.showinfo("报告", report))

    def on_closing(self):
        self.minimize_to_tray()

    def minimize_to_tray(self):
        self.root.withdraw()
        
        # Load icon image
        icon_path = self.resource_path(APP_ICON_NAME)
        image = Image.open(icon_path) if os.path.exists(icon_path) else self.create_default_icon()
        
        # Set default action on double click (or single click depending on OS)
        menu = pystray.Menu(
            pystray.MenuItem("显示", self.show_window, default=True),
            pystray.MenuItem("退出", self.quit_window)
        )
        
        self.icon = pystray.Icon("name", image, APP_TITLE, menu)
        # Use setup callback to show notification once icon is ready
        threading.Thread(target=self.icon.run, kwargs={'setup': self.setup_tray}, daemon=True).start()

    def setup_tray(self, icon):
        icon.visible = True
        try:
            icon.notify("程序已最小化到此处，双击图标可恢复显示", COMPANY_NAME)
        except Exception as e:
            print(f"Notification failed: {e}")

    def show_window(self, icon, item):
        self.icon.stop()
        self.root.after(0, self.root.deiconify)

    def quit_window(self, icon, item):
        self.icon.stop()
        self.root.after(0, self.root.destroy)

    def create_default_icon(self):
        # Create a basic image if icon file not found
        width = 64
        height = 64
        color1 = (0, 0, 255)
        color2 = (255, 255, 255)
        image = Image.new('RGB', (width, height), color1)
        return image

    def show_settings(self):
        if hasattr(self, 'settings_win') and self.settings_win.winfo_exists():
            self.settings_win.lift()
            return
        self.settings_win = SettingsDialog(self.root, self, self.app_config)

    def update_settings(self, new_conf):
        # Update config dict
        self.app_config.update(new_conf)
        self.save_config()
        
        # Apply Auto Start
        self.set_auto_start(self.app_config.get("auto_start_enabled", False))
        
        # Trigger automation thread check (it loops, so it will pick up changes)
        # But if we just enabled it, we might want to wake it up or just wait for next loop.
        # It runs in a loop checking the flag, so it's fine.

    def set_auto_start(self, enable):
        if platform.system() != "Windows":
            return
            
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "YunKaiSMBClient"
        exe_path = sys.executable
        
        # If running as script, use python executable + script path (but usually we package it)
        # For frozen app (PyInstaller):
        if getattr(sys, 'frozen', False):
            exe_path = sys.executable
        else:
            # Development mode: maybe skip or point to python
            # exe_path = f'"{sys.executable}" "{os.path.abspath(__file__)}"'
            return # Skip in dev mode or handle carefully

        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            if enable:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            print(f"Auto-start registry error: {e}")

    def start_automation_thread(self):
        # Start a daemon thread that runs forever
        threading.Thread(target=self.automation_loop, daemon=True).start()

    def automation_loop(self):
        while True:
             try:
                # Check interval
                interval = self.app_config.get("check_interval", 60)
                if interval < 5: interval = 5 # Safety minimum
                time.sleep(interval)
                
                if not self.app_config.get("auto_download_enabled", False):
                    continue
                
                # Check requirements
                src_path = self.app_config.get("auto_source_path", "").strip()
                local_path = self.app_config.get("auto_local_path", "").strip()
                ip = self.app_config.get("ip", "")
                
                if not src_path or not local_path or not ip:
                    continue
                
                # Connect with separate connection
                client_name = socket.gethostname().split('.')[0][:15]
                conn = SMBConnection(
                    self.app_config.get("user", "guest"),
                    self.app_config.get("password", ""),
                    client_name,
                    self.server_ip.get() or "Server", # Remote name guess
                    use_ntlm_v2=True,
                    is_direct_tcp=True
                )
                
                # Try connect
                connected = conn.connect(ip, int(self.app_config.get("port", 445)), timeout=10)
                if not connected:
                     # Fallback port 139?
                     connected = conn.connect(ip, 139, timeout=10)
                
                if not connected:
                    print("Auto-download: Connection failed")
                    continue
                
                # List files
                # src_path format: "ShareName/Folder/Subfolder"
                # Need to split Share and Path
                parts = src_path.replace('\\', '/').split('/', 1)
                share = parts[0]
                rel_path = parts[1] if len(parts) > 1 else ""
                
                files = conn.listPath(share, rel_path)
                
                for f in files:
                    if f.filename in ['.', '..']: continue
                    if f.isDirectory: continue # Skip folders for now in automation
                    
                    # Check History
                    if self.app_config.get("skip_downloaded_today", True):
                        if self.history.is_downloaded(f.filename):
                            continue
                    
                    # Download
                    if not os.path.exists(local_path):
                        os.makedirs(local_path)
                        
                    file_path = os.path.join(local_path, f.filename)
                    remote_file_path = os.path.join(rel_path, f.filename).replace('\\', '/')
                    
                    with open(file_path, 'wb') as local_f:
                        conn.retrieveFile(share, remote_file_path, local_f)
                    
                    # Mark history
                    self.history.add_record(f.filename)
                    
                    # Delete if enabled
                    if self.app_config.get("delete_after_download", False):
                        conn.deleteFiles(share, remote_file_path)
                        print(f"Auto-download: Downloaded & Deleted {f.filename}")
                    else:
                        print(f"Auto-download: Downloaded {f.filename}")
                
                conn.close()
                
             except Exception as e:
                 print(f"Auto-download error: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = SMBBrowserApp(root)
    root.mainloop()
