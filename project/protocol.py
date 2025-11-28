import struct

# --- Definiciones de Comandos de Red y Aplicación ---
# Comandos de Red (0x00 - 0x0F)
CMD_HELLO = 0x01                 # Anuncio de Vecino (Broadcast)
CMD_ROUTE_AD = 0x02              # Anuncio de Rutas (Broadcast)

# Comandos de Aplicación (0x10 - 0xFF)
CMD_PING = 0x10                  # Petición de Ping
CMD_GET_SENSOR_STATUS = 0x20     # Pedir estado de sensores (temp, presión, etc.)
CMD_SET_CONFIG = 0x30            # Setear un valor de configuración
CMD_GET_CONFIG = 0x31            # Pedir un valor de configuración
CMD_UPDATE_RTC = 0x40            # Actualizar el reloj de tiempo real
CMD_MODULE_CTRL = 0x41           # Habilitar/deshabilitar un módulo
CMD_GET_PARAM = 0x50  # <<< NUEVO: Obtener un parámetro específico
CMD_SET_PARAM = 0x51  # <<< NUEVO: Establecer un parámetro específico

# --- Definiciones de Tipos de Datos para Payloads de Parámetros ---
DTYPE_BOOL = 0x01       # Valor es 1 byte (0 o 1)
DTYPE_UINT = 0x02       # Valor es 4 bytes, unsigned int
DTYPE_SINT = 0x03       # Valor es 4 bytes, signed int
DTYPE_FLOAT = 0x04      # Valor es 4 bytes, float

# --- Definiciones del Byte de Control ---
FRAME_TYPE_CMD = 0b00000000
FRAME_TYPE_RESP = 0b01000000
FRAME_TYPE_ACK = 0b10000000
FRAME_TYPE_NACK = 0b11000000

FLAG_ACK_REQUIRED = 0b00100000

# --- Constantes de Enrutamiento ---
BROADCAST_ID = 255
INITIAL_TTL = 16 # Número máximo de saltos permitidos

def build_packet(dest_id: int, src_id: int, control: int, ttl: int, command: int, payload: bytes = b''):
    """
    Construye un paquete binario a partir de sus componentes.
    Cabecera de 5 bytes + Payload.
    """
    header = struct.pack('>BBBBB', dest_id, src_id, control, ttl, command)
    return header + payload

def parse_packet(packet: bytes):
    """
    Analiza un paquete binario y lo devuelve como un diccionario.
    Retorna None si el paquete es inválido.
    """
    if not isinstance(packet, bytes) or len(packet) < 5:
        return None  # Paquete demasiado corto o tipo incorrecto
    
    dest_id, src_id, control, ttl, command = struct.unpack('>BBBBB', packet[:5])
    payload = packet[5:]
    
    return {
        "dest_id": dest_id,
        "src_id": src_id,
        "control": control,
        "ttl": ttl,
        "command": command,
        "payload": struct.unpack('>hh',payload)
    }
