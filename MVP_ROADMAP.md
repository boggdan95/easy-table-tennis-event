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

### ✅ Estado Actual del MVP (V1.1.0)

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
| **Ingresar resultados de bracket** | ✅ **COMPLETO** | Usa mismo sistema que grupos |
| **Avance automático de ganadores** | ✅ **COMPLETO** | Winner → siguiente ronda |
| **Ver campeón y podio** | ⚠️ **FALTA** | Vista dedicada final |
| Exportar a CSV | ✅ Completo | CLI (grupos/standings/bracket) |
| Exportar a CSV desde UI | ❌ Falta | Mejora futura |

---

## 🚧 Para Completar el MVP

### 📋 Tareas Críticas (V1.1.1 - MVP Final)

1. **Vista de Resultados Finales y Podio** 🏆
   - Página dedicada `/category/{category}/results`
   - Mostrar campeón (ganador de Final)
   - Mostrar podio (1°, 2°, 3°/4°)
   - Mostrar clasificación completa de bracket
   - Navegación desde página de categoría

2. **Mejoras UX Críticas**
   - Botón en navbar para "Resultados Finales" cuando existe bracket completo
   - Indicador visual de progreso del torneo (Grupos → Bracket → Finalizado)
   - Badge de "CAMPEÓN" en vista de bracket cuando hay ganador

3. **Testing del Flujo Completo**
   - Test end-to-end de torneo completo
   - Validar que todos los partidos se pueden jugar
   - Validar que avance automático funciona correctamente
   - Validar que se puede identificar al campeón

### 📝 Tareas Opcionales (Nice to Have)

- Exportar resultados finales a CSV desde UI
- Imprimir certificado/diploma del campeón
- Estadísticas agregadas del torneo
- Histórico de partidos por jugador

---

## 🗺️ Roadmap Post-MVP

### V1.2 - Mejoras de Usabilidad

**Objetivo:** Hacer la herramienta más amigable y robusta

- [ ] Editar jugadores desde UI
- [ ] Eliminar jugadores (con validación de dependencias)
- [ ] Eliminar categorías completas
- [ ] Regenerar bracket con nuevas configuraciones
- [ ] Undo/Redo de operaciones críticas
- [ ] Backup y restore de base de datos
- [ ] Validaciones más estrictas en formularios
- [ ] Mensajes de error más descriptivos

**Duración estimada:** 2-3 sesiones

---

### V1.3 - Exportación e Impresión

**Objetivo:** Generar documentos imprimibles para operación del torneo

- [ ] Exportar a CSV desde UI (grupos, standings, bracket, resultados)
- [ ] Generar PDF de hojas de grupo (group sheets)
- [ ] Generar PDF de bracket vacío
- [ ] Generar PDF de resultados finales con podio
- [ ] Generar PDF de certificados de participación
- [ ] Generar PDF de certificados de campeón/podio
- [ ] Imprimir etiquetas para mesas

**Duración estimada:** 3-4 sesiones

---

### V1.4 - Múltiples Categorías

**Objetivo:** Gestionar eventos con múltiples categorías simultáneas

- [ ] Dashboard global con todas las categorías
- [ ] Selector de categoría activa
- [ ] Vista comparativa de progreso entre categorías
- [ ] Operaciones batch (ej: calcular standings de todas las categorías)
- [ ] Validación de jugadores duplicados entre categorías
- [ ] Exportación agregada de todas las categorías

**Duración estimada:** 2-3 sesiones

---

### V2.0 - Scheduler y Asignación de Mesas

**Objetivo:** Asignar horarios y mesas automáticamente

- [ ] Configuración de mesas disponibles
- [ ] Configuración de horarios (inicio, duración, breaks)
- [ ] Algoritmo de scheduling automático
- [ ] Asignación manual de partidos a mesas/horarios
- [ ] Vista de cronograma por mesa
- [ ] Vista de cronograma por jugador
- [ ] Notificaciones de próximos partidos
- [ ] Buffers entre partidos
- [ ] Manejo de delays y reprogramaciones

**Duración estimada:** 5-7 sesiones

---

### V2.1 - Operación en Vivo

**Objetivo:** Herramientas para operar el torneo en tiempo real

- [ ] Panel de control para mesa (tablet/móvil)
- [ ] Ingreso rápido de resultados por mesa
- [ ] Display público de resultados en vivo
- [ ] Display de "próximos partidos"
- [ ] Notificaciones automáticas a jugadores
- [ ] QR codes para tracking de jugadores
- [ ] Marcador electrónico integrado

**Duración estimada:** 6-8 sesiones

---

### V3.0 - Avanzado

**Objetivo:** Funcionalidades profesionales para eventos grandes

- [ ] Sistema de credenciales y roles (admin, referee, player)
- [ ] Multi-tenant (múltiples eventos en paralelo)
- [ ] API REST para integraciones
- [ ] App móvil (React Native / Flutter)
- [ ] Integración con sistemas de ranking (ITTF, nacionales)
- [ ] Streaming de resultados a web pública
- [ ] Análisis estadístico avanzado
- [ ] Soporte para dobles y equipos

**Duración estimada:** 15-20 sesiones

---

## 📊 Prioridades

### Ahora (V1.1.1)
1. ✅ Vista de Resultados Finales
2. ✅ Testing del flujo completo
3. ✅ Documentación de uso

### Próximo (V1.2-V1.4)
- Mejoras de usabilidad
- Exportación e impresión
- Soporte multi-categoría

### Futuro (V2.0+)
- Scheduler
- Operación en vivo
- Funcionalidades avanzadas

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
- **No scheduler en V1:** Complejidad deferida

---

## 📈 Métricas de Éxito del MVP

Un MVP exitoso debe poder:

- [ ] Gestionar un torneo de 12+ jugadores en 1 categoría
- [ ] Completar todos los partidos de grupos (Round Robin)
- [ ] Calcular clasificaciones correctamente con desempates
- [ ] Generar bracket de 8/16/32 jugadores
- [ ] Completar todos los partidos de bracket hasta final
- [ ] Identificar al campeón correctamente
- [ ] Exportar resultados a CSV
- [ ] Durar un evento de 4-6 horas sin crashes
- [ ] Usarse por una persona sin conocimientos técnicos

---

## 🔄 Proceso de Desarrollo

### Workflow por Versión

1. **Planning:** Definir scope de la versión
2. **Desarrollo:** Implementar funcionalidades
3. **Testing:** Pruebas manuales + automatizadas
4. **Documentación:** Actualizar README y CLAUDE.md
5. **Release:** Merge a `main` con tag de versión

### Ramas de Git

- `main` - Código estable y probado
- `feature/*` - Nuevas funcionalidades
- `bugfix/*` - Correcciones de bugs
- `hotfix/*` - Fixes urgentes en producción

---

## 📞 Próximos Pasos

### Sesión Actual (Completar MVP V1.1.1)

1. Crear vista de resultados finales (`/category/{category}/results`)
2. Implementar lógica de podio (1°, 2°, 3°/4°)
3. Agregar navegación a resultados finales
4. Testing end-to-end del flujo completo
5. Actualizar documentación

**Tiempo estimado:** 1-2 horas
