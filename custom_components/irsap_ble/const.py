"""Constants for the IRSAP BLE integration."""

DOMAIN = "irsap_ble"

NAME_PREFIX = "IRSAP_RS_"

CONF_LOCAL_NAME = "local_name"
CONF_DEVICES = "devices"
CONF_COMFORT_TEMP = "comfort_temp"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_COMFORT_TEMP = 24.0
DEFAULT_SCAN_INTERVAL = 300  # seconds

MIN_TEMP = 5.0
MAX_TEMP = 30.0
