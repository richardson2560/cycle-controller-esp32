import sys, time, struct, ujson
from machine import RTC
import board
import hardware
from utils import Timer, pad_str
from env import MODULE_CONFIGURATION, MODULE_REGISTRY
from lib.urtc import tuple2seconds, seconds2timetuple, seconds2tuple
from pubsub import event_manager
from config import config_manager

_modules = {}

class _BaseModule:
    def __init__(self):
        self.timer = {"timer0": Timer()}
        self.autostart = True
        self.states = {}
        self.current_state = None
        self.previous_state = None
        self.polling = True

    def update(self):
        """Se ejecuta en cada ciclo del main loop"""
        if self.current_state in self.states:
            self.states[self.current_state]()
    
    def start(self, interval, timer="timer0"):
        """inicia el temporizador y permite que se ejecute."""
        self.autostart = True
        self.timer[timer].start(interval)
    
    def resume(self, timer="timer0"):
        """reanuda el temporizador."""
        self.autostart = True
        self.timer[timer].resume()

    def pause(self, timer="timer0"):
        """pausa el temporizador."""
        self.timer[timer].pause()
    
    def stop(self, timer="timer0"):
        """Detiene el módulo, pausando su temporizador y evitando que se ejecute."""
        self.autostart = False
        self.timer[timer].pause()
    
    def reset(self, timer="timer0"):
        self.timer[timer].reset()
    
    def set_interval(self, timer="timer0", interval=None):
        if interval:
            self.timer[timer].set_interval(interval)
    
    def check(self, timer="timer0"):
        return self.timer[timer].check()

    def elapsed(self, timer="timer0"):
        """Devuelve el tiempo transcurrido desde el último reinicio en ms."""
        return self.timer[timer].elapsed()
    
    def remaining(self, timer="timer0"):
        """Devuelve el tiempo restante hasta que expire el intervalo en ms."""
        return self.timer[timer].remaining()

class Clock(_BaseModule):
    def __init__(self, config, name=None, is_reinit=False):
        super().__init__()
        self.device_key = config.get("device_key", None)
        self.drift_check_interval_s = config.get("drift_check_interval_s", 60)
        self.max_drift_s = config.get("max_drift_s", 2)
        self.driver = hardware._drivers[self.device_key]
        self.start(self.drift_check_interval_s)
    def update(self):
        if self.check():
            driver_seconds = tuple2seconds(self.driver.datetime())
            rtc_seconds = time.time()
            if abs(driver_seconds - rtc_seconds) > self.max_drift_s:
                RTC().datetime(seconds2timetuple(driver_seconds))

def _format_time(fmt_str, time_tuple):
    s = fmt_str
    s = s.replace("%H", "{:02d}".format(time_tuple[3]))
    s = s.replace("%M", "{:02d}".format(time_tuple[4]))
    s = s.replace("%S", "{:02d}".format(time_tuple[5])) 
    s = s.replace("%d", "{:02d}".format(time_tuple[2]))
    s = s.replace("%m", "{:02d}".format(time_tuple[1]))
    s = s.replace("%y", "{:02d}".format(time_tuple[0] % 100))
    s = s.replace("%Y", "{}".format(time_tuple[0]))
    return s

def _format_hms(ms):
    if ms is None:
        return "00:00:00"
    s = ms // 1000
    h = s // 3600
    m = (s % 3600) // 60
    s = s % 60
    return f"{h:02}:{m:02}:{s:02}"

class Display(_BaseModule):
    def __init__(self, config, name=None, is_reinit=False):
        super().__init__()
        self.timer["timer1"] = Timer(one_shot=True)
        self.device_key = config.get("device_key", None)
        self.refresh_interval_s = config.get("refresh_interval_s", 1)
        self.boot_duration_s = config.get("boot_duration_s", 5)
        self.backlight_timeout_s = config.get("backlight_timeout_s", 30)
        self.rows = config.get("rows", 2)
        self.cols = config.get("cols", 16)
        self.to_start = config.get("to_start")
        self.disp_buffer = [pad_str("", self.cols) for _ in range(self.rows)]
        self.input_buffer = ""
        self.current_config = None
        self.prev_disp_buffer = [""] * self.rows
        self.edit_buffer = "" 
        self.edited_value = None
        self.original_config_value_s = 0 
        self.states = {
            "boot": self.boot, 
            "idle": self.idle, 
            "main": self.main, 
            "idle_1": self.idle_1,
            "set": self.set_view,
            "config": self.config_view,
        }
        if not is_reinit:
            self.current_state = "boot"
            self.start(self.boot_duration_s, timer="timer1")
        else:
            self.current_state = "main" # Saltar directamente a la pantalla principal
            self.start(self.refresh_interval_s, timer="timer0")
            if self.to_start in _modules: # Asegurarse que el loop se inicie
                _modules[self.to_start].resume()

        self.driver = hardware._drivers.get(self.device_key)
        if not self.driver: self.stop()
        self.read = config.get("read")
        if self.read: event_manager.subscribe(f'irq:{self.read}:key_pressed', self.read_keypad)

    def boot(self):
        custom_chars = [
            [0b00000, 0b00000, 0b00000, 0b00000, 0b00001, 0b00011, 0b00011, 0b00111], # Char 0
            [0b00100, 0b01100, 0b11110, 0b11111, 0b11111, 0b11111, 0b11111, 0b11111], # Char 1
            [0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b10000, 0b11000, 0b11000], # Char 2
            [0b01111, 0b01111, 0b01111, 0b11111, 0b11111, 0b11111, 0b11111, 0b01110], # Char 3
            [0b11011, 0b11011, 0b10001, 0b10000, 0b00000, 0b00000, 0b00000, 0b00000], # Char 4
            [0b11100, 0b11100, 0b11110, 0b11110, 0b01110, 0b01110, 0b00110, 0b00100], # Char 5
            [0b00110, 0b00110, 0b00010, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000], # Char 6
        ]
        self.driver.clear()
        dx = 3; dy = 1
        for i, charmap in enumerate(custom_chars):
            self.driver.custom_char(i, charmap)

        for i in range(7):
            row = i // 3
            col = i % 3 
            self.driver.move_to(col + dx, row + dy)
            self.driver.putchar(chr(i))

        self.driver.move_to(4 + dx, 0 + dy)
        self.driver.putstr("GTG")
        self.driver.move_to(4 + dx, 1 + dy)
        self.driver.putstr("PETROLEUM")
        self.current_state = "idle"
    def idle(self):
        if self.check(timer="timer1"):
            self.start(self.refresh_interval_s, timer="timer0")
            self.driver.clear()
            _modules[self.to_start].resume()
            self.current_state = "main"
    def main(self):
        self.driver.hide_cursor()

        now_tuple = time.localtime(time.time()) 
        time_str = _format_time("%d/%m/%y %H:%M:%S", now_tuple)

        loop_state = board.states.get("loop_state", "close")
        loop_open_s = config_manager.get("MODULE_CONFIGURATION.loop.open_time_s", 120)
        loop_close_s = config_manager.get("MODULE_CONFIGURATION.loop.close_time_s", 3480)
        loop_remaining_ms = board.states.get("loop_remaining_ms", 0)

        # Selecciona tiempo total según estado
        if loop_state == "open":
            total_time = _format_hms(loop_open_s * 1000)
            prefix = "TO:"
        else:
            total_time = _format_hms(loop_close_s * 1000)
            prefix = "TC:"

        # Estado alineado a la derecha
        state_str = loop_state.upper()
        line3 = pad_str(f"{prefix}{total_time}", self.cols - len(state_str)) + state_str

        # Tiempo restante
        line4 = pad_str(f"TR:{_format_hms(loop_remaining_ms)}", self.cols)

        # Construir buffer
        self.disp_buffer[0] = pad_str(time_str, self.cols)   # Fila 1
        self.disp_buffer[1] = pad_str("", self.cols)         # Fila 2 (vacía)
        self.disp_buffer[2] = line3                          # Fila 3
        self.disp_buffer[3] = line4                          # Fila 4

        # Renderiza solo si cambió
        for row in range(self.rows):
            if row < len(self.disp_buffer) and self.disp_buffer[row] != self.prev_disp_buffer[row]:
                self.driver.move_to(0, row)
                self.driver.putstr(self.disp_buffer[row])
                self.prev_disp_buffer[row] = self.disp_buffer[row]

        self.current_state = "idle_1"
    def idle_1(self):
        if self.check(timer="timer0"):
            self.current_state = "main"
    def set_view(self):
        self.driver.show_cursor() 
        self.driver.blink_cursor_off()
        code_display = self.input_buffer or ""
        self.disp_buffer[0] = pad_str("ENTER CODE:", self.cols)
        self.disp_buffer[1] = pad_str(code_display, self.cols)
        self.disp_buffer[2] = pad_str("(*=OK  #=DEL)", self.cols)
        self.disp_buffer[3] = pad_str("", self.cols)

        for row in range(self.rows):
            if self.disp_buffer[row] != self.prev_disp_buffer[row]:
                self.driver.move_to(0, row)
                self.driver.putstr(self.disp_buffer[row])
                self.prev_disp_buffer[row] = self.disp_buffer[row]
        
        cursor_col = min(len(code_display), self.cols - 1)  # evita ir fuera de rango
        self.driver.move_to(cursor_col, 1)
    def _leave_config_state(self):
        """Función auxiliar para limpiar al salir del modo configuración."""
        self.driver.hide_cursor()
        self.driver.blink_cursor_off()
        self.current_state = "main"
        self.prev_disp_buffer = [""] * self.rows
    def read_keypad(self, key=None):
        print(key)
        if self.current_state == "idle_1":
            if key == "C":
                self.input_buffer = ""
                self.current_state = "set"
                self.prev_disp_buffer = [""] * self.rows

        elif self.current_state == "set":
            if key and key.isdigit() and len(self.input_buffer) < 4:
                self.input_buffer += key
            elif key == "#":  # borrar
                self.input_buffer = self.input_buffer[:-1]
            elif key == "*":  # enter
                if self.validate_code(self.input_buffer):
                    if self.config_action == "set_open_time":
                        self.original_config_value_s = config_manager.get("MODULE_CONFIGURATION.loop.open_time_s", 0)
                    elif self.config_action == "set_close_time":
                        self.original_config_value_s = config_manager.get("MODULE_CONFIGURATION.loop.close_time_s", 0)
                    self.current_config = self.input_buffer
                    self.current_state = "config"
                    self.edit_buffer = "" # Limpiar buffer de edición
                    self.driver.blink_cursor_on()
                else:
                    self.current_state = "main"
            elif key == "D":
                self._leave_config_state()

        elif self.current_state == "config":
            max_len = 6
            if key and key.isdigit():
                if len(self.edit_buffer) < max_len:
                    self.edit_buffer += key
            
            elif key == "#":
                self.edit_buffer = self.edit_buffer[:-1]
            
            elif key == "*":
                if self.edit_buffer:
                    if self.config_action in ("set_open_time", "set_close_time"):
                        # 1. Crear la cadena base del valor original (HHMMSS)
                        h = self.original_config_value_s // 3600
                        m = (self.original_config_value_s % 3600) // 60
                        s = self.original_config_value_s % 60
                        base_str = f"{h:02}{m:02}{s:02}"
                        
                        # 2. Superponer el buffer de edición
                        len_edit = len(self.edit_buffer)
                        merged_str = self.edit_buffer + base_str[len_edit:]
                        
                        # 3. Parsear la cadena fusionada para obtener el valor final
                        h_new = int(merged_str[0:2])
                        m_new = int(merged_str[2:4])
                        s_new = int(merged_str[4:6])
                        total_s_new = h_new * 3600 + m_new * 60 + s_new
                        
                        # 4. Guardar el nuevo valor
                        config_key = ""
                        if self.config_action == "set_open_time":
                            config_key = "MODULE_CONFIGURATION.loop.open_time_s"
                        elif self.config_action == "set_close_time":
                            config_key = "MODULE_CONFIGURATION.loop.close_time_s"
                        
                        if config_key:
                            config_manager.set(config_key, total_s_new, persistent=True)
                    else:
                        self.save_datetime()
                
                self._leave_config_state() # Siempre salir
            
            elif key == "D":
                # Salir sin guardar cambios
                self._leave_config_state()

    def save_datetime(self):
        try:
            rtc_driver = hardware._drivers.get('rtc')
            if not rtc_driver: return

            current_seconds = time.time()
            (y, M, d, h, m, s, wd, yd) = time.localtime(current_seconds)

            if self.config_action == "set_date":
                base_str = f"{d:02d}{M:02d}{y % 100:02d}"
                merged_str = self.edit_buffer + base_str[len(self.edit_buffer):]
                d = int(merged_str[0:2]); M = int(merged_str[2:4]); y = 2000 + int(merged_str[4:6])
            
            elif self.config_action == "set_time":
                base_str = f"{h:02d}{m:02d}{s:02d}"
                merged_str = self.edit_buffer + base_str[len(self.edit_buffer):]
                h = int(merged_str[0:2]); m = int(merged_str[2:4]); s = int(merged_str[4:6])

            new_time_secs = time.mktime((y, M, d, h, m, s, 0, 0))

            rtc_driver.datetime(seconds2tuple(new_time_secs))
            RTC().datetime(seconds2timetuple(new_time_secs))

        except (ValueError, TypeError) as e:
            print(f"Error guardando fecha/hora: {e}")

    def validate_code(self, code: str) -> bool:
        valid_codes = {
            "10": "set_open_time",
            "14": "set_close_time",
            "02": "set_date",
            "01": "set_time"
        }
        if code in valid_codes:
            self.config_action = valid_codes[code]
            return True
        return False

    def _map_pos_to_cursor(self, pos, separator):
        if pos < 2: return pos
        if pos < 4: return pos + 1
        if pos < 6: return pos + 2
        return 7 # Devuelve la última posición posible

    def config_view(self):
        title = ""
        prefix = ""
        fmt = ""
        separator = ':' # Por defecto para la hora

        if self.config_action == "set_open_time":
            title = "SET OPEN TIME"
            prefix = "TO:"
            # Leemos el valor actual desde la configuración
            total_s = config_manager.get("MODULE_CONFIGURATION.loop.open_time_s", 0)
            fmt = self.format_edit_time(total_s)

        elif self.config_action == "set_close_time":
            title = "SET CLOSE TIME"
            prefix = "TC:"
            total_s = config_manager.get("MODULE_CONFIGURATION.loop.close_time_s", 0)
            fmt = self.format_edit_time(total_s)

        elif self.config_action == "set_date":
            title = "SET DATE"
            prefix = "DT:"
            separator = '/'
            fmt = self.format_edit_date(time.time())

        elif self.config_action == "set_time":
            title = "SET TIME"
            prefix = "TM:"
            fmt = self.format_edit_time(time.time())
        
        else:
            self._leave_config_state()
            return
        
        # Renderizado
        self.disp_buffer[0] = pad_str(title, self.cols)
        self.disp_buffer[1] = pad_str(f"{prefix} {fmt}", self.cols)
        self.disp_buffer[2] = pad_str("(*=OK #=DEL D=ESC)", self.cols)
        self.disp_buffer[3] = pad_str("", self.cols)

        for row in range(self.rows):
            if self.disp_buffer[row] != self.prev_disp_buffer[row]:
                self.driver.move_to(0, row)
                self.driver.putstr(self.disp_buffer[row])
                self.prev_disp_buffer[row] = self.disp_buffer[row]
        
        # Posicionar el cursor parpadeante
        cursor_x_base = len(prefix) + 1
        cursor_x_offset = self._map_pos_to_cursor(len(self.edit_buffer), separator)
        self.driver.move_to(cursor_x_base + cursor_x_offset, 1)
    
    def format_edit_time(self,total_s):
        now_tuple = time.localtime(total_s)
        h,m,s = now_tuple[3], now_tuple[4], now_tuple[5]
        base=f"{h:02}{m:02}{s:02}"
        filled=list(base)
        for i,ch in enumerate(self.edit_buffer): 
            filled[i]=ch
        return f"{filled[0]}{filled[1]}:{filled[2]}{filled[3]}:{filled[4]}{filled[5]}"

    def format_edit_date(self, total_s):
        now_tuple = time.localtime(total_s)
        d, m, y = now_tuple[2], now_tuple[1], now_tuple[0] % 100
        base=f"{d:02}{m:02}{y:02}"
        filled=list(base)
        for i,ch in enumerate(self.edit_buffer): 
            filled[i]=ch
        return f"{filled[0]}{filled[1]}/{filled[2]}{filled[3]}/{filled[4]}{filled[5]}"

class Loop(_BaseModule):
    def __init__(self, config, name=None, is_reinit=False):
        super().__init__()
        self.name = name
        self.timer["timer1"] = Timer(one_shot=True)
        self.refresh_interval_s = config_manager.get(f"MODULE_CONFIGURATION.{name}.refresh_interval_s", 1)
        self.open_time_s = config_manager.get(f"MODULE_CONFIGURATION.{name}.open_time_s", 120)
        self.close_time_s = config_manager.get(f"MODULE_CONFIGURATION.{name}.close_time_s", 3480)
        self.subs_1 = config.get("subs_1")
        self.subs_2 = config.get("subs_2")
        self.read = config.get("read")
        if self.subs_1: event_manager.subscribe(f'irq:{self.subs_1}:triggered', self.open)
        if self.subs_2: event_manager.subscribe(f'irq:{self.subs_2}:triggered', self.close)
        if self.read:
            event_manager.subscribe(f'irq:{self.read}:key_pressed', self.read_keypad)
        self.states = {
            "open": self.open, 
            "close": self.close, 
            "idle": self.idle
        }
        self.current_state = "close"
        event_manager.subscribe('config:updated', self.handle_config_update)
        self.start(self.refresh_interval_s)
    
    def handle_config_update(self, key, value):
        """Manejador para actualizar la configuración de forma silenciosa."""
        current_state = board.states.get("loop_state")

        if key == f"MODULE_CONFIGURATION.{self.name}.open_time_s":
            print(f"[{self.name}] Tiempo de apertura actualizado a: {value}s")
            self.open_time_s = value
            if current_state == "open":
                print(f"[{self.name}] Ciclo de apertura reiniciado con nuevo tiempo: {value}s")
                self.start(self.open_time_s, "timer1")

        elif key == f"MODULE_CONFIGURATION.{self.name}.close_time_s":
            print(f"[{self.name}] Tiempo de cierre actualizado a: {value}s")
            self.close_time_s = value
            if current_state == "close":
                print(f"[{self.name}] Ciclo de cierre reiniciado con nuevo tiempo: {value}s")
                self.start(self.close_time_s, "timer1")
    
    def read_keypad(self, key=None):
        if key == "A" and self.autostart: self.current_state = "open"
        if key == "B" and self.autostart: self.current_state = "close"
    
    def close(self,state=None, pin_value=None):
        if (state is None or state == 1) and self.autostart:
            self.start(self.close_time_s, timer="timer1")
            board.states["loop_state"] = "close"
            board.states["loop_open_ms"] = self.open_time_s * 1000
            board.states["loop_close_ms"] = self.close_time_s * 1000
            event_manager.publish('loop:state_changed', state='close')
            self.current_state = "idle"
    
    def open(self,state=None, pin_value=None):
        if (state is None or state == 1) and self.autostart:
            self.start(self.open_time_s, timer="timer1")
            board.states["loop_state"] = "open"
            board.states["loop_open_ms"] = self.open_time_s * 1000
            board.states["loop_close_ms"] = self.close_time_s * 1000
            event_manager.publish('loop:state_changed', state='open')
            self.current_state = "idle"
    
    def idle(self):
        # Actualizamos el tiempo restante para que el display lo muestre
        board.states["loop_remaining_ms"] = self.remaining(timer="timer1")
        
        # Usamos el check del timer para una transición de estado precisa
        if self.check(timer="timer1"):
            if board.states["loop_state"] == "close":
                self.current_state = "open"
            elif board.states["loop_state"] == "open":
                self.current_state = "close"    

class RelayController(_BaseModule):
    def __init__(self, config, name=None, is_reinit=False):
        super().__init__()
        self.pulse_duration_ms = config.get("pulse_duration_ms", 100)
        
        self.timer["open_pulse"] = Timer(one_shot=True, use_ms=True)
        self.timer["close_pulse"] = Timer(one_shot=True, use_ms=True)

        self.open_driver = hardware._drivers.get(config.get("open_pin_key"))
        self.close_driver = hardware._drivers.get(config.get("close_pin_key"))
        self.open_led_driver = hardware._drivers.get(config.get("open_pin_led"))
        self.close_led_driver = hardware._drivers.get(config.get("close_pin_led"))

        event_manager.subscribe('loop:state_changed', self.handle_loop_state_change)
    
    def handle_loop_state_change(self, state):
        """Este método se ejecuta cuando Loop anuncia un nuevo estado."""
        if state == 'open' and self.open_driver:
            print("[Relay] Iniciando pulso de APERTURA.")
            self.open_driver.value(1) # Iniciar pulso
            self.open_led_driver.value(1)
            self.close_led_driver.value(0)
            self.start(self.pulse_duration_ms, timer="open_pulse")
        
        elif state == 'close' and self.close_driver:
            print("[Relay] Iniciando pulso de CIERRE.")
            self.close_driver.value(1) # Iniciar pulso
            self.open_led_driver.value(0)
            self.close_led_driver.value(1)
            self.start(self.pulse_duration_ms, timer="close_pulse")

    def update(self):
        """Se ejecuta en cada ciclo del main loop para terminar los pulsos."""
        if self.check("open_pulse"):
            self.open_driver.value(0) # Terminar pulso de apertura
            print("[Relay] Pulso de APERTURA finalizado.")
            
        if self.check("close_pulse"):
            self.close_driver.value(0) # Terminar pulso de cierre
            print("[Relay] Pulso de CIERRE finalizado.")

def reinit_modules(module_names: list, is_reinit=True):
    """
    Reinicia selectivamente una lista de módulos por su nombre.
    """
    print(f"[Modules] Reinicio selectivo para: {module_names}")
    for name in module_names:
        if name in _modules:
            # Detener y limpiar el módulo existente
            if hasattr(_modules[name], 'stop'):
                _modules[name].stop()
            del _modules[name]

            # Re-crear solo el módulo específico
            module_info = MODULE_REGISTRY.get(name)
            if module_info:
                try:
                    class_name = module_info["class"]
                    module_class = globals().get(class_name)
                    if module_class:
                        config = config_manager.get(f"MODULE_CONFIGURATION.{name}", {})
                        _modules[name] = module_class(config, name, is_reinit=is_reinit)
                        print(f"[Modules] Módulo '{name}' reinicializado.")
                        if not module_info["autostart"]:
                            _modules[name].stop()
                except Exception as e:
                    print(f"Error reinicializando módulo '{name}':")
                    sys.print_exception(e)

def reinit(is_reinit=True):
    """Limpia y reinicializa TODOS los módulos (para cambios mayores)."""
    print("[Modules] Reinicializando TODOS los módulos...")
    for module in _modules.values():
        if hasattr(module, 'stop'): module.stop()
    _modules.clear()
    init(is_reinit=is_reinit)
    print("[Modules] Módulos reinicializados.")

def init(is_reinit=False):
    ordered_modules = sorted(MODULE_REGISTRY.items(), key=lambda x: x[1]["order"])
    for name, module_info in ordered_modules:
        try:
            class_name = module_info["class"]
            module_class = globals().get(class_name)
            if module_class:
                config = MODULE_CONFIGURATION.get(name, {})
                _modules[name] = module_class(config, name, is_reinit=is_reinit)
                if not module_info["autostart"]: _modules[name].stop()
        except Exception as e:
            sys.print_exception(e)
            if module_info["critical"]: break

def update():
    for name, module in _modules.items():
        if module.autostart and module.polling:
            module.update()
