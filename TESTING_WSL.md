# Testing Guide for WSL (Windows Subsystem for Linux)

Como tienes Windows con WSL, puedes ejecutar el proyecto de **dos formas**:

---

## 🪟 **Opción 1: Ejecutar desde Windows (PowerShell/CMD)**

**Ventajas:**
- Usa tu instalación de Python de Windows
- El navegador se abre automáticamente
- Más familiar si trabajas en Windows

**Pasos:**

```powershell
# En PowerShell o CMD
cd "C:\Users\boggd\Documents\Boggdan - Projects\Code\projects\personal\easy-table-tennis-event"

# Ejecutar script de Windows
.\test_project.bat
```

---

## 🐧 **Opción 2: Ejecutar desde WSL (Recomendado para desarrollo)**

**Ventajas:**
- Entorno Linux completo
- Mejor para desarrollo Python
- Comandos Unix nativos

**Pasos:**

### 1. Abrir WSL
```bash
# Desde PowerShell/CMD, inicia WSL:
wsl
```

### 2. Navegar al Proyecto
```bash
# WSL puede acceder a archivos de Windows en /mnt/c/
cd "/mnt/c/Users/boggd/Documents/Boggdan - Projects/Code/projects/personal/easy-table-tennis-event"
```

### 3. Verificar Python en WSL
```bash
# Verificar versión (necesitas Python 3.11+)
python3 --version

# Si no tienes Python 3.11+, instálalo:
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip
```

### 4. Crear Entorno Virtual (Primera vez)
```bash
# Crear venv
python3.11 -m venv .venv

# Activar venv
source .venv/bin/activate

# Instalar dependencias
pip install -e .
```

### 5. Ejecutar Script de Prueba
```bash
# Asegurar que el script es ejecutable
chmod +x test_project.sh

# Ejecutar
./test_project.sh
```

### 6. Abrir el Navegador
El servidor se ejecutará en `http://127.0.0.1:8000`

**Desde Windows**, abre tu navegador en:
```
http://localhost:8000
```

---

## 🔄 **Ejecutar Comandos Manualmente en WSL**

Si prefieres ejecutar paso a paso:

```bash
# Activar entorno virtual
source .venv/bin/activate

# 1. Limpiar datos
rm -rf .ettem out
mkdir -p out

# 2. Importar jugadores
ettem import-players --csv data/samples/players.csv --category U13

# 3. Construir grupos
ettem build-groups --config config/sample_config.yaml --out out/

# 4. Calcular standings
ettem compute-standings --out out/

# 5. Construir bracket
ettem build-bracket --out out/

# 6. Exportar
ettem export --what groups --format csv --out out/
ettem export --what standings --format csv --out out/
ettem export --what bracket --format csv --out out/

# 7. Abrir panel web
ettem open-panel
```

---

## 🌍 **Probar Internacionalización en WSL**

```bash
# Español (default)
ettem import-players --csv data/samples/players.csv --category U13

# Inglés
ettem --lang en import-players --csv data/samples/players.csv --category U13

# Usando variable de entorno
export ETTEM_LANG=en
ettem import-players --csv data/samples/players.csv --category U13
```

---

## 📂 **Acceso a Archivos entre WSL y Windows**

### Desde WSL acceder a Windows:
```bash
# Archivos de Windows están en /mnt/c/
cd /mnt/c/Users/boggd/Documents/...

# Ver archivos generados
ls -la out/
cat out/groups.csv
```

### Desde Windows acceder a WSL:
```powershell
# En el Explorador de Windows, escribe:
\\wsl$\Ubuntu\home\tu_usuario\

# O si instalaste el proyecto en /mnt/c/:
C:\Users\boggd\Documents\Boggdan - Projects\Code\projects\personal\easy-table-tennis-event\out\
```

---

## 🔧 **Troubleshooting en WSL**

### Error: "python3.11: command not found"
```bash
# Instalar Python 3.11
sudo apt update
sudo apt install software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt install python3.11 python3.11-venv python3.11-dev
```

### Error: "Permission denied" al ejecutar script
```bash
chmod +x test_project.sh
```

### Error: "Module not found: ettem"
```bash
# Asegurar que estás en el venv
source .venv/bin/activate

# Reinstalar en modo desarrollo
pip install -e .
```

### El navegador no abre automáticamente
```bash
# Normal en WSL - el servidor corre en WSL pero el navegador está en Windows
# Abre manualmente desde Windows:
# http://localhost:8000
```

### Puerto 8000 ocupado
```bash
# Ver qué proceso usa el puerto
sudo lsof -i :8000

# Matar proceso
sudo kill -9 <PID>

# O cambiar el puerto (editar src/ettem/webapp/app.py)
```

---

## ⚡ **Comandos Rápidos para WSL**

```bash
# Iniciar proyecto rápidamente
cd "/mnt/c/Users/boggd/Documents/Boggdan - Projects/Code/projects/personal/easy-table-tennis-event"
source .venv/bin/activate
./test_project.sh

# Detener servidor
Ctrl + C

# Salir de WSL
exit

# Ver logs de la app
tail -f out/standings.csv  # o cualquier output
```

---

## 🎯 **Recomendación**

Para **desarrollo**: Usa WSL (Opción 2)
- Mejor compatibilidad con herramientas Python
- Entorno más cercano a producción (si despliegas en Linux)
- Comandos Unix nativos

Para **prueba rápida**: Usa Windows (Opción 1)
- Más rápido si ya tienes Python instalado en Windows
- Menos pasos de configuración

---

## 📝 **Nota sobre el Navegador**

Cuando ejecutes desde WSL:
1. El servidor corre en **WSL (Linux)**
2. El navegador se abre en **Windows**
3. Ambos se comunican a través de `localhost:8000`
4. ¡Funciona perfectamente! 🎉

---

## ✅ **Próximos Pasos**

1. Elige tu opción (Windows o WSL)
2. Ejecuta el script de prueba
3. Explora la interfaz web en http://localhost:8000
4. Prueba ingresar algunos resultados
5. Repórtame cómo fue la experiencia
6. ¡Preparamos V1.1! 🚀
