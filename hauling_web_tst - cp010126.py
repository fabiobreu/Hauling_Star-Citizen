import os, time, re, threading, json, sys
from flask import Flask, render_template_string, request, jsonify
from datetime import datetime

# --- CONFIGURATION ---
LOG_PATH = r"C:\Program Files\Roberts Space Industries\StarCitizen\LIVE\Game.log"

if getattr(sys, 'frozen', False):
    # Running as compiled exe
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # Running as script
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(BASE_DIR, 'hauling_config.json')

STATE_FILE = os.path.join(BASE_DIR, 'hauling_state.json')

app = Flask(__name__)

def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, set):
        return list(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

def save_state():
    """Save current data_store to disk"""
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_store, f, default=json_serial, indent=2)
    except Exception as e:
        print(f"⚠ Failed to save state: {e}")

def load_state():
    """Load data_store from disk"""
    global data_store
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                
                # Restore datetime objects
                if 'session_start' in saved:
                    try:
                        saved_start = datetime.fromisoformat(saved['session_start'])
                        
                        # Check if session is from a previous day
                        if saved_start.date() < datetime.now().date():
                            print(f"♻️ Old session found ({saved_start.strftime('%Y-%m-%d')}). Starting fresh.")
                            return # Do not load old state
                        
                        saved['session_start'] = saved_start
                    except:
                        saved['session_start'] = datetime.now()
                
                # Merge into data_store (preserving keys not in saved if any)
                data_store.update(saved)
                print(f"✓ State loaded from {STATE_FILE} (Session: {saved['session_start'].strftime('%H:%M')})")
        except Exception as e:
            print(f"⚠ Failed to load state: {e}")

data_store = {
    "missions": {}, 
    "finished_missions": [], 
    "player_name": "Waiting for Login...", 
    "ship_name": "Waiting for Ship...",
    "current_location": "Synchronizing...", 
    "next_destination": "None",
    "fuel_estimate": 0,
    "mission_status": "READY",
    "session_start": datetime.now()
}

def clean_location_name(raw_name):
    """Convert log location names to readable format - Generic approach"""
    name = re.sub(r'^(OOC_|ObjectContainer_)', '', raw_name)
    name = re.sub(r'Stanton_\d+_', '', name, flags=re.IGNORECASE)
    name = name.replace('_', ' ')
    name = name.title()
    name = re.sub(r'\bOm\b', 'OM', name)
    name = re.sub(r'\bL(\d+)\b', r'L\1', name)
    name = re.sub(r'\bHur\b', 'HUR', name)
    name = re.sub(r'\bCru\b', 'CRU', name)
    name = re.sub(r'\bArc\b', 'ARC', name)
    name = re.sub(r'\bMic\b', 'MIC', name)
    name = re.sub(r'\bHdpc\b', 'HDPC', name)
    name = re.sub(r'\bScu\b', 'SCU', name)
    return name.strip()


def load_saved_config():
    """Load saved config (if any) from disk and merge into LOG_PATH."""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as fh:
                cfg = json.load(fh)
                if 'log_path' in cfg:
                    global LOG_PATH
                    LOG_PATH = cfg['log_path']
                return True
    except Exception as e:
        print(f"⚠ Failed to load config: {e}")
    return False


def save_config(log_path=None):
    """Save config to disk."""
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as fh:
                cfg = json.load(fh)
        except Exception:
            cfg = {}

    if log_path is not None:
        cfg['log_path'] = log_path

    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as fh:
            json.dump(cfg, fh, indent=2)
        return True
    except Exception as e:
        print(f"⚠ Failed to save config: {e}")
        return False



class HaulingMonitor:
    def __init__(self):
        self.processed_ids = set()
        self.processed_notification_ids = set()
        self.last_notification_mission_id = None

    def process_line(self, line):
        line = line.strip()

        # --- NEW: SHUDEvent Notification with MissionID (PRIORITY) ---
        # Handles events that contain the real Backend Mission ID
        if "<SHUDEvent_OnNotification>" in line and "MissionId:" in line:
            # Extract Notification ID to prevent duplicates in fallback logic
            notif_id_match = re.search(r'Added notification ".*?" \[(\d+)\]', line)
            if notif_id_match:
                self.processed_notification_ids.add(notif_id_match.group(1))

            # Extract Mission ID
            mid_match = re.search(r'MissionId:\s*\[([a-f0-9\-]+)\]', line)
            if mid_match:
                mission_id = mid_match.group(1)
                
                # Extract Notification Text
                text_match = re.search(r'Added notification "(.*?)"', line)
                if text_match:
                    notification_text = text_match.group(1)
                    
                    # 1. Contract Accepted
                    if "Contract Accepted" in notification_text:
                        title_match = re.search(r'Contract Accepted:\s*(.+?)(?::|\"|\[)', notification_text)
                        title = title_match.group(1).strip() if title_match else "Unknown Contract"
                        
                        if mission_id not in data_store["missions"]:
                            data_store["missions"][mission_id] = {
                                "id": mission_id,
                                "title": title,
                                "items": {},
                                "started": time.strftime("%H:%M:%S"),
                                "source": "LOG (Native)",
                                "status": "ACTIVE"
                            }
                            print(f"✅ LOG (Native): Missão Aceita - {title} (ID: {mission_id})")
                            data_store["mission_status"] = "ACTIVE"
                            
                    # 2. New Objective / Objective Complete
                    elif "New Objective" in notification_text or "Objective Complete" in notification_text:
                        # Ensure mission exists (if we missed the accepted log)
                        if mission_id not in data_store["missions"]:
                             data_store["missions"][mission_id] = {
                                "id": mission_id,
                                "title": "Unknown Mission (Native)",
                                "items": {},
                                "started": time.strftime("%H:%M:%S"),
                                "source": "LOG (Native)",
                                "status": "ACTIVE"
                            }
                        
                        # Parse Objective
                        # 1. Try Standard SCU Regex
                        # Modified to support "Transport X SCU of Y to Z" (which might not have x/y format)
                        obj_match = re.search(
                            r"(Deliver|Pickup|Dropoff|Transport|Collect|Entregue|Coletar|Pegar)\s+(\d+)(?:[/\s]+(\d+))?\s+SCU\s+(?:of|de)?\s*([A-Za-z0-9\s\(\)\-\.]+?)\s+(?:to|at|for|towards|para|em|de)\s+([A-Za-z0-9\s\(\)\-\.]+?)(?::|\"|\[)", 
                            notification_text, re.IGNORECASE
                        )
                        
                        if obj_match:
                            action = obj_match.group(1).upper()
                            
                            # Handle current/total logic
                            val1 = int(obj_match.group(2))
                            val2 = obj_match.group(3)
                            
                            if val2:
                                current = val1
                                total = int(val2)
                            else:
                                # If only one number, assume it's the total to move
                                current = 0 
                                total = val1

                            material = obj_match.group(4).strip().upper()
                            location = clean_location_name(obj_match.group(5))
                            
                            is_pickup = action in ['COLLECT', 'PICKUP', 'RETRIEVE', 'COLETAR', 'PEGAR']
                            type_str = "PICKUP" if is_pickup else "DELIVERY"
                            
                            item_key = f"{material}_{location}_{type_str}"
                            
                            # Check for MANUAL_ADD duplicates and remove them
                            keys_to_remove = []
                            for k, v in data_store["missions"][mission_id]["items"].items():
                                if v.get("action") == "MANUAL_ADD" and v.get("mat") == material and v.get("dest") == location:
                                    keys_to_remove.append(k)
                            
                            for k in keys_to_remove:
                                del data_store["missions"][mission_id]["items"][k]
                                print(f"♻️ LOG Replaced Manual Item: {material} -> {location}")

                            # Check explicit completion event
                            is_complete_event = "Objective Complete" in notification_text
                            
                            # Logic: If it is "Objective Complete", FORCE status=COMPLETED
                            # Logic: If current >= total, also status=COMPLETED
                            status_val = "COMPLETED" if (is_complete_event or (current >= total and total > 0)) else "PENDING"
                            
                            # Update or Create item
                            # NOTE: We overwrite any existing item with this key to ensure status updates!
                            data_store["missions"][mission_id]["items"][item_key] = {
                                "mat": material,
                                "dest": location,
                                "vol": total,
                                "delivered": current,
                                "status": status_val,
                                "type": type_str,
                                "action": action
                            }
                            print(f"📦 LOG (Native): Item {action} {current}/{total} {material} -> {location} [{status_val}]")
                        else:
                            # 2. Try Generic/Non-SCU Regex (e.g. Luminalia Gifts)
                            # "Deliver Gift for X To Y" or "Collect Gift for X From Y"
                            # No SCU count, usually implies 1 item
                            # Also handles "Transport Medical Supplies to ..." without SCU explicit sometimes?
                            generic_match = re.search(
                                r"(Deliver|Pickup|Collect|Entregue|Coletar)\s+(.+?)\s+(?:to|at|from|para|de)\s+([A-Za-z0-9\s\-\.]+?)(?::|\"|\[)", 
                                notification_text, re.IGNORECASE
                            )
                            
                            if generic_match:
                                action = generic_match.group(1).upper()
                                material = generic_match.group(2).strip()
                                location = clean_location_name(generic_match.group(3))
                                
                                # Default to 1 item
                                current = 0
                                total = 1
                                
                                is_pickup = action in ['COLLECT', 'PICKUP', 'COLETAR']
                                type_str = "PICKUP" if is_pickup else "DELIVERY"
                                
                                item_key = f"{material}_{location}_{type_str}"
                                
                                # Check for MANUAL_ADD duplicates and remove them
                                keys_to_remove = []
                                for k, v in data_store["missions"][mission_id]["items"].items():
                                    if v.get("action") == "MANUAL_ADD" and v.get("mat") == material and v.get("dest") == location:
                                        keys_to_remove.append(k)
                                
                                for k in keys_to_remove:
                                    del data_store["missions"][mission_id]["items"][k]
                                    print(f"♻️ LOG Replaced Manual Item: {material} -> {location}")
                                
                                data_store["missions"][mission_id]["items"][item_key] = {
                                    "mat": material,
                                    "dest": location,
                                    "vol": total,
                                    "delivered": current,
                                    "status": "PENDING",
                                    "type": type_str,
                                    "action": action
                                }
                                print(f"🎁 LOG (Native/Gift): {action} {material} -> {location}")
                            else:
                                print(f"⚠️ LOG (Native): Unparsed Objective: {notification_text}")

            # --- DEBUG: MISSING INFO FROM NOTIFICATIONS ---
            # Fallback to CLocalMissionPhaseMarker if notifications fail to provide details
            # Log Example: Creating objective marker: ... contract [HaulCargo_AToB_NonMetal_Silicon_Stanton1_SmallGrade1]
            if "<CLocalMissionPhaseMarker::CreateMarker>" in line and "contract [" in line:
                mission_id_match = re.search(r"missionId \[([a-f0-9\-]+)\]", line)
                contract_match = re.search(r"contract \[([a-zA-Z0-9_]+)\]", line)
                
                if mission_id_match and contract_match:
                    mission_id = mission_id_match.group(1)
                    contract_str = contract_match.group(1)
                    
                    # Parse contract string for details (HaulCargo_AToB_NonMetal_Silicon_Stanton1_SmallGrade1)
                    # Format seems to be: HaulCargo_AToB_Category_Material_Location_Grade
                    parts = contract_str.split('_')
                    if len(parts) >= 5:
                        material = parts[4] # Silicon
                        # location_hint = parts[5] # Stanton1 (Generic)
                        
                        if mission_id not in data_store["missions"]:
                             data_store["missions"][mission_id] = {
                                "id": mission_id,
                                "title": f"Contract: {material} Haul",
                                "items": {},
                                "started": time.strftime("%H:%M:%S"),
                                "source": "LOG (Marker)",
                                "status": "ACTIVE"
                            }
                        
                        # Add placeholder item if empty
                        if not data_store["missions"][mission_id]["items"]:
                            item_key = f"{material}_Unknown_DELIVERY"
                            data_store["missions"][mission_id]["items"][item_key] = {
                                "mat": material,
                                "dest": "See Objective",
                                "vol": 0, # Unknown quantity from this log
                                "delivered": 0,
                                "status": "PENDING",
                                "type": "DELIVERY",
                                "action": "HAUL"
                            }
                            print(f"📍 LOG (Marker): Found Mission Info via Marker: {material}")

            # --- INVENTORY / ELEVATOR ACTIVITY (Debug/Status) ---
            if "Inventory Result Item Count" in line:
                count_match = re.search(r"Item Count:\[(\d+)\]", line)
                if count_match:
                    count = count_match.group(1)
                    print(f"🏗️ LOG (Native): Elevador de Carga detectou {count} itens no grid.")


        # --- NOTIFICATION BASED PARSING (UI Logs - Fallback) ---
        # Handle "Contract Accepted" and "New Objective" from UI notifications (when backend MissionId is missing)
        # Format: <UpdateNotificationItem> Notification "Text..." [ID], Action: ...
        if "<UpdateNotificationItem>" in line and "Notification" in line:
            # Extract Notification ID to avoid duplicates (StartFade, Remove, etc.)
            notif_id_match = re.search(r'Notification ".*?" \[(\d+)\]', line)
            if notif_id_match:
                notif_id = notif_id_match.group(1)
                if notif_id in self.processed_notification_ids:
                    return # Already processed this notification event
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
                        "id": m_id,
                        "title": title,
                        "items": {},
                        "started": time.strftime("%H:%M:%S"),
                        "source": "LOG (UI)",
                        "status": "ACTIVE"
                    }
                    print(f"✅ LOG (UI): Missão Aceita - {title} (ID: {m_id})")
                    data_store["mission_status"] = "ACTIVE"
            
            # B. New Objective (Notification)
            elif "New Objective" in line or "Objective Complete" in line:
                # Regex for cargo details (English/Portuguese)
                obj_match = re.search(
                    r"(Deliver|Pickup|Dropoff|Transport|Collect|Entregue|Coletar|Pegar)\s+(\d+)[/\s]+(\d+)\s+SCU\s+(?:of|de)?\s*([A-Za-z0-9\s\(\)\-\.]+?)\s+(?:to|at|for|towards|para|em|de)\s+([A-Za-z0-9\s\(\)\-\.]+?)(?::|\"|\[)", 
                    line, re.IGNORECASE
                )
                
                if obj_match:
                    # Use the last accepted mission ID, or create a catch-all if none exists
                    m_id = self.last_notification_mission_id
                    if not m_id:
                        m_id = "ui_unknown_mission"
                        self.last_notification_mission_id = m_id
                        
                    if m_id not in data_store["missions"]:
                         data_store["missions"][m_id] = {
                            "id": m_id,
                            "title": "Unknown Mission (UI)",
                            "items": {},
                            "started": time.strftime("%H:%M:%S"),
                            "source": "LOG (UI)",
                            "status": "ACTIVE"
                        }

                    action = obj_match.group(1).upper()
                    current = int(obj_match.group(2))
                    total = int(obj_match.group(3))
                    material = obj_match.group(4).strip().upper()
                    location = clean_location_name(obj_match.group(5))
                    
                    is_pickup = action in ['COLLECT', 'PICKUP', 'RETRIEVE', 'COLETAR', 'PEGAR']
                    type_str = "PICKUP" if is_pickup else "DELIVERY"
                    
                    item_key = f"{material}_{location}_{type_str}"
                    
                    # Check for MANUAL_ADD duplicates and remove them
                    keys_to_remove = []
                    if m_id in data_store["missions"]:
                        for k, v in data_store["missions"][m_id]["items"].items():
                            if v.get("action") == "MANUAL_ADD" and v.get("mat") == material and v.get("dest") == location:
                                keys_to_remove.append(k)
                        
                        for k in keys_to_remove:
                            del data_store["missions"][m_id]["items"][k]
                            print(f"♻️ LOG Replaced Manual Item: {material} -> {location}")
                    
                    is_complete_event = "Objective Complete" in line
                    
                    # Logic: If it is "Objective Complete", FORCE status=COMPLETED
                    status_val = "COMPLETED" if (is_complete_event or (current >= total and total > 0)) else "PENDING"

                    data_store["missions"][m_id]["items"][item_key] = {
                        "mat": material,
                        "dest": location,
                        "vol": total,
                        "delivered": current,
                        "status": status_val,
                        "type": type_str,
                        "action": action
                    }
                    print(f"📦 LOG (UI): Item {action} {current}/{total} {material} -> {location} [{status_val}]")
                    save_state()

        # 1. IDENTITY DETECTION
        chat_match = re.search(r"joined channel '(.+?) : (.+?)'", line)
        if chat_match:
            ship = chat_match.group(1).strip().upper()
            player = chat_match.group(2).strip()
            if data_store["ship_name"] != ship or data_store["player_name"] != player:
                data_store["ship_name"] = ship
                data_store["player_name"] = player
                print(f"✓ Identity: {player} on {ship}")

        # 1A. LOCATION DETECTION (Inventory Request)
        # <RequestLocationInventory> Player[...] requested inventory for Location[Stanton1_DistributionCentre_SakuraSun_Magnolia]
        if "<RequestLocationInventory>" in line and "Location[" in line:
            loc_match = re.search(r"Location\[(.*?)\]", line)
            if loc_match:
                raw_loc = loc_match.group(1)
                clean_loc = clean_location_name(raw_loc)
                if data_store["current_location"] != clean_loc:
                    data_store["current_location"] = clean_loc
                    print(f"📍 Location Update (Inventory): {clean_loc}")
        
        # 1B. FALLBACK: Ship detection
        if data_store["ship_name"] == "Waiting for Ship...":
            ship_fallback = re.search(r"(ARGO_RAFT|CONSTELLATION|CATERPILLAR|C2_HERCULES|FREELANCER|HULL_[A-E]|DRAKE_CORSAIR)_\d+", line, re.IGNORECASE)
            if ship_fallback:
                ship_model = ship_fallback.group(1).replace('_', ' ').upper()
                data_store["ship_name"] = ship_model
                print(f"✓ Ship detected: {ship_model}")

        # 3. MISSION START (Contract Accepted)
        # <SHUDEvent_OnNotification> Added notification "Contract Accepted: Title..." ... MissionId: [ID]
        if "Contract Accepted" in line and "MissionId" in line:
            id_match = re.search(r"MissionId:\s*\[([a-f0-9\-]+)\]", line)
            title_match = re.search(r"Contract Accepted:\s*(.+?)(?::|\"|\[)", line)
            
            if id_match:
                m_id = id_match.group(1)
                title = title_match.group(1).strip() if title_match else "Unknown Contract"
                
                if m_id not in data_store["missions"]:
                    data_store["missions"][m_id] = {
                        "id": m_id,
                        "title": title,
                        "items": {},
                        "started": time.strftime("%H:%M:%S"),
                        "source": "LOG (Native)",
                        "status": "ACTIVE"
                    }
                    print(f"✅ LOG: Missão Aceita - {title} (ID: {m_id})")
                    data_store["mission_status"] = "ACTIVE"
                    save_state()

        # 4. MISSION OBJECTIVE (Cargo Details)
        # "New Objective: Deliver 0/9 SCU of Silicon to HDPC-Farnesway: " ... MissionId: [ID]
        if ("New Objective:" in line or "Objective Complete:" in line) and "MissionId" in line:
            id_match = re.search(r"MissionId:\s*\[([a-f0-9\-]+)\]", line)
            
            # Regex for cargo details (English/Portuguese)
            # Added '<' to terminator list to handle timestamped logs like "...Workcenter <2025..."
            obj_match = re.search(
                r"(Deliver|Pickup|Dropoff|Transport|Collect|Entregue|Coletar|Pegar)\s+(\d+)[/\s]+(\d+)\s+SCU\s+(?:of|de)?\s*([A-Za-z0-9\s\(\)\-\.]+?)\s+(?:to|at|for|towards|para|em|de)\s+([A-Za-z0-9\s\(\)\-\.]+?)(?::|\"|\[|<)", 
                line, re.IGNORECASE
            )
            
            if id_match and obj_match:
                m_id = id_match.group(1)
                action = obj_match.group(1).upper()
                current = int(obj_match.group(2))
                total = int(obj_match.group(3))
                material = obj_match.group(4).strip().upper()
                location = clean_location_name(obj_match.group(5))
                
                is_pickup = action in ['COLLECT', 'PICKUP', 'RETRIEVE', 'COLETAR', 'PEGAR']
                type_str = "PICKUP" if is_pickup else "DELIVERY"

                # Ensure mission exists (handle out-of-order logs)
                if m_id not in data_store["missions"]:
                     data_store["missions"][m_id] = {
                        "id": m_id,
                        "title": "Unknown Mission",
                        "items": {},
                        "started": time.strftime("%H:%M:%S"),
                        "source": "LOG (Native)",
                        "status": "ACTIVE"
                    }
                
                # Unique key for this item step
                item_key = f"{material}_{location}_{type_str}"
                
                # Check for MANUAL_ADD duplicates and remove them
                keys_to_remove = []
                if m_id in data_store["missions"]:
                    for k, v in data_store["missions"][m_id]["items"].items():
                        if v.get("action") == "MANUAL_ADD" and v.get("mat") == material and v.get("dest") == location:
                            keys_to_remove.append(k)
                    
                    for k in keys_to_remove:
                        del data_store["missions"][m_id]["items"][k]
                        print(f"♻️ LOG Replaced Manual Item: {material} -> {location}")

                # Check explicit completion event
                is_complete_event = "Objective Complete" in line
                
                # Logic: If it is "Objective Complete", FORCE status=COMPLETED
                status_val = "COMPLETED" if (is_complete_event or (current >= total and total > 0)) else "PENDING"

                data_store["missions"][m_id]["items"][item_key] = {
                    "mat": material,
                    "dest": location,
                    "vol": total,
                    "delivered": current,
                    "status": status_val,
                    "type": type_str,
                    "action": action
                }
                print(f"📦 LOG: Item {action} {current}/{total} {material} -> {location}")
                save_state()

        # 5. MISSION END (Abandon/Success/Fail)
        # <EndMission> Ending mission for player. MissionId[...] CompletionType[Abandon] Reason[...]
        # Also handle "MissionEnded" push message
        if ("<EndMission>" in line and "MissionId" in line) or ("<MissionEnded>" in line and "mission_id" in line):
            
            # Pattern A: <EndMission>
            id_match_a = re.search(r"MissionId\[([a-f0-9\-]+)\]", line)
            type_match_a = re.search(r"CompletionType\[(.+?)\]", line)
            
            # Pattern B: <MissionEnded> push message
            id_match_b = re.search(r"mission_id ([a-f0-9\-]+)", line)
            state_match_b = re.search(r"mission_state MISSION_STATE_([A-Z]+)", line)
            
            m_id = None
            comp_type = "UNKNOWN"

            if id_match_a:
                m_id = id_match_a.group(1)
                comp_type = type_match_a.group(1).upper() if type_match_a else "UNKNOWN"
            elif id_match_b:
                m_id = id_match_b.group(1)
                raw_state = state_match_b.group(1) if state_match_b else "UNKNOWN"
                if raw_state == "COMPLETED": comp_type = "SUCCESS"
                elif raw_state == "ABANDONED": comp_type = "ABANDON"
                elif raw_state == "FAILED": comp_type = "FAIL"
                else: comp_type = raw_state
                
            if m_id and m_id in data_store["missions"]:
                # Normalizar SUCCESS/COMPLETE
                if comp_type in ["COMPLETE", "COMPLETED"]:
                    comp_type = "SUCCESS"

                print(f"🏁 LOG: Missão Finalizada - {comp_type} (ID: {m_id})")
                
                if comp_type == "SUCCESS":
                        # Archive to history
                        mission_data = data_store["missions"][m_id]
                        data_store["finished_missions"].insert(0, {
                            "id": m_id,
                            "title": mission_data.get("title", "Unknown Mission"),
                            "items": mission_data.get("items", {}).copy(),
                            "value": 0, # Placeholder, will be updated by "Awarded" log
                            "started": mission_data.get("started", "?"),
                            "time": time.strftime("%H:%M:%S"),
                            "source": "LOG",
                            "status": "COMPLETED"
                        })
                        del data_store["missions"][m_id]
                        save_state()
                        
                elif comp_type in ["ABANDON", "FAIL", "ABANDONED", "FAILED"]:
                    # Just remove active mission
                    del data_store["missions"][m_id]
                    if not data_store["missions"]:
                        data_store["mission_status"] = "CANCELLED"
                    save_state()

        # 6. REWARD DETECTION
        # "Awarded 50250 aUEC: " [21]
        if "Awarded" in line and "aUEC" in line:
            reward_match = re.search(r"Awarded\s+(\d+)\s+aUEC", line)
            if reward_match:
                amount = int(reward_match.group(1))
                # Update the most recent finished mission if it exists
                if data_store["finished_missions"]:
                    # Assume it belongs to the last finished mission
                    data_store["finished_missions"][0]["value"] = amount
                    print(f"💰 LOG: Reward detected: {amount} aUEC (Updated History)")
                    save_state()

        return False

def background_log_reader():
    monitor = HaulingMonitor()
    
    if not os.path.exists(LOG_PATH):
        print(f"⚠ Log file not found: {LOG_PATH}")
        return
    
    print(f"📖 Monitoring: {LOG_PATH}")
    
    with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
        # Ler os últimos 5MB para capturar missões já aceitas
        f.seek(0, 2)
        size = f.tell()
        start_pos = max(0, size - 5 * 1024 * 1024)
        f.seek(start_pos)
        print("✓ Lendo histórico recente do log (recuperando missões ativas)...")
        
        while True:
            line = f.readline()
            if not line:
                # Fim do arquivo alcançado, entrar em modo de espera (live tail)
                time.sleep(0.5)
                continue
            monitor.process_line(line)




@app.route('/manual_add_item', methods=['POST'])
def manual_add_item():
    m_id = request.form.get('mission_id')
    mats = request.form.getlist('material')
    qtys = request.form.getlist('quantity')
    dests = request.form.getlist('destination')
    
    if m_id and m_id in data_store["missions"]:
        # Zip inputs to handle multiple rows
        # We use zip_longest or just zip if we assume UI sends consistent arrays
        # Since these are simple inputs, they should align.
        
        for i in range(len(mats)):
            mat = mats[i]
            qty = qtys[i]
            dest = dests[i]
            
            if mat and qty and dest:
                try:
                    vol = int(qty)
                    mat = mat.upper().strip()
                    dest = clean_location_name(dest)
                    
                    # Create a DELIVERY item
                    item_key = f"{mat}_{dest}_DELIVERY_{int(time.time())}_{i}"
                    
                    data_store["missions"][m_id]["items"][item_key] = {
                        "mat": mat,
                        "dest": dest,
                        "vol": vol,
                        "delivered": 0,
                        "status": "PENDING",
                        "type": "DELIVERY",
                        "action": "MANUAL_ADD"
                    }
                    print(f"✏️ MANUAL ADD: {vol} {mat} -> {dest} (Mission: {m_id})")
                    save_state()
                except ValueError:
                    pass 
            
    return '<meta http-equiv="refresh" content="0;url=/">'

@app.route('/delete_mission/<mission_id>')
def delete_mission(mission_id):
    if mission_id in data_store["missions"]:
        del data_store["missions"][mission_id]
        print(f"🗑️ Manual Delete: Mission {mission_id}")
        save_state()
    return '<meta http-equiv="refresh" content="0;url=/">'

@app.route('/')
def index():
    # AGGREGATION LOGIC
    summary = {}
    
    for m_id, m_data in data_store["missions"].items():
        for item in m_data["items"].values():
            d, m, v, status = item["dest"], item["mat"], item["vol"], item["status"]
            delivered = item.get("delivered", 0)
            i_type = item.get("type", "DELIVERY") # PICKUP or DELIVERY
            
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
            
            # Check individual item completion
            if status != "COMPLETED":
                summary[d][m]["all_items_completed"] = False

            # Sum up volumes based on type
            if i_type == "PICKUP":
                summary[d][m]["pickup_vol"] += v
                summary[d][m]["delivered_pickup"] += delivered
            else:
                summary[d][m]["deliver_vol"] += v
                summary[d][m]["delivered_delivery"] += delivered
            
            # Status check:
            # 1. If explicitly all items are COMPLETED, then COMPLETED.
            # 2. OR if delivery count is satisfied (fallback)
            if summary[d][m]["all_items_completed"]:
                 summary[d][m]["status"] = "COMPLETED"
            elif summary[d][m]["deliver_vol"] > 0 and summary[d][m]["delivered_delivery"] >= summary[d][m]["deliver_vol"]:
                 summary[d][m]["status"] = "COMPLETED"

    mission_icons = {
        "READY": "⚪", "ACTIVE": "🟡", "COMPLETED": "✅", "CANCELLED": "🔴"
    }
    
    mission_icon = mission_icons.get(data_store["mission_status"], "⚪")
    
    duration = datetime.now() - data_store["session_start"]
    hours = int(duration.total_seconds() // 3600)
    minutes = int((duration.total_seconds() % 3600) // 60)
    session_time = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
    
    html = (
        "<!DOCTYPE html><html><head><meta charset='UTF-8'>"
        "<title>SC Hauling Monitor - LOG Mode</title>"
        "<style>"
        "body{background:#0b0e14;color:#a1c4d4;font-family:sans-serif;padding:20px;margin:0;}"
        ".header{border-bottom:2px solid #00f2ff44; padding-bottom:15px; margin-bottom:20px; display:flex; justify-content:space-between; align-items:flex-start;}"
        ".header-left{flex:1;}"
        ".header-right{margin-left:20px;}"
        ".status-row{display:flex; gap:15px; margin-top:10px; flex-wrap:wrap;}"
        ".status-badge{background:#161b22; border:1px solid #30363d; padding:8px 15px; border-radius:5px; font-size:0.9rem;}"
        ".loc-box{color:#00f2ff; font-size:1.3rem; font-weight:bold;}"
        ".mission-status{border-left:3px solid #ffcc00; padding-left:10px;}"
        ".card-loc{background:#161b22; border:1px solid #30363d; padding:15px; border-radius:5px; margin-bottom:15px; border-left: 5px solid #00f2ff;}"
        ".scu-box{padding:3px 10px; border-radius:4px; font-weight:bold; font-family:monospace; font-size:0.9rem; margin-left: 5px;}"
        ".pickup-tag{background:#ff00ff22; color:#ff00ff; border:1px solid #ff00ff44;}"
        ".deliver-tag{background:#00f2ff22; color:#00f2ff; border:1px solid #00f2ff44;}"
        ".COMPLETED{background:#00ff8822; color:#00ff88; border: 1px solid #00ff88; text-decoration: line-through; opacity: 0.6;}"
        ".footer{background:#0d1117; border:1px solid #21262d; padding:15px; margin-top:30px; border-radius:5px; font-family:monospace; font-size:0.8rem;}"
        ".info-grid{display:flex; justify-content:space-between; align-items:center; margin-top:10px; flex-wrap:wrap; gap:10px;}"
        ".history-item{border-bottom:1px solid #21262d; padding:8px 0; display:flex; justify-content:space-between;}"
        ".empty-state{text-align:center; padding:40px; color:#666; font-style:italic;}"
        ".pause-btn{background:#333; color:#fff; border:1px solid #555; padding:8px 15px; cursor:pointer; border-radius:5px; font-weight:bold; font-size:0.9rem;}"
        ".pause-btn.paused{background:#ffcc00; color:#000; border:1px solid #ffcc00; animation: pulse 2s infinite;}"
        "@keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.8; } 100% { opacity: 1; } }"
        "</style></head><body>"
        "<div class='header'>"
        "<div class='header-left'>"
        f"<div class='loc-box'>📍 CURRENT: {data_store['current_location']}</div>"
        "<div class='status-row'>"
        f"<div class='status-badge mission-status'>{mission_icon} MISSION: {data_store['mission_status']}</div>"
        "</div></div>"
        "<div class='header-right'>"
        "<button id='pauseBtn' class='pause-btn' onclick='togglePauseManual()'>⏸ PAUSAR</button>"
        "</div>"
        "</div>"
        "<div class='info-grid'>"
        f"<span>🚀 <b>{data_store['ship_name']}</b> | 👤 <b>{data_store['player_name']}</b></span>"
        f"<span>⏱ {session_time}</span>"
        "</div>"
    )

    if summary:
        html += "<div id='mission-list'>"
        for d, mats in summary.items():
            html += f"<div class='card-loc'><b>📦 DESTINATION: {d}</b>"
            for m, data in mats.items():
                p_vol = data["pickup_vol"]
                d_vol = data["deliver_vol"]
                status = data["status"]
                
                # Build badges
                badges = ""
                
                # Check completion first to apply style
                is_completed = (status == "COMPLETED")
                tag_class_extra = " COMPLETED" if is_completed else ""
                
                if p_vol > 0:
                    prefix = "✅ " if is_completed else "⬇️ "
                    p_current = data["delivered_pickup"]
                    vol_display = f"{p_vol} SCU"
                    if p_current > 0 and p_current < p_vol and not is_completed:
                         vol_display = f"{p_current}/{p_vol} SCU"
                    badges += f"<span class='scu-box pickup-tag{tag_class_extra}'>{prefix}COLETAR: {vol_display}</span>"
                if d_vol > 0:
                    prefix = "✅ " if is_completed else "⬆️ "
                    label = "ENTREGUE" if is_completed else "ENTREGAR"
                    d_current = data["delivered_delivery"]
                    vol_display = f"{d_vol} SCU"
                    if d_current > 0 and d_current < d_vol and not is_completed:
                         vol_display = f"{d_current}/{d_vol} SCU"
                    badges += f"<span class='scu-box deliver-tag{tag_class_extra}'>{prefix}{label}: {vol_display}</span>"
                
                if p_vol == 0 and d_vol == 0:
                    badges += f"<span class='scu-box' style='color:#ffcc00; border:1px solid #ffcc0044;'>⏳ AGUARDANDO CARGA...</span>"

                html += f"<div style='display:flex; justify-content:space-between; align-items:center; margin:8px 0; padding:5px 0; border-bottom:1px solid #21262d33;'>"
                html += f"<span>▪ {m}</span><div style='display:flex; align-items:center; gap:10px;'>{badges}"
                
                # Render buttons for each linked mission
                if "mission_ids" in data:
                    for mid in data["mission_ids"]:
                         html += f"<button onclick='toggleEdit(\"{mid}\")' style='background:none; border:1px solid #444; color:#888; cursor:pointer; padding:2px 6px; border-radius:3px; font-size:0.8rem;' title='Adicionar itens'>➕</button>"
                         html += f" <a href='/delete_mission/{mid}' onclick=\"return confirm('Excluir missão?')\" style='text-decoration:none; border:1px solid #663333; color:#cc5555; padding:2px 6px; border-radius:3px; font-size:0.8rem; margin-left:5px;' title='Excluir Missão'>🗑️</a>"
                
                html += "</div></div>"
                
                # Hidden Edit Form for this mission
                if "mission_ids" in data:
                    for mid in data["mission_ids"]:
                        form_id = f"form_edit_{mid}"
                        container_id = f"container_edit_{mid}"
                        html += f"""
                        <div id="edit_{mid}" style="display:none; background:#111; padding:10px; margin-bottom:10px; border-radius:5px; border-left:3px solid #ffcc00;">
                            <form id="{form_id}" action="/manual_add_item" method="post">
                                <input type="hidden" name="mission_id" value="{mid}">
                                <div style="font-size:0.8rem; color:#aaa; margin-bottom:5px;">Adicionar itens extras a: {m}</div>
                                <div id="{container_id}">
                                    <div style="display:flex; gap:5px; margin-bottom:5px;">
                                        <input type="text" name="material" placeholder="Material" style="width:100px; background:#222; border:1px solid #444; color:#fff; padding:3px; border-radius:3px;" required>
                                        <input type="number" name="quantity" placeholder="SCU" style="width:50px; background:#222; border:1px solid #444; color:#fff; padding:3px; border-radius:3px;" required>
                                        <input type="text" name="destination" placeholder="Destino" style="width:100px; background:#222; border:1px solid #444; color:#fff; padding:3px; border-radius:3px;" required>
                                    </div>
                                </div>
                                <div style="margin-top:5px; display:flex; gap:10px;">
                                    <button type="button" onclick="addRow('{container_id}')" style="background:#333; color:#ccc; border:none; padding:3px 8px; cursor:pointer; font-size:0.8rem;">+ Linha</button>
                                    <button type="submit" style="background:#00f2ff; color:#000; border:none; padding:3px 10px; font-weight:bold; cursor:pointer; font-size:0.8rem;">SALVAR</button>
                                </div>
                            </form>
                        </div>
                        """
            html += "</div>"
        html += "</div>"
    else:
        html += "<div id='mission-list'></div>"
            
    # Also show active missions that have no items yet (just accepted)
    # We filter out missions that are already in 'summary' (which means they have items)
    # Missions without items are not in summary because summary is built from items.
    
    missions_with_items = set()
    for m_data in data_store["missions"].values():
        if m_data["items"]:
            missions_with_items.add(m_data["id"])

    # Also show active missions that have no items yet OR explicitly requested missions for editing
    # We want to keep the "Add Item" form available even if the mission already has items,
    # IF it's in a special "Manual Edit Mode" or simply always show it for active missions?
    
    # --- 1. NEW MISSIONS (Waiting for Cargo) ---
    # Only show the full manual add form for missions that have NO items.
    missions_needing_input = [m for m_id, m in data_store["missions"].items() if not m["items"]]
    
    html += "<div id='new-missions-list'>"
    if missions_needing_input:
        html += "<div class='card-loc' style='border-left: 5px solid #ffcc00; margin-top: 20px;'>"
        html += "<b>📝 NOVOS CONTRATOS (Aguardando Carga)</b><br><small style='color:#666'>Adicione os itens manualmente abaixo.</small>"
        
        for m in missions_needing_input:
            html += f"<div style='margin:15px 0; padding:10px; background:#1a1a0a; border:1px solid #333; border-radius:5px;'>"
            html += f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;'>"
            html += f"<div style='font-weight:bold; color:#ffcc00;'>📜 {m['title']}</div>"
            html += f"<a href='/delete_mission/{m['id']}' onclick=\"return confirm('Tem certeza que deseja excluir esta missão?')\" style='color:#ff5555; text-decoration:none; font-size:0.8rem; border:1px solid #ff5555; padding:2px 5px; border-radius:3px;'>🗑️ Excluir</a>"
            html += f"</div>"
            
            # Form with ID for JS targeting
            form_id = f"form_{m['id']}"
            container_id = f"container_{m['id']}"
            
            html += f"""
            <form id="{form_id}" action="/manual_add_item" method="post">
                <input type="hidden" name="mission_id" value="{m['id']}">
                <div id="{container_id}">
                    <div style="display:flex; gap:5px; margin-bottom:5px;">
                        <input type="text" name="material" placeholder="Material (ex: Gold)" style="width:120px; background:#222; border:1px solid #444; color:#fff; padding:5px; border-radius:3px;" required>
                        <input type="number" name="quantity" placeholder="SCU" style="width:60px; background:#222; border:1px solid #444; color:#fff; padding:5px; border-radius:3px;" required>
                        <input type="text" name="destination" placeholder="Destino" style="width:120px; background:#222; border:1px solid #444; color:#fff; padding:5px; border-radius:3px;" required>
                    </div>
                </div>
                
                <div style="margin-top:10px; display:flex; gap:10px;">
                    <button type="button" onclick="addRow('{container_id}')" style="background:#333; color:#fff; border:1px solid #555; padding:5px 10px; cursor:pointer; border-radius:3px;">+ Adicionar Linha</button>
                    <button type="submit" style="background:#00f2ff; color:#000; border:none; padding:5px 15px; font-weight:bold; cursor:pointer; border-radius:3px;">💾 SALVAR</button>
                </div>
            </form>
            </div>"""
        html += "</div>"
    html += "</div>"

    # --- 2. ACTIVE MISSIONS (Edit Mode) ---
    # Hidden by default, accessible via Main Cards
    # We will inject a modal or hidden div structure for each active mission so user can add items later.
    
    active_missions_list = [m for m_id, m in data_store["missions"].items()]
    if active_missions_list:
        html += "<script>"
        html += """
        function addRow(containerId) {
            isPaused = true; 
            updatePauseUI();
            const container = document.getElementById(containerId);
            const div = document.createElement('div');
            div.style.cssText = "display:flex; gap:5px; margin-bottom:5px;";
            div.innerHTML = `
                <input type="text" name="material" placeholder="Material" style="width:120px; background:#222; border:1px solid #444; color:#fff; padding:5px; border-radius:3px;" onfocus="setPaused()" required>
                <input type="number" name="quantity" placeholder="SCU" style="width:60px; background:#222; border:1px solid #444; color:#fff; padding:5px; border-radius:3px;" onfocus="setPaused()" required>
                <input type="text" name="destination" placeholder="Destino" style="width:120px; background:#222; border:1px solid #444; color:#fff; padding:5px; border-radius:3px;" onfocus="setPaused()" required>
                <button type="button" onclick="this.parentElement.remove()" style="background:#442222; color:#ff5555; border:none; padding:0 8px; cursor:pointer;">x</button>
            `;
            container.appendChild(div);
        }
        function toggleEdit(id) {
            setPaused();
            const el = document.getElementById('edit_' + id);
            if (el.style.display === 'none') el.style.display = 'block';
            else el.style.display = 'none';
        }
        """
        html += "</script>"

    if not summary and not missions_needing_input:
        html += "<div class='empty-state'>⏳ Sem missões ativas<br><small>Aceite um contrato no jogo para iniciar o rastreamento via LOG</small></div>"

    html += "<div class='footer' id='footer-content'><b>📋 HISTÓRICO DE MISSÕES:</b><hr style='border-color:#21262d; margin:10px 0;'>"
    if data_store["finished_missions"]:
        for f in data_store["finished_missions"][:10]:
            mission_short = f['id'][:8] if len(f['id']) > 8 else f['id']
            title = f.get('title', f"Mission {mission_short}")
            value = f.get('value', 0)
            
            value_str = f"{value:,} aUEC" if value > 0 else "---"
            
            # Summarize items
            items_summary = "Sem Carga"
            if 'items' in f and f['items']:
                total_scu = 0
                mats = set()
                for item in f['items'].values():
                    total_scu += item.get('vol', 0)
                    mats.add(item.get('mat', 'Unknown'))
                
                if total_scu > 0:
                    mat_str = ", ".join(mats)
                    items_summary = f"{total_scu} SCU ({mat_str})"
                else:
                    items_summary = f"Itens: {len(f['items'])}"

            html += (
                f"<div class='history-item' style='flex-direction:column; align-items:flex-start; padding:10px 0;'>"
                f"<div style='display:flex; justify-content:space-between; width:100%; margin-bottom:4px;'>"
                f"  <span style='font-weight:bold; color:#e6edf3; font-size:0.95rem;'>{title}</span>"
                f"  <span style='color:#00ff88; font-family:monospace;'>{value_str}</span>"
                f"</div>"
                f"<div style='display:flex; justify-content:space-between; width:100%; font-size:0.85rem; color:#8b949e;'>"
                f"  <span>📦 {items_summary}</span>"
                f"  <span>🕒 {f['time']}</span>"
                f"</div>"
                f"</div>"
            )
    else:
        html += "<div style='color:#666; font-style:italic; padding:10px 0;'>Nenhuma missão completada nesta sessão</div>"
    
    html += "</div>"
    
    html += """
    <script>
    var isPaused = false;
    var manualPause = false;

    function updatePauseUI() {
        const btn = document.getElementById('pauseBtn');
        if (!btn) return;
        if (isPaused || manualPause) {
            btn.classList.add('paused');
            btn.textContent = '▶ RETOMAR';
        } else {
            btn.classList.remove('paused');
            btn.textContent = '⏸ PAUSAR';
        }
    }

    function togglePauseManual() {
        manualPause = !manualPause;
        
        // If we are resuming (manualPause became false), we should also clear the auto-pause
        // assuming the user wants to see updates again.
        if (!manualPause) {
            isPaused = false;
        }
        
        updatePauseUI();
    }
    
    function setPaused() {
        // If manually paused, do nothing (keep it paused)
        if (manualPause) return;
        
        isPaused = true;
        updatePauseUI();
    }

    async function updateContent() {
        if (isPaused || manualPause) {
            return;
        }

        var active = document.activeElement;
        if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA')) {
            // Only set paused if we are NOT interacting with the pause button (which is handled separately)
            // But activeElement is the focused element.
            setPaused();
            return;
        }
        
        try {
            const response = await fetch(window.location.href);
            const text = await response.text();
            
            // Double check pause after fetch
             if (isPaused || manualPause) {
                return;
            }
            
            const parser = new DOMParser();
            const doc = parser.parseFromString(text, 'text/html');
            
            // Selective Update - NO BODY REPLACEMENT
            const headerLeft = document.querySelector('.header-left');
            if (headerLeft && doc.querySelector('.header-left')) {
                headerLeft.innerHTML = doc.querySelector('.header-left').innerHTML;
            }
            
            const infoGrid = document.querySelector('.info-grid');
            if (infoGrid && doc.querySelector('.info-grid')) {
                infoGrid.innerHTML = doc.querySelector('.info-grid').innerHTML;
            }
            
            const missionList = document.getElementById('mission-list');
            if (missionList && doc.getElementById('mission-list')) {
                missionList.innerHTML = doc.getElementById('mission-list').innerHTML;
            }
            
            const newMissionsList = document.getElementById('new-missions-list');
            if (newMissionsList && doc.getElementById('new-missions-list')) {
                newMissionsList.innerHTML = doc.getElementById('new-missions-list').innerHTML;
            }
            
            const footerContent = document.getElementById('footer-content');
            if (footerContent && doc.getElementById('footer-content')) {
                footerContent.innerHTML = doc.getElementById('footer-content').innerHTML;
            }

        } catch (e) {
            console.error("Update failed", e);
        }
    }
    
    document.addEventListener('focus', function(e) {
        if(e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'BUTTON')) {
            // Ignore the pause button itself to prevent infinite loop of pausing when trying to unpause
            if (e.target.id === 'pauseBtn') return;
            setPaused();
        }
    }, true);
    
    setInterval(updateContent, 2000);
    </script>
    </div></body></html>"""
    return render_template_string(html)

if __name__ == '__main__':
    # Load saved config (if any) so calibration persists
    load_saved_config()
    
    # Load persisted state (history, active missions)
    load_state()
    
    print("=" * 60)
    print("🚀 STAR CITIZEN HAULING MONITOR - HYBRID MODE")
    print("=" * 60)
    print(f"📊 Dashboard: http://localhost:5000")
    print(f"⏰ Session started: {data_store['session_start'].strftime('%H:%M:%S')}")
    print(f"📖 Log monitoring: ENABLED")
    

    
    print("=" * 60)
    
    threading.Thread(target=background_log_reader, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=False)