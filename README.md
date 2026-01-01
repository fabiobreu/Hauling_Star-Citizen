# Star Citizen Hauling Monitor

Hauling mission monitoring tool for Star Citizen. This application reads the game log file in real-time (`Game.log`) to track accepted missions, cargo updates, deliveries, and rewards, displaying everything on an interactive Web Dashboard.

*Note: Reading the Log presents significant challenges as it is not a formal API that provides structured information. This can cause failures or missing information regarding cargo delivery, especially if log formats change with game version updates. Additionally, since the universe mapping is extensive and requires refinement, we have focused testing on specific sectors, which may result in missing data for other areas. Expanding this mapping is a key area for future improvement.*

-   <img width="909" height="917" alt="image" src="https://github.com/user-attachments/assets/204040bd-1356-4f28-851c-96a3ec472c49" />

## 🚀 Features

-   **Automatic Tracking**: Detects accepted Hauling missions, cargo pickup, and deliveries directly from the game log.
-   **Web Dashboard**: Modern and responsive visual interface (Dark Mode) to track your missions on a second monitor, tablet, or phone.
-   **Multi-Language**: Full support for Portuguese (PT) and English (EN), configurable via JSON file.
-   **Manual Editing**: Allows manual addition of items if the log fails to capture an event or for older missions.
-   **Mission History**: Saves completed, abandoned, or failed missions, with calculations for total earnings and mission time.
-   **Persistence**: Current state is automatically saved (`hauling_state.json`), allowing you to close and reopen the tool without losing progress.
-   **Identification**: Automatically detects the player name and ship used.

## 🛠️ Installation and Execution

### Prerequisites
-   Python 3.8 or higher installed.
-   Required Python libraries (install via pip):
    ```bash
    pip install flask
    ```

### How to Run
1.  Clone this repository.
2.  Check your log file path in `hauling_config.json` (see Configuration section below).
3.  Run the main script:
    ```bash
    python hauling_web_tst.py
    ```
4.  Open your browser at the indicated address (usually `http://0.0.0.0:5000` or `http://localhost:5000`).

## ⚙️ Configuration (`hauling_config.json`)

The `hauling_config.json` file controls the tool's behavior. The main options are:

*   `"log_path"`: Absolute path to the Star Citizen `Game.log` file.
    *   Example: `"C:/Program Files/Roberts Space Industries/StarCitizen/LIVE/Game.log"`
*   `"language"`: Defines the interface language (`"pt"` for Portuguese, `"en"` for English).
*   `"web_port"`: Port for the web server (default: `5000`).
*   `"refresh_interval_ms"`: Page refresh interval in milliseconds (default: `2000`).

## 🌍 Translation and Internationalization

The translation system is based on JSON files. To change the language or add a new one:

1.  Edit the `"language"` parameter in `hauling_config.json`.
2.  Ensure a corresponding `hauling_lang_{LANGUAGE}.json` file exists (e.g., `hauling_lang_en.json`).
3.  **To contribute a new language**:
    *   Copy the `hauling_lang_en.json` file.
    *   Rename it to `hauling_lang_fr.json` (e.g., for French).
    *   Translate the key values (do not change the keys!).
    *   Submit a Pull Request!

## 🤝 How to Contribute

Contributions are welcome! If you want to improve the code, add features, or fix bugs:

1.  **Fork** the project.
2.  Create a **Branch** for your feature (`git checkout -b feature/new-feature`).
3.  **Commit** your changes (`git commit -m 'Add new feature'`).
4.  **Push** to the Branch (`git push origin feature/new-feature`).
5.  Open a **Pull Request**.

### Areas for Improvement
*   Refinement of Regex patterns to capture more mission log variations.
*   UI/UX improvements for the Dashboard.
*   Support for more mission types (beyond Hauling).

## 📂 File Structure

*   `hauling_web_tst.py`: Main application code (Flask Server + Log Parser).
*   `hauling_config.json`: Configuration file.
*   `hauling_lang_pt.json`: PT-BR translation file.
*   `hauling_lang_en.json`: EN translation file.
*   `hauling_state.json`: Automatically generated file to save progress (should not be committed).

---
Developed by the community for the community. Fly safe! o7
