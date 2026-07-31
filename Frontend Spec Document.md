# Bytehound Frontend Specification Document

## 1. Visual Design & Interface Styling

Bytehound features a modern, clean, and dark/light mode responsive desktop interface built using the **PySide6 (Qt)** framework. The stylesheet and interface styling rules are managed dynamically at runtime using `pyqt-darktheme` combined with targeted QSS (Qt Style Sheets) overrides.

### 1.1 Palette & Color Palette System
The user interface uses specific hex palettes to convey status and focus.

| UI Element | Dark Mode Value | Light Mode Value | Notes |
|---|---|---|---|
| **Primary Theme** | `qdarktheme` default dark | `qdarktheme` default light | Set with rounded corners |
| **Menu Item Hover** | `#2563EB` (Tailwind Blue-600) | `#2563EB` (Tailwind Blue-600) | Applied across all dropdown/context menus |
| **Status Badge: OK** | `#10B981` (Emerald-500) | `#10B981` (Emerald-500) | Rounded pill with bold white text |
| **Status Badge: Warning** | `#F59E0B` (Amber-500) | `#F59E0B` (Amber-500) | Rounded pill with bold white text |
| **Status Badge: Error** | `#EF4444` (Rose-500) | `#EF4444` (Rose-500) | Rounded pill with bold white text |
| **Primary Action Pill** | `#388E3C` (Green-700) | `#388E3C` (Green-700) | Bold white text for Connect/Auto-Fetch |
| **Primary Action Hover** | `#4CAF50` (Green-500) | `#4CAF50` (Green-500) | Used for active action buttons |
| **Status Bar LED: Connected** | `#66BB6A` (Material Green) | `#66BB6A` (Material Green) | Small circular indicator |
| **Status Bar LED: Offline** | `#ef5350` (Material Red) | `#ef5350` (Material Red) | Small circular indicator |

### 1.2 Layout Responsiveness & Hierarchy
* **Default Window Size**: 1400 × 820 px.
* **Minimum Supported Dimensions**: 640 × 480 px.
* **Layout Adaptability**: To allow clean side-by-side splitting (50/50 screen split on a 1080p display), secondary text and labels in the plot panels use elastic policies (`QSizePolicy.Ignored` for sizing hints). This forces labels to clip gracefully rather than locking the column width and breaking the layout.

---

## 2. Core Panels & Dock Widgets

The workspace layout is composed of a central widget surrounded by dockable panels (`QDockWidget`). All panels can be rearranged, stacked, or popped out.

### 2.1 Central Widget: Main Data Table
A `QTableWidget` displaying active telemetry parameters.
* **Columns**: `Frame | Group | Variable | Start B. | Data Type | Raw | Value | Unit | Status | Updated`
* **Plot Checkbox**: The `Variable` column includes checkboxes next to each signal name. Checking a box adds the signal to the Live Plot panel; unchecking it removes it.
* **Status Badges**: The `Status` column uses a custom delegate (`QStyledItemDelegate`) that draws rounded color pills based on the cell text (e.g., green for `ok`, red for `error`, yellow for `warn`).

### 2.2 Connection Dock Panel
* Located in the top-left quadrant by default.
* Includes `QComboBox` dropdown selectors for COM Port and Baud Rate.
* Includes a **Refresh Ports** button to trigger a scan of active interfaces.
* Includes connection state toggles.

### 2.3 Live Plot Panel
A multi-grid plot panel powered by a custom `pyqtgraph.GraphicsLayoutWidget`.

```
+-------------------------------------------------------------+
| Plot Settings: Layout [ 2x1 ]  X-Axis [ Elapsed ] [ Pause ] |
+-------------------------------------------------------------+
| Panel 1: [ Signal A (Red) (x) ] [ Signal B (Blue) (x) ] [+] |
| [ pyqtgraph plot grid ]                                     |
+-------------------------------------------------------------+
| Panel 2: [ Signal C (Green) (x) ]                       [+] |
| [ pyqtgraph plot grid ]                                     |
+-------------------------------------------------------------+
```

* **Grid Configuration**: Supports dynamic layout dimensions (`1×1`, `1×2`, `2×1`, `1×3`, `3×1`, `2×2`, `2×4`, `4×2`). Changing the layout dynamically redistributes active variables across panels.
* **Linked X-Axes**: All active plot subplots link their X-axes (`setXLink`). Panning or zooming one subplot synchronizes all other plots.
* **Variable Chips**: Each subplot has a header row displaying assigned variables as colored button chips. Clicking a chip removes the variable. A `+ Add` button opens a dialog to select from the loaded variables.
* **Viewing Modes**:
  * **Live Mode**: Plots auto-scroll along the X-axis (`0` to `current_t`).
  * **Explore Mode**: Auto-scrolling pauses if the user manually pans or zooms. This allows inspection of past data points while the worker continues writing data to the background buffers.
* **Time Axis Display**:
  * **Elapsed Time**: Renders as fractional seconds since the session started (e.g., `1.5s`, `1.12s`, `2:30`).
  * **System Time**: Renders as system wall-clock timestamps (`HH:MM:SS`).

### 2.4 Auxiliary Panels
* **Bitfields Panel**: Displays binary LED state arrays grouped by parent variable. Each bit position contains a text description and changes state dynamically.
* **Enums Panel**: Monitors state variables, mapping active telemetry integers to their label descriptions (e.g., `0` -> `Init`).
* **TX Commands Panel**: Displays configurable dropdown forms for every command found in the loaded configuration. Pressing a button transmits static payloads immediately, while parameterized commands render an inline form with numeric inputs, boolean flag toggles, and live telemetry readbacks (`Current: X`). A frame format byte visualizer renders interactive payload tooltips (highlighting header, frame ID, static payload, field parameters, bit-packed boolean flags, and CRC).
* **Parameter Editor Panel**: Displays a table of writable (`W`/`RW`) signals. 
  * Columns: `Frame ID | Signal | Live Value | Write Input (QLineEdit) | Send (QPushButton)`
  * Inputs display live telemetry readback labels (`Current: X`), support range checking (`min_value`, `max_value`), and format bit-packed boolean flags or scaled numeric types. Pressing Enter inside the write box sends the data.
* **Raw Console Panel**: Prints a continuous log of RX and TX hex frames.
  * Tints lines: Green text for `TX` commands and Amber/White text for incoming `RX` frames.
* **Activity Log Panel**: Logs operational messages and diagnostic warnings.

---

## 3. Top-Level Menus & Actions

The menu bar contains six top-level sections:

```
[ File ]   [ Edit ]   [ View ]   [ Device ]   [ Tools ]   [ Help ]
```

### 3.1 Menu Items & Commands
1. **File Menu**:
   * *Import Config*: Opens a file dialog to load an `.xlsx` workbook or directory of CSV files.
   * *Export Template*: Generates a blank configuration spreadsheet schema.
   * *Exit*: Saves layout states and closes the application.
2. **Edit Menu**:
   * *Copy Value* (`Ctrl+Shift+C`): Copies the currently selected table cell value to the clipboard.
   * *Clear Console / Log*: Wipes the data table, consoles, and live plot history.
3. **View Menu**:
   * *Panels Submenu*: Exposes checkable actions to toggle visibility of each panel.
   * *Theme Submenu*: Sets the color scheme (**Dark**, **Light**, **System**).
   * *Reset Window Layout*: Restores the default layout arrangement.
4. **Device Menu**:
   * *Connect / Disconnect*: Establishes or terminates the connection to the selected serial port.
   * *Start / Stop Auto-Fetch*: Toggles automatic polling requests.
   * *Start / Stop Logging*: Toggles streaming data to the Raw and Decoded log files.
5. **Tools Menu**:
   * *Analysis Suite*: Opens the Analysis Suite window.
6. **Help Menu**:
   * *View Documentation*: Opens the user manual in the default web browser.
   * *Check for Updates*: Queries the remote update server.
   * *About*: Opens the developer credits dialog.

---

## 4. Layout Persistence & Native Integration

### 4.1 Native Windows Title Bar Integration
To maintain a unified visual style, the application applies dark styling to native OS title bars on Windows systems:
* The application imports `dwmapi` via `ctypes`.
* It calls `DwmSetWindowAttribute` with the immersive dark attribute (`DWMWA_USE_IMMERSIVE_DARK_MODE`).
* This themes the application title bar to dark grey when dark mode is enabled, replacing the default Windows white title bar.

### 4.2 State Restoration
Using `QSettings` pointing to `HKCU\Software\Bytehound\Bytehound`, the application saves the workspace state on exit and restores it on startup:
* **Geometry**: Saved using `saveGeometry()` and restored via `restoreGeometry()`.
* **Dock Layout**: Saved using `saveState()` and restored via `restoreState()`.
* **Preferences**: Saves theme preferences, last connected COM port, baud rate, plot configurations, and active signals.

### 4.3 Popped-Out Dock Promotion
When a user detaches a dock widget from the main window, the application intercepts the change (`topLevelChanged` signal):
* It updates the widget flags to `Qt.Window` and adds standard minimize, maximize, and close buttons.
* When the widget is docked back, it restores the default toolbar chrome. This allows users to place the Live Plot or Raw Console on secondary monitors.
