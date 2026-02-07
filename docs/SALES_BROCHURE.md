# ETTEM - Easy Table Tennis Event Manager

### El software profesional para gestionar torneos de tenis de mesa

**Version 2.2 | 100% Offline | Listo para usar**

---

## El problema que resolvemos

Organizar un torneo de tenis de mesa es complejo: inscripciones, sorteos, grupos, clasificaciones, llaves eliminatorias, asignacion de mesas, horarios, marcadores en vivo, resultados para el publico...

La mayoria de los organizadores todavia usan hojas de calculo, pizarras y WhatsApp. Esto genera errores, retrasos y una experiencia poco profesional para jugadores y espectadores.

**ETTEM cambia eso.** Un solo programa que maneja todo el torneo, desde la inscripcion hasta la premiacion, sin necesitar internet.

---

## Por que ETTEM

### Funciona sin internet

ETTEM opera 100% offline. Toda la informacion se guarda localmente en tu computadora. Esto es fundamental para gimnasios, polideportivos y centros deportivos donde la conectividad es limitada o inexistente. Sin servidores en la nube, sin dependencias externas, sin sorpresas.

### Todo en un solo lugar

No necesitas combinar multiples herramientas. ETTEM integra:
- Inscripcion de jugadores
- Sorteo de grupos con snake seeding
- Fase de grupos (Round Robin)
- Clasificaciones con desempates avanzados
- Llave eliminatoria (Knockout)
- Programacion de mesas y horarios
- Marcador digital para arbitros (desde el celular)
- Pantalla publica de resultados en tiempo real
- Centro de impresion (hojas de partido, grupos, llaves, grillas)

### Cumple con las reglas de la ITTF

- Categorias estandar ITTF (U11, U13, U15, U17, U19, U21, MS, WS)
- Validacion de puntajes con reglas de deuce
- Formatos configurables (Mejor de 3, 5 o 7)
- Colocacion en llave segun normativa ITTF
- Deteccion de enfrentamientos entre jugadores del mismo pais

### No requiere conocimiento tecnico

ETTEM es una aplicacion web que se abre en tu navegador. La interfaz es intuitiva, con botones claros y flujos paso a paso. Si sabes usar un navegador de internet, sabes usar ETTEM.

---

## Funcionalidades principales

### 1. Dashboard del torneo

Vista general con todas las categorias, partidos pendientes y completados. Un vistazo rapido al estado completo del evento.

![Dashboard del torneo](screenshots/01_dashboard.png)

---

### 2. Gestion completa de categorias

Controla cada etapa del torneo: fase de grupos, clasificaciones, llave eliminatoria. Visualiza el progreso de cada categoria y el campeon al finalizar.

![Estado del torneo con campeon](screenshots/03_tournament_status.png)

---

### 3. Fase de grupos (Round Robin)

Partidos todos contra todos con asignacion automatica de mesa y hora. Marcadores en tiempo real, con estado visible de cada encuentro.

![Partidos de grupo](screenshots/07_group_matches.png)

---

### 4. Llave eliminatoria profesional

Bracket generado automaticamente respetando las reglas ITTF de colocacion, o creado manualmente con drag-and-drop. Vista de arbol imprimible con marcadores de cada ronda.

![Llave eliminatoria](screenshots/23_bracket_tree.png)

---

### 5. Programacion de mesas y horarios

Grilla visual para asignar partidos a mesas y horarios. Arrastra partidos para programarlos. Imprime la grilla para publicar en el venue.

![Grilla de programacion](screenshots/14_scheduler_grid.png)

---

### 6. Configuracion de mesas para arbitros

Define cuantas mesas tiene tu venue, el modo de arbitraje de cada una, y genera codigos QR para que los arbitros accedan al marcador desde su celular.

![Configuracion de mesas](screenshots/17_table_config.png)

---

### 7. Marcador digital para arbitros

El arbitro escanea el codigo QR con su celular y accede al marcador digital. Botones grandes de +/- para registrar puntos. El marcador se sincroniza en tiempo real con el sistema central. No necesita instalar ninguna aplicacion.

Dos modos de operacion:
- **Punto por punto:** El arbitro registra cada punto. Ideal para partidos importantes.
- **Resultado por set:** El arbitro ingresa el marcador final de cada set. Mas rapido para fases de grupo.

![Marcador de arbitro en celular](screenshots/19_referee_scoreboard.png)

---

### 8. Pantalla publica de resultados

Conecta un monitor o TV al servidor y muestra resultados en tiempo real. La pantalla rota automaticamente entre partidos en vivo, resultados recientes y proximos encuentros. Se actualiza cada 5 segundos sin intervencion manual. Tema oscuro optimizado para pantallas grandes.

![Pantalla publica](screenshots/20_public_display.png)

---

### 9. Codigos QR para cada mesa

Imprime los codigos QR y pegalos en cada mesa. Los arbitros escanean y acceden directamente al marcador de esa mesa. Sin configuracion, sin contraseñas, sin fricciones.

![Codigos QR](screenshots/18_qr_codes.png)

---

### 10. Centro de impresion

Genera e imprime todos los documentos del torneo desde un solo lugar:
- Hojas de partido individuales
- Hojas de grupo con matriz de resultados
- Arbol de llave eliminatoria
- Grilla de horarios
- Exportacion a CSV para Excel

![Centro de impresion](screenshots/16_print_center.png)

---

## Ventajas competitivas

| Caracteristica | ETTEM | Hojas de calculo | Otros software |
|---|---|---|---|
| Funciona sin internet | Si | Si | Generalmente no |
| Marcador desde celular | Si (QR, sin app) | No | Requiere app |
| Pantalla publica en TV | Si (incluido) | No | Costo extra |
| Bracket segun ITTF | Si (automatico) | Manual | Parcial |
| Bilingue (ES/EN) | Si | No aplica | Solo EN |
| Ejecutable standalone | Si (doble clic) | No aplica | Requiere instalacion |
| Impresion de documentos | Todo incluido | Manual | Parcial |

---

## Especificaciones tecnicas

- **Sistema operativo:** Windows 10 o superior
- **Formato:** Archivo ejecutable standalone (.exe), no requiere instalacion
- **Almacenamiento:** SQLite local (tus datos nunca salen de tu computadora)
- **Idiomas:** Español e Ingles
- **Interfaz:** Navegador web (Chrome, Edge, Firefox)
- **Red local:** Los arbitros se conectan via WiFi del venue (sin internet)
- **Tema visual:** Claro y oscuro

---

## Flujo tipico de un torneo

```
1. Abrir ETTEM (doble clic en el .exe)
2. Crear torneo y categorias
3. Importar jugadores desde CSV o agregarlos manualmente
4. Crear grupos (snake seeding automatico)
5. Programar mesas y horarios
6. Imprimir codigos QR para cada mesa
7. Iniciar partidos - arbitros registran puntajes desde su celular
8. La pantalla publica muestra resultados en tiempo real
9. Al completar grupos, calcular clasificaciones
10. Generar llave eliminatoria
11. Continuar hasta la final
12. Imprimir bracket con campeon
```

---

## Ideal para

- **Federaciones nacionales y regionales** que organizan torneos regulares con multiples categorias
- **Clubes de tenis de mesa** que realizan torneos internos o abiertos
- **Colegios e instituciones educativas** con eventos deportivos escolares
- **Organizadores de eventos WTT Youth, circuitos juveniles y torneos abiertos**
- **Cualquier organizador** que quiera ofrecer una experiencia profesional sin complicaciones

---

## Planes y licencias

ETTEM utiliza un sistema de licencias offline. La clave se activa una vez y funciona sin conexion a internet durante toda su vigencia.

| Plan | Duracion | Ideal para |
|---|---|---|
| **Mensual** | 1 mes | Organizadores ocasionales, prueba extendida |
| **Semestral** | 6 meses | Clubes con torneos regulares |
| **Anual** | 12 meses | Federaciones, mejor relacion costo-beneficio |

Todos los planes incluyen la totalidad de las funcionalidades. Sin versiones "lite" o "premium". Pagas una licencia y accedes a todo.

Contactanos para conocer los precios vigentes para tu pais o region.

---

## Preguntas frecuentes

**Necesito internet para usar ETTEM?**
No. ETTEM funciona 100% offline. Solo necesitas una red WiFi local (un router sin internet es suficiente) para que los arbitros se conecten desde sus celulares.

**Los arbitros necesitan instalar una app?**
No. El arbitro escanea el codigo QR con la camara de su celular y se abre el marcador en el navegador. Funciona en cualquier celular moderno (Android o iPhone).

**Puedo usar ETTEM en Mac o Linux?**
Actualmente el ejecutable standalone es para Windows. Si tienes Python instalado, puedes ejecutar ETTEM desde el codigo fuente en cualquier sistema operativo.

**Cuantas categorias puedo manejar en un torneo?**
No hay limite. Puedes crear todas las categorias que necesites (U11, U13, U15, MS, WS, etc.).

**Que pasa si se corta la luz?**
Los datos se guardan automaticamente en cada operacion. Al volver a abrir ETTEM, todo estara exactamente como lo dejaste.

**Puedo usar ETTEM en multiples computadoras a la vez?**
ETTEM esta diseñado para ejecutarse en una computadora central que actua como servidor. Los arbitros y la pantalla publica se conectan a este servidor por red local.

**En que idiomas esta disponible?**
Español e ingles. El idioma se cambia con un clic desde cualquier pantalla.

---

## Contacto

Estamos listos para ayudarte a profesionalizar tus torneos.

- **Demo personalizada:** Agenda una videollamada para ver ETTEM en accion con tus datos reales.
- **Cotizacion:** Solicita precios para tu federacion, club o evento.
- **Soporte:** Acompañamiento en tu primer torneo con ETTEM.

**Escríbenos para solicitar una demo o cotización.**

---

*ETTEM - Easy Table Tennis Event Manager*
*Software profesional para torneos de tenis de mesa*
*Version 2.2*
