class EventManager:
    def __init__(self):
        """Inicializa el diccionario para almacenar los suscriptores a cada tema."""
        self._subscribers = {}

    def subscribe(self, topic: str, callback):
        """Suscribe una función (callback) a un tema (topic)."""
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(callback)
        # print(f"[PubSub] Nuevo suscriptor para '{topic}': {callback}")

    def publish(self, topic: str, *args, **kwargs):
        """Publica un evento a todos los suscriptores de un tema."""
        if topic in self._subscribers:
            # print(f"[PubSub] Publicando en '{topic}' con args: {args}")
            for callback in self._subscribers[topic]:
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    print(f"Error al ejecutar callback para el tema '{topic}':")
                    import sys
                    sys.print_exception(e)

# Instancia única y global que será usada en todo el proyecto.
event_manager = EventManager()