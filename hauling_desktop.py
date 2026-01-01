import os
import time
import json
import re
import threading
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

# --- CONFIGURAÇÃO E CONSTANTES ---
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(BASE_DIR, 'hauling_config.json')
STATE_FILE = os.path.join(BASE_DIR, 'hauling_state.json')

# --- ESTADO GLOBAL ---
data_store = {
    "missions": {}, 
    "finished_missions": [], 
    "current_location": "Desconhecido", 
    "total_earnings": 0,
    "session_start": datetime.now().isoformat()
}

def load_config():
    default_config = {
        "log_path": r"C:\Program Files\Roberts Space Industries\StarCitizen\LIVE\Game.log"
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            return default_config
    return default_config

def save_config(config):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Erro ao salvar config: {e}")

def json_serial(obj):
    if isinstance(obj, (datetime, set)):
        return str(obj)
    return str(obj)

def save_state():
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_store, f, default=json_serial, indent=2)
    except Exception as e:
        print(f"⚠ Failed to save state: {e}")

def load_state():
    global data_store
    if not os.path.exists(STATE_FILE):
        return
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            saved = json.load(f)
            
            # Verificar se é do mesmo dia
            if "session_start" in saved:
                saved_date = saved["session_start"].split('T')[0]
                today_date = datetime.now().isoformat().split('T')[0]
                if saved_date != today_date:
                    print("📅 Sessão anterior de outro dia. Iniciando limpo.")
                    return 

            data_store.update(saved)
            print(f"✅ Estado restaurado: {len(data_store['missions'])} missões ativas.")
    except Exception as e:
        print(f"⚠ Erro ao carregar estado: {e}")

def clean_location_name(raw_name):
    """Limpa nomes de localização dos logs"""
    if not raw_name: return "Desconhecido"
    name = re.sub(r'^(OOC_|ObjectContainer_)', '', raw_name)
    name = re.sub(r'Stanton_\d+_', '', name, flags=re.IGNORECASE)
    name = name.replace('_', ' ').replace("DistributionCentre", "Dist.Center")
    name = name.title()
    name = re.sub(r'\bOm\b', 'OM', name)
    name = re.sub(r'\bL(\d+)\b', r'L\1', name)
    return name.strip()

# --- MONITOR DE LOGS (LÓGICA COMPLETA) ---
class HaulingMonitor:
    def __init__(self, log_path):
        self.log_path = log_path
        self.running = False
        self.processed_notification_ids = set()
        self.last_notification_mission_id = None

    def start(self):
        self.running = True
        t = threading.Thread(target=self.tail_log_file, daemon=True)
        t.start()

    def process_line(self, line):
        line = line.strip()

        # 1. Localização
        if "<RequestLocationInventory>" in line:
            match = re.search(r"Location\[(.*?)\]", line)
            if match:
                loc = clean_location_name(match.group(1))
                data_store["current_location"] = loc
                save_state()

        # 2. Notificações SHUDEvent (Missão Backend ID)
        if "<SHUDEvent_OnNotification>" in line and "MissionId:" in line:
            notif_id_match = re.search(r'Added notification ".*?" \[(\d+)\]', line)
            if notif_id_match:
                self.processed_notification_ids.add(notif_id_match.group(1))

            mid_match = re.search(r'MissionId:\s*\[([a-f0-9\-]+)\]', line)
            if mid_match:
                mission_id = mid_match.group(1)
                text_match = re.search(r'Added notification "(.*?)"', line)
                if text_match:
                    notification_text = text_match.group(1)
                    
                    if "Contract Accepted" in notification_text:
                        title_match = re.search(r'Contract Accepted:\s*(.+?)(?::|\"|\[)', notification_text)
                        title = title_match.group(1).strip() if title_match else "Unknown Contract"
                        if mission_id not in data_store["missions"]:
                            data_store["missions"][mission_id] = {
                                "id": mission_id, "title": title, "items": {}, 
                                "status": "ACTIVE", "timestamp": datetime.now().strftime("%H:%M:%S")
                            }
                            save_state()

                    elif "New Objective" in notification_text or "Objective Complete" in notification_text:
                        if mission_id not in data_store["missions"]:
                            data_store["missions"][mission_id] = {
                                "id": mission_id, "title": "Unknown Mission", "items": {}, 
                                "status": "ACTIVE", "timestamp": datetime.now().strftime("%H:%M:%S")
                            }
                        
                        # Regex para SCU
                        obj_match = re.search(
                            r"(Deliver|Pickup|Dropoff|Transport|Collect|Entregue|Coletar|Pegar)\s+(\d+)(?:[/\s]+(\d+))?\s+SCU\s+(?:of|de)?\s*([A-Za-z0-9\s\(\)\-\.]+?)\s+(?:to|at|for|towards|para|em|de)\s+([A-Za-z0-9\s\(\)\-\.]+?)(?::|\"|\[)", 
                            notification_text, re.IGNORECASE
                        )
                        if obj_match:
                            action = obj_match.group(1).upper()
                            val1 = int(obj_match.group(2))
                            val2 = obj_match.group(3)
                            total = int(val2) if val2 else val1
                            current = val1 if val2 else 0
                            material = obj_match.group(4).strip().upper()
                            location = clean_location_name(obj_match.group(5))
                            
                            type_str = "PICKUP" if action in ['COLLECT', 'PICKUP', 'COLETAR', 'PEGAR'] else "DELIVERY"
                            item_key = f"{material}_{location}_{type_str}"
                            
                            is_complete_event = "Objective Complete" in notification_text
                            status_val = "COMPLETED" if (is_complete_event or (current >= total and total > 0)) else "PENDING"
                            
                            data_store["missions"][mission_id]["items"][item_key] = {
                                "mat": material, "dest": location, "vol": total, 
                                "delivered": current, "status": status_val, "type": type_str
                            }
                            save_state()

        # 3. UI Notification Fallback (CRITICAL FIX)
        # Handle "Contract Accepted" and "New Objective" from UI notifications (when backend MissionId is missing)
        if "<UpdateNotificationItem>" in line and "Notification" in line:
            # Extract Notification ID to avoid duplicates
            notif_id_match = re.search(r'Notification ".*?" \[(\d+)\]', line)
            if notif_id_match:
                notif_id = notif_id_match.group(1)
                if notif_id in self.processed_notification_ids:
                    return
                self.processed_notification_ids.add(notif_id)
            
            # A. Contract Accepted (Notification)
            if "Contract Accepted" in line:
                title_match = re.search(r'Contract Accepted:\s*(.+?)(?::|\"|\[)', line)
                title = title_match.group(1).strip() if title_match else "Unknown Contract"
                
                # Generate a temporary ID since UI logs don't have the UUID
                m_id = f"ui_{int(time.time()*1000)}"
                self.last_notification_mission_id = m_id
                
                if m_id not in data_store["missions"]:
                    data_store["missions"][m_id] = {
                        "id": m_id, "title": title, "items": {}, 
                        "status": "ACTIVE", "timestamp": datetime.now().strftime("%H:%M:%S")
                    }
                    save_state()
            
            # B. New Objective (Notification)
            elif "New Objective" in line or "Objective Complete" in line:
                obj_match = re.search(
                    r"(Deliver|Pickup|Dropoff|Transport|Collect|Entregue|Coletar|Pegar)\s+(\d+)(?:[/\s]+(\d+))?\s+SCU\s+(?:of|de)?\s*([A-Za-z0-9\s\(\)\-\.]+?)\s+(?:to|at|for|towards|para|em|de)\s+([A-Za-z0-9\s\(\)\-\.]+?)(?::|\"|\[)", 
                    line, re.IGNORECASE
                )
                
                if obj_match:
                    m_id = self.last_notification_mission_id
                    if not m_id:
                        m_id = "ui_unknown_mission"
                        self.last_notification_mission_id = m_id
                        
                    if m_id not in data_store["missions"]:
                         data_store["missions"][m_id] = {
                            "id": m_id, "title": "Unknown Mission (UI)", "items": {}, 
                            "status": "ACTIVE", "timestamp": datetime.now().strftime("%H:%M:%S")
                        }

                    action = obj_match.group(1).upper()
                    val1 = int(obj_match.group(2))
                    val2 = obj_match.group(3)
                    total = int(val2) if val2 else val1
                    current = val1 if val2 else 0
                    material = obj_match.group(4).strip().upper()
                    location = clean_location_name(obj_match.group(5))
                    
                    type_str = "PICKUP" if action in ['COLLECT', 'PICKUP', 'COLETAR', 'PEGAR'] else "DELIVERY"
                    item_key = f"{material}_{location}_{type_str}"
                    
                    # Remove MANUAL_ADD duplicates logic omitted for brevity as it's less critical for desktop MVP, 
                    # but we keep the core update logic.
                    
                    is_complete_event = "Objective Complete" in line
                    status_val = "COMPLETED" if (is_complete_event or (current >= total and total > 0)) else "PENDING"

                    data_store["missions"][m_id]["items"][item_key] = {
                        "mat": material, "dest": location, "vol": total, 
                        "delivered": current, "status": status_val, "type": type_str
                    }
                    save_state()

        # 4. Fim de Missão
        if "<EndMission>" in line or "<MissionEnded>" in line:
            match = re.search(r"Mission\[(.*?)\]", line)
            if match:
                m_id = match.group(1)
                is_success = "Success" in line or "Complete" in line
                
                if m_id in data_store["missions"]:
                    mission = data_store["missions"].pop(m_id)
                    mission["status"] = "Completed" if is_success else "Failed"
                    mission["end_time"] = datetime.now().strftime("%H:%M:%S")
                    
                    reward = 0
                    if "reward" in line.lower():
                        r_match = re.search(r"reward\s*(\d+)", line.lower())
                        if r_match: reward = int(r_match.group(1))
                    
                    mission["final_reward"] = reward
                    if is_success:
                        data_store["total_earnings"] += reward
                        data_store["finished_missions"].insert(0, mission)
                    save_state()

    def tail_log_file(self):
        try:
            with open(self.log_path, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(0, 2)
                while self.running:
                    line = f.readline()
                    if not line:
                        time.sleep(0.5)
                        continue
                    try:
                        self.process_line(line)
                    except Exception as e:
                        print(f"Erro log: {e}")
        except FileNotFoundError:
            print("Log não encontrado")

# --- INTERFACE GRÁFICA ---

class HaulingDesktopApp(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title("Star Citizen Hauling Monitor (Desktop)")
        self.geometry("1100x700")
        
        self.config_data = load_config()
        load_state()
        
        self.monitor = HaulingMonitor(self.config_data.get("log_path", ""))
        self.monitor.start()
        
        self.last_ui_hash = "" # Hash to prevent unnecessary redraws
        
        style = ttk.Style()
        style.theme_use('clam')
        
        self.create_menu()
        
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        self.tab_active = ttk.Frame(self.notebook)
        self.tab_history = ttk.Frame(self.notebook)
        self.tab_config = ttk.Frame(self.notebook)
        
        self.notebook.add(self.tab_active, text="📍 Ativas")
        self.notebook.add(self.tab_history, text="📜 Histórico")
        self.notebook.add(self.tab_config, text="⚙ Configuração")
        
        self.setup_active_tab()
        self.setup_history_tab()
        self.setup_config_tab()
        
        self.status_var = tk.StringVar(value="Monitorando...")
        self.status_bar = ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor='w')
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.update_ui_loop()

    def create_menu(self):
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Sair", command=self.quit)
        menubar.add_cascade(label="Arquivo", menu=file_menu)
        self.config(menu=menubar)

    def setup_active_tab(self):
        self.paused = False # Initialize pause state
        
        top_frame = ttk.Frame(self.tab_active, padding=10)
        top_frame.pack(fill='x')
        
        # Left side: Location
        ttk.Label(top_frame, text="Localização Atual:", font=('Arial', 12, 'bold')).pack(side='left')
        self.lbl_location = ttk.Label(top_frame, text="...", font=('Arial', 12), foreground='blue')
        self.lbl_location.pack(side='left', padx=10)
        
        # Right side: Pause Button
        self.btn_pause = tk.Button(top_frame, text="⏸ PAUSAR", command=self.toggle_pause, bg="#dddddd", relief="raised", font=('Arial', 9, 'bold'), width=12)
        self.btn_pause.pack(side='right')
        
        self.canvas_active = tk.Canvas(self.tab_active)
        scrollbar = ttk.Scrollbar(self.tab_active, orient="vertical", command=self.canvas_active.yview)
        self.scroll_frame_active = ttk.Frame(self.canvas_active)
        
        self.scroll_frame_active.bind("<Configure>", lambda e: self.canvas_active.configure(scrollregion=self.canvas_active.bbox("all")))
        self.canvas_active.create_window((0, 0), window=self.scroll_frame_active, anchor="nw")
        self.canvas_active.configure(yscrollcommand=scrollbar.set)
        
        self.canvas_active.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def setup_history_tab(self):
        frame_stats = ttk.Frame(self.tab_history, padding=10)
        frame_stats.pack(fill='x')
        self.lbl_total_earnings = ttk.Label(frame_stats, text="Total Ganho: 0 aUEC", font=('Arial', 14, 'bold'), foreground='green')
        self.lbl_total_earnings.pack(side='right')
        
        cols = ("Data", "Título", "Status", "Valor")
        self.tree_history = ttk.Treeview(self.tab_history, columns=cols, show='headings')
        self.tree_history.heading("Data", text="Hora")
        self.tree_history.heading("Título", text="Missão")
        self.tree_history.heading("Status", text="Status")
        self.tree_history.heading("Valor", text="Valor (aUEC)")
        self.tree_history.column("Data", width=100)
        self.tree_history.column("Título", width=400)
        self.tree_history.column("Status", width=100)
        self.tree_history.column("Valor", width=100, anchor='e')
        self.tree_history.pack(fill='both', expand=True, padx=10, pady=10)

    def setup_config_tab(self):
        frame = ttk.Frame(self.tab_config, padding=20)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text="Caminho do Game.log:", font=('Arial', 10, 'bold')).pack(anchor='w', pady=5)
        path_frame = ttk.Frame(frame)
        path_frame.pack(fill='x')
        self.entry_log_path = ttk.Entry(path_frame)
        self.entry_log_path.insert(0, self.config_data.get("log_path", ""))
        self.entry_log_path.pack(side='left', fill='x', expand=True)
        ttk.Button(path_frame, text="...", width=3, command=self.browse_log).pack(side='left', padx=5)
        ttk.Button(frame, text="Salvar Configuração", command=self.save_settings).pack(pady=20)

    def browse_log(self):
        filename = filedialog.askopenfilename(title="Selecione o Game.log", filetypes=[("Log Files", "*.log"), ("All Files", "*.*")])
        if filename:
            self.entry_log_path.delete(0, tk.END)
            self.entry_log_path.insert(0, filename)

    def save_settings(self):
        path = self.entry_log_path.get()
        if os.path.exists(path):
            self.config_data["log_path"] = path
            save_config(self.config_data)
            messagebox.showinfo("Sucesso", "Configuração salva! Reinicie o aplicativo para aplicar.")
        else:
            messagebox.showerror("Erro", "Arquivo não encontrado.")

    def toggle_pause(self):
        self.paused = not self.paused
        if self.paused:
            self.btn_pause.config(text="▶ RETOMAR", bg="#ffcc00")
        else:
            self.btn_pause.config(text="⏸ PAUSAR", bg="#dddddd")

    def delete_mission(self, mission_id):
        if messagebox.askyesno("Confirmar", "Tem certeza que deseja excluir esta missão?"):
            if mission_id in data_store["missions"]:
                del data_store["missions"][mission_id]
                save_state()
                # Force UI update immediately
                self.update_ui_loop(force=True)

    def update_ui_loop(self, force=False):
        if self.paused and not force:
            self.after(1000, self.update_ui_loop)
            return

        self.lbl_location.config(text=data_store.get("current_location", "Desconhecido"))
        
        # --- AGGREGATION LOGIC (MATCHING WEB APP) ---
        summary = {}
        missions_needing_input = []
        
        active_missions = data_store.get("missions", {})
        
        for m_id, m_data in active_missions.items():
            # If no items, it goes to "New Missions" list
            if not m_data.get("items"):
                missions_needing_input.append(m_data)
                continue
                
            # Otherwise, aggregate by Destination
            for item in m_data["items"].values():
                d, m, v, status = item["dest"], item["mat"], item["vol"], item["status"]
                delivered = item.get("delivered", 0)
                i_type = item.get("type", "DELIVERY")
                
                if d not in summary:
                    summary[d] = {}
                
                if m not in summary[d]:
                    summary[d][m] = {
                        "pickup_vol": 0, 
                        "deliver_vol": 0, 
                        "status": "PENDING",
                        "delivered_pickup": 0,
                        "delivered_delivery": 0,
                        "mission_ids": set(),
                        "all_items_completed": True
                    }
                
                summary[d][m]["mission_ids"].add(m_id)
                
                if status != "COMPLETED":
                    summary[d][m]["all_items_completed"] = False

                if i_type == "PICKUP":
                    summary[d][m]["pickup_vol"] += v
                    summary[d][m]["delivered_pickup"] += delivered
                else:
                    summary[d][m]["deliver_vol"] += v
                    summary[d][m]["delivered_delivery"] += delivered
                
                if summary[d][m]["all_items_completed"]:
                    summary[d][m]["status"] = "COMPLETED"
                elif summary[d][m]["deliver_vol"] > 0 and summary[d][m]["delivered_delivery"] >= summary[d][m]["deliver_vol"]:
                    summary[d][m]["status"] = "COMPLETED"

        # --- OPTIMIZED RENDER CHECK ---
        import hashlib
        current_state_str = json.dumps(summary, sort_keys=True) + json.dumps(missions_needing_input, sort_keys=True) + str(self.paused)
        current_hash = hashlib.md5(current_state_str.encode()).hexdigest()
        
        if current_hash == self.last_ui_hash and not force:
            self.after(1000, self.update_ui_loop)
            return
            
        self.last_ui_hash = current_hash

        # --- RENDER UI ---
        for widget in self.scroll_frame_active.winfo_children():
            widget.destroy()

        # 1. NEW MISSIONS (Waiting for Cargo)
        if missions_needing_input:
            frame_new = ttk.LabelFrame(self.scroll_frame_active, text=" 📝 NOVOS CONTRATOS (Aguardando Carga) ", padding=10)
            frame_new.pack(fill='x', padx=10, pady=10)
            
            for m in missions_needing_input:
                row = ttk.Frame(frame_new)
                row.pack(fill='x', pady=2)
                
                ttk.Label(row, text=f"📜 {m['title']}", font=('Arial', 10, 'bold')).pack(side='left')
                
                btn_del = ttk.Button(row, text="🗑️", width=3, command=lambda mid=m['id']: self.delete_mission(mid))
                btn_del.pack(side='right', padx=2)
                
                btn_add = ttk.Button(row, text="➕ Itens", command=lambda mid=m['id']: self.open_manual_edit(mid))
                btn_add.pack(side='right', padx=2)

        # 2. DESTINATIONS (Summary View)
        if summary:
            for d, mats in summary.items():
                card = ttk.LabelFrame(self.scroll_frame_active, text=f" 📦 DESTINO: {d} ", padding=10)
                card.pack(fill='x', padx=10, pady=5)
                
                for m, data in mats.items():
                    row = ttk.Frame(card)
                    row.pack(fill='x', pady=5)
                    
                    # Material Name
                    mat_font = ('Arial', 10)
                    mat_fg = 'black'
                    if is_completed:
                         mat_font = ('Arial', 10, 'overstrike')
                         mat_fg = 'gray'
                    
                    ttk.Label(row, text=f"▪ {m}", font=mat_font, foreground=mat_fg).pack(side='left')
                    
                    # Badges Frame
                    badges_frame = ttk.Frame(row)
                    badges_frame.pack(side='left', padx=10)
                    
                    p_vol = data["pickup_vol"]
                    d_vol = data["deliver_vol"]
                    
                    # Pickup Badge
                    if p_vol > 0:
                        p_cur = data["delivered_pickup"]
                        p_done = (p_cur >= p_vol) or is_completed
                        
                        txt = f"⬇️ COLETAR: {p_vol} SCU"
                        if p_cur > 0 and p_cur < p_vol and not p_done:
                             txt = f"⬇️ COLETAR: {p_cur}/{p_vol} SCU"
                        if p_done:
                            txt = f"✅ COLETADO: {p_vol} SCU"
                            
                        lbl = tk.Label(badges_frame, text=txt, bg="#2a0a2a" if not p_done else "#0a2a0a", fg="#ff55ff" if not p_done else "#55ff55", font=('Consolas', 9), padx=5, pady=2)
                        lbl.pack(side='left', padx=2)
                        
                    # Deliver Badge
                    if d_vol > 0:
                        d_cur = data["delivered_delivery"]
                        d_done = (d_cur >= d_vol) or is_completed
                        
                        txt = f"⬆️ ENTREGAR: {d_vol} SCU"
                        if d_cur > 0 and d_cur < d_vol and not d_done:
                             txt = f"⬆️ ENTREGAR: {d_cur}/{d_vol} SCU"
                        if d_done:
                            txt = f"✅ ENTREGUE: {d_vol} SCU"

                        lbl = tk.Label(badges_frame, text=txt, bg="#0a2a2a" if not d_done else "#0a2a0a", fg="#00f2ff" if not d_done else "#55ff55", font=('Consolas', 9), padx=5, pady=2)
                        lbl.pack(side='left', padx=2)

                    # Action Buttons (Edit/Delete)
                    actions_frame = ttk.Frame(row)
                    actions_frame.pack(side='right')
                    
                    if "mission_ids" in data:
                        for mid in data["mission_ids"]:
                             ttk.Button(actions_frame, text="➕", width=3, command=lambda x=mid: self.open_manual_edit(x)).pack(side='left', padx=1)
                             ttk.Button(actions_frame, text="🗑️", width=3, command=lambda x=mid: self.delete_mission(x)).pack(side='left', padx=1)

        # 3. EMPTY STATE
        if not summary and not missions_needing_input:
            ttk.Label(self.scroll_frame_active, text="⏳ Sem missões ativas\nAceite um contrato no jogo para iniciar.", justify='center', padding=20).pack()

        # Atualizar Histórico (Existing Logic)
        hist = data_store.get("finished_missions", [])
        if len(self.tree_history.get_children()) != len(hist):
            for item in self.tree_history.get_children():
                self.tree_history.delete(item)
            total = 0
            for m in hist:
                val = m.get('final_reward', 0)
                # Fallback for 'value' key if 'final_reward' is missing (web app uses 'value')
                if val == 0: val = m.get('value', 0)
                
                total += val
                self.tree_history.insert("", "end", values=(
                    m.get('time', '-'), # Web uses 'time', Desktop used 'end_time'
                    m.get('title', 'Missão Encerrada'),
                    m.get('status', 'Done'),
                    f"{val:,}"
                ))
            self.lbl_total_earnings.config(text=f"Total Ganho: {total:,} aUEC")

        self.after(2000, self.update_ui_loop)

    def open_manual_edit(self, mission_id):
        # Janela popup para edição manual
        popup = tk.Toplevel(self)
        popup.title("Editar Missão Manualmente")
        popup.geometry("400x300")
        
        mission = data_store["missions"].get(mission_id)
        if not mission:
            popup.destroy()
            return

        ttk.Label(popup, text=f"Editando: {mission.get('title')}", font=('Arial', 10, 'bold')).pack(pady=10)
        
        frame_form = ttk.Frame(popup, padding=10)
        frame_form.pack(fill='both', expand=True)
        
        ttk.Label(frame_form, text="Material:").grid(row=0, column=0, sticky='w')
        entry_mat = ttk.Entry(frame_form)
        entry_mat.grid(row=0, column=1, sticky='ew', pady=2)
        
        ttk.Label(frame_form, text="Quantidade (SCU):").grid(row=1, column=0, sticky='w')
        entry_vol = ttk.Entry(frame_form)
        entry_vol.grid(row=1, column=1, sticky='ew', pady=2)
        
        ttk.Label(frame_form, text="Destino:").grid(row=2, column=0, sticky='w')
        entry_dest = ttk.Entry(frame_form)
        entry_dest.grid(row=2, column=1, sticky='ew', pady=2)
        
        frame_form.columnconfigure(1, weight=1)
        
        def save_item():
            mat = entry_mat.get().strip().upper()
            try:
                vol = int(entry_vol.get().strip())
            except:
                vol = 0
            dest = clean_location_name(entry_dest.get().strip())
            
            if not mat or not dest:
                messagebox.showwarning("Aviso", "Preencha Material e Destino!")
                return
            
            # Criar chave única para o item (USANDO TIMESTAMP PARA EVITAR DUPLICATAS)
            import time
            item_key = f"{mat}_{dest}_DELIVERY_{int(time.time())}"
            
            # Atualizar data_store
            if "items" not in data_store["missions"][mission_id]:
                data_store["missions"][mission_id]["items"] = {}
                
            data_store["missions"][mission_id]["items"][item_key] = {
                "mat": mat,
                "dest": dest,
                "vol": vol,
                "delivered": 0,
                "status": "PENDING",
                "type": "DELIVERY",
                "action": "MANUAL_ADD"
            }
            save_state()
            popup.destroy()
            
        ttk.Button(popup, text="💾 Salvar Item", command=save_item).pack(pady=10)
        
        # Lista de itens existentes para referência (opcional)
        if mission.get("items"):
            ttk.Label(popup, text="Itens existentes:", font=('Arial', 9, 'bold')).pack(pady=(10,5))
            list_frame = ttk.Frame(popup)
            list_frame.pack(fill='both', expand=True, padx=10)
            for k, v in mission["items"].items():
                ttk.Label(list_frame, text=f"- {v['mat']} -> {v['dest']} ({v['vol']} SCU)").pack(anchor='w')

if __name__ == "__main__":
    app = HaulingDesktopApp()
    app.mainloop()
