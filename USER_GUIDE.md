# Guía de Usuario - ETTEM

**Easy Table Tennis Event Manager**

Versión 2.1.0

---

## Contenido

1. [Introducción](#introducción)
2. [Instalación y Primer Inicio](#instalación-y-primer-inicio)
3. [Activar Licencia](#activar-licencia)
4. [Panel Principal](#panel-principal)
5. [Crear una Categoría](#crear-una-categoría)
6. [Importar Jugadores](#importar-jugadores)
7. [Crear Grupos](#crear-grupos)
8. [Ingresar Resultados de Grupos](#ingresar-resultados-de-grupos)
9. [Ver Standings](#ver-standings)
10. [Generar Bracket (Llave)](#generar-bracket-llave)
11. [Ingresar Resultados de Knockout](#ingresar-resultados-de-knockout)
12. [Scheduler (Mesas y Horarios)](#scheduler-mesas-y-horarios)
13. [Centro de Impresión](#centro-de-impresión)
14. [Configuración](#configuración)
15. [Preguntas Frecuentes](#preguntas-frecuentes)

---

## Introducción

ETTEM es una aplicación para gestionar torneos de tenis de mesa con:

- **Fase de Grupos** (Round Robin): Todos contra todos dentro del grupo
- **Fase Eliminatoria** (Knockout): Llave directa hasta el campeón

La aplicación funciona **100% offline** - no necesita conexión a internet. Todos los datos se guardan localmente en tu computadora.

---

## Instalación y Primer Inicio

### Windows (Ejecutable)

1. Descarga el archivo `ETTEM.exe`
2. Colócalo en una carpeta de tu preferencia (ej: `C:\ETTEM\`)
3. Haz **doble clic** en `ETTEM.exe`
4. Tu navegador se abrirá automáticamente en `http://127.0.0.1:8000`

> **Nota:** La primera vez puede tardar unos segundos en iniciar.

### Desde Código (Desarrolladores)

```bash
# Instalar dependencias
pip install -r requirements.txt

# Iniciar panel web
python -m ettem open-panel
```

---

## Activar Licencia

La primera vez que abras ETTEM, verás la pantalla de activación.

1. Ingresa tu **clave de licencia** en el formato: `ETTEM-XXXX-MMYY-SSSSSSSS`
2. Haz clic en **Activar**
3. Si la clave es válida, accederás al panel principal

> **¿No tienes licencia?** Contacta al proveedor para adquirir una.

### Verificar Estado de Licencia

En la barra lateral izquierda verás los días restantes de tu licencia.

- **Verde:** Más de 30 días restantes
- **Amarillo/Parpadeante:** Menos de 7 días - ¡Renueva pronto!
- **Expirada:** Contacta al proveedor para renovar

---

## Panel Principal

Al ingresar verás el **Dashboard** con:

- Lista de categorías activas
- Estado de cada categoría (jugadores, grupos, fase actual)
- Accesos rápidos a las funciones principales

### Navegación

La **barra lateral izquierda** te permite acceder a:

- **Inicio:** Dashboard principal
- **Categorías:** Lista de todas las categorías
- **Scheduler:** Gestión de mesas y horarios
- **Impresión:** Centro de impresión
- **Configuración:** Idioma y tema

---

## Crear una Categoría

1. En el Dashboard, haz clic en **"Nueva Categoría"**
2. Ingresa el **nombre** usando nomenclatura ITTF:

| Código | Significado |
|--------|-------------|
| U11BS | Under 11 Boys Singles (Varones Sub-11) |
| U13GS | Under 13 Girls Singles (Damas Sub-13) |
| U15BS | Under 15 Boys Singles (Varones Sub-15) |
| MS | Men's Singles (Varones Mayores) |
| WS | Women's Singles (Damas Mayores) |

3. Haz clic en **Crear**

> **Tip:** Usa nombres descriptivos como `U15BS`, `MS`, `WS` para facilitar la organización.

---

## Importar Jugadores

### Opción 1: Desde archivo CSV

1. Ve a la categoría deseada
2. Haz clic en **"Importar Jugadores"**
3. Selecciona tu archivo CSV
4. Revisa la vista previa
5. Haz clic en **Importar**

#### Formato del CSV

Tu archivo CSV debe tener estas columnas:

| Columna | Descripción | Ejemplo |
|---------|-------------|---------|
| `id` | Identificador único | 1, 2, 3... |
| `nombre` | Nombre del jugador | Juan |
| `apellido` | Apellido | Pérez |
| `genero` | M o F | M |
| `pais_cd` | Código ISO-3 del país | ESP, MEX, ARG |
| `ranking_pts` | Puntos de ranking (0 si no tiene) | 1200 |
| `categoria` | Categoría | U15BS |

**Ejemplo de archivo CSV:**
```csv
id,nombre,apellido,genero,pais_cd,ranking_pts,categoria
1,Juan,Pérez,M,ESP,1200,U15BS
2,María,García,F,ESP,1150,U15GS
3,Pedro,López,M,MEX,0,U15BS
```

### Opción 2: Agregar manualmente

1. Ve a la categoría deseada
2. Haz clic en **"Agregar Jugador"**
3. Completa el formulario
4. Haz clic en **Guardar**

> **Nota:** Los jugadores con `ranking_pts=0` se consideran "sin ranking" y se ordenan después de los jugadores rankeados.

---

## Crear Grupos

Una vez que tengas jugadores importados:

1. Ve a la categoría
2. Haz clic en **"Crear Grupos"**
3. Configura:
   - **Tamaño preferido de grupo:** 3 o 4 jugadores
   - **Jugadores que avanzan:** 1 o 2 por grupo
4. Revisa la **vista previa** con el seeding snake
5. Opcionalmente, arrastra jugadores para ajustar grupos manualmente
6. Haz clic en **Crear Grupos**

### Snake Seeding

Los jugadores se distribuyen en forma de "serpiente" según su ranking:

```
Grupo A: Seed 1, Seed 4, Seed 5, Seed 8
Grupo B: Seed 2, Seed 3, Seed 6, Seed 7
```

Esto asegura grupos balanceados.

---

## Ingresar Resultados de Grupos

1. Ve a la categoría → pestaña **Grupos**
2. Selecciona un grupo
3. Haz clic en un partido pendiente
4. Ingresa los sets:
   - Cada set tiene formato `XX-YY` (ej: `11-9`, `12-10`)
   - El sistema valida automáticamente las reglas ITTF
5. Haz clic en **Guardar Resultado**

### Reglas de Validación

- Un set se gana a 11 puntos
- Debe haber diferencia de 2 puntos
- En deuce (10-10), el ganador debe tener exactamente +2 (12-10, 13-11, etc.)
- Best of 3: Primero en ganar 2 sets
- Best of 5: Primero en ganar 3 sets
- Best of 7: Primero en ganar 4 sets

### Walkover (W.O.)

Si un jugador no se presenta:

1. Haz clic en el partido
2. Selecciona **Walkover**
3. Indica el **ganador**
4. El perdedor recibe 0 puntos de torneo

---

## Ver Standings

Los standings se calculan automáticamente:

1. Ve a la categoría → pestaña **Standings**
2. Verás la clasificación de cada grupo

### Sistema de Puntos

| Resultado | Puntos |
|-----------|--------|
| Victoria | 2 |
| Derrota (jugada) | 1 |
| Derrota por W.O. | 0 |

### Desempates

Cuando hay empate en puntos, se aplica (solo entre los empatados):

1. **Ratio de sets:** sets ganados / sets perdidos
2. **Ratio de puntos:** puntos ganados / puntos perdidos
3. **Seed:** el mejor seed gana el desempate

---

## Generar Bracket (Llave)

Cuando todos los partidos de grupos estén completos:

1. Ve a la categoría → pestaña **Bracket**
2. Elige el modo:

### Modo Automático

- Genera el bracket siguiendo reglas ITTF
- G1 (mejor 1° lugar) va arriba
- G2 (segundo mejor 1°) va abajo
- Los 2° lugares van en la mitad opuesta a su grupo
- Los BYEs se colocan según posiciones ITTF oficiales

### Modo Manual (Drag & Drop)

- Arrastra jugadores a los slots deseados
- El sistema valida:
  - No pueden estar en la misma mitad jugadores del mismo grupo
  - Advertencias visuales si hay compatriotas en primera ronda

---

## Ingresar Resultados de Knockout

1. Ve a la categoría → pestaña **Bracket**
2. Haz clic en un partido de la llave
3. Ingresa los sets (igual que en grupos)
4. El ganador avanza automáticamente a la siguiente ronda

> **Tip:** Puedes configurar diferente formato para grupos y knockout (ej: Bo3 en grupos, Bo5 en bracket).

---

## Scheduler (Mesas y Horarios)

El scheduler te permite organizar partidos por mesa y hora.

### Configurar Mesas

1. Ve a **Scheduler** → **Configuración**
2. Indica cuántas mesas tienes disponibles
3. Nombra cada mesa (ej: Mesa 1, Mesa 2...)

### Crear Sesión

1. Ve a **Scheduler** → **Nueva Sesión**
2. Configura:
   - **Nombre:** ej. "Mañana", "Tarde", "Día 1"
   - **Hora de inicio**
   - **Duración de cada slot** (ej: 20 minutos)
   - **Cantidad de slots**
3. Haz clic en **Crear**

### Asignar Partidos

1. Ve a la sesión creada
2. Verás una **grilla** con mesas (columnas) y horarios (filas)
3. Haz clic en una celda vacía
4. Selecciona el partido a asignar
5. El partido aparecerá en la grilla

### Finalizar Sesión

Cuando termines una sesión:

1. Haz clic en **Finalizar Sesión**
2. Los partidos asignados quedan bloqueados
3. Puedes **Reabrir** si necesitas hacer cambios

---

## Centro de Impresión

Accede desde **Impresión** en la barra lateral.

### Documentos Disponibles

| Documento | Descripción |
|-----------|-------------|
| **Hoja de Partido** | Para que el árbitro anote el resultado |
| **Hoja de Grupo** | Matriz de resultados del grupo |
| **Llave (Bracket)** | Visualización del bracket eliminatorio |
| **Grilla de Scheduler** | Asignaciones de mesas y horarios |

### Cómo Imprimir

1. Selecciona el tipo de documento
2. Elige la categoría y/o grupo
3. Haz clic en **Vista Previa**
4. En la vista previa, usa **Ctrl+P** (o Cmd+P en Mac) para imprimir
5. Opcionalmente, descarga como PDF

> **Tip:** Usa "Guardar como PDF" en el diálogo de impresión para crear archivos PDF.

---

## Configuración

### Cambiar Idioma

1. Ve a **Configuración**
2. Selecciona **Español** o **English**
3. La interfaz se actualiza inmediatamente

### Cambiar Tema

1. Ve a **Configuración**
2. Selecciona **Claro** u **Oscuro**

> **Tip:** El tema oscuro es ideal para usar de noche o en ambientes con poca luz.

---

## Preguntas Frecuentes

### ¿Dónde se guardan mis datos?

En la carpeta `.ettem/` junto al ejecutable (o en tu directorio de usuario). Contiene:
- `ettem.sqlite` - Base de datos con todos los torneos
- `license.key` - Tu clave de licencia

### ¿Puedo hacer backup de mis datos?

Sí, simplemente copia la carpeta `.ettem/` a otro lugar seguro.

### ¿Puedo usar la misma licencia en otra computadora?

Sí, puedes ingresar la misma clave en otra computadora. Sin embargo, los datos de torneo no se sincronizan automáticamente.

### ¿Qué pasa si mi licencia expira durante un torneo?

Podrás ver los datos existentes pero no podrás ingresar nuevos resultados hasta renovar.

### ¿Cómo cambio un resultado ya ingresado?

1. Ve al partido en cuestión
2. Haz clic en **Editar Resultado**
3. Modifica los sets
4. Guarda los cambios

> **Nota:** Si el partido de bracket ya avanzó, es posible que necesites ajustar resultados posteriores.

### ¿Puedo eliminar una categoría?

Sí, pero se eliminarán todos los jugadores, grupos, partidos y resultados de esa categoría. Esta acción no se puede deshacer.

### El programa no abre / se cierra inmediatamente

- Verifica que tienes una licencia válida
- Intenta ejecutar desde línea de comandos para ver errores:
  ```cmd
  ETTEM.exe --help
  ```
- Contacta soporte si el problema persiste

### ¿Cómo actualizo a una nueva versión?

1. Descarga el nuevo `ETTEM.exe`
2. Reemplaza el archivo anterior
3. Tus datos se conservan (están en `.ettem/`)

---

## Soporte

¿Tienes preguntas o problemas?

- Revisa esta guía
- Contacta al proveedor de tu licencia

---

*ETTEM v2.1.0 - Easy Table Tennis Event Manager*
