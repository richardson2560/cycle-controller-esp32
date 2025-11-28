import time

class Timer:
    """Temporizador no bloqueante con soporte para pausa, reinicio, cambio de intervalo y modo one-shot."""

    def __init__(self, one_shot=False, use_ms = False):
        self.one_shot = one_shot
        self.ultimo_tiempo = time.ticks_ms()
        self.pausado = False
        self.tiempo_pausa = 0
        self.forzar_disparo = False
        self.disparado = False
        self.use_ms = use_ms
        self.intervalo_ms = -1
    
    def start(self, intervalo):
        self.set_interval(intervalo)
        self.reset()

    def set_interval(self, intervalo):
        """Establece un nuevo intervalo."""
        if self.use_ms:
            self.intervalo_ms = intervalo if intervalo > 0 else -1
        else:
            self.intervalo_ms = int(intervalo * 1000) if intervalo > 0 else -1

    def check(self):
        """Retorna True si se ha cumplido el intervalo."""
        if self.intervalo_ms < 0 or self.pausado:
            return False

        if self.one_shot and self.disparado:
            return False

        if self.forzar_disparo:
            self.forzar_disparo = False
            if self.one_shot:
                self.disparado = True
            return True

        actual = time.ticks_ms()
        if time.ticks_diff(actual, self.ultimo_tiempo) >= self.intervalo_ms:
            self.ultimo_tiempo = actual
            if self.one_shot:
                self.disparado = True
            return True
        return False

    def pause(self):
        """Pausa el temporizador."""
        if not self.pausado:
            self.pausado = True
            self.tiempo_pausa = time.ticks_ms()

    def resume(self):
        """Reanuda el temporizador, compensando el tiempo de pausa."""
        if self.pausado:
            pausa_duracion = time.ticks_diff(time.ticks_ms(), self.tiempo_pausa)
            self.ultimo_tiempo = time.ticks_add(self.ultimo_tiempo, pausa_duracion)
            self.pausado = False

    def reset(self):
        """Reinicia el temporizador desde el tiempo actual."""
        self.ultimo_tiempo = time.ticks_ms()
        self.pausado = False
        self.forzar_disparo = False
        self.tiempo_pausa = 0
        self.disparado = False

    def trigger(self):
        """Fuerza la expiración del temporizador. El siguiente check() devolverá True."""
        self.forzar_disparo = True

    def elapsed(self):
        """Devuelve el tiempo transcurrido desde el último reinicio en ms."""
        if self.pausado:
            return time.ticks_diff(self.tiempo_pausa, self.ultimo_tiempo)
        else:
            return time.ticks_diff(time.ticks_ms(), self.ultimo_tiempo)

    def remaining(self):
        """Devuelve el tiempo restante hasta que expire el intervalo en ms.
        Retorna None si no hay intervalo activo."""
        if self.intervalo_ms < 0:
            return None
        restante = self.intervalo_ms - self.elapsed()
        return max(0, restante)

