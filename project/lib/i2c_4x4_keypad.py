from pcf8574 import PCF8574

class Keypad:
    def __init__(self, i2c, address, keymap, rows, columns):
        self._pcf8574 = PCF8574(i2c=i2c, address=address)
        self._keymap = keymap
        self.rows = rows
        self.columns = columns

    def check(self):
        return self._pcf8574.check()

    def _cols_mask(self, cols):
        # devuelve byte con las columnas en 'cols' puestas a 0, las demás en 1
        port = 0xFF
        for c in cols:
            port &= ~(1 << c)
        return port

    def _rows_mask(self):
        m = 0
        for r in self.rows:
            m |= (1 << r)
        return m

    def get_key(self):
        """
        Escanea el teclado y devuelve el carácter pulsado según keymap,
        o None si ninguna tecla está presionada.
        Uso: no bloqueante, retorna inmediatamente.
        """
        if not self.columns or not self.rows:
            return None

        rows_mask = self._rows_mask()
        cols = self.columns

        try:
            # 1) Detección rápida: baja todas las columnas, lee filas
            self._pcf8574.port = self._cols_mask(cols)   # write
            port_read = self._pcf8574.port               # read
            rows_read = port_read & rows_mask

            # Si todas las filas están en 1, no hay tecla (ninguna fila aterrizada a 0)
            if rows_read == rows_mask:
                return None

            # 2) Binary-scan sobre columnas (divide en mitades)
            half = len(cols) // 2
            left = cols[:half]
            right = cols[half:]

            # prueba mitad izquierda
            self._pcf8574.port = self._cols_mask(left)  # write
            port_read = self._pcf8574.port              # read
            rows_read = port_read & rows_mask

            if rows_read != rows_mask:
                candidate_cols = left
                candidate_rows_read = rows_read
            else:
                candidate_cols = right
                # ya sabemos que alguna columna de la mitad derecha tiene la tecla,
                # así que leemos con la mitad derecha baja
                self._pcf8574.port = self._cols_mask(right)  # write
                port_read = self._pcf8574.port                # read
                candidate_rows_read = port_read & rows_mask

            # 3) Si candidate_cols tiene más de 1 columna, distinguir entre ellas
            if len(candidate_cols) > 1:
                # prueba la primera columna del candidato
                first_col = [candidate_cols[0]]
                self._pcf8574.port = self._cols_mask(first_col)  # write
                port_read = self._pcf8574.port                    # read
                rows_read = port_read & rows_mask
                if rows_read != rows_mask:
                    chosen_col = candidate_cols[0]
                    chosen_rows_read = rows_read
                else:
                    chosen_col = candidate_cols[1]
                    # leemos filas con la otra columna baja (podemos reusar si ya leímos antes)
                    self._pcf8574.port = self._cols_mask([chosen_col])  # write
                    port_read = self._pcf8574.port                      # read
                    chosen_rows_read = port_read & rows_mask
            else:
                chosen_col = candidate_cols[0]
                chosen_rows_read = candidate_rows_read

            # 4) Determinar fila (buscar el bit de fila que esté a 0)
            row_index = None
            for idx, r in enumerate(self.rows):
                if (chosen_rows_read & (1 << r)) == 0:
                    row_index = idx
                    break

            if row_index is None:
                # situación inesperada: no se detectó fila aunque column indicaba algo
                return None

            col_index = self.columns.index(chosen_col)

            # 5) Mapear al keymap (row-major)
            cols_count = len(self.columns)
            key_pos = row_index * cols_count + col_index
            if 0 <= key_pos < len(self._keymap):
                return self._keymap[key_pos]
            return None

        finally:
            # siempre restaurar el puerto a 1s (estado inactivo)
            try:
                self._pcf8574.port = 0xFF
            except Exception:
                pass