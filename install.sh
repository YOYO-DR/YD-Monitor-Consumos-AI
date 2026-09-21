#!/usr/bin/env bash
# Instala o actualiza monitor-consumos en el sistema.
#
# Se puede usar de dos formas:
#   1. Local: desde un clon ya descargado
#        ./install.sh [--force]
#   2. Remoto: descarga/actualiza el repo y lo instala en un paso
#        curl -fsSL https://raw.githubusercontent.com/YOYO-DR/YD-Monitor-Consumos-AI/main/install.sh | bash
#
# Idempotente: se puede relanzar sin miedo.
set -euo pipefail

REPO_HTTPS="https://github.com/YOYO-DR/YD-Monitor-Consumos-AI.git"
DEFAULT_INSTALL_DIR="$HOME/.local/share/monitor-consumos"
DESKTOP_FILE_NAME="monitor-consumos.desktop"
APPLICATIONS_DIR="$HOME/.local/share/applications"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=11

# -----------------------------------------------------------------------------
# Preflight: comprobar que el sistema tiene lo mínimo para que esto funcione.
# Las estrictas abortan; las opcionales solo avisan y siguen.
# -----------------------------------------------------------------------------
missing=()
warn_missing=()

need_cmd() { command -v "$1" >/dev/null 2>&1 || missing+=("$1"); }
soft_cmd() { command -v "$1" >/dev/null 2>&1 || warn_missing+=("$1"); }

need_cmd bash
need_cmd git
need_cmd python3
need_cmd sed
need_cmd tr
need_cmd head

soft_cmd xdg-user-dir    # sin él, Desktop cae a $HOME/Desktop
soft_cmd curl            # útil si en el futuro hay descarga directa

if [ ${#missing[@]} -gt 0 ]; then
    echo "Faltan programas requeridos para instalar monitor-consumos:" >&2
    for cmd in "${missing[@]}"; do
        echo "  - $cmd" >&2
    done
    echo "" >&2
    echo "Instálalos con el gestor de paquetes de tu distro (apt, dnf, pacman...) y vuelve a ejecutar." >&2
    exit 1
fi

# Versión de Python: pyproject exige >=3.11. sys.exit(0)=OK, exit !=0=error,
# así que negamos el resultado de la comparación para que solo falle cuando
# python es demasiado viejo.
if ! python3 -c "import sys; sys.exit(not (sys.version_info >= ($MIN_PYTHON_MAJOR, $MIN_PYTHON_MINOR)))"; then
    echo "Se necesita Python >= ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}, pero python3 es:" >&2
    python3 --version >&2
    echo "Instala una versión reciente de Python o ajusta pyproject.toml." >&2
    exit 1
fi

# pip y venv se comprueban aquí (no antes) porque la lógica de instalación los
# usa por comandos y, si faltan, fallaremos con un mensaje claro más abajo.
if ! python3 -m pip --version >/dev/null 2>&1; then
    echo "Falta el módulo 'pip' en python3. Instálalo (p. ej. 'apt install python3-pip') y vuelve a ejecutar." >&2
    exit 1
fi
if ! python3 -m venv --help >/dev/null 2>&1; then
    echo "Falta el módulo 'venv' en python3. Instálalo (p. ej. 'apt install python3-venv') y vuelve a ejecutar." >&2
    exit 1
fi

if [ ${#warn_missing[@]} -gt 0 ]; then
    echo "Aviso: faltan algunas utilidades opcionales (${warn_missing[*]}). El instalador seguirá, pero puede que pierdas algún detalle de integración con el escritorio." >&2
fi

if command -v xdg-user-dir >/dev/null 2>&1; then
    DESKTOP_DIR="$(xdg-user-dir DESKTOP)"
else
    DESKTOP_DIR="$HOME/Desktop"
fi

force=0
case "${1:-}" in
    --force|-f) force=1 ;;
    "") ;;
    *) echo "uso: $0 [--force]" >&2; exit 2 ;;
esac

# -----------------------------------------------------------------------------
# Detección: ¿estamos corriendo desde un clon local o desde un pipe (curl|bash)?
# -----------------------------------------------------------------------------
# Si el script se ejecuta por pipe (`curl ... | bash`), BASH_SOURCE[0] no es un
# archivo real existente en disco. En ese caso nos aseguramos de que el repo
# esté clonado en DEFAULT_INSTALL_DIR y relanzamos el script desde ahí.
_script_path="${BASH_SOURCE[0]:-}"
if [ -n "$_script_path" ] && [ -f "$_script_path" ]; then
    PROJECT_DIR="$(cd "$(dirname "$_script_path")" && pwd)"
else
    PROJECT_DIR="$DEFAULT_INSTALL_DIR"
    echo "==> Instalando desde origen remoto vía one-liner"

    if [ -d "$PROJECT_DIR/.git" ]; then
        echo "    Repo ya presente en $PROJECT_DIR: actualizando con git pull..."
        git -C "$PROJECT_DIR" pull --ff-only origin main || {
            echo "    Aviso: git pull falló (cambios locales o red). Continuando con lo que hay..."
        }
    else
        echo "    Clonando en $PROJECT_DIR..."
        mkdir -p "$(dirname "$PROJECT_DIR")"
        git clone "$REPO_HTTPS" "$PROJECT_DIR"
    fi

    # Cede el control al script dentro del repo clonado, pasándole los argumentos
    exec bash "$PROJECT_DIR/install.sh" "$@"
fi

# -----------------------------------------------------------------------------
# Lógica de instalación (ya dentro de un clon local garantizado)
# -----------------------------------------------------------------------------
VENV_DIR="$PROJECT_DIR/.venv"
VERSION_FILE="$PROJECT_DIR/.install.version"
PYPROJECT="$PROJECT_DIR/pyproject.toml"

# Lee la versión declarada en pyproject.toml bajo [project].
project_version() {
    sed -n '/^\[project\]/,/^\[/p' "$PYPROJECT" \
        | sed -n 's/^version[ ]*=[ ]*"\([^"]*\)".*/\1/p' | head -n1
}

installed_version() {
    [ -f "$VERSION_FILE" ] || { echo ""; return; }
    tr -d '[:space:]' < "$VERSION_FILE"
}

PROJECT_VERSION="$(project_version)"
INSTALLED_VERSION="$(installed_version)"

echo "==> Directorio:        $PROJECT_DIR"
echo "==> Versión declarada: $PROJECT_VERSION"
echo "==> Versión instalada: ${INSTALLED_VERSION:-ninguna}"

needs_install=0
if [ "$force" -eq 1 ]; then
    echo "    (--force: reinstalando)"
    needs_install=1
elif [ -z "$INSTALLED_VERSION" ]; then
    echo "    Sin marca de instalación previa: instalación nueva."
    needs_install=1
elif [ "$INSTALLED_VERSION" != "$PROJECT_VERSION" ]; then
    echo "    Cambió la versión: actualizando."
    needs_install=1
elif [ ! -d "$VENV_DIR" ] || [ ! -x "$VENV_DIR/bin/python" ]; then
    echo "    Falta el venv o el python de dentro: reinstalando."
    needs_install=1
else
    echo "    Versión coincide y el venv está sano: no se reinstala."
fi

if [ "$needs_install" -eq 1 ]; then
    echo "==> Preparando el entorno virtual"
    if [ ! -d "$VENV_DIR" ]; then
        python3 -m venv "$VENV_DIR"
    fi
    "$VENV_DIR/bin/pip" install --upgrade pip --quiet
    "$VENV_DIR/bin/pip" install -e "$PROJECT_DIR" --quiet
    "$VENV_DIR/bin/playwright" install chromium

    printf '%s' "$PROJECT_VERSION" > "$VERSION_FILE"
    echo "    marca de versión actualizada en $VERSION_FILE"
else
    # Asegura que el chromium de pruebas esté listo sin reinstalar el venv.
    "$VENV_DIR/bin/playwright" install chromium >/dev/null 2>&1 || true
fi

echo "==> Creando el lanzador de escritorio"
mkdir -p "$APPLICATIONS_DIR"

DESKTOP_ENTRY="[Desktop Entry]
Type=Application
Name=Monitor de consumos
Comment=Widget de bandeja para vigilar el consumo de cuentas de IA (v${PROJECT_VERSION})
Exec=\"$VENV_DIR/bin/python\" \"$PROJECT_DIR/run.py\"
Icon=utilities-system-monitor
Terminal=false
Categories=Utility;
"

printf '%s' "$DESKTOP_ENTRY" > "$APPLICATIONS_DIR/$DESKTOP_FILE_NAME"
chmod +x "$APPLICATIONS_DIR/$DESKTOP_FILE_NAME"
echo "    menú de aplicaciones: $APPLICATIONS_DIR/$DESKTOP_FILE_NAME"

if [ -d "$DESKTOP_DIR" ]; then
    printf '%s' "$DESKTOP_ENTRY" > "$DESKTOP_DIR/$DESKTOP_FILE_NAME"
    chmod +x "$DESKTOP_DIR/$DESKTOP_FILE_NAME"
    echo "    escritorio: $DESKTOP_DIR/$DESKTOP_FILE_NAME"
    echo "    (la primera vez, tu gestor de archivos puede pedirte 'Permitir ejecución' o 'Confiar' al hacer doble clic)"
fi

echo
echo "Listo (v${PROJECT_VERSION}). Búscalo como 'Monitor de consumos' en el menú de aplicaciones,"
echo "o lánzalo a mano con:"
echo "  $VENV_DIR/bin/python $PROJECT_DIR/run.py"
echo
echo "Para que arranque solo con la sesión, abre la app -> Cuentas... ->"
echo "Preferencias -> 'Iniciar automáticamente con el sistema'."
