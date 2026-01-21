# ETTEM - Roadmap de Desarrollo

> Última actualización: 2026-01-21
> Versión actual: 2.1.0

---

## Filosofía de Desarrollo

Priorizar funcionalidades que:
1. **Resuelvan dolores reales** del organizador durante el torneo
2. **Mejoren la experiencia** de jugadores y espectadores
3. **Reduzcan trabajo manual** y errores humanos
4. **Funcionen offline** (internet no siempre es confiable en gimnasios)

---

## V2.2 - Pantalla Pública (Próxima versión)

**Objetivo:** Display en TV/monitor para espectadores y jugadores

### 2.2.1 - Live Display (Prioridad Alta)
- [ ] Ruta `/display` optimizada para TV (fullscreen, auto-refresh)
- [ ] Vista de resultados recientes (últimos 5-10 partidos)
- [ ] Partidos en curso (mesa, jugadores, score parcial)
- [ ] Próximos partidos (llamado a mesa)
- [ ] Rotación automática entre vistas
- [ ] Diseño grande y legible (para ver desde lejos)
- [ ] Tema oscuro por defecto (mejor para pantallas)

### 2.2.2 - Llamado a Mesa
- [ ] Lista de "Próximos partidos" con countdown
- [ ] Estado: "Prepararse" → "A mesa" → "En juego"
- [ ] Alerta visual cuando jugador no se presenta (parpadeo)
- [ ] Sonido opcional de llamado (configurable)

### 2.2.3 - Score en Vivo (Opcional)
- [ ] Actualización de score set por set desde panel admin
- [ ] Vista de partido individual (para segunda pantalla en mesa)

### Consideraciones Técnicas
- Sin websockets (polling cada 5-10 seg para simplicidad)
- CSS responsive para diferentes tamaños de TV
- Modo "kiosko" sin controles de navegación

---

## V2.3 - Check-in de Jugadores

**Objetivo:** Saber quién llegó y quién falta

### 2.3.1 - Control de Asistencia
- [ ] Marcar jugador como "presente" (check-in)
- [ ] Vista de jugadores pendientes por categoría
- [ ] Hora de check-in registrada
- [ ] Filtro: "Solo ausentes"

### 2.3.2 - Alertas de Ausencia
- [ ] Advertencia al generar grupos si hay jugadores sin check-in
- [ ] Opción de excluir automáticamente ausentes
- [ ] Reporte de no-shows al final del torneo

### 2.3.3 - QR Check-in (Opcional)
- [ ] Generar QR único por jugador
- [ ] Escanear con celular del organizador
- [ ] Auto check-in al escanear

---

## V2.4 - Mejoras de Impresión y Reportes

**Objetivo:** Documentación oficial y exportaciones

### 2.4.1 - Acta Oficial de Torneo
- [ ] Formato estándar de federación (configurable)
- [ ] Firma digital del árbitro principal
- [ ] Resumen de resultados por categoría
- [ ] Lista de participantes con club/asociación

### 2.4.2 - Exportaciones
- [ ] CSV de todos los resultados
- [ ] Formato ITTF (si existe estándar)
- [ ] Excel con múltiples hojas (jugadores, grupos, bracket, resultados)

### 2.4.3 - Certificados
- [ ] Template de diploma/certificado
- [ ] Generación automática para top 3
- [ ] Personalizable (logo del torneo, sponsors)

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

**Objetivo:** Varios organizadores/árbitros trabajando simultáneamente

### 4.0.1 - Roles de Usuario
- [ ] Admin: control total
- [ ] Árbitro: ingresar resultados de sus mesas asignadas
- [ ] Visor: solo lectura (para pantallas públicas)

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
| 2.1.0 | MVP Comercial | **Actual** |
| 2.2.0 | Pantalla Pública | Próxima |
| 2.3.0 | Check-in | Planeada |
| 2.4.0 | Reportes | Planeada |
| 3.0.0 | Notificaciones | Futura |
| 3.1.0 | Inscripciones | Futura |
| 3.2.0 | Dobles | Futura |
| 4.0.0 | Multi-usuario | Futura |

---

## Feedback

¿Tienes sugerencias? ¿Qué funcionalidad te haría la vida más fácil como organizador?

Contacta al equipo de desarrollo para proponer ideas.
