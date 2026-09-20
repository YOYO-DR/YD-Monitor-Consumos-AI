#!/usr/bin/env bash
# Instala o actualiza monitor-consumos en el sistema:
#   - Lee la versión del proyecto desde pyproject.toml.
#   - Compara con la versión instalada (marcada en .install.version) y decide
#     si reinstalar o solo recrear los lanzadores de escritorio.
#   - Reinstala siempre que falte el venv, falte la marca o pidamos --force.
# Idempotente: se puede relanzar sin miedo.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
VERSION_FILE="$PROJECT_DIR/.install.version"
PYPROJECT="$PROJECT_DIR/pyproject.toml"
DESKTOP_FILE_NAME="monitor-consumos.desktop"
APPLICATIONS_DIR="$HOME/.local/share/applications"

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

# Lee la versión declarada en pyproject.toml. Solo el primer match de
# '^version = ' bajo [project], que es lo que pip usa.
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

echo "==> Versión declarada:  $PROJECT_VERSION"
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
    # Aun sin reinstalar, nos aseguramos de que el navegador de pruebas esté
    # listo: es barato y evita un fallo la primera vez que se use.
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
