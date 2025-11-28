# --- START OF FILE config.py ---

import json
from env import (
    HARDWARE_CONFIGURATION,
    MODULE_CONFIGURATION,
    MODULE_REGISTRY,
    STORAGE_PATH,
    DEFAULT_LOG_LEVEL,
    SYSTEM_NAME,
    SYSTEM_ID,
    BASE_STATION_ID,
)
from pubsub import event_manager

class ConfigManager:
    """
    Gestiona la configuración del proyecto. Fusiona la configuración base de env.py
    con las modificaciones de storage.json usando claves con formato de ruta.
    Notifica a los suscriptores sobre los cambios de configuración para una recarga dinámica.
    """
    def __init__(self):
        self._config = {}
        self._persistent_keys = set() # Almacenará las claves que SÍ deben guardarse

    def _get_nested(self, keys: str):
        """Obtiene un valor de un diccionario anidado usando una clave como 'a.b.c'"""
        data = self._config
        for key in keys.split('.'):
            if isinstance(data, dict) and key in data:
                data = data[key]
            else:
                return None
        return data

    def _set_nested(self, keys: str, value):
        """Establece un valor en un diccionario anidado usando una clave como 'a.b.c'"""
        dic = self._config
        key_list = keys.split('.')
        for key in key_list[:-1]:
            if key not in dic or not isinstance(dic[key], dict):
                dic[key] = {}
            dic = dic[key]
        dic[key_list[-1]] = value
        
    def load(self):
        """
        Carga la configuración base de env.py y la sobrescribe con los valores
        de storage.json, interpretando las claves como rutas.
        """
        # 1. Cargar la configuración base de env.py
        self._config = {
            "HARDWARE_CONFIGURATION": HARDWARE_CONFIGURATION,
            "MODULE_CONFIGURATION": MODULE_CONFIGURATION,
            "MODULE_REGISTRY": MODULE_REGISTRY,
            "STORAGE_PATH": STORAGE_PATH,
            "DEFAULT_LOG_LEVEL": DEFAULT_LOG_LEVEL,
            "SYSTEM_NAME": SYSTEM_NAME,
            "SYSTEM_ID": SYSTEM_ID,
            "BASE_STATION_ID": BASE_STATION_ID,
        }
        print("[Config] Configuración base cargada desde env.py.")

        # 2. Cargar la configuración persistente y fusionarla
        try:
            with open(self.get('STORAGE_PATH'), 'r') as f:
                persistent_config = json.load(f)
            
            for key_path, value in persistent_config.items():
                self._set_nested(key_path, value)
                self._persistent_keys.add(key_path) # Marcar esta clave como persistente
            
            print(f"[Config] {len(self._persistent_keys)} claves persistentes cargadas desde {self.get('STORAGE_PATH')}.")

        except (OSError, ValueError):
            print(f"[Config] No se encontró o no se pudo leer '{self.get('STORAGE_PATH')}'. Usando solo configuración por defecto.")
    
    def get(self, key_path, default=None):
        """Obtiene un valor de la configuración, usando una ruta como clave."""
        value = self._get_nested(key_path)
        return value if value is not None else default

    def set(self, key_path, value, persistent=False):
        """
        Establece un valor en la configuración. Si es persistente,
        actualiza el archivo storage.json. Luego, publica un evento.
        """
        print(f"[Config] Intentando setear '{key_path}' a '{value}'. Persistente: {persistent}")
        
        # 1. Actualizar el valor en memoria
        self._set_nested(key_path, value)

        # 2. Si la clave debe ser persistente, actualizar el JSON
        if persistent:
            self._persistent_keys.add(key_path) # Asegurarse de que esté en la lista
            try:
                # Leemos el archivo para no perder otras claves
                with open(self.get('STORAGE_PATH'), 'r') as f:
                    current_persistent = json.load(f)
            except (OSError, ValueError):
                current_persistent = {}
            
            current_persistent[key_path] = value
            self._save_persistent(current_persistent)
            print(f"[Config] Clave '{key_path}' actualizada en {self.get('STORAGE_PATH')}.")

        # 3. Publicar el evento para que los otros sistemas reaccionen
        event_manager.publish('config:updated', key=key_path, value=value)
        print(f"[Config] Evento 'config:updated' publicado para la clave '{key_path}'.")

    def _save_persistent(self, data):
        """Guarda un diccionario en el archivo storage.json."""
        try:
            with open(self.get('STORAGE_PATH'), 'w') as f:
                json.dump(data, f)
        except OSError as e:
            print(f"[Config] Error al guardar en storage.json: {e}")

# Instancia global única que será usada en todo el proyecto
config_manager = ConfigManager()