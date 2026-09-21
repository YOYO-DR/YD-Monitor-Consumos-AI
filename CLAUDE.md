# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

El código, los comentarios y la interfaz están en español. Escribe igual.

## Comandos

```bash
./install.sh                      # venv + deps + playwright + lanzadores .desktop (idempotente)
./install.sh --force              # reinstalar aunque la versión no haya cambiado

# Desde otra máquina, sin clonar a mano:
curl -fsSL https://raw.githubusercontent.com/YOYO-DR/YD-Monitor-Consumos-AI/main/install.sh | bash

./run.py                          # arrancar (mete src/ en sys.path, no hace falta instalar)
.venv/bin/python test_monitor.py  # toda la batería
```

### Preflight de `install.sh`

Antes de hacer nada, `install.sh` valida que el sistema tenga lo mínimo para
funcionar. Aborta con un mensaje claro si falta algo:

- **Estrictas (aborta):** `bash`, `git`, `python3`, `sed`, `tr`, `head`, `pip`, `venv`,
  Python ≥ 3.11.
- **Opcionales (avisa y sigue):** `xdg-user-dir` (Desktop cae a `$HOME/Desktop`),
  `curl`.

Si el script lo ejecutas por `curl | bash` y aún no hay clon local, lo clona
en `~/.local/share/monitor-consumos` vía HTTPS y se relanza a sí mismo desde
ahí, así que cualquier ejecución posterior desde esa misma URL hace `git pull`
+ `pip install -e .` sin duplicar código.

### Versionado

La versión vive en `pyproject.toml` (`[project] version`). `install.sh` la lee, la
compara con `.install.version` (que escribe él mismo en el directorio del proyecto)
y reinstala el venv solo si:

- `--force`, **o**
- no existe `.install.version`, **o**
- la versión declarada no coincide con la guardada, **o**
- el venv está roto o falta.

En cualquier otro caso se limita a reescribir los `.desktop` (idempotente, barato).

**Cada vez que cambies el comportamiento del paquete de forma que merezca una
release, sube la versión en `pyproject.toml`** (`0.1.0` → `0.2.0` si añades algo,
`0.1.0` → `0.1.1` si es un parche). Sin cambio de versión, `./install.sh`
detectará que "ya está al día" y no reinstalará nada.

`.install.version` está en `.gitignore`: es estado local de cada máquina.

### Subir cambios

Repositorio remoto: `origin` apunta a `git@github.com:YOYO-DR/YD-Monitor-Consumos-AI.git`.
`git push` directo desde `main`; no hay rama ni política de PRs configurada todavía.

No hay pytest, linter ni formateador. `test_monitor.py` es un script de asserts:
para ejecutar uno solo, `.venv/bin/python -c "import test_monitor as t; t.test_real_response()"`,
y si el test toca disco (`test_accounts`, `test_settings`, `test_credential_store`,
`test_autostart`, `test_legacy_migration`, `test_account_removal_clears_credential`)
antes hay que llamar a `t._point_config_at(Path(tmp))`, que reescribe las rutas de
`config` para no pisar `~/.config/monitor-consumos`. `main()` ya lo hace con un
`TemporaryDirectory` nuevo por test.

## Arquitectura

App de bandeja PySide6. Tres capas que no se conocen entre sí:

- **`core/`**: dominio puro, sin Qt ni red. `Quota`/`UsageSnapshot`/`Severity` y las dos
  excepciones que mandan en todo el flujo: `AuthRequired` (hay que volver a iniciar sesión)
  vs. `FetchFailed` (fallo transitorio, se reintenta solo). `provider.Provider` es el contrato.
- **`providers/`**: un módulo por servicio, registrado en `providers/__init__.py:REGISTRY`.
  Traduce la respuesta del servicio a `UsageSnapshot` y decide cuál de las dos excepciones lanzar.
- **`ui/`**: Qt. No sabe qué proveedores existen; solo lee `REGISTRY` para el desplegable de alta.

Entre medias, `services/` mueve todo el trabajo bloqueante a `QThread` propios
(`poller.py` para el sondeo periódico de todas las cuentas, `login.py` para el navegador),
y `auth/` persiste: `accounts.py` el índice sin secretos, `store.py` una credencial `0600`
por cuenta, `browser_login.py` el login con Playwright.

`ui/tray.py` es el único orquestador: crea el poller y el login, conecta sus señales al panel,
al manager y al icono, y guarda los `UsageSnapshot` por cuenta.

### Invariantes que conviene no romper

- **Una cuenta ≠ un proveedor.** Todo se indexa por `account.id` (hex de 12), no por la clave
  del proveedor. Puede haber dos MiniMax. Cada cuenta tiene credencial y **perfil de navegador
  propios**: compartir perfil haría que el segundo login heredase la sesión del primero.
  `auth/accounts.py:_migrate_legacy` convierte el formato viejo (credencial por proveedor) la
  primera vez, y ese camino no debería perder sesiones.
- **Playwright solo en `auth/browser_login.py`.** El refresco va con `httpx` puro; no debe quedar
  ningún navegador vivo después del login.
- **Todo lo que escribe en `~/.config/monitor-consumos/` usa `os.open(..., 0o600)` + `os.replace`**,
  nunca `write_text` directo: ni ventana de fichero legible por otros ni fichero a medio escribir.
- **Ningún `fetch()` en el hilo de la UI**: las animaciones del anillo darían tirones. El poller
  además ignora un tick si el ciclo anterior sigue en vuelo.
- `login_mode` decide el alta: `"browser"` (por defecto) llama a `extract_credential(cookies, url)`
  en bucle mientras el usuario teclea — por eso debe lanzar `AuthRequired` hasta que el login haya
  terminado **de verdad** (OpenCode suelta cookies anónimas antes de autenticar); `"local"` llama a
  `read_local_credential()` y no abre navegador (Claude, que reusa `~/.claude/.credentials.json`).

### Cosas frágiles, documentadas en su módulo

Cada proveedor lleva en su docstring lo verificado contra la red real; léelo antes de tocarlo.
En corto: MiniMax devuelve **200 con `base_resp.status_code = 1016`** en vez de 401, así que hay
que mirar el cuerpo. Claude exige `User-Agent: claude-code/<versión>` o responde 429 —
`_USER_AGENT` en `providers/claude.py` es lo primero a subir si deja de funcionar. OpenCode no
tiene API: se saca a regex del HTML del workspace, y es lo primero que se rompe si cambian su web.

### Añadir un proveedor

Implementa `Provider` en `providers/`, regístralo en `REGISTRY`. `core/` y `ui/` no se tocan.
