# Mejoras de UX Detectadas en Testing

## Issues Encontrados Durante Testing End-to-End (2025-11-02)

### 1. Importar Jugadores - Falta Confirmación Previa
**Problema:**
- Al subir CSV, los jugadores se importan DIRECTAMENTE a la base de datos
- No hay preview ni confirmación antes de guardar
- Usuario no puede revisar datos antes de confirmar

**Mejora Sugerida:**
1. Mostrar preview de jugadores a importar con tabla
2. Botón "Confirmar Importación" para guardar a DB
3. Botón "Cancelar" para descartar
4. Permitir editar datos en preview antes de confirmar

**Prioridad:** Media (funciona, pero confuso)

---

### 2. Vista de Categoría - Navegación Poco Clara
**Problema:**
- Desde dashboard principal → "Ver Categoría" → Llega a vista de categoría
- En vista de categoría solo muestra label "U13" pero sin acciones claras
- No hay botón obvio para "Crear Grupos" en esa vista
- Usuario tiene que ir a sidebar → "Admin" → "Crear Grupos"

**Mejora Sugerida:**
- Agregar botones de acción rápida en vista de categoría:
  - "Crear Grupos" (si no existen grupos)
  - "Ver Grupos" (si ya existen)
  - "Calcular Standings"
  - "Generar Bracket"
- Mostrar estado del torneo: "Sin grupos" / "Grupos creados" / "Bracket generado"

**Prioridad:** Alta (navegación confusa)

---

### 3. Crear Grupos - Opción de Automatización al Inicio
**Problema:**
- Actualmente SIEMPRE muestra preview con drag-and-drop
- Para torneos automáticos, esto es innecesario
- Usuario debe decidir upfront si quiere control manual o automático

**Mejora Sugerida:**
1. Al inicio de "Crear Grupos", preguntar:
   - ⚡ **Automático:** Snake seeding estándar, sin preview
   - 🎯 **Manual:** Preview con drag-and-drop para ajustes

2. Si elige Automático:
   - Configurar tamaño preferido (3 o 4)
   - Click "Crear" → Grupos creados directamente
   - Muestra resumen de grupos creados

3. Si elige Manual:
   - Flujo actual con preview y drag-and-drop

**Prioridad:** Media (mejora eficiencia para caso común)

---

### 4. Navegación General - Breadcrumbs Faltantes
**Problema:**
- No hay breadcrumbs para saber dónde estás
- Difícil volver atrás sin usar sidebar

**Mejora Sugerida:**
- Agregar breadcrumbs en topbar:
  - Inicio > Admin > Importar Jugadores
  - Inicio > U13 > Grupos > Grupo A
  - Inicio > U13 > Bracket

**Prioridad:** Baja (nice to have)

---

### 5. Estado del Torneo - Indicador Visual
**Problema:**
- No se ve claramente en qué etapa está el torneo
- Usuario no sabe qué hacer a continuación

**Mejora Sugerida:**
- Agregar "Stepper" o indicador de progreso:
  ```
  [✓] Jugadores → [✓] Grupos → [⏳] Resultados → [ ] Bracket → [ ] Final
  ```
- Mostrar en dashboard y vista de categoría
- Resaltar siguiente paso recomendado

**Prioridad:** Media (mejora onboarding)

---

### 6. Ingresar Resultados - Instrucciones No Pegables
**Problema:**
- Las instrucciones sobre cómo ingresar sets están en texto estático
- Usuario no puede copiar/pegar fácilmente
- Al ingresar 48 partidos, es repetitivo leer las instrucciones cada vez

**Mejora Sugerida:**
1. Hacer instrucciones colapsables (collapsed por defecto después del primer uso)
2. Agregar ejemplos pegables:
   - "Victoria 3-0: 11-9, 11-7, 11-5"
   - "Victoria 3-1: 11-8, 9-11, 11-6, 11-4"
   - "Victoria 3-2: 11-9, 9-11, 11-8, 8-11, 11-7"
3. Considerar **Quick Entry Mode:**
   - Solo pedir ganador + score de sets (ej: "Jugador 1 - 3-0")
   - Auto-generar sets default (11-9, 11-8, 11-7)
   - Opción "Detalles" para ingresar sets manualmente

**Prioridad:** Alta (ingresar 48 partidos es tedioso sin esto)

---

### 7. Bracket Manual Drag-and-Drop - Jugadores No Se Eliminan de Lista
**Problema:**
- Al arrastrar un jugador de la lista lateral al bracket, el jugador NO desaparece de la lista
- Usuario puede arrastrar el mismo jugador múltiples veces
- No es intuitivo - debería desaparecer de la lista al ser usado
- Dificulta saber qué jugadores ya fueron asignados

**Mejora Sugerida:**
1. Al arrastrar jugador de lista → slot:
   - Ocultar/eliminar jugador de la lista lateral
   - Marcar visualmente como "usado"
2. Al eliminar jugador de un slot:
   - Devolver jugador a la lista lateral
   - Ordenar por grupo original
3. Contador visual: "X de Y jugadores asignados"
4. Validación: Deshabilitar botón "Crear Bracket" hasta que todos los slots tengan jugador

**Prioridad:** Media (mejora usabilidad del bracket manual)

---

### 8. Formulario de Resultados - Input de Puntos Sin Límite
**Problema:**
- Los campos de puntos de cada set permiten ingresar más de 2 dígitos
- Usuario podría ingresar "111" en lugar de "11" por error
- No hay validación de longitud máxima en el input

**Mejora Sugerida:**
1. Agregar `maxlength="2"` a los inputs de puntos
2. Validación JavaScript para:
   - Solo permitir números
   - Máximo 2 dígitos
   - Opcional: Auto-focus al siguiente campo al llegar a 2 dígitos
3. Validación backend ya existe (11 puntos mínimo para ganar)

**Prioridad:** Baja (validación backend ya previene errores)

---

## Resumen de Prioridades

### Alta Prioridad (V1.2)
- [ ] Vista de categoría con botones de acción claros
- [ ] Navegación mejorada entre secciones
- [ ] Quick Entry Mode para resultados (ganador + score, sin detalles de sets)

### Media Prioridad (V1.2-V1.3)
- [ ] Preview de importación con confirmación
- [ ] Opción de creación automática vs manual de grupos
- [ ] Indicador de progreso del torneo

### Baja Prioridad (V1.3+)
- [ ] Breadcrumbs de navegación
- [ ] Tooltips y ayuda contextual

---

---

## 🐛 BUGS Detectados

### BUG #1: Desempate de 2 Jugadores No Usa Head-to-Head
**Problema:**
- En `standings.py` líneas 226-234
- Para 2 jugadores empatados en puntos, usa stats generales del grupo
- **NO usa resultado directo** entre los dos jugadores empatados
- Esto viola reglas ITTF

**Reglas Correctas (ITTF):**
Para 2 jugadores empatados:
1. **Resultado directo** (head-to-head) - quien ganó ese partido
2. Si no se enfrentaron (imposible en round robin): Sets ratio entre ellos
3. Si persiste: Points ratio entre ellos
4. Si persiste: Seed

**Código Actual (INCORRECTO):**
```python
elif len(group) == 2:
    # For 2-way ties, use overall stats (not head-to-head)  ← WRONG
    def sort_key_2way(s: GroupStanding):
        player = player_repo.get_by_id(s.player_id)
        seed = player.seed if player and player.seed else 999
        return (-s.sets_ratio, -s.points_ratio, seed)
    sorted_group = sorted(group, key=sort_key_2way)
```

**Fix Requerido:**
- Aplicar mismo algoritmo de `break_ties()` para 2 jugadores
- O simplificar: si hay 1 partido entre ellos → ganador queda arriba
- Si no hay partido (caso edge): aplicar ratios head-to-head

**Prioridad:** CRÍTICA (afecta clasificación correcta)

---

### BUG #2: Validación de Sets No Rechaza 4-0, 4-1, etc.
**Problema:**
- El formulario de ingreso de resultados permite ingresar 4-0, 4-1, 5-0, etc.
- En tenis de mesa (mejor de 5), el máximo es 3-0, 3-1, 3-2
- La validación en `validation.py` líneas 107-132 SÍ existe y es correcta
- Pero no se está ejecutando o rechazando correctamente en el endpoint

**Validación Esperada (ya existe en código):**
- Máximo 5 sets totales
- Mínimo 3 sets (para tener ganador)
- Uno de los jugadores debe tener exactamente 3 sets ganados
- No puede haber sets después de que alguien ganó 3

**Fix Requerido:**
- Verificar que el endpoint `/match/{id}/save-result` llame a `validate_match_sets()`
- Asegurar que el error se muestre al usuario como toast (no redirect)
- Agregar validación JavaScript en frontend para feedback inmediato

**Prioridad:** ALTA (permite resultados inválidos)

---

### BUG #3: Bracket Solo Genera Primera Ronda - Faltan QF/SF/F
**Problema:**
- Al generar bracket de 16 jugadores, solo se crean 8 partidos (R16/Octavos)
- NO se crean los partidos de QF (Cuartos), SF (Semis), ni F (Final)
- El código en líneas 400-426 intenta avanzar ganadores a `next_match_id`
- Pero esos partidos siguientes NO EXISTEN en la base de datos

**Comportamiento Actual:**
- Se generan 8 partidos de R16
- Al completar un partido, se intenta avanzar ganador a `next_match_id`
- Pero `next_match_id` apunta a un partido que no existe → Error silencioso

**Comportamiento Esperado:**
- Generar TODOS los partidos del bracket desde el inicio:
  - R16: 8 partidos (con jugadores asignados)
  - QF: 4 partidos (slots vacíos, se llenan al completar R16)
  - SF: 2 partidos (slots vacíos)
  - F: 1 partido (slots vacíos)
- Total: 15 partidos creados desde el inicio
- Los campos `next_match_id` y `next_match_slot` apuntan a partidos reales

**Fix Requerido:**
- Modificar generación de bracket para crear TODA la estructura desde el inicio
- Crear partidos vacíos (con player1_id=None, player2_id=None) para rondas futuras
- Asignar correctamente `next_match_id` y `next_match_slot` para cada partido

**Prioridad:** CRÍTICA (MVP no funciona sin esto - no se puede completar torneo)

---

## Notas del Testing
- Los grupos SÍ se crean correctamente desde el preview
- El drag-and-drop funciona bien
- Snake seeding se aplica correctamente
- La funcionalidad core está bien, solo falta pulir la navegación
- **BUG CRÍTICO:** Desempate de 2 jugadores no funciona correctamente
