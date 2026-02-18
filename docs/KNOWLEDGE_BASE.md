# Supervisor NOC: Development Knowledge Base

## 1. Reticulum Interface Requirements
When building custom interfaces (drivers) for the Reticulum Network Stack (RNS), the main class MUST inherit from `RNS.Interfaces.Interface`. Failing to define specific attributes will cause the RNS Core to crash during status checks (`rnstatus`) or traffic shaping.

### Critical Attributes Checklist
| Attribute | Type | Purpose | Fix/Lesson |
| :--- | :--- | :--- | :--- |
| `ingress_control` | `bool` | Traffic policing flag | Must be set to `False` to prevent "Traffic Cop" crashes. |
| `held_announces` | `list` | Packet queue | Must be a `list` `[]`. Initializing as `int` `0` causes `len()` crashes. |
| `ia_freq_deque` | `deque` | Inbound frequency log | Required for `rnstatus`. Use `collections.deque(maxlen=100)`. |
| `oa_freq_deque` | `deque` | Outbound frequency log | Required for `rnstatus`. Use `collections.deque(maxlen=100)`. |
| `mode` | `int` | Operation Mode | Set to `RNS.Interfaces.Interface.MODE_ACCESS_POINT` for correct reporting. |

## 2. Meshtastic Hardware Integration
* **Broadcast vs. Unicast:** The Meshtastic python library often drops packets if the destination is unclear.
    * *Solution:* Explicitly force `destinationId='^all'` in `sendData()` during Alpha testing to ensure packets leave the radio.
* **Serial Locking:** Only one process can hold the COM port. `launcher.py` and `rnstatus` (RPC) can run together, but a second script trying to open Serial will fail.

## 3. Connection Modes
The driver supports two connection modes, configured via `connection_type` in `config.json`:

### Serial (default)
* Connects directly via USB: `meshtastic.serial_interface.SerialInterface(port)`
* Auto-detects serial ports if none configured; falls back to `COM3` (Windows) or `/dev/ttyUSB0` (Linux)
* Only one process can hold the serial port at a time

### TCP (meshtasticd)
* Connects over network: `meshtastic.tcp_interface.TCPInterface(hostname, portNumber)`
* Default: `localhost:4403`
* **Single-client limitation:** meshtasticd's TCP port allows only ONE client at a time. The firmware enforces this — competing apps (CLI, web client, scripts) cause connection refusals.
* Use TCP mode when the radio is connected to a remote host running meshtasticd
* Future phases may add HTTP protobuf transport and MQTT bridge to avoid TCP contention (see SESSION_NOTES)

### Config Example
```json
{
    "gateway": {
        "connection_type": "serial",
        "port": "COM3",
        "host": "localhost",
        "tcp_port": 4403
    }
}
```

## 4. Architecture Principles (Meshforge Aligned)
* **Separation of Concerns:** The Driver (`src/`) handles hardware bytes. The Launcher handles RNS logic.
* **Resilience:** The driver creates a "Kitchen Sink" of attributes to satisfy RNS, even if not all are used, to prevent runtime crashes.