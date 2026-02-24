# ETTEM - UX & Navigation Architecture

> Documento de referencia para el flujo de navegacion, estructura de pantallas y convenciones de UX.
> Ultima actualizacion: v2.6 (Feb 2026)

---

## Filosofia de Navegacion

ETTEM sigue un flujo lineal de torneo con navegacion contextual:

```
Crear Torneo → Importar → Organizar → Jugar → Calcular → Coronar Campeon
```

**Principios:**
1. **Back button siempre visible** — Cada pantalla tiene un boton de retorno claro
2. **Etiqueta descriptiva** — El back button dice *a donde* va, no "Volver"
3. **Sidebar como mapa global** — Siempre accesible para saltar entre secciones
4. **Hub por categoria** — Cada categoria tiene su pagina central con acceso a todo
5. **Sin callejones sin salida** — Toda pantalla tiene al menos una salida

---

## Estructura General

```
┌──────────────────────────────────────────────────────────┐
│  SIDEBAR (siempre visible)     │  TOPBAR (contextual)    │
│                                │  [← Back] [Acciones]    │
│  Principal                     ├─────────────────────────┤
│    Inicio (/)                  │                         │
│    Torneos (/tournaments)      │  CONTENIDO PRINCIPAL    │
│                                │                         │
│  Gestion del Torneo            │                         │
│    Estado General              │                         │
│    Importar Jugadores          │                         │
│    Crear Grupos                │                         │
│    Programacion                │                         │
│    Resultados en Vivo          │                         │
│    Calcular Standings          │                         │
│    Generar Bracket             │                         │
│                                │                         │
│  Categorias (dinamico)         │                         │
│    MS ▼                        │                         │
│      Grupos                    │                         │
│      Standings                 │                         │
│      Bracket                   │                         │
│      Partidos                  │                         │
│      Resultados                │                         │
│                                │                         │
│  Herramientas                  │                         │
│    Personalizacion             │                         │
│    Config. Mesas               │                         │
│    Centro de Impresion         │                         │
└──────────────────────────────────────────────────────────┘
```

---

## Mapa de Pantallas

### Nivel 0: Home
```
/ (Dashboard)
├── Resumen del torneo activo
├── Quick actions por fase
└── Estado de categorias
```

### Nivel 1: Administracion (desde sidebar)

| Pantalla | Ruta | Back → | Descripcion |
|----------|------|--------|-------------|
| Torneos | `/tournaments` | `← Inicio` → `/` | CRUD de torneos |
| Estado General | `/tournament-status` | `← Inicio` → `/` | Progreso global |
| Importar Jugadores | `/admin/import-players` | `← Inicio` → `/` | CSV + manual |
| Importar Parejas | `/admin/import-pairs` | `← Inicio` → `/` | Dobles |
| Importar Equipos | `/admin/import-teams` | `← Inicio` → `/` | Swaythling/Corbillon/Olympic |
| Crear Grupos | `/admin/create-groups` | `← Inicio` → `/` | Snake seeding + D&D |
| Programacion | `/admin/scheduler` | `← Inicio` → `/` | Mesas y horarios |
| Resultados en Vivo | `/admin/live-results` | `← Inicio` → `/` | Monitoreo tiempo real |
| Calcular Standings | `/admin/calculate-standings` | `← Inicio` → `/` | Clasificaciones RR |
| Generar Bracket | `/admin/generate-bracket` | `← Inicio` → `/` | Llave eliminatoria |
| KO Directo | `/admin/direct-bracket` | `← Inicio` → `/` | Bracket sin grupos |
| Personalizacion | `/admin/tournament-settings` | `← Inicio` → `/` | Colores, logo, branding |
| Config. Mesas | `/admin/table-config` | `← Inicio` → `/` | Mesas + QR codes |
| Centro Impresion | `/admin/print-center` | `← Inicio` → `/` | PDFs, exports, diplomas |

### Nivel 2: Categoria (hub)

```
/category/{cat}  ← Pagina central de la categoria
├── ← Inicio (back al home)
├── Resultados (btn)
├── Bracket Visual (btn)
├── Partidos Bracket (btn)
├── Quick Actions contextuales
└── Grid de grupos con acciones por grupo
```

### Nivel 3: Vistas de Categoria

| Pantalla | Ruta | Back → | Descripcion |
|----------|------|--------|-------------|
| Categoria (hub) | `/category/{cat}` | `← Inicio` → `/` | Vista central |
| Standings Cat. | `/category/{cat}/standings` | `← {cat}` → `/category/{cat}` | Clasificacion general |
| Bracket Visual | `/category/{cat}/bracket` | `← {cat}` → `/category/{cat}` | Arbol visual |
| Partidos Bracket | `/bracket/{cat}` | `← {cat}` → `/category/{cat}` | Lista por ronda |
| Resultados/Podio | `/category/{cat}/results` | `← {cat}` → `/category/{cat}` | Campeon + podio |
| Sin Bracket | `/category/{cat}/bracket` (vacio) | `← {cat}` → `/category/{cat}` | Placeholder |

### Nivel 4: Vistas de Grupo

| Pantalla | Ruta | Back → | Descripcion |
|----------|------|--------|-------------|
| Partidos Grupo | `/group/{id}/matches` | `← {cat}` → `/category/{cat}` | Ingresar resultados |
| Standings Grupo | `/group/{id}/standings` | `← {cat}` → `/category/{cat}` | Tabla de posiciones |
| Hoja de Grupo | `/group/{id}/sheet` | `← {cat}` → `/category/{cat}` | Vista imprimible |

### Nivel 5: Detalle

| Pantalla | Ruta | Back → | Descripcion |
|----------|------|--------|-------------|
| Ingresar Resultado | `/match/{id}/enter-result` | `← Cancelar` → origen | Marcador set por set |
| Encuentro Equipos | `/team-match/{id}` | `← {cat}` → `/category/{cat}` | Partidos individuales |
| QR Codes | `/admin/table-qr-codes` | `← Config. Mesas` → `/admin/table-config` | Codigos QR |

### Pantallas Sin Sidebar (standalone)

| Pantalla | Ruta | Navegacion |
|----------|------|------------|
| Marcador Arbitro | `/mesa/{n}` | Selector de mesa (dropdown) |
| Display Publico | `/display` | Sin navegacion |
| Activar Licencia | `/license/activate` | Solo formulario |

---

## Flujos de Trabajo

### Flujo 1: Torneo Individual con Grupos (mas comun)

```
1. / ──────────────────────── Dashboard
   │
2. /tournaments ──────────── Crear torneo
   │
3. /admin/import-players ─── Importar CSV
   │
4. /admin/create-groups ──── Crear grupos (snake seeding)
   │
5. /category/{cat} ───────── Hub de categoria
   │  │
   │  ├─ /group/{id}/matches ─── Ingresar resultados
   │  │     └─ /match/{id}/enter-result ── Set por set
   │  │
   │  └─ /group/{id}/standings ── Ver posiciones
   │
6. /admin/calculate-standings ── Calcular clasificaciones
   │
7. /admin/generate-bracket ──── Generar llave
   │
8. /bracket/{cat} ────────────── Partidos de llave
   │  └─ /match/{id}/enter-result ── Set por set
   │
9. /category/{cat}/results ───── Campeon y podio
```

### Flujo 2: KO Directo (sin grupos)

```
1. / → /tournaments → /admin/import-players
   │
2. /admin/direct-bracket ───── Crear bracket directo
   │
3. /bracket/{cat} ──────────── Partidos
   │
4. /category/{cat}/results ─── Campeon
```

### Flujo 3: Equipos

```
1. / → /tournaments → /admin/import-teams
   │
2. /admin/create-groups ──── (con sistema de equipos seleccionado)
   │
3. /category/{cat} ────────── Hub
   │  └─ /team-match/{id} ──── Encuentro (partidos individuales)
   │
4. /admin/calculate-standings → /admin/generate-bracket
   │
5. /category/{cat}/results
```

### Flujo 4: Operacion en Vivo (dia del torneo)

```
Admin (PC):                          Arbitro (movil):
┌────────────────────┐               ┌──────────────────┐
│ /admin/scheduler   │               │ /mesa/{n}        │
│   └─ Asignar       │──── QR ────→  │   └─ Seleccionar │
│      partidos      │               │      partido     │
│      a mesas       │               │   └─ Marcar      │
│                    │               │      puntos      │
│ /admin/live-results│◄── sync ────  │   └─ Enviar      │
│   └─ Monitorear    │               │      resultado   │
└────────────────────┘               └──────────────────┘
```

### Flujo 5: Impresion y Exportacion

```
/admin/print-center
├── Tab "Torneo" ──── Excel, CSV global, Diplomas todos
├── Tab "{cat}" ───── Quick actions + Grupos + Bracket
│   ├── Hojas de partido (PDF)
│   ├── Hojas de grupo (PDF)
│   ├── Llave (PDF)
│   ├── Standings CSV
│   ├── Bracket CSV
│   ├── Diplomas categoria
│   ├── Tabla de grupos (impresion individual)
│   └── Bracket (seleccion por rondas)
└── Ayuda (siempre visible)
```

---

## Convenciones de Back Buttons

### Formato Standard
```html
<a href="{destino}" class="btn btn-secondary btn-sm">
    <span>←</span>
    <span>{Etiqueta}</span>
</a>
```

### Reglas

| Contexto | Etiqueta | Destino |
|----------|----------|---------|
| Pagina admin → Home | `← Inicio` | `/` |
| Subpagina → Categoria | `← {cat}` (ej: `← MS`) | `/category/{cat}` |
| QR Codes → Config | `← Config. Mesas` | `/admin/table-config` |
| Match entry → Origen | `← Cancelar` | Pagina de donde vino |

**Nunca usar:**
- "Volver" (no dice a donde)
- "Back" (no dice a donde)
- "Volver al Inicio" (redundante, "Inicio" ya implica volver)
- Back button sin flecha `←`

---

## Componentes de Navegacion

### Sidebar (base.html)
- Siempre visible excepto en pantallas standalone
- Colapsable con boton toggle
- Categorias dinamicas con submenu expandible
- Footer con info de licencia y version

### Topbar (base.html)
- Titulo de pagina (izquierda)
- Acciones contextuales (derecha): back button + botones de accion
- Theme toggle + Language selector (por defecto)

### Tabs (usados en)
- **Print Center**: Tab por categoria + tab "Torneo"
- **Bracket Matches**: Tab por ronda (R128, R64, ... F)
- Persistencia en localStorage

### Quick Actions
- Cards con botones contextuales segun el estado actual
- Patron: icono + texto descriptivo
- Ejemplo en category.html: Standings, Calcular, Generar Bracket

---

## Paginas con Auto-Refresh

| Pagina | Intervalo | Razon |
|--------|-----------|-------|
| `/admin/live-results` | 10s | Monitoreo en vivo |
| `/bracket/{cat}` | 10s | Resultados de llave |
| `/mesa/{n}` | Variable | Sincronizacion de marcador |

---

## Responsive / Mobile

- Sidebar colapsa en pantallas < 768px
- Grid de grupos pasa de 2 columnas a 1
- Referee scoreboard (`/mesa/{n}`) optimizado para movil (standalone, touch-friendly)
- Print center tabs se hacen scrolleables horizontalmente

---

## Conteo de Rutas

| Area | GET | POST | Total |
|------|-----|------|-------|
| Core (home, tournaments) | 3 | 5 | 8 |
| Import (players, pairs, teams) | 5 | 12 | 17 |
| Groups | 4 | 3 | 7 |
| Matches | 3 | 4 | 7 |
| Standings | 3 | 2 | 5 |
| Bracket | 6 | 9 | 15 |
| Results & Certificates | 3 | 1 | 4 |
| Scheduler | 5 | 8 | 13 |
| Live & Tables | 5 | 8 | 13 |
| Referee (`/mesa`) | 1 | 5 | 6 |
| API (JSON) | 3 | 0 | 3 |
| Display | 1 | 0 | 1 |
| Print/Preview | 8 | 8 | 16 |
| Exports | 4 | 0 | 4 |
| Settings | 2 | 2 | 4 |
| License | 2 | 1 | 3 |
| **Total** | **~58** | **~68** | **~126** |

---

## Decisiones de Diseno

### Por que hub por categoria?
En un torneo real, el operador trabaja categoria por categoria. El hub `/category/{cat}` le da todo lo que necesita: grupos, standings, bracket, resultados. No tiene que buscar en menus.

### Por que tabs en Print Center?
Con 3+ categorias, el print center tenia 30+ botones visibles. Los tabs reducen la carga cognitiva: selecciona categoria, ve solo lo relevante.

### Por que selector de mesa en el arbitro?
En torneos con multiples mesas, el arbitro puede necesitar cambiar de mesa sin escanear otro QR. El dropdown lo permite sin salir de la interfaz.

### Por que back button con etiqueta y no generico?
"Volver" no comunica destino. `← MS` le dice al usuario exactamente a donde va. Reduce la ansiedad de navegacion ("si hago click, pierdo lo que estoy viendo?").

### Por que no breadcrumbs?
La jerarquia es poco profunda (max 4 niveles). Un back button descriptivo + sidebar es suficiente. Breadcrumbs agregarian ruido visual en una interfaz ya densa.
