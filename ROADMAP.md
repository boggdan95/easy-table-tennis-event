# ETTEM - Roadmap de Desarrollo

> Última actualización: 2026-02-06
> Versión actual: 2.2.0

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

- [ ] URL simple por mesa: `/mesa/1`, `/mesa/2`, etc.
- [ ] Código QR en cada mesa física (imprimible)
- [ ] Sin login complejo (PIN simple por sesión o solo acceso por QR)
- [ ] Solo muestra partidos asignados a esa mesa

**Control de acceso por mesa:**
- [ ] Una mesa = un dispositivo activo a la vez
- [ ] Al abrir mesa → se bloquea para otros
- [ ] Si alguien intenta abrir mesa en uso → mensaje "Mesa ocupada"
- [ ] Timeout automático por inactividad (configurable, ej: 10 min)
- [ ] Admin puede forzar desbloqueo desde panel si es necesario
- [ ] Indicador visual en admin de qué mesas están activas

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
- [ ] Botones grandes +1 para cada jugador
- [ ] Score del set actual en tiempo real
- [ ] Detecta automáticamente fin de set (11 pts o deuce +2)
- [ ] Botón "Deshacer" último punto
- [ ] Sync automático al terminar set

**Modo Resultado por Set:**
- [ ] Árbitro ingresa score final del set (ej: 11-9)
- [ ] Validación de reglas ITTF
- [ ] Más rápido si árbitro usa marcador físico
- [ ] Sync al guardar cada set

**Configuración de Mesas (nuevo tab o sección):**
- [ ] Separado del Scheduler (config fija vs asignaciones del día)
- [ ] Por cada mesa:
  - Nombre/número
  - Modo de árbitro (punto por punto / resultado por set)
  - Generar/imprimir código QR
  - Estado (activa/inactiva)
- [ ] Default global para nuevas mesas
- [ ] Puede modificarse durante el torneo

**Funciones comunes (ambos modos):**
- [ ] Funciona offline (no requiere conexión constante)
- [ ] Si no hay conexión → guarda local y reintenta
- [ ] Indicador visual de estado de conexión
- [ ] Historial de sets jugados
- [ ] Opción de walkover
- [ ] Ver siguiente partido de la mesa

### 2.2.2 - Pantalla Pública (`/display`)

**Display para TV/monitor - espectadores y jugadores**

- [ ] Ruta `/display` optimizada para TV (fullscreen, auto-refresh)
- [ ] Diseño grande y legible (visible desde 5+ metros)
- [ ] Tema oscuro por defecto (mejor contraste)
- [ ] Modo kiosko (sin controles de navegación)

**Vistas con rotación automática:**
- [ ] **Partidos en curso:** Mesa, jugadores, score actual (ej: "Mesa 1: Juan 2-1 Pedro")
- [ ] **Resultados recientes:** Últimos 5-10 partidos terminados
- [ ] **Llamado a mesa:** Próximos partidos con countdown
- [ ] Tiempo configurable por vista (ej: 10 seg cada una)

**Estados de partido:**
- [ ] "Prepararse" → jugadores deben acercarse
- [ ] "A mesa" → partido por comenzar
- [ ] "En juego" → mostrando score en vivo
- [ ] "Finalizado" → resultado final

### 2.2.3 - Llamado a Mesa

- [ ] Lista de próximos partidos ordenada por prioridad
- [ ] Countdown visual ("Partido en 5 minutos")
- [ ] Alerta visual si jugador no se presenta (parpadeo rojo)
- [ ] Sonido opcional de llamado (configurable, para usar con parlantes)

### 2.2.4 - Vista de Mesa Individual (Opcional)

**Para pantalla/tablet en cada mesa física**

- [ ] Ruta `/display/mesa/1` - solo muestra esa mesa
- [ ] Score grande del partido actual
- [ ] Ideal para segunda pantalla junto al árbitro

### Consideraciones Técnicas

**Arquitectura:**
- Polling cada 5 segundos (simple, sin websockets)
- LocalStorage para persistencia offline del árbitro
- Service Worker para funcionar sin conexión (PWA)

**Rendimiento:**
- Endpoint liviano `/api/live-scores` con solo datos necesarios
- Cache de 5 segundos en servidor
- Compresión gzip

**Compatibilidad:**
- Árbitro: cualquier celular con navegador moderno
- Display: Chrome/Edge en modo kiosko (F11)
- Responsive para diferentes tamaños de pantalla

---

## V2.3 - Reportes Personalizables

**Objetivo:** Documentos profesionales con identidad del torneo

### 2.3.1 - Configuración de Torneo/Evento
- [ ] Subir logo del torneo (PNG/JPG)
- [ ] Nombre oficial del evento
- [ ] Fecha y sede
- [ ] Organizador / Federación
- [ ] Sponsors (logos secundarios)

### 2.3.2 - Personalización de Reportes
- [ ] Logo en encabezado de todos los documentos
- [ ] Bandera del país junto a jugadores (usando pais_cd)
- [ ] Colores personalizables (primario/secundario)
- [ ] Pie de página con datos del evento

### 2.3.3 - Documentos Mejorados
- [ ] Hoja de partido con logo y datos del torneo
- [ ] Hoja de grupo con encabezado profesional
- [ ] Bracket con identidad visual
- [ ] Acta oficial de resultados por categoría

### 2.3.4 - Exportaciones
- [ ] CSV de todos los resultados
- [ ] Excel con múltiples hojas (jugadores, grupos, bracket, resultados)
- [ ] PDF de resumen del torneo

### 2.3.5 - Certificados (Opcional)
- [ ] Template de diploma/certificado
- [ ] Generación automática para top 3
- [ ] Logo, firma, datos del evento

---

## V2.4 - Portal Público para Jugadores

**Objetivo:** Jugadores consultan horarios y resultados desde su celular (sin imprimir)

```
JUGADOR (su celular)              SERVIDOR
┌──────────────────┐              ┌──────────────────┐
│ "¿Cuándo juego?" │  ◄────────   │ Horarios,        │
│ "¿En qué mesa?"  │   consulta   │ resultados,      │
│ "¿Cómo voy?"     │              │ standings        │
└──────────────────┘              └──────────────────┘
```

### 2.4.1 - Acceso al Portal
- [ ] Ruta pública: `/torneo` o `/public`
- [ ] Código QR para compartir (imprimible, para pegar en entrada)
- [ ] Sin login requerido
- [ ] Funciona en red local o expuesto a internet

### 2.4.2 - Vista General
- [ ] Lista de categorías del torneo
- [ ] Estado de cada categoría (grupos, bracket, finalizado)
- [ ] Resultados recientes
- [ ] Próximos partidos (todas las mesas)

### 2.4.3 - Búsqueda de Jugador
- [ ] Buscar por nombre
- [ ] Ver todos los partidos del jugador (pasados y próximos)
- [ ] Mesa y hora del próximo partido
- [ ] Resultados de sus partidos jugados

### 2.4.4 - Vista por Categoría
- [ ] Grupos con resultados y standings
- [ ] Bracket interactivo (zoom, scroll)
- [ ] Horarios de la categoría

### 2.4.5 - Diseño y UX (Prioridad Alta)

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

## V2.5 - Check-in de Jugadores

**Objetivo:** Saber quién llegó y quién falta

### 2.5.1 - Control de Asistencia
- [ ] Marcar jugador como "presente" (check-in)
- [ ] Vista de jugadores pendientes por categoría
- [ ] Hora de check-in registrada
- [ ] Filtro: "Solo ausentes"

### 2.5.2 - Alertas de Ausencia
- [ ] Advertencia al generar grupos si hay jugadores sin check-in
- [ ] Opción de excluir automáticamente ausentes
- [ ] Reporte de no-shows al final del torneo

### 2.5.3 - QR Check-in (Opcional)
- [ ] Generar QR único por jugador
- [ ] Escanear con celular del organizador
- [ ] Auto check-in al escanear

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

## V3.2 - Dobles

**Objetivo:** Soportar torneos de dobles

### 3.2.1 - Parejas
- [ ] Crear pareja (2 jugadores)
- [ ] Pareja como "unidad" en grupos y bracket
- [ ] Seeding por suma de rankings

### 3.2.2 - Mixtos
- [ ] Validar género en parejas mixtas
- [ ] Categorías: MD (Men's Doubles), WD (Women's Doubles), XD (Mixed)

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

- **Torneos por equipos:** Ligas, formato por puntos
- **Rankings:** Sistema de puntos acumulados entre torneos
- **Streaming:** Integración con OBS para overlays
- **App móvil nativa:** iOS/Android para árbitros
- **Estadísticas avanzadas:** Head-to-head, rachas, promedios
- **Multi-idioma:** Portugués, inglés, francés
- **Modo offline-first con sync:** Trabajar sin internet y sincronizar después
- **Integración con federaciones:** Envío automático de resultados

---

## Versionado

| Versión | Enfoque | Estado |
|---------|---------|--------|
| 2.1.0 | MVP Comercial | Completada |
| 2.2.0 | Pantalla Pública + Marcador Árbitro | **Actual** |
| 2.3.0 | Reportes Personalizables | Próxima |
| 2.4.0 | Portal Público para Jugadores | Planeada |
| 2.5.0 | Check-in de Jugadores | Planeada |
| 3.0.0 | Notificaciones (WhatsApp/SMS) | Futura |
| 3.1.0 | Inscripciones Online | Futura |
| 3.2.0 | Dobles | Futura |
| 4.0.0 | Multi-usuario y Cloud | Futura |

---

## Feedback

¿Tienes sugerencias? ¿Qué funcionalidad te haría la vida más fácil como organizador?

Contacta al equipo de desarrollo para proponer ideas.
