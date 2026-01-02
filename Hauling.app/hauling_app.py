import os
import json
import shutil
import time
import uuid
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageGrab, ImageTk
from google import genai
from pydantic import BaseModel, Field
from typing import List

# --- CONSTANTS ---
DB_FILE = "hauling_database.json"
CONFIG_FILE = "hauling_config.json"
HISTORY_DIR = "processed_history"

# --- DATA MODELS ---
class Shipment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    commodity: str = Field(description="Item name (e.g. 'Iron').")
    quantity_scu: int = Field(description="Quantity.")
    pickup_location: str = Field(description="Pickup location.")
    delivery_location: str = Field(description="Delivery location.")
    delivered: bool = False

class HaulingContract(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_image: str = ""
    reward_auec: int = Field(description="Contract reward.")
    shipments: List[Shipment] = Field(description="List of shipments.")
    created_at: float = Field(default_factory=time.time)

    @property
    def is_complete(self):
        if not self.shipments: return False
        return all(s.delivered for s in self.shipments)

    @property
    def remaining_scu(self):
        return sum(s.quantity_scu for s in self.shipments if not s.delivered)

    @property
    def destinations(self):
        return ", ".join(sorted(list(set(s.delivery_location for s in self.shipments))))

    @property
    def commodities(self):
        return ", ".join(sorted(list(set(s.commodity for s in self.shipments))))

# --- CONFIG MANAGER ---
class ConfigManager:
    def __init__(self):
        self.api_key = ""
        self.model_name = "gemini-2.0-flash" # Default fallback
        self.load_config()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    self.api_key = data.get("api_key", "")
                    self.model_name = data.get("model_name", "gemini-2.0-flash")
            except Exception as e:
                print(f"Config load error: {e}")

    def save_config(self, api_key, model_name):
        self.api_key = api_key
        self.model_name = model_name
        with open(CONFIG_FILE, 'w') as f:
            json.dump({"api_key": self.api_key, "model_name": self.model_name}, f)

# --- BACKEND LOGIC ---
class MissionManager:
    def __init__(self, config_manager):
        self.cfg = config_manager
        self.contracts = []
        self.load_db()
        
        if not os.path.exists(HISTORY_DIR):
            os.makedirs(HISTORY_DIR)

    def get_client(self):
        if not self.cfg.api_key:
            return None
        return genai.Client(api_key=self.cfg.api_key)

    def load_db(self):
        if os.path.exists(DB_FILE):
            try:
                with open(DB_FILE, 'r') as f:
                    data = json.load(f)
                    self.contracts = []
                    for c_data in data:
                        if 'id' not in c_data: c_data['id'] = str(uuid.uuid4())
                        self.contracts.append(HaulingContract(**c_data))
            except Exception as e:
                print(f"Error loading DB: {e}")

    def save_db(self):
        with open(DB_FILE, 'w') as f:
            json.dump([c.model_dump() for c in self.contracts], f, indent=2)

    def process_image(self, image_path, original_filename=None):
        client = self.get_client()
        if not client:
            return False, "No API Key configured. Go to Settings."

        try:
            img = Image.open(image_path)
            prompt = """
            Analyze this Star Citizen contract.
            1. Find 'Reward' for 'reward_auec'.
            2. Identify shipments (Collect/Deliver pairs).
            """
            response = client.models.generate_content(
                model=self.cfg.model_name,
                contents=[img, prompt],
                config={'response_mime_type': 'application/json', 'response_schema': HaulingContract}
            )
            data = json.loads(response.text)
            contract = HaulingContract(**data)
            
            if original_filename:
                contract.source_image = original_filename
            else:
                contract.source_image = os.path.basename(image_path)
                
            self.contracts.append(contract)
            self.save_db()
            
            # History move
            if os.path.exists(image_path) and original_filename:
                dest = os.path.join(HISTORY_DIR, os.path.basename(image_path))
                if os.path.exists(dest):
                    base, ext = os.path.splitext(os.path.basename(image_path))
                    dest = os.path.join(HISTORY_DIR, f"{base}_{int(time.time())}{ext}")
                shutil.move(image_path, dest)
            return True, "Success"
        except Exception as e:
            return False, str(e)

    def toggle_shipment(self, contract_id, shipment_id):
        for c in self.contracts:
            if c.id == contract_id:
                for s in c.shipments:
                    if s.id == shipment_id:
                        s.delivered = not s.delivered
                        self.save_db()
                        return

# --- SETTINGS GUI ---
class ConfigWindow(tk.Toplevel):
    def __init__(self, parent, config_manager):
        super().__init__(parent)
        self.cfg = config_manager
        self.title("Configuration")
        self.geometry("500x400")
        self.parent = parent
        
        # UI Elements
        ttk.Label(self, text="Google API Configuration", font=("Arial", 14, "bold")).pack(pady=10)
        
        # API Key Input
        frame_key = ttk.LabelFrame(self, text="API Key", padding=10)
        frame_key.pack(fill="x", padx=10, pady=5)
        
        self.var_apikey = tk.StringVar(value=self.cfg.api_key)
        entry_key = ttk.Entry(frame_key, textvariable=self.var_apikey, width=50, show="*")
        entry_key.pack(side="left", padx=5)
        
        btn_show = ttk.Button(frame_key, text="👁", width=3, command=lambda: self.toggle_show(entry_key))
        btn_show.pack(side="left")

        # Model Selection
        frame_model = ttk.LabelFrame(self, text="Model Selection", padding=10)
        frame_model.pack(fill="x", padx=10, pady=5)
        
        self.btn_fetch = ttk.Button(frame_model, text="🔄 Connect & Fetch Models", command=self.fetch_models)
        self.btn_fetch.pack(fill="x", pady=5)
        
        ttk.Label(frame_model, text="Select Model:").pack(anchor="w")
        self.combo_models = ttk.Combobox(frame_model, state="readonly")
        self.combo_models.pack(fill="x", pady=5)
        self.combo_models.set(self.cfg.model_name)
        
        self.lbl_suggestion = ttk.Label(frame_model, text="", foreground="blue", wraplength=450)
        self.lbl_suggestion.pack(pady=5)
        
        # Save Button
        ttk.Button(self, text="💾 Save Configuration", command=self.save_settings).pack(pady=20, fill="x", padx=20)

    def toggle_show(self, entry):
        if entry.cget('show') == '':
            entry.config(show='*')
        else:
            entry.config(show='')

    def fetch_models(self):
        key = self.var_apikey.get().strip()
        if not key:
            messagebox.showerror("Error", "Please enter an API Key first.")
            return
            
        try:
            client = genai.Client(api_key=key)
            self.lbl_suggestion.config(text="Connecting to Google...", foreground="black")
            self.update()
            
            models = []
            # List models
            for m in client.models.list():
                if "generateContent" in m.supported_generation_methods:
                    models.append(m.name)
            
            if not models:
                messagebox.showwarning("Warning", "No models found regarding generateContent.")
                return

            # Sort and populate
            models.sort()
            self.combo_models['values'] = models
            
            # Smart Suggestion Logic
            recommended = None
            # Priority list for "Best" model for this task
            priorities = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
            
            for p in priorities:
                # Look for exact matches or versioned matches (e.g. flash-001)
                matches = [m for m in models if p in m]
                if matches:
                    # Pick the shortest name usually implies the stable alias
                    recommended = min(matches, key=len) 
                    break
            
            if not recommended:
                recommended = models[0] # Fallback
                
            self.combo_models.set(recommended)
            self.lbl_suggestion.config(text=f"✅ Connected! Recommended Model: {recommended}", foreground="green")
            
        except Exception as e:
            self.lbl_suggestion.config(text=f"Error: {e}", foreground="red")
            messagebox.showerror("Connection Failed", str(e))

    def save_settings(self):
        key = self.var_apikey.get().strip()
        model = self.combo_models.get().strip()
        
        if not key or not model:
            messagebox.showwarning("Incomplete", "Please provide both an API Key and select a Model.")
            return
            
        self.cfg.save_config(key, model)
        messagebox.showinfo("Saved", "Configuration saved successfully!")
        self.destroy()

# --- MAIN GUI ---
class HaulingApp(tk.Tk):
    def __init__(self, manager):
        super().__init__()
        self.manager = manager
        self.title("Star Citizen Hauling Logistics")
        self.geometry("1100x700")
        
        # Top Toolbar
        toolbar = ttk.Frame(self, padding=5)
        toolbar.pack(side="top", fill="x")
        
        ttk.Button(toolbar, text="⚙️ Settings", command=self.open_settings).pack(side="right")
        self.lbl_current_config = ttk.Label(toolbar, text=f"Model: {self.manager.cfg.model_name}", foreground="gray")
        self.lbl_current_config.pack(side="right", padx=10)

        # Tabs
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(expand=1, fill="both")
        
        self.tab1 = ttk.Frame(self.tabs)
        self.tab2 = ttk.Frame(self.tabs)
        self.tab4 = ttk.Frame(self.tabs) 
        self.tab3 = ttk.Frame(self.tabs)
        
        self.tabs.add(self.tab1, text="📍 Active Deliveries")
        self.tabs.add(self.tab2, text="📜 Active Contracts")
        self.tabs.add(self.tab4, text="💰 Completed History")
        self.tabs.add(self.tab3, text="📥 Import")
        
        self.setup_tab1()
        self.setup_tab2()
        self.setup_tab4()
        self.setup_tab3()
        
        self.refresh_data()
        
        # Check if setup is needed on first run
        if not self.manager.cfg.api_key:
            self.after(500, self.open_settings)

    def open_settings(self):
        win = ConfigWindow(self, self.manager.cfg)
        self.wait_window(win)
        # Refresh UI label after close
        self.lbl_current_config.config(text=f"Model: {self.manager.cfg.model_name}")

    # --- TAB 1: ACTIVE SHIPMENTS ---
    def setup_tab1(self):
        self.t1_info_frame = ttk.Frame(self.tab1, padding=10, relief="groove")
        self.t1_info_frame.pack(fill="x", side="top")
        self.lbl_t1_stats = ttk.Label(self.t1_info_frame, text="Loading...", font=("Arial", 11, "bold"))
        self.lbl_t1_stats.pack()

        self.canvas = tk.Canvas(self.tab1)
        self.scrollbar = ttk.Scrollbar(self.tab1, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        self.t1_content = ttk.Frame(self.scrollable_frame)
        self.t1_content.pack(fill="both", expand=True)

    # --- TAB 2: ACTIVE CONTRACTS ---
    def setup_tab2(self):
        cols = ("Image", "Destinations", "Items", "Progress", "Reward")
        self.tree_active = ttk.Treeview(self.tab2, columns=cols, show='headings')
        
        self.tree_active.heading("Image", text="Contract Source")
        self.tree_active.heading("Destinations", text="Deliver To")
        self.tree_active.heading("Items", text="Cargo")
        self.tree_active.heading("Progress", text="Status")
        self.tree_active.heading("Reward", text="Value")
        
        self.tree_active.column("Image", width=150)
        self.tree_active.column("Destinations", width=200)
        self.tree_active.column("Items", width=200)
        self.tree_active.column("Progress", width=100)
        self.tree_active.column("Reward", width=100, anchor="e")

        self.tree_active.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.lbl_t2_total = ttk.Label(self.tab2, text="Total Active Value: 0 aUEC", font=("Arial", 12, "bold"))
        self.lbl_t2_total.pack(pady=10, padx=10, anchor="e")

    # --- TAB 4: COMPLETED HISTORY ---
    def setup_tab4(self):
        cols = ("Image", "Destinations", "Items", "Reward")
        self.tree_history = ttk.Treeview(self.tab4, columns=cols, show='headings')
        self.tree_history.heading("Image", text="Contract Source")
        self.tree_history.heading("Destinations", text="Delivered To")
        self.tree_history.heading("Items", text="Cargo")
        self.tree_history.heading("Reward", text="Paid (aUEC)")
        self.tree_history.column("Reward", anchor="e")
        
        self.tree_history.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.lbl_t4_total = ttk.Label(self.tab4, text="Total Earnings: 0 aUEC", font=("Arial", 14, "bold"), foreground="green")
        self.lbl_t4_total.pack(pady=10, padx=10, anchor="e")

    # --- TAB 3: IMPORT ---
    def setup_tab3(self):
        frame = ttk.Frame(self.tab3, padding=20)
        frame.pack(fill="both", expand=True)
        
        ttk.Label(frame, text="Batch Process Folder", font=("Arial", 12, "bold")).pack(anchor="w")
        ttk.Button(frame, text="Select Folder with Screenshots", command=self.process_folder).pack(pady=5, anchor="w")
        
        ttk.Separator(frame, orient='horizontal').pack(fill='x', pady=20)
        
        ttk.Label(frame, text="Quick Paste", font=("Arial", 12, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Take a screenshot (Win+Shift+S) then click below:").pack(anchor="w")
        ttk.Button(frame, text="Paste Image from Clipboard", command=self.process_clipboard).pack(pady=5, anchor="w")

        self.log_text = tk.Text(frame, height=10, state='disabled', bg="#f0f0f0")
        self.log_text.pack(fill="x", pady=20)

    def log(self, message):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
        self.update_idletasks()

    def refresh_data(self):
        active_contracts = [c for c in self.manager.contracts if not c.is_complete]
        completed_contracts = [c for c in self.manager.contracts if c.is_complete]
        
        total_active_value = sum(c.reward_auec for c in active_contracts)
        total_earned_value = sum(c.reward_auec for c in completed_contracts)
        
        total_remaining_scu = 0
        for c in active_contracts:
            total_remaining_scu += c.remaining_scu

        self.lbl_t1_stats.config(text=f"📦 Remaining Cargo: {total_remaining_scu} SCU   |   💰 Potential Payout: {total_active_value:,.0f} aUEC")
        self.lbl_t2_total.config(text=f"Total Pending Value: {total_active_value:,.0f} aUEC")
        self.lbl_t4_total.config(text=f"TOTAL EARNINGS: {total_earned_value:,.0f} aUEC")

        # REFRESH TAB 1
        for widget in self.t1_content.winfo_children():
            widget.destroy()
            
        grouped = {}
        for c in active_contracts:
            for s in c.shipments:
                if not s.delivered:
                    if s.delivery_location not in grouped: grouped[s.delivery_location] = []
                    grouped[s.delivery_location].append((c, s))

        if not grouped:
            ttk.Label(self.t1_content, text="No active deliveries! Import a contract to start.", padding=20).pack()

        for location, items in grouped.items():
            loc_frame = ttk.LabelFrame(self.t1_content, text=f" 🏢 {location} ", padding=10)
            loc_frame.pack(fill="x", padx=10, pady=5)
            
            for contract, shipment in items:
                row = ttk.Frame(loc_frame)
                row.pack(fill="x", pady=2)
                
                txt = f"[{shipment.commodity}]  {shipment.quantity_scu} SCU  (Pickup: {shipment.pickup_location})"
                ttk.Label(row, text=txt, font=("Consolas", 10)).pack(side="left")
                
                ttk.Button(row, text="Mark Delivered", 
                           command=lambda c=contract.id, s=shipment.id: self.mark_done(c, s)).pack(side="right")

        # REFRESH TAB 2
        for item in self.tree_active.get_children():
            self.tree_active.delete(item)
        for c in active_contracts:
            done = sum(1 for s in c.shipments if s.delivered)
            progress_str = f"{done}/{len(c.shipments)} Items"
            self.tree_active.insert("", "end", values=(c.source_image, c.destinations, c.commodities, progress_str, f"{c.reward_auec:,}"))

        # REFRESH TAB 4
        for item in self.tree_history.get_children():
            self.tree_history.delete(item)
        for c in completed_contracts:
            self.tree_history.insert("", "end", values=(c.source_image, c.destinations, c.commodities, f"{c.reward_auec:,}"))

    def mark_done(self, contract_id, shipment_id):
        self.manager.toggle_shipment(contract_id, shipment_id)
        self.refresh_data()

    def process_folder(self):
        if not self.manager.cfg.api_key:
            messagebox.showerror("Error", "Please configure your API Key in Settings first.")
            return
        folder = filedialog.askdirectory()
        if not folder: return
        files = [f for f in os.listdir(folder) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        if not files:
            messagebox.showinfo("Info", "No images found.")
            return

        self.log(f"Processing {len(files)} images...")
        for f in files:
            self.manager.process_image(os.path.join(folder, f), original_filename=f)
        self.refresh_data()
        self.log("Batch complete.")
        messagebox.showinfo("Done", "Processing complete!")

    def process_clipboard(self):
        if not self.manager.cfg.api_key:
            messagebox.showerror("Error", "Please configure your API Key in Settings first.")
            return
        try:
            img = ImageGrab.grabclipboard()
            if isinstance(img, Image.Image):
                temp_name = f"clipboard_{int(time.time())}.png"
                img.save(temp_name)
                self.log("Analyzing clipboard...")
                success, msg = self.manager.process_image(temp_name, original_filename="Clipboard Paste")
                if os.path.exists(temp_name): os.remove(temp_name)
                if success:
                    self.refresh_data()
                    self.log("Success!")
                else:
                    self.log(f"Error: {msg}")
            else:
                messagebox.showwarning("Warning", "No image in clipboard.")
        except Exception as e:
            self.log(f"Clipboard error: {e}")

if __name__ == "__main__":
    cfg_mgr = ConfigManager()
    mission_mgr = MissionManager(cfg_mgr)
    app = HaulingApp(mission_mgr)
    app.mainloop()