# Próximos pasos para ETTEM V1.1

## ✅ Completado (Sesión actual)
- [x] Creación automática de matches de bracket
- [x] Avance automático de ganadores entre rondas
- [x] Manejo de BYEs (avance automático sin match)
- [x] Navegación UI completa entre vistas de bracket
- [x] Ingreso/edición/eliminación de resultados de bracket
- [x] Indicador visual "✓ BYE" para jugadores que avanzaron automáticamente
- [x] Ruta `/admin/regenerate-matches` para regenerar matches de brackets existentes

## 🔴 Prioridad ALTA (Crítico para V1.1)

### 1. ✅ Deshacer avances de bracket (COMPLETADO - 2025-12-18)
**Problema:** Si eliminas un resultado de bracket, el jugador ya avanzado a la siguiente ronda NO se elimina automáticamente.

**Solución implementada:**
- Agregada función `rollback_bracket_advancement(match_orm, winner_id, category, session)` en app.py:2193
- Modificada ruta `POST /match/{match_id}/delete-result`:
  - Detecta si es match de bracket (group_id == None)
  - Verifica si el ganador ya jugó en la siguiente ronda (error si es así)
  - Limpia el slot de la siguiente ronda (player_id = None)
  - Actualiza el match de la siguiente ronda para quitar al jugador
  - Redirige correctamente a la página del bracket

**Validaciones:**
- Si el ganador ya jugó en la siguiente ronda, muestra error y pide eliminar primero ese resultado
- Esto previene estados inconsistentes en el bracket

---

### 2. ✅ Vista del campeón (COMPLETADO - 2025-12-18)
**Problema:** No hay una vista clara que muestre quién ganó el torneo cuando se completa la final.

**Ya implementado previamente:**
- `bracket.html`: Banner "¡Torneo Finalizado!" con link a resultados + badge 👑 en campeón
- `results.html`: Vista completa de resultados finales con podio (1°, 2°, 3°/4°)
- `category.html`: Botón "🏆 Resultados Finales" en topbar

**Agregado en esta sesión:**
- `view_bracket_matches` (app.py:981-989): Detecta campeón y lo pasa al template
- `bracket_matches.html`: Banner de campeón con "Ver Podio Completo →"
- `bracket_matches.html`: Botón "🏆 Resultados" en topbar

---

### 3. ✅ Validación de orden de matches (COMPLETADO - 2025-12-28)
**Problema:** Técnicamente se puede ingresar resultado de semifinal antes de que terminen los cuartos.

**Solución implementada:**
- Validación en `enter_result_form` (GET) y `save_result` (POST)
- Si un jugador es TBD, redirige con mensaje de error
- Ubicación: `app.py:428-445` y `app.py:486-493`

---

## 🟡 Prioridad MEDIA (Importante pero no bloqueante)

### 4. ✅ Exportación de bracket/standings a CSV (COMPLETADO - 2025-12-28)
**Problema:** Ya existe exportación de grupos/standings pero no de bracket.

**Solución implementada:**
- Ruta `/export/bracket/{category}` - Descarga CSV del bracket
- Ruta `/export/standings/{category}` - Descarga CSV de standings
- Ambas con BOM para compatibilidad con Excel (acentos)
- Botones agregados en Centro de Impresión

---

### 5. Resetear bracket
**Problema:** Si hay errores, no hay forma fácil de limpiar todos los resultados del bracket.

**Solución propuesta:**
- Agregar botón en admin: "Resetear resultados de bracket"
- Elimina todos los resultados de matches de bracket (pero mantiene los slots)
- Útil para testing o si se ingresaron resultados incorrectos

**Archivos a modificar:**
- `src/ettem/webapp/app.py` - Nueva ruta `POST /admin/reset-bracket/{category}`
- `src/ettem/webapp/templates/admin_generate_bracket.html` - Botón de reset

---

### 6. ✅ Vista consolidada del torneo (COMPLETADO - 2025-12-28)
**Problema:** No hay una vista que muestre el estado general del torneo.

**Solución implementada:**
- Ruta `/tournament-status` con estado de cada categoría
- Muestra: grupos, standings, bracket por rondas, campeón
- Botones contextuales: "Calcular Standings" y "Generar Bracket"
- Link en sidebar: "Estado General"
- Sidebar reorganizado con sección "Gestión del Torneo"

---

## 🟢 Prioridad BAJA (Nice-to-have)

### 7. Estadísticas del torneo
- Total de partidos jugados
- Promedio de puntos por set
- Jugador con más victorias
- Walkover count

### 8. Vista para impresión
- CSS optimizado para imprimir bracket
- Ocultar botones de navegación
- Formato landscape

### 9. Partido por 3er puesto
- Match de consolación entre perdedores de semifinales
- Requiere agregar nueva ronda "Third Place" al modelo

---

## 📝 Notas técnicas

### Schema de DB actualizado
Se agregó columna `advanced_by_bye` a `bracket_slots`:
```sql
ALTER TABLE bracket_slots ADD COLUMN advanced_by_bye BOOLEAN DEFAULT 0;
```

### Funciones principales agregadas
1. `process_bye_advancements(category, bracket_repo, session)` - app.py:1813
2. `create_bracket_matches(category, bracket_repo, match_repo)` - app.py:1719
3. `advance_bracket_winner(match_orm, winner_id, category, session)` - app.py:1585

### Archivos modificados en esta sesión
- `src/ettem/storage.py` - Agregada columna `advanced_by_bye`
- `src/ettem/webapp/app.py` - Múltiples funciones nuevas y rutas
- `src/ettem/webapp/templates/bracket.html` - Badge visual "✓ BYE"
- `src/ettem/webapp/templates/bracket_matches.html` - Nueva template
- `src/ettem/webapp/templates/category.html` - Navegación a bracket

---

## Orden sugerido de implementación (próxima sesión)

1. **Deshacer avances de bracket** (1-2 horas) - Crítico para testing
2. **Vista del campeón** (30 min) - Visualmente importante
3. **Validación de orden** (30 min) - Previene errores de usuario
4. **Exportación CSV** (1 hora) - Funcionalidad útil
5. **Vista consolidada** (1-2 horas) - Gran UX improvement

Total estimado: 4-6 horas de desarrollo

---

## 📅 Notas para V2.0 (Scheduler)

### Filtros en Lista de Partidos
Cuando se implemente el sistema de horarios, agregar filtros a la lista de partidos:
- Filtro por día/fecha
- Filtro por mesa
- Filtro por hora/rango horario

Esto permitirá imprimir solo los partidos de un día específico o de ciertas mesas.

---

## 🐛 Bugs Conocidos

### ✅ CLI import-players no asocia tournament_id (CORREGIDO - 2025-12-28)
**Problema:** Al importar jugadores con `ettem import-players`, no se asociaba el `tournament_id` del torneo actual.

**Solución implementada:**
- CLI ahora obtiene el torneo actual automáticamente
- Asigna `tournament_id` a jugadores y grupos
- Muestra mensaje: `[TOURNAMENT] Using current tournament: X`
- Advertencia si no hay torneo configurado

---

## 📅 Notas para V2.0

### Sistema de Registro de Jugadores
**Visión:** Base de datos maestra de jugadores con ID único global.

**Características propuestas:**
- Registro universal de jugadores (nombre, apellido, fecha nacimiento, género, nacionalidad)
- ID único por jugador (no duplicados entre categorías/torneos)
- Inscripciones como entidad separada (jugador → torneo → categoría)
- Historial de participaciones por jugador
- Campo "País/Región" configurable por torneo (puede ser país, departamento, club, etc.)

**Modelo de datos propuesto:**
```
Jugadores (registro maestro)
    └── Inscripciones (jugador + torneo + categoría)
            └── Grupos, Partidos, Resultados
```

### Scheduler / Programación de Horarios
- Asignación de mesas y horarios
- Filtros en lista de partidos por día/mesa/hora
- Vista de programación por mesa
- Control de tiempos entre partidos del mismo jugador
