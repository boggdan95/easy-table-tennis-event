# Testing Guide - Easy Table Tennis Event Manager V1

Este documento explica cómo probar todas las funcionalidades del proyecto.

## 🚀 Ejecución Rápida

### Windows
```bash
test_project.bat
```

### Linux/Mac
```bash
chmod +x test_project.sh
./test_project.sh
```

El script automáticamente:
1. ✅ Limpia datos previos
2. ✅ Importa 12 jugadores de ejemplo (U13)
3. ✅ Crea 3 grupos round robin
4. ✅ Calcula standings iniciales
5. ✅ Genera bracket knockout
6. ✅ Exporta todo a CSV
7. ✅ Lanza el panel web en http://127.0.0.1:8000

---

## 📋 Pruebas Manuales Paso a Paso

Si prefieres ejecutar cada paso manualmente para entender el flujo:

### 1. Limpiar Datos Anteriores
```bash
# Windows
rmdir /s /q .ettem
rmdir /s /q out
mkdir out

# Linux/Mac
rm -rf .ettem out
mkdir -p out
```

### 2. Importar Jugadores
```bash
# Español (default)
ettem import-players --csv data/samples/players.csv --category U13

# Inglés
ettem --lang en import-players --csv data/samples/players.csv --category U13
```

**Resultado esperado:**
- Importa 12 jugadores
- Crea archivo `.ettem/ettem.sqlite`
- Asigna seeds automáticamente basados en ranking

### 3. Construir Grupos
```bash
ettem build-groups --config config/sample_config.yaml --out out/
```

**Resultado esperado:**
- Crea 3 grupos de 4 jugadores
- Distribución snake (serpiente) de seeds
- Genera fixture round robin para cada grupo
- Muestra resumen de grupos y partidos

### 4. Ver Grupos en Panel Web
```bash
ettem open-panel
```

Abre http://127.0.0.1:8000 y verás:
- Lista de categorías (U13)
- Grupos con jugadores
- Partidos pendientes por grupo

### 5. Ingresar Resultados (Web Panel)

En el panel web:
1. Navega a **Category: U13**
2. Selecciona un grupo (ej: "Group A")
3. Click en **"Ver Partidos"**
4. Para cada partido:
   - Click **"Ingresar Resultado"**
   - Opciones:
     - **Partido Normal**: Ingresa sets (ej: 11-9, 11-7, 9-11)
     - **Walkover**: Marca checkbox y selecciona ganador
   - Click **"Guardar"**

**Validaciones automáticas:**
- Sets deben ser 11+ puntos
- Deuce a 10-10 requiere ganar por 2
- Best of 5 (mínimo 3 sets, máximo 5)
- Ganador debe tener mayoría de sets

### 6. Calcular Standings
```bash
ettem compute-standings --out out/
```

**Resultado esperado:**
- Calcula puntos por jugador (victoria=2, derrota=1, WO=0)
- Aplica desempate si ≥3 empatados:
  1. Sets ratio
  2. Points ratio
  3. Seed
- Muestra tabla de standings por grupo

### 7. Construir Bracket
```bash
ettem build-bracket --out out/
```

**Resultado esperado:**
- Toma 1ros y 2dos de cada grupo (6 jugadores)
- Crea bracket de 8 posiciones (next power of 2)
- G1 en slot 1 (top)
- G2 en último slot (bottom)
- Resto sorteados (determinista con random_seed)
- 2dos en mitad opuesta a su 1ro
- Rellena con BYEs
- Marca warnings si mismo país en 1ra ronda

### 8. Ver Bracket en Panel Web

En el panel web:
1. Navega a **Category: U13**
2. Click en **"Ver Llave"** o **"Bracket"**
3. Verás el cuadro eliminatorio con:
   - Rondas (SF → F)
   - Jugadores posicionados
   - BYEs marcados
   - Warnings de mismo país

### 9. Exportar Datos
```bash
# Exportar grupos
ettem export --what groups --format csv --out out/

# Exportar standings
ettem export --what standings --format csv --out out/

# Exportar bracket
ettem export --what bracket --format csv --out out/
```

**Archivos generados:**
- `out/groups.csv` - Lista de grupos con jugadores
- `out/standings.csv` - Clasificación detallada
- `out/bracket.csv` - Llave eliminatoria con slots

---

## 🌍 Pruebas de Internacionalización

### Español (default)
```bash
ettem import-players --csv data/samples/players.csv --category U13
# O explícitamente:
ettem --lang es import-players --csv data/samples/players.csv --category U13
```

### Inglés
```bash
ettem --lang en import-players --csv data/samples/players.csv --category U13
```

### Variable de Entorno
```bash
# Windows
set ETTEM_LANG=en
ettem import-players --csv data/samples/players.csv --category U13

# Linux/Mac
export ETTEM_LANG=en
ettem import-players --csv data/samples/players.csv --category U13
```

**Qué se traduce:**
- Mensajes del CLI
- Salidas de consola
- Mensajes de error
- Textos del panel web (próximamente en templates)

---

## 🎨 Explorar la Interfaz Web

### Características principales:

#### 1. **Home** (http://127.0.0.1:8000)
- Lista de categorías registradas
- Acceso rápido a cada categoría

#### 2. **Vista de Categoría** (/category/U13)
- Muestra todos los grupos
- Jugadores por grupo con seeds
- Botón "Recalcular Standings"

#### 3. **Partidos por Grupo** (/group/{id}/matches)
- Lista de todos los partidos
- Estado: Pendiente / Completado / Walkover
- Formulario para ingresar resultados
- Editar/Eliminar resultados existentes

#### 4. **Clasificación** (/group/{id}/standings)
- Tabla de standings ordenada
- Columnas: Pos, Jugador, PJ, G, P, SW, SL, PW, PL, Pts
- Ratios calculados para desempates

#### 5. **Hoja de Grupo** (/group/{id}/sheet)
- Matriz de resultados (estilo tradicional)
- Muestra enfrentamientos directos
- Vista de resultados por sets

#### 6. **Llave Eliminatoria** (/category/U13/bracket)
- Visualización del bracket
- Slots organizados por ronda
- Indicadores de BYE
- Warnings de mismo país

### Estilos y Botones:
- ✅ **Verde** (Success) - Acciones principales
- ⚠️ **Amarillo** (Warning) - Editar
- ❌ **Rojo** (Danger) - Eliminar
- ℹ️ **Azul** (Primary) - Información

---

## 🧪 Tests Automatizados

### Ejecutar todos los tests:
```bash
pytest
```

### Ejecutar tests específicos:
```bash
# Tests de grupos
pytest tests/test_groups.py -v

# Tests de standings
pytest tests/test_standings.py -v

# Tests de bracket
pytest tests/test_bracket.py -v

# Tests de validación
pytest tests/test_validation.py -v

# Tests de i18n
pytest tests/test_i18n.py -v

# Tests de export
pytest tests/test_export.py -v
```

### Con cobertura:
```bash
pytest --cov=ettem --cov-report=term-missing
```

---

## 📊 Datos de Ejemplo

El archivo `data/samples/players.csv` contiene:
- 12 jugadores
- Categoría: U13
- Países: ESP (8), MEX (2), ARG (2)
- Rankings: 1200 a 650 puntos

**Grupos esperados con 4 jugadores:**
- Grupo A: Seeds 1, 6, 7, 12
- Grupo B: Seeds 2, 5, 8, 11
- Grupo C: Seeds 3, 4, 9, 10

---

## ✅ Checklist de Pruebas

- [ ] Importar jugadores desde CSV
- [ ] Validación de datos (género, país, ranking)
- [ ] Construcción de grupos (snake seeding)
- [ ] Generación de fixture round robin
- [ ] Panel web accesible en http://127.0.0.1:8000
- [ ] Ingresar resultados de partidos
- [ ] Validación de scores (11 puntos, deuce, etc.)
- [ ] Editar/eliminar resultados
- [ ] Walkover functionality
- [ ] Cálculo de standings
- [ ] Desempate ≥3 jugadores (ratios)
- [ ] Construcción de bracket
- [ ] Posicionamiento G1 top, G2 bottom
- [ ] BYEs generados correctamente
- [ ] Exportar a CSV (groups, standings, bracket)
- [ ] i18n español
- [ ] i18n inglés
- [ ] Estilos y botones funcionan
- [ ] Navegación entre páginas

---

## 🐛 Troubleshooting

### Error: "ModuleNotFoundError: No module named 'ettem'"
```bash
# Instalar el paquete en modo desarrollo
pip install -e .
```

### Error: "Python 3.11 required"
El proyecto requiere Python 3.11+. Verifica tu versión:
```bash
python --version
```

### Error: "Database locked"
Cierra todas las instancias del panel web:
```bash
# Windows
taskkill /f /im python.exe

# Linux/Mac
pkill -f "ettem open-panel"
```

### Panel web no carga
Verifica que el puerto 8000 esté libre:
```bash
# Windows
netstat -ano | findstr :8000

# Linux/Mac
lsof -i :8000
```

---

## 📝 Notas

- **V1 NO incluye scheduler**: Las funciones de asignación de mesas/horarios están planeadas para V1.1
- **Base de datos**: SQLite en `.ettem/ettem.sqlite` (offline-first)
- **Exportaciones**: Solo CSV en V1 (PDF/Excel planeados para futuro)
- **Modo desarrollo**: El servidor web se reinicia automáticamente en cambios (uvicorn)

---

## 🎯 Siguiente Paso: V1.1

Una vez que hayas probado todo y esté funcionando:
- [ ] Confirmar que todo funciona
- [ ] Reportar cualquier bug encontrado
- [ ] Preparar para V1.1 (scheduler, mesas, múltiples categorías simultáneas)

¡Disfruta probando el sistema! 🏓
