# Bytehound Security and Access Document

## 1. Security Posture Overview

Bytehound is a local desktop serial monitor and telemetry decoder. It runs completely offline and operates strictly on the host PC. 

### Core Design Security Assumptions
* **Local Operation**: There are no cloud-based account databases, SaaS synchronization features, telemetry collection platforms, or external network integrations. Data never leaves the host computer unless explicitly exported by the user.
* **No Authentication Required**: Because the application runs in the user's local operating system session, it relies on the host OS credentials for access control.
* **Hardware-Bound Communication**: Data transmission is limited to local physical and virtual serial interfaces (COM ports).

---

## 2. Local Access & System Permissions

Bytehound interacts directly with local Windows hardware interfaces and the host filesystem. This section outlines the required system privileges and resource usage.

### 2.1 Serial Port Access & Drivers
* **COM Port Exclusivity**: On Windows, COM ports are accessed using exclusive handles. When Bytehound connects to a serial interface, the host OS locks the port. No other running application can read or write to it until the connection is closed.
* **User Permissions**: Operating standard COM ports (physical DB9 interfaces or USB-to-UART virtual COM ports) does not require elevated (Administrator) user privileges. The application runs under standard user mode.
* **Driver Security**: Bytehound communicates via standard Windows serial APIs wrapped by `pyserial`. System administrators should ensure that virtual COM port drivers (FTDI, CP210x, CH340) are verified and signed to prevent system-level vulnerabilities.

### 2.2 Filesystem Usage & Scope
Bytehound writes files to specific directories on the user's system:
* **Decoded Data Logs**: Written to the user’s personal document directory: `~\Documents\Bytehound\Logs\`.
* **Saved Analysis Sessions**: Stored in `~\Documents\Bytehound\Analysis\`.
* **System Log Files (Diagnostics)**: 
  * In development mode: Written to `logs/bytehound.log` inside the project root folder.
  * In compiled mode: Written to `%APPDATA%\Bytehound\logs\bytehound.log` (user application data space, requiring no special permissions).
* **Auto-Updater Downloader**: Downloads installation packages directly to `%TEMP%/Bytehound_Update.exe` before validation.
* **Privilege Level**: All filesystem operations are scoped to the running user's directory permissions. The application does not write to restricted system paths (`Windows\System32` or global `Program Files` directories) during runtime, ensuring standard user profiles can run the app without triggering UAC (User Account Control) prompts.

### 2.3 Registry & Settings Access
* Bytehound stores user preferences (active theme, window geometries, plot scales, last selected COM port, and configuration paths) in the Windows Registry.
* **Path**: `HKCU\Software\Bytehound\Bytehound` (Registry key `HKEY_CURRENT_USER`).
* **Security Scope**: Writing to `HKEY_CURRENT_USER` is scoped to the logged-in user profile, requiring no administrative privileges and preventing alterations to system-wide configurations.

---

## 3. Data Integrity & Communications Security

Because serial communication lacks native authentication and encryption layers, Bytehound uses robust verification protocols to prevent data corruption and host crashes when receiving malformed bytes.

### 3.1 Checksum and CRC Verification
To protect against line noise, electromagnetic interference, and framing issues, Bytehound validates the integrity of every incoming framed packet.
* **Supported Checksums**:
  * **CRC16 Modbus**: Poly `0x8005` reflected (effective `0xA001`), initial value `0xFFFF`.
  * **CRC16 CCITT**: CCITT-FALSE, poly `0x1021`, initial value `0xFFFF`.
  * **CRC32**: Standard zlib validation.
* **Verification Logic**: Incoming frames are discarded if their calculated checksum does not match the received checksum. The UI metrics increment the `Errors` counter, and the raw CSV logger flags the frame error.

### 3.2 Parser Robustness & Resynchronization
* **Garbage Tolerance**: If the serial port receives noise or arbitrary bytes (common when hot-plugging cables or during device power cycles), the parser sliding window discards the unaligned prefix.
* **1-Byte Shift Resync**: If a frame match fails validation (due to size or CRC errors), the parser shifts its pointer forward by **exactly 1 byte** and scans again, preventing lockups.
* **Buffer Isolation**: The internal parsing buffers are isolated from the main application thread, ensuring malformed packet payloads do not crash the UI.

### 3.3 Buffer Overrun Prevention
* **Bounded TX Queue**: The priority transmission queue is strictly bounded to `256` elements (`queue.Queue(maxsize=256)`).
* **Write Flooding Guard**: If the target device cannot process packets quickly enough and the queue fills up, Bytehound halts subsequent writes and raises a non-fatal `TX queue full` warning. This protects host memory from expanding indefinitely.

---

## 4. Software Integrity & System Security

### 4.1 Configuration Input Validation
The configuration spreadsheets loaded at runtime are potential vectors for invalid inputs. Bytehound implements strict structural parsing limits:
* **Boundary Checks**: All parameter values in the parameter editor are validated against `min_value` and `max_value` ranges before transmission.
* **Static Range Enforcement**: Values outside the range are rejected, preventing overflow or underflow commands from reaching the device.
* **CLI Config Validator**: Users can run validation checks on configurations without launching the GUI:
  ```powershell
  python -m app.main --validate path_to_config.xlsx
  ```
  This command exits with code `0` if the file is secure and structural checks pass, or `1` if anomalies are found, enabling automated pipeline integration.

### 4.2 Auto-Updater Integrity Check
To prevent unauthorized code execution during updates, the update system verifies installer binaries:
* **Cryptographic Verification**: During update checks, Bytehound fetches the developer-signed `version.json` file from a secure remote URL. It extracts the `sha256` hash of the target update executable.
* **Post-Download Checksum**: When download completes, the updater calculates the SHA-256 hash of the local file and compares it case-insensitively with the expected manifest hash.
* **Download Abort**: If the hashes do not match, or if the update manifest lacks a `sha256` signature, the updater deletes the downloaded file and halts installation.
