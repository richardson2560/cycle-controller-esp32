import time, gc, json, sys
import hardware, board, modules
from config import config_manager
from pubsub import event_manager
from env import CONFIG_DEPENDENCIES

def handle_config_change(key, value):
    print(f"\n[Main] Se detectó un cambio de configuración en '{key}'.")
    
    # 1. Casos de reinicio total (los más críticos primero)
    if key.startswith('HARDWARE_CONFIGURATION'):
        hardware.reinit()
        modules.reinit(is_reinit=True)
        return
        
    if key.startswith('MODULE_REGISTRY'):
        modules.reinit(is_reinit=True)
        return

    # 2. Casos de reinicio selectivo (leídos desde la configuración)
    for config_prefix, modules_to_reinit in CONFIG_DEPENDENCIES.items():
        if key.startswith(config_prefix):
            if modules_to_reinit: # Solo si la lista no está vacía
                modules.reinit_modules(modules_to_reinit, is_reinit=True)
            # Nota: No hay 'return' aquí, porque el evento debe seguir propagándose
            # para que los módulos que escuchan (como Loop) puedan reaccionar.
    
    # 3. El evento 'config:updated' ya se ha publicado, así que los módulos
    # que se actualizan silenciosamente (como Loop) ya han recibido la notificación.

# --- setup ---
config_manager.load()
event_manager.subscribe('config:updated', handle_config_change)

gc.enable()
hardware.init()
modules.init()
print("SYSTEM_ID:",config_manager.get("SYSTEM_ID"))
print("SYSTEM_NAME:",config_manager.get("SYSTEM_NAME"))
print(hardware._buses)
print(hardware._drivers)
print(board.states)
print(modules._modules)

# --- loop ---
try:
    while True:
        hardware.update()
        hardware.process_irq_events()
        modules.update()
        time.sleep_ms(10)
        if time.ticks_ms() % 60000 < 10:
            gc.collect()

except KeyboardInterrupt:
    print("\n[main.py] Execution interrupted forcefully.")
except Exception as e:
    print("\n[main.py] FATAL UNHANDLED EXCEPTION")
    sys.print_exception(e)
finally:
    gc.collect()