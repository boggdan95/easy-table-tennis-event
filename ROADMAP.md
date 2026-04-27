# ETTEM - Roadmap de Desarrollo

> Última actualización: 2026-04-26
> Versión actual: 2.8.0

---

## Filosofía de Desarrollo

Priorizar funcionalidades que:
1. **Resuelvan dolores reales** del organizador durante el torneo
2. **Mejoren la experiencia** de jugadores y espectadores
3. **Reduzcan trabajo manual** y errores humanos
4. **Funcionen offline** (internet no siempre es confiable en gimnasios)

---

## V2.2 - Pantalla Pública + Marcador de Árbitro (Completada - 2026-02-06)

**Objetivo:** Sistema completo de resultados en tiempo real

```
ÁRBITRO (celular)              SERVIDOR                 PANTALLA PÚBLICA (TV)
┌──────────────┐              ┌──────────┐              ┌──────────────┐
│ Punto x punto│  ──sync──►   │ Guarda   │  ──poll──►   │ Muestra      │
│ 9-7 → 10-7   │  al acabar   │ set por  │  cada 5s     │ score en     │
│ → 11-7 ✓     │  cada set    │ set      │              │ vivo         │
└──────────────┘              └──────────┘              └──────────────┘
```

### 2.2.1 - Marcador de Árbitro (`/mesa/{numero}`)

**Vista móvil para árbitros - reemplaza el marcador físico**

- [x] URL simple por mesa: `/mesa/1`, `/mesa/2`, etc.
- [x] Código QR en cada mesa física (imprimible)
- [x] Sin login complejo (PIN simple por sesión o solo acceso por QR)
- [x] Solo muestra partidos asignados a esa mesa

**Control de acceso por mesa:**
- [x] Una mesa = un dispositivo activo a la vez
- [x] Al abrir mesa → se bloquea para otros
- [x] Si alguien intenta abrir mesa en uso → mensaje "Mesa ocupada"
- [x] Timeout automático por inactividad (configurable, ej: 10 min)
- [x] Admin puede forzar desbloqueo desde panel si es necesario
- [x] Indicador visual en admin de qué mesas están activas

**Dos modos de operación (configurable por mesa):**

```
MODO PUNTO POR PUNTO              MODO RESULTADO POR SET
┌──────────────────┐              ┌──────────────────┐
│  JUAN    PEDRO   │              │  Set 1:          │
│  [ 9 ]   [ 7 ]   │              │  [11] - [ 9]     │
│                  │              │                  │
│  [+1]     [+1]   │              │  Set 2:          │
│                  │              │  [11] - [ 7]     │
│  Auto al llegar  │              │                  │
│  a 11 (o deuce)  │              │  [GUARDAR SET]   │
└──────────────────┘              └──────────────────┘
   Para mesas con                    Para árbitros que
   árbitro dedicado                  prefieren método
   o finales                         tradicional
```

**Modo Punto por Punto:**
- [x] Botones grandes +1 para cada jugador
- [x] Score del set actual en tiempo real
- [x] Detecta automáticamente fin de set (11 pts o deuce +2)
- [x] Botón "Deshacer" último punto
- [x] Sync automático al terminar set

**Modo Resultado por Set:**
- [x] Árbitro ingresa score final del set (ej: 11-9)
- [x] Validación de reglas ITTF
- [x] Más rápido si árbitro usa marcador físico
- [x] Sync al guardar cada set

**Configuración de Mesas (nuevo tab o sección):**
- [x] Separado del Scheduler (config fija vs asignaciones del día)
- [x] Por cada mesa:
  - Nombre/número
  - Modo de árbitro (punto por punto / resultado por set)
  - Generar/imprimir código QR
  - Estado (activa/inactiva)
- [x] Default global para nuevas mesas
- [x] Puede modificarse durante el torneo

**Funciones comunes (ambos modos):**
- [x] Funciona offline (no requiere conexión constante)
- [x] Si no hay conexión → guarda local y reintenta
- [x] Indicador visual de estado de conexión
- [x] Historial de sets jugados
- [x] Opción de walkover
- [x] Ver siguiente partido de la mesa

### 2.2.2 - Pantalla Pública (`/display`)

**Display para TV/monitor - espectadores y jugadores**

- [x] Ruta `/display` optimizada para TV (fullscreen, auto-refresh)
- [x] Diseño grande y legible (visible desde 5+ metros)
- [x] Tema oscuro por defecto (mejor contraste)
- [x] Modo kiosko (sin controles de navegación)

**Vistas con rotación automática:**
- [x] **Partidos en curso:** Mesa, jugadores, score actual (ej: "Mesa 1: Juan 2-1 Pedro")
- [x] **Resultados recientes:** Últimos 5-10 partidos terminados
- [x] **Llamado a mesa:** Próximos partidos programados
- [x] Rotación automática cada 5 segundos

**Estados de partido:**
- [x] "En juego" → mostrando score en vivo
- [x] "Finalizado" → resultado final
- [ ] "Prepararse" → jugadores deben acercarse (futuro)
- [ ] "A mesa" → partido por comenzar (futuro)

### 2.2.3 - Llamado a Mesa (Pendiente - mover a V2.4+)

- [ ] Lista de próximos partidos ordenada por prioridad
- [ ] Countdown visual ("Partido en 5 minutos")
- [ ] Alerta visual si jugador no se presenta (parpadeo rojo)
- [ ] Sonido opcional de llamado (configurable, para usar con parlantes)

### 2.2.4 - Vista de Mesa Individual (Pendiente - mover a V2.4+)

**Para pantalla/tablet en cada mesa física**

- [ ] Ruta `/display/mesa/1` - solo muestra esa mesa
- [ ] Score grande del partido actual
- [ ] Ideal para segunda pantalla junto al árbitro

### Consideraciones Técnicas (Implementado)

**Arquitectura:**
- Polling cada 5 segundos (simple, sin websockets)
- LocalStorage para persistencia offline del árbitro
- Validación de session token en live-score API
- Filtro por torneo activo en display

**Compatibilidad:**
- Árbitro: cualquier celular con navegador moderno (probado)
- Display: Chrome/Edge en modo kiosko F11 (probado)
- Responsive para TV 1080p y 4K

---

## V2.3 - Validación Online de Licencias (Completada - 2026-02-08)

**Objetivo:** Control de licencias por máquina con validación online periódica

```
DESKTOP APP                    SERVIDOR (Bluehost)           ADMIN PANEL
┌──────────────┐              ┌──────────────────┐          ┌──────────────┐
│ Activar      │  ──POST──►   │ Registra         │          │ Ver licencias│
│ licencia     │              │ máquina          │  ◄────   │ Gestionar    │
│              │  ◄──JSON──   │ (máx 2 slots)    │          │ máquinas     │
│ Validar      │  cada 30d    │                  │          │ Ver logs     │
│ periódico    │  ──POST──►   │ Verificar        │          └──────────────┘
└──────────────┘              └──────────────────┘
```

### 2.3.1 - API de Licencias (Servidor PHP + MySQL)
- [x] `POST /api/activate` — Registrar máquina al activar licencia
- [x] `POST /api/validate` — Validación periódica cada 30 días
- [x] `POST /api/deactivate` — Liberar slot de máquina
- [x] Límite de 2 máquinas simultáneas por licencia
- [x] HMAC re-verificación en servidor
- [x] Rate limiting (20 req/min por IP)
- [x] API key auth + HTTPS

### 2.3.2 - Cliente Python
- [x] `machine_id.py` — ID único de hardware (Windows + macOS)
- [x] `license_online.py` — Cliente HTTP (urllib.request, sin dependencias)
- [x] Validación online cada 30 días con gracia de 30 días adicionales
- [x] Backwards compatible: sin `.meta` = modo offline puro
- [x] Fallback: errores online NUNCA rompen el flujo offline

### 2.3.3 - Panel Admin (`ettem.boggdan.com/admin/`)
- [x] Dashboard con lista de licencias y estadísticas
- [x] Detalle por licencia: máquinas registradas, logs de validación
- [x] Activar/desactivar licencias y máquinas remotamente
- [x] Historial de validaciones filtrable con paginación
- [x] Auth con cookie firmada HMAC (compatible Bluehost)

### 2.3.4 - Gestor Local de Licencias
- [x] GUI con tkinter: generar licencias con nombre/email del cliente
- [x] Auto-guardado en Excel (`tools/licencias.xlsx`)
- [x] Tabla de licencias generadas con estado (activa/expirada)
- [x] CLI con `--name`, `--email`, `--list` flags
- [x] Auto-copy al clipboard

### 2.3.5 - Indicadores en UI
- [x] Status online en sidebar (checkmark verde / warning amarillo)
- [x] Slot de máquina visible (ej: "1/2")
- [x] Error de límite de máquinas con lista de dispositivos registrados
- [x] Opción de desactivar máquina online

---

## V2.4 - KO Directo, Equipos y Grupo de 5 (Completada - 2026-02-18)

**Objetivo:** Ampliar formatos de competencia más allá de singles con fase de grupos

### 2.4.1 - KO Directo (Sin fase de grupos)
- [x] Bracket directo sin necesidad de fase de grupos
- [x] Importar jugadores e ir directamente a bracket eliminatorio
- [x] Seeding automático basado en ranking

### 2.4.2 - Torneos por Equipos
- [x] Tres sistemas de match: Swaythling (5S), Corbillon (4S+1D), Olympic (1D+4S)
- [x] Encuentro por equipos contiene partidos individuales (TeamMatchDetailORM)
- [x] Prevención de duplicados en asignación de jugadores
- [x] Homologación de resultados de equipo
- [x] Referencia de orden de partidos en UI
- [x] Sistema de match seleccionable al importar equipos

### 2.4.3 - Grupos de 5 Jugadores
- [x] Soporte para grupos de tamaño 5
- [x] Orden de partidos usando tabla de Berger
- [x] 10 partidos por grupo (todos contra todos)

### 2.4.4 - CI/CD y Distribución
- [x] GitHub Actions workflow para builds automáticos
- [x] Windows (.exe) + macOS (.dmg) en paralelo
- [x] Release automático con `softprops/action-gh-release@v2`
- [x] DMG con layout drag-to-Applications (`create-dmg`)

---

## V2.5 - Mejoras de UI, macOS e ITTF (Completada - 2026-02-20)

**Objetivo:** Pulir la experiencia visual y corregir bugs

### 2.5.0 - macOS y UX
- [x] Ícono de paleta de tenis de mesa para .app y .exe
- [x] Fix de carga de app en macOS (rutas de recursos)
- [x] Esperar servidor listo antes de abrir navegador

### 2.5.1 - Bugfixes
- [x] Fix scoring: validación de sets en formatos especiales
- [x] Fix network: conectividad en red local
- [x] Fix scheduler: asignación de partidos
- [x] Fix UI: mejoras visuales varias
- [x] Colores pot ITTF en bracket manual (Rojo, Magenta, Amarillo, Verde, Cyan)
- [x] Leyenda dinámica de pots para brackets >= 64

### 2.5.2 - Import Scope Fix
- [x] Detección de duplicados por (original_id, categoría) en vez de solo original_id
- [x] Fix en CSV import, manual import, pairs import y player edit
- [x] Soporte para CSV multi-categoría sin falsos duplicados

---

## V2.6 - Reportes Personalizables (Completada)

**Objetivo:** Documentos profesionales con identidad del torneo

### 2.6.1 - Configuración de Torneo/Evento
- [x] Subir logo del torneo (PNG/JPG)
- [x] Nombre oficial del evento
- [x] Fecha y sede
- [x] Organizador / Federación
- [x] Sponsors (logos secundarios)

### 2.6.2 - Personalización de Reportes
- [x] Logo en encabezado de todos los documentos
- [x] Bandera del país junto a jugadores (usando pais_cd)
- [x] Colores personalizables (primario/secundario)
- [x] Pie de página con datos del evento

### 2.6.3 - Documentos Mejorados
- [x] Hoja de partido con logo y datos del torneo
- [x] Hoja de grupo con encabezado profesional
- [x] Bracket con identidad visual
- [x] Acta oficial de resultados por categoría

### 2.6.4 - Exportaciones
- [x] CSV de todos los resultados
- [x] Excel con múltiples hojas (jugadores, grupos, bracket, resultados)
- [x] PDF de resumen del torneo

### 2.6.5 - Certificados (Opcional)
- [x] Template de diploma/certificado
- [x] Generación automática para top 3
- [x] Logo, firma, datos del evento

---

## V2.7 - Guía de Usuario Online (Completada)

**Objetivo:** Documentación completa y landing page actualizado

```
JUGADOR (su celular)              SERVIDOR
┌──────────────────┐              ┌──────────────────┐
│ "¿Cuándo juego?" │  ◄────────   │ Horarios,        │
│ "¿En qué mesa?"  │   consulta   │ resultados,      │
│ "¿Cómo voy?"     │              │ standings        │
└──────────────────┘              └──────────────────┘
```

### 2.7.1 - Acceso al Portal
- [ ] Ruta pública: `/torneo` o `/public`
- [ ] Código QR para compartir (imprimible, para pegar en entrada)
- [ ] Sin login requerido
- [ ] Funciona en red local o expuesto a internet

### 2.7.2 - Vista General
- [ ] Lista de categorías del torneo
- [ ] Estado de cada categoría (grupos, bracket, finalizado)
- [ ] Resultados recientes
- [ ] Próximos partidos (todas las mesas)

### 2.7.3 - Búsqueda de Jugador
- [ ] Buscar por nombre
- [ ] Ver todos los partidos del jugador (pasados y próximos)
- [ ] Mesa y hora del próximo partido
- [ ] Resultados de sus partidos jugados

### 2.7.4 - Vista por Categoría
- [ ] Grupos con resultados y standings
- [ ] Bracket interactivo (zoom, scroll)
- [ ] Horarios de la categoría

### 2.7.5 - Diseño y UX (Prioridad Alta)

**UI completamente diferente al admin - moderna y amigable:**

- [ ] Diseño visual atractivo (no tablas densas)
- [ ] Cards grandes con información clara
- [ ] Iconos y colores para estados (en juego, próximo, finalizado)
- [ ] Tipografía grande y legible
- [ ] Animaciones sutiles (transiciones, loading)
- [ ] Banderas de países visibles
- [ ] Fotos de jugadores (si están disponibles)

**Optimizado para móvil:**
- [ ] Mobile-first (diseñado para celular primero)
- [ ] Touch-friendly (botones grandes, swipe)
- [ ] Carga rápida (datos mínimos, lazy loading)
- [ ] Pull-to-refresh para actualizar
- [ ] Modo oscuro opcional

**Ejemplo de card de partido:**
```
┌─────────────────────────────────┐
│  🏓 MESA 3 - EN JUEGO          │
│  ─────────────────────────────  │
│  🇪🇸 Juan Pérez                │
│         2 - 1                   │
│  🇲🇽 Pedro López               │
│                                 │
│  Set actual: 9-7               │
│  ─────────────────────────────  │
│  U15 Masculino - Semifinal     │
└─────────────────────────────────┘
```

### Consideraciones Técnicas
- [ ] Red local: accesible via IP del servidor (ej: 192.168.1.100:8000/torneo)
- [ ] Internet: exponer con ngrok, túnel SSH, o IP pública
- [ ] Cache agresivo para reducir carga
- [ ] PWA opcional (agregar a pantalla de inicio)

---

## V2.8 - Registration Sheets & Teams (Completada)

**Objetivo:** Hojas de registro para jugadores, parejas y equipos

### 2.8.1 - Registration Sheets
- [x] Hojas de registro para jugadores individuales
- [x] Hojas de registro para parejas (doubles)
- [x] Hojas de registro para equipos (teams)
- [x] Impresión y exportación de hojas de registro

---

## V3.0 - Comunicación con Jugadores

**Objetivo:** Notificar a jugadores cuando les toca jugar

### 3.0.1 - Notificaciones WhatsApp
- [ ] Integración con WhatsApp Business API
- [ ] Mensaje automático: "Tu partido en Mesa X en 10 minutos"
- [ ] Confirmación de recibido
- [ ] Opt-in del jugador (cumplir privacidad)

### 3.0.2 - Notificaciones SMS (Alternativa)
- [ ] Integración con Twilio o similar
- [ ] Fallback si no hay WhatsApp

### 3.0.3 - Panel de Jugador (Web)
- [ ] URL única por jugador (sin login)
- [ ] Ver sus próximos partidos
- [ ] Historial de resultados
- [ ] Notificaciones push en navegador

---

## V3.1 - Inscripciones Online

**Objetivo:** Recibir inscripciones sin caos de mensajes

### 3.1.1 - Formulario Público
- [ ] Página de inscripción por torneo
- [ ] Campos: nombre, categoría, club, contacto
- [ ] Validación de edad vs categoría
- [ ] Confirmación por email

### 3.1.2 - Gestión de Inscripciones
- [ ] Lista de inscritos con estado (pendiente, confirmado, pagado)
- [ ] Aprobar/rechazar inscripciones
- [ ] Límite de cupos por categoría
- [ ] Lista de espera

### 3.1.3 - Pagos (Opcional)
- [ ] Integración con MercadoPago/Stripe
- [ ] Confirmar automáticamente al pagar
- [ ] Reembolsos

---

## V4.0 - Multi-usuario y Cloud

**Objetivo:** Varios organizadores trabajando simultáneamente

> **Nota:** En V2.2, los árbitros ya pueden ingresar resultados desde `/mesa/X`,
> pero sin autenticación completa (solo bloqueo por sesión). V4.0 agrega
> autenticación real y múltiples admins.

### 4.0.1 - Roles de Usuario
- [ ] **Admin:** control total (crear torneos, categorías, grupos, brackets)
- [ ] **Operador:** ingresar resultados desde panel admin (sin config)
- [ ] **Árbitro:** ya existe en V2.2 - solo su mesa asignada
- [ ] **Visor:** solo lectura (para pantallas públicas)
- [ ] Autenticación con usuario/contraseña
- [ ] Gestión de usuarios desde panel admin

### 4.0.2 - Sincronización
- [ ] Base de datos centralizada (PostgreSQL)
- [ ] Múltiples dispositivos conectados
- [ ] Resolución de conflictos

### 4.0.3 - Cloud Hosting
- [ ] Opción de despliegue en la nube
- [ ] Backup automático
- [ ] Acceso desde cualquier lugar

---

## Backlog (Sin priorizar)

Ideas para evaluar en el futuro:

- **Rankings:** Sistema de puntos acumulados entre torneos
- **Streaming:** Integración con OBS para overlays
- **App móvil nativa:** iOS/Android para árbitros
- **Estadísticas avanzadas:** Head-to-head, rachas, promedios
- **Multi-idioma:** Portugués, inglés, francés
- **Modo offline-first con sync:** Trabajar sin internet y sincronizar después
- **Integración con federaciones:** Envío automático de resultados
- **Dobles avanzado:** Soporte básico de parejas ya existe; falta categorías MD/WD/XD y validación de género en mixtos

---

## Versionado

| Versión | Enfoque | Estado |
|---------|---------|--------|
| 2.1.0 | MVP Comercial | Completada |
| 2.2.0 | Pantalla Pública + Marcador Árbitro | Completada |
| 2.3.0 | Validación Online de Licencias | Completada |
| 2.4.0 | KO Directo + Equipos + Grupo de 5 | Completada |
| 2.5.2 | macOS, CI/CD, Colores Pot ITTF, Bugfixes | Completada |
| 2.6.0 | Reportes Personalizables | **Próxima** |
| 2.7.0 | Portal Público para Jugadores | Planeada |
| 2.8.0 | Check-in de Jugadores | Planeada |
| 3.0.0 | Notificaciones (WhatsApp/SMS) | Futura |
| 3.1.0 | Inscripciones Online | Futura |
| 4.0.0 | Multi-usuario y Cloud | Futura |

---

## Feedback

¿Tienes sugerencias? ¿Qué funcionalidad te haría la vida más fácil como organizador?

Contacta al equipo de desarrollo para proponer ideas.
