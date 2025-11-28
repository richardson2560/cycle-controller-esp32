import sys, time
from machine import Pin, ADC, I2C, UART, RTC
import board
from lib.urtc import DS3231, tuple2seconds, seconds2timetuple
from lib.machine_i2c_lcd import I2cLcd
from lib.i2c_4x4_keypad import Keypad
from config import config_manager
from pubsub import event_manager

_buses, _drivers = {}, {}
_pending_irqs = {}

DRIVER_CLASS_MAP = {
    "GPIO_Pin": Pin,
    "IRQ_Pin": Pin,
    "DS3231": DS3231,
    "LCD_I2C": I2cLcd,
    "Keypad": Keypad,
}

def init():
    HARDWARE_CONFIGURATION = config_manager.get("HARDWARE_CONFIGURATION", {})
    for bus_type in ['i2c', 'uart']:
        for bus_id, config in HARDWARE_CONFIGURATION.get(bus_type, {}).items():
            try:
                bus_key = f"{bus_type}_{bus_id}"
                if bus_type == 'i2c': _buses[bus_key] = I2C(int(bus_id), scl=Pin(config['scl']), sda=Pin(config['sda']), freq=config['freq'])
                elif bus_type == 'uart': 
                    _buses[bus_key] = UART(int(bus_id), **config)
                    board.messages[bus_key] = {
                        "in": [],
                        "out": []
                    }
            except Exception as e: pass
    
    for name, config in HARDWARE_CONFIGURATION.get('devices', {}).items():
        driver_key = config.get("driver")
        driver_class = DRIVER_CLASS_MAP.get(driver_key)
        if not driver_class: continue
        try:
            instance = None
            if config.get("bus_type") == "i2c":
                bus = _buses.get(f"i2c_{config['bus_id']}")
                if driver_class == DS3231:
                    instance = DS3231(bus, config['address'])
                    dt_seconds = tuple2seconds(instance.datetime()) # Life-check
                    RTC().datetime(seconds2timetuple(dt_seconds))
                elif driver_class == I2cLcd:
                    instance = I2cLcd(bus, config['address'], config['rows'], config['cols'])
                    instance.clear() # Life-check
                elif driver_class == Keypad:
                    instance = Keypad(bus, config['address'], config['keymap'], config['rows'], config['cols'])
                    board.states[f"{name}_last_key"] = None
                    board.states[f"{name}_pressed_key"] = None
            elif driver_class == ADC:
                instance = ADC(Pin(config['pin']))
                if 'attenuation' in config: instance.atten(getattr(ADC, config['attenuation']))
                instance.read_u16() # Life-check
                board.states[name] = None
            elif driver_class == Pin:
                mode = Pin.OUT if config.get('mode', 'OUT').upper() == 'OUT' else Pin.IN
                pull = getattr(Pin, config['pull'].upper()) if 'pull' in config and config['pull'] else None
                if mode == Pin.OUT:
                    print(config['pin'])
                if pull:
                    instance = Pin(config['pin'], mode, pull)
                else:
                    instance = Pin(config['pin'], mode)
                if mode == Pin.OUT and 'value' in config: instance.value(config['value'])
                elif mode == Pin.IN: 
                    board.states[name] = None
                    if driver_key == "IRQ_Pin":
                        _pending_irqs[name] = False
                        def make_handler(name):
                            def handler(pin):
                                _pending_irqs[name] = True
                            return handler
                        instance.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=make_handler(name))

            if instance: _drivers[name] = instance
        except Exception as e: 
            sys.print_exception(e)
            print(f"[Message] No se pudo crear el driver {name}: {e}")

def reinit():
    global _buses, _drivers, _pending_irqs
    print("\n[Hardware] Reinicializando el hardware debido a un cambio de configuración...")
    
    # Aquí iría la lógica para desinicializar I2C, UART si es necesario
    # for bus in _buses.values():
    #     if hasattr(bus, 'deinit'):
    #         bus.deinit()

    _buses.clear()
    _drivers.clear()
    _pending_irqs.clear()
    
    init()
    print("[Hardware] Hardware reinicializado.\n")

def update():
    HARDWARE_CONFIGURATION = config_manager.get("HARDWARE_CONFIGURATION", {})
    states = board.states
    for name, config in HARDWARE_CONFIGURATION.get('devices', {}).items():
        driver = config.get("driver")
        if driver == "GPIO_Pin" and config.get('mode', 'OUT').upper() == 'IN':
            if config.get('pull') == 'PULL_UP':
                states[name] = 1 - _drivers[name].value()
            else:
                states[name] = _drivers[name].value()
        elif driver == "ADC_Pin":
            states[name] = _drivers[name].read() 
        elif driver == "Keypad":
            key = _drivers[name].get_key()
            last_key = states.get(f"{name}_pressed_key", None)
            if key != last_key:  # hubo cambio
                states[f"{name}_last_key"] = last_key
                states[f"{name}_pressed_key"] = key
                states[f"{name}_key_changed"] = True
                if key is not None:
                    event_manager.publish(f'irq:{name}:key_pressed', key=key)
            else:
                states[f"{name}_key_changed"] = False
        
def process_irq_events():
    """
    Procesa las banderas de IRQ pendientes.
    Esta función DEBE ser llamada desde el bucle principal.
    """
    HARDWARE_CONFIGURATION = config_manager.get("HARDWARE_CONFIGURATION", {})
    global _pending_irqs
    for name, pending in _pending_irqs.items():
        if pending:
            _pending_irqs[name] = False
            pin_value = _drivers[name].value()
            pull = HARDWARE_CONFIGURATION['devices'][name].get("pull")
            if pull == "PULL_UP":
                current_state = 1 - pin_value
            else:
                current_state = pin_value
            board.states[name] = current_state
            event_manager.publish(f'irq:{name}:triggered', state=current_state, pin_value=pin_value)
            
