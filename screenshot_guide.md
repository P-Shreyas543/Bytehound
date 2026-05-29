# Screenshot Capture Checklist Guide

To compile the user manual document (`Documentation/Bytehound_User_Manual.docx`) with real application images, please capture screenshots matching the instructions below. 

Save all image files in the directory:
📂 **`app/resources/images/`** (Format: **PNG**)

---

### Screenshot Checklist

| Filename | Crop / Scope | Window / Panel State to Capture | Key Visual Indicators to Highlight |
| :--- | :--- | :--- | :--- |
| **`connection_dialog.png`** | Crop to Dialog | Click **Connect** in the toolbar to open the **Serial Connection Settings** dialog. | COM port dropdown list, Baud Rate selection, Data/Stop/Parity dropdowns, and "Auto-reconnect on disconnect" checkbox. |
| **`connection_status.png`** | Dialog / Focus Crop | The toolbar **Disconnect** button and the bottom-left **Status LED**. | The circular status LED turns **green** (`⬤`), and the toolbar button changes to **Disconnect** with a **pink** (`#DB2777`) background. |
| **`auto_fetch_dialog.png`** | Crop to Dialog | Click **Start Auto-Fetch** (or press `F10`) to open the Polling Configuration dialog. | Target checklist, "Pipeline poll requests" checkbox, "Max in-flight" count, and "TX gap (ms)" input field. |
| **`collision_warning.png`** | Crop to Dialog | With a device actively streaming unsolicited data (no polling active), click **Start Auto-Fetch**. | The **Potential Collision Warning** dialog box with its warning icon, collision warning message, and Yes/No buttons. |
| **`main_window_overview.png`** | Full Window | Loaded configuration receiving live telemetry data in the center Data Table. | The layout showing the main central table, docked panels, active connection, and the main toolbar at the top. |
| **`live_plot_panel.png`** | Crop to Panel | The **Live Plot** panel displaying active, wiggling signals. | The subplot grid (e.g. 2×1 or 2×2 stacked plots) with time-based X-axis and visible Y-scale dropdown controls. |
| **`plot_trigger_dialog.png`** | Crop to Dialog | Click **Trigger...** on the Live Plot toolbar to open the **Plot Trigger Configuration** dialog. | The threshold settings form: Parameter selection dropdown, Operator select (>, <), Threshold Value field, and action checkboxes. |
| **`bitfields_enums_panels.png`** | Crop to Panels | The **Bitfields** and **Enums** translation panels. | Active decoded bit flags (ON/OFF) and state enums mapped to their string labels (e.g., `0 = OFF`, `1 = RUN`). |
| **`console_activity_log.png`** | Crop to Panels | The **Raw Console** and **Activity Log** dock panels. | Raw hex lines with `RX` / `TX` direction markers and timestamped event strings. |
| **`status_bar_counters.png`** | Crop to Status Bar | Bottom status bar counters and the Warning Badge. | The aligned status label counters (Frames, Errors, Timeouts, RX, TX, Latency) and the yellow **⚠️ Queue Saturated** badge if visible. |
| **`config_info_dialog.png`** | Crop to Dialog | Go to **View → Config Info...** to open the details dialog. | The dialog showing active config stats, the **Frame Format Diagram** (color-coded byte layout grid) on the **RX Frames** or **TX Commands** tabs. |
| **`tx_commands_panel.png`** | Crop to Panel | The **TX Commands** dock panel. | The command selector dropdown, numeric input fields for command parameters, the packet preview hex row, and the **Build** and **Send** buttons. |
| **`parameter_editor_panel.png`** | Crop to Panel | The **Parameter Editor** dock panel. | Writable config signals displaying their live value, write input field, unit labels, and inline **Write** buttons. |
| **`logging_dialog.png`** | Crop to Dialog | Click **Device → Start Logging** (or `Ctrl+L`) to open the logging configuration dialog. | The file save picker path, and the logging mode options: **Raw only**, **Decoded only**, and **Raw + Decoded** checkboxes. |
| **`analysis_suite.png`** | Full Window | Open the **Analysis Suite** window under **Tools → Analysis Suite**. | Loaded historical `_decoded.xlsx` runs, aligned time plots, active cursor lines, and the bottom Cursors/Statistics panels. |
| **`schema_mapper.png`** | Crop to Dialog | In the Analysis Suite, go to **Tools → Import Schema Mapper...**. | The schema layout inputs: Sheet Names list, Time Columns list, and Time Scale mapping multipliers list. |
| **`xy_plotter.png`** | Crop to Dialog | In the Analysis Suite, go to **Scatter** in the menu bar. | The X-Y Plotter dialog containing the scatter plot comparing two parameters, best-fit linear regression line, and R-squared readout. |

---

### Step-by-Step Compilation Verification

1. Capture each screenshot according to the guidelines above.
2. Crop the screenshots cleanly to remove window borders or unrelated parts where specified.
3. Save each screenshot with the exact filename (case-sensitive) under `app/resources/images/`.
4. Run the DOCX manual compiler command to build the Word manual without any missing image warnings:
   ```powershell
   .venv\Scripts\python.exe generate_docx.py
   ```
5. Open the compiled document `Documentation/Bytehound_User_Manual.docx` in Word, select all text (`Ctrl+A`), and press `F9` to refresh the dynamic Table of Contents.
