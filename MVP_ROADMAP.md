# MVP & Roadmap - Easy Table Tennis Event Manager

## 🎯 MVP (Minimum Viable Product)

**Objetivo:** Herramienta funcional para correr un evento completo de tenis de mesa de al menos 1 categoría desde inicio hasta fin.

### Definición del MVP

El MVP debe permitir gestionar un torneo completo de principio a fin:

1. **Inscribir jugadores** (CSV o manual)
2. **Crear grupos** de Round Robin
3. **Ingresar resultados** de fase de grupos
4. **Calcular clasificaciones** con desempates
5. **Generar bracket** de eliminación directa
6. **Ingresar resultados** de partidos de bracket
7. **Avanzar ganadores** automáticamente por rondas
8. **Ver resultados finales** (campeón, podio, clasificaciones)

### ✅ Estado Actual: MVP COMPLETO (V1.1.1)

| Funcionalidad | Estado | Notas |
|--------------|--------|-------|
| Importar jugadores (CSV) | ✅ Completo | UI + CLI |
| Importar jugadores (manual) | ✅ Completo | Formulario web |
| Crear grupos Round Robin | ✅ Completo | Snake seeding, preferencia 3/4 |
| Ver grupos y fixtures | ✅ Completo | Vista web con cards |
| Ingresar resultados de grupos | ✅ Completo | Formulario validado |
| Editar resultados de grupos | ✅ Completo | Con validación ITTF |
| Eliminar resultados de grupos | ✅ Completo | Con confirmación |
| Calcular standings | ✅ Completo | Desempate triple con ratios |
| Ver clasificaciones | ✅ Completo | Con medallas y stats |
| Generar bracket (automático) | ✅ Completo | ITTF positioning, BYEs |
| Generar bracket (manual) | ✅ Completo | Drag-and-drop, validaciones |
| Ver bracket visual | ✅ Completo | Vista gráfica por rondas |
| Ver partidos de bracket | ✅ Completo | Lista por ronda |
| Ingresar resultados de bracket | ✅ Completo | Usa mismo sistema que grupos |
| Avance automático de ganadores | ✅ Completo | Winner → siguiente ronda |
| Ver campeón y podio | ✅ Completo | Vista `/category/{cat}/results` |
| Exportar a CSV | ✅ Completo | CLI (grupos/standings/bracket) |

---

## ✅ V2.0 - Scheduler COMPLETO

**Objetivo:** Asignar horarios y mesas para los partidos del torneo.

| Funcionalidad | Estado | Notas |
|--------------|--------|-------|
| Configuración de mesas | ✅ Completo | Número de mesas configurable |
| Configuración de horarios | ✅ Completo | Jornadas con inicio/fin |
| Crear/editar/eliminar jornadas | ✅ Completo | UI completa |
| Cuadrícula drag-and-drop | ✅ Completo | Asignar partidos a mesa/hora |
| Validación de conflictos | ✅ Completo | Rojo/verde al arrastrar |
| Warnings visuales | ✅ Completo | Sin descanso, superposición |
| Buscador de jugador | ✅ Completo | Resalta partidos del jugador |
| Duraciones flexibles | ✅ Completo | Editar duración por bloque |
| Añadir bloques horarios | ✅ Completo | Botón "+ Añadir" |
| Finalizar jornadas | ✅ Completo | Limpia slots vacíos |
| Reabrir jornadas | ✅ Completo | Para continuar editando |
| Vista imprimible | ✅ Completo | Sin slots vacíos, con países |
| Filtros por categoría/ronda | ✅ Completo | En panel de partidos |

---

## 🗺️ Roadmap Futuro

### V2.1 - Mejoras de Usabilidad

**Objetivo:** Hacer la herramienta más amigable y robusta

- [ ] Editar jugadores desde UI
- [ ] Eliminar jugadores (con validación de dependencias)
- [ ] Eliminar categorías completas
- [ ] Regenerar bracket con nuevas configuraciones
- [ ] Backup y restore de base de datos
- [ ] Validaciones más estrictas en formularios
- [ ] Mensajes de error más descriptivos

---

### V2.2 - Exportación e Impresión

**Objetivo:** Generar documentos imprimibles para operación del torneo

- [ ] Exportar a CSV desde UI (grupos, standings, bracket, horarios)
- [ ] Encabezado personalizable (logo, nombre torneo)
- [ ] Generar PDF de hojas de grupo (group sheets)
- [ ] Generar PDF de bracket vacío
- [ ] Generar PDF de resultados finales con podio
- [ ] Generar PDF de certificados de participación
- [ ] Generar PDF de certificados de campeón/podio
- [ ] Imprimir etiquetas para mesas
- [ ] Imprimir horario por jugador

---

### V2.3 - Múltiples Categorías Mejorado

**Objetivo:** Gestionar eventos con múltiples categorías de forma más eficiente

- [ ] Dashboard global con todas las categorías
- [ ] Vista comparativa de progreso entre categorías
- [ ] Operaciones batch (ej: calcular standings de todas las categorías)
- [ ] Validación de jugadores duplicados entre categorías
- [ ] Exportación agregada de todas las categorías

---

### V3.0 - Operación en Vivo

**Objetivo:** Herramientas para operar el torneo en tiempo real

- [ ] Panel de control para mesa (tablet/móvil)
- [ ] Ingreso rápido de resultados por mesa
- [ ] Display público de resultados en vivo
- [ ] Display de "próximos partidos"
- [ ] Notificaciones automáticas a jugadores
- [ ] QR codes para tracking de jugadores
- [ ] Marcador electrónico integrado

---

### V4.0 - Avanzado

**Objetivo:** Funcionalidades profesionales para eventos grandes

- [ ] Sistema de credenciales y roles (admin, referee, player)
- [ ] Multi-tenant (múltiples eventos en paralelo)
- [ ] API REST para integraciones
- [ ] App móvil (React Native / Flutter)
- [ ] Integración con sistemas de ranking (ITTF, nacionales)
- [ ] Streaming de resultados a web pública
- [ ] Análisis estadístico avanzado
- [ ] Soporte para dobles y equipos

---

## 📊 Estado del Proyecto

### Versiones Completadas

| Versión | Descripción | Estado |
|---------|-------------|--------|
| V1.0.0 | Core funcional (CLI + motor deportivo) | ✅ |
| V1.0.1 | Edición de resultados + validación | ✅ |
| V1.0.2 | i18n + UI moderna | ✅ |
| V1.1.0 | Gestión completa desde UI | ✅ |
| V1.1.1 | MVP Final (podio, resultados) | ✅ |
| V2.0.0 | Scheduler completo | ✅ |

### Próxima Versión Sugerida

**V2.1 - Mejoras de Usabilidad** o **V2.2 - Exportación e Impresión**

---

## 🎓 Filosofía del Proyecto

### Principios de Diseño

1. **Offline-first:** El torneo debe funcionar sin internet
2. **Windows-first:** Optimizado para Windows (mayoría de torneos)
3. **Simple por defecto:** UI clara, sin complejidad innecesaria
4. **Progresivo:** Funcionalidades avanzadas opcionales
5. **Confiable:** Datos persistentes, validaciones estrictas
6. **ITTF-compliant:** Reglas oficiales de tenis de mesa

### Decisiones Técnicas

- **Python 3.11+:** Lenguaje principal
- **FastAPI + Jinja2:** Web framework
- **SQLite:** Base de datos (simple, portátil)
- **SQLAlchemy:** ORM robusto
- **Vanilla JS:** Sin frameworks pesados

---

## 📈 Métricas de Éxito (MVP Cumplido)

- [x] Gestionar un torneo de 12+ jugadores en 1 categoría
- [x] Completar todos los partidos de grupos (Round Robin)
- [x] Calcular clasificaciones correctamente con desempates
- [x] Generar bracket de 8/16/32 jugadores
- [x] Completar todos los partidos de bracket hasta final
- [x] Identificar al campeón correctamente
- [x] Exportar resultados a CSV
- [x] Programar partidos en mesas y horarios
- [ ] Durar un evento de 4-6 horas sin crashes (pendiente testing real)
- [ ] Usarse por una persona sin conocimientos técnicos (pendiente testing real)
