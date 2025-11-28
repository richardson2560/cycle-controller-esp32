HARDWARE_CONFIGURATION = {
    "i2c": {
        "1": { "sda": 21, "scl": 22, "freq": 400000 },
    },
    "devices": {
        "rtc": { "driver": "DS3231", "bus_type": "i2c", "bus_id": "1", "address": 0x68 },
        "display": { "driver": "LCD_I2C", "bus_type": "i2c", "bus_id": "1", "address": 0x27, "rows": 4, "cols": 20 },
        "keypad": { "driver": "Keypad", "bus_type": "i2c", "bus_id": "1", "address": 0x20, "rows": [7,6,5,4], "cols": [3,2,1,0], "keymap": "123A456B789C*0#D" },
        "open_button": { "driver": "IRQ_Pin", "pin": 4, "mode": "IN", "pull": "PULL_UP"},
        "close_button": { "driver": "IRQ_Pin", "pin": 0, "mode": "IN", "pull": "PULL_UP"},
        "open_led": { "driver": "GPIO_Pin", "pin": 15, "mode": "OUT", "value": 0 },
        "close_led": { "driver": "GPIO_Pin", "pin": 2, "mode": "OUT", "value": 0 },
        "relay_open": { "driver": "GPIO_Pin", "pin": 32, "mode": "OUT", "value": 0 },
        "relay_close": { "driver": "GPIO_Pin", "pin": 33, "mode": "OUT", "value": 0 },
    },
}

MODULE_CONFIGURATION = {
    "clock":            { "device_key": "rtc", "drift_check_interval_s": 60, "max_drift_s": 10 },
    "display":          { "device_key": "display", "refresh_interval_s": 0.1, "boot_duration_s": 5, "backlight_timeout_s": 60, "rows": 4, "cols": 20, "to_start": "loop", "read": "keypad"},
    "loop":             { "refresh_interval_s": 0.1, "open_time_s": 120, "close_time_s": 3480, "subs_1": "open_button", "subs_2": "close_button", "read": "keypad"},
    "relays":           { "open_pin_key": "relay_open", "close_pin_key": "relay_close", "open_pin_led":"open_led", "close_pin_led":"close_led", "pulse_duration_ms": 100 },
}

MODULE_REGISTRY = {
    "clock":            { "class": "Clock",             "order": 10, "autostart": True, "critical": True  },
    "display":          { "class": "Display",           "order": 20, "autostart": True, "critical": False },
    "loop":             { "class": "Loop",              "order": 15, "autostart": False,"critical": False },
    "relays":           { "class": "RelayController",   "order": 30, "autostart": True, "critical": False },
}

CONFIG_DEPENDENCIES = {
    # Clave de configuración (o prefijo) -> Lista de nombres de módulos a reiniciar
    'MODULE_CONFIGURATION.loop': [],
}

STORAGE_PATH = 'storage.json'
DEFAULT_LOG_LEVEL = 'INFO'
SYSTEM_NAME = 'BaseStation'
SYSTEM_ID = 0
BASE_STATION_ID = 0

print("[env.py] Project configuration loaded.")