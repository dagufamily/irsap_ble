# IRSAP BLE Radiator (Home Assistant custom integration)

Controls IRSAP electric radiators (Ares, advertised as `IRSAP_RS_xxxxxxx`) over Bluetooth, without the IRSAP cloud.
One `climate` entity per radiator.

## Install
1. Copy `custom_components/irsap_ble` into `/config/custom_components/` (create the folder if needed).
2. Restart Home Assistant.
3. Settings > Devices & services > Add integration > **IRSAP BLE Radiator**. The integration scans for radiators,
   lets you tick the ones to add, and asks a name for each (for example the room).
   Radiators in range are also offered automatically in the "Discovered" section.

The radiators must be reachable by a Bluetooth adapter of Home Assistant (the Raspberry's own, or an ESPHome Bluetooth
proxy with `bluetooth_proxy: active: true`). Close the IRSAP NOW phone app: the radiator accepts one connection only.

## Entity
| Home Assistant | Radiator |
|---|---|
| `hvac_mode` `heat` | on, back to the normal program (Comfort preset rewritten, see options) |
| `hvac_mode` `off` | off, antifreeze 5 C |
| `set_temperature` | manual setpoint with no expiry ("until next modification" in the app) |
| `current_temperature` | measured temperature |
| `target_temperature` | effective setpoint |
| attribute `control_mode` | `manual` or `program` |
| attribute `until` | program: next program change; manual with timer: end of the timer |

Options (per radiator): Comfort temperature written back when you choose `heat` (default 24.0 C), polling interval
(default 300 s). The integration connects only for a few seconds per poll or command, so the phone app keeps working
between two operations.

## Icon
`custom_components/irsap_ble/brand/icon.png` is shown in the integrations page from Home Assistant 2026.3 on
(older versions need the icon in the central brands repository and show a placeholder).
The image is the IRSAP NOW app icon, cropped from a phone screenshot (low resolution, 256 px). It is a third-party
trademark: fine for private use, replace it before publishing the integration.

## Known limits
* Eco / Comfort / antifreeze presets cannot be changed over Bluetooth (the app keeps them locally). Choosing `heat`
  writes back the Comfort value set in the options.
* Setting a temperature switches the radiator to manual mode until the next change. Use `heat` to return to the program.
* Temperature range 5-30 C is a safe guess, the real limits were not verified.
* Tested on the protocol level only (captures from one model, firmware 01.0.55). Writes use the full configuration
  table captured from the app: if your firmware differs, check before using it on other models.
