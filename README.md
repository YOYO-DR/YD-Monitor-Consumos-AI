# Monitor de consumos

Widget de bandeja para vigilar el consumo de cuentas de IA. Ahora mismo soporta
**MiniMax**, **Claude** y **OpenCode Zen**; la arquitectura está preparada
para añadir más proveedores, y admite **varias cuentas del mismo
proveedor**.

El icono de la bandeja es un anillo que refleja la ventana más cargada de todas
tus cuentas y cambia de color: verde por debajo del 70 %, ámbar a partir del
70 %, rojo a partir del 90 %. Al pulsarlo se despliega el panel con el detalle.

## Instalación

```bash
./install.sh
```

Crea el entorno virtual, instala las dependencias y Chromium, y deja un
icono de "Monitor de consumos" tanto en el menú de aplicaciones como en tu
escritorio (la primera vez que lo abras desde ahí, tu gestor de archivos
puede pedirte "Permitir ejecución" o "Confiar"). Se puede volver a ejecutar
sin miedo: todo lo que crea, lo sobrescribe.

Instalación manual, sin icono ni menú:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/playwright install chromium
```

## Uso

```bash
./run.py
```

O, si instalaste con `install.sh`, desde el menú de aplicaciones o el icono
del escritorio. En **Cuentas… → Preferencias** hay un checkbox **"Iniciar
automáticamente con el sistema"**: lo activa/desactiva escribiendo o
borrando un `.desktop` en `~/.config/autostart/` (el mecanismo estándar de
autoarranque de GNOME/KDE/XFCE), sin tocar systemd ni pedir contraseña.

El menú del icono de la bandeja tiene:

| Entrada | Qué hace |
|---|---|
| **Ver consumo** | Abre y cierra el panel |
| **Cuentas…** | Ventana para añadir, renombrar y eliminar cuentas |
| **Actualizar ahora** | Fuerza una lectura sin esperar al siguiente ciclo |
| **Anclar al escritorio** | Deja el panel fijo y siempre visible |
| **Salir** | Termina el proceso |

La primera vez abre el navegador para que inicies sesión. A partir de ahí el
widget usa peticiones HTTP puras: **no deja ningún navegador corriendo**.

### Varias cuentas

En **Cuentas…** puedes dar de alta tantas como quieras, incluso varias de
MiniMax. Cada una tiene su propio perfil de navegador
(`~/.config/monitor-consumos/browser-profiles/<id>/`), así que los logins no se
pisan entre sí: si compartieran perfil, la segunda cuenta heredaría la sesión de
la primera y acabarías viendo dos veces el mismo consumo.

Eliminar una cuenta borra también su credencial y su perfil de navegador.

### Panel anclado al escritorio

Con **Anclar** el panel deja de comportarse como un menú y pasa a ser un widget
de escritorio: siempre encima, sin barra de título, fuera de la barra de tareas
y del alt-tab, y **arrastrable** con el ratón. Recuerda dónde lo dejaste.

La **✕** del panel solo lo esconde; la aplicación sigue viva en la bandeja. Para
terminar el proceso está «Salir» en el menú del icono.

### Intervalo de actualización

Por defecto relee cada **30 segundos** (además de al abrir el panel). Se cambia
en **Cuentas… → Preferencias**, entre 5 y 3600 segundos. La consola web de
MiniMax usa 5 s; 30 s va sobrado para un widget y no machaca el endpoint.

La sesión de MiniMax dura unos 40 días. Cuando caduca, el widget lo detecta, te
avisa con una notificación y ofrece el botón de volver a entrar.

### Google dice «es posible que el navegador o la aplicación no sean seguros»

Google bloquea su OAuth cuando cree que el navegador está pilotado por un
programa. Dos salidas:

1. **Entra por email en vez de por Google.** En la pantalla de MiniMax usa el
   campo *«Enter your email»* → *Continue* y mete el código que te llega al
   correo. Ese camino no pasa por Google, así que su detector no interviene.
   Funciona siempre.
2. El widget ya lanza el **Chrome del sistema** (no el Chromium de pruebas de
   Playwright) y le quita los delatores de automatización: `navigator.webdriver`
   queda en `false`, `window.chrome` presente y el user-agent es el real. Con
   eso el login de Google suele pasar, pero es una carrera contra un detector
   que cambia; si algún día vuelve a fallar, tira de la opción 1.

El perfil del navegador se guarda en `~/.config/monitor-consumos/browser-profile/`,
así que la sesión con Google o GitHub sobrevive: renovar la credencial dentro de
40 días será un par de clics, sin volver a teclear la contraseña.

## Cómo obtiene los datos

### MiniMax

No publica un endpoint de consumo en su API, así que se usa el mismo que
consulta su consola web:

```
GET https://platform.minimax.io/backend/account/token_plan/remains_percent
```

Comprobado contra la red real:

- La única credencial necesaria es la cookie **`_token`** (un JWT, `HttpOnly`)
  del dominio `platform.minimax.io`.
- La cabecera `x-group-id` que manda la web **no** es obligatoria.
- Sin cookie válida responde **HTTP 200** con `base_resp.status_code = 1016`
  (`invalid api key`), no un 401. Por eso hay que mirar el cuerpo y no solo el
  código de estado.
- La respuesta trae `end_time` y `weekly_end_time`, que alimentan la cuenta
  atrás hasta el reinicio de cada ventana.

### Claude

No hace login por navegador: reutiliza la sesión OAuth que **Claude Code** ya
deja en `~/.claude/.credentials.json` la primera vez que ejecutas `claude`. Al
dar de alta la cuenta, el widget solo lee ese fichero; si no existe, pide
ejecutar `claude` primero.

```
GET https://api.anthropic.com/api/oauth/usage
```

Comprobado contra la red real:

- Cabeceras necesarias: `Authorization: Bearer <accessToken>`,
  `User-Agent: claude-code/<versión>` (sin ella responde 429) y
  `anthropic-beta: oauth-2025-04-20`.
- La respuesta trae `limits`: una lista de ventanas activas (`session`,
  `weekly_all`, …) con `percent` (0-100) y `resets_at` en ISO 8601.
- También trae gasto en dólares (`spend`, `extra_usage`) del "extra usage"
  opcional de los planes Max; no se muestra, es otra unidad (dinero, no % de
  cuota).

### OpenCode Zen

No hay API JSON ni API key de autoservicio para el balance: el dato solo
existe embebido en el HTML que sirve la propia página del workspace.

```
GET https://opencode.ai/workspace/<id>/go       -> HTML con el consumo embebido
```

Comprobado contra la red real:

- No existe una ruta genérica `/workspace` que redirija al workspace por
  defecto (responde 404): el `<id>` solo aparece en la URL a la que aterriza
  el propio login, así que se captura ahí en el momento del login, junto con
  las cookies, en vez de intentar "descubrirlo" después con otra petición.
- Como no hay un cookie documentado, se guardan **todas** las cookies del
  dominio `opencode.ai` tras el login.
- El HTML trae, sin ser JSON, bloques `rollingUsage` / `weeklyUsage` /
  `monthlyUsage`, cada uno con `usagePercent` (0-100) y `resetInSec`
  (segundos hasta el reinicio, no un timestamp).
- Es el proveedor más frágil de los tres: depende de que la web siga
  serializando el estado con esos mismos nombres de clave. Si `opencode.ai`
  cambia su frontend, este proveedor es el primero que hay que revisar.

Las credenciales se guardan en `~/.config/monitor-consumos/credentials/` con
permisos `0600`.

## Estructura

```
src/monitor_consumos/
├── config.py            rutas y constantes
├── settings.py          preferencias (anclado, posición, intervalo)
├── autostart.py         activa/desactiva el arranque con la sesión (XDG autostart)
├── core/                dominio, sin dependencias de Qt ni de red
│   ├── models.py        Quota, UsageSnapshot, Severity, errores
│   ├── account.py       una cuenta: id, proveedor, nombre
│   └── provider.py      contrato que cumple cada proveedor
├── auth/
│   ├── accounts.py      alta, baja y migración del formato antiguo
│   ├── store.py         credenciales en disco, una por cuenta
│   └── browser_login.py login interactivo con Playwright
├── providers/
│   ├── minimax.py       endpoint, parseo y extracción de credencial
│   ├── claude.py        endpoint, parseo y lectura de la sesión local de Claude Code
│   └── opencode.py      login por navegador y parseo del HTML embebido de OpenCode Zen
├── services/
│   ├── poller.py        relectura periódica de todas las cuentas
│   └── login.py         login en segundo plano
└── ui/
    ├── theme.py         colores, tipografía y espaciado
    ├── ring.py          anillo animado (QPainter + QPropertyAnimation)
    ├── panel.py         panel de consumo (desplegable o anclado)
    ├── manager.py       ventana de administración de cuentas
    └── tray.py          icono de bandeja y orquestación
```

### Ficheros en disco

```
~/.config/monitor-consumos/
├── accounts.json           índice de cuentas (sin secretos)
├── settings.json           preferencias de la interfaz
├── credentials/<id>.json   credencial por cuenta, permisos 0600
└── browser-profiles/<id>/  perfil de navegador por cuenta
```

Las peticiones de red y el login corren en hilos propios: el hilo de la interfaz
nunca se bloquea, así que las animaciones no dan tirones.

## Añadir otro proveedor

1. Implementa `core.provider.Provider` en `providers/loquesea.py`
   (`fetch()` y `extract_credential()`). Si el proveedor no necesita
   navegador porque la sesión ya existe en disco (como Claude), pon
   `login_mode = "local"` e implementa `read_local_credential()` en vez de
   `extract_credential()`.
2. Regístralo en `providers/__init__.py`.
3. `./run.py loquesea`

`core/` y `ui/` no saben nada de MiniMax ni de Claude, así que no hay que
tocarlos.

## Tests

```bash
.venv/bin/python test_monitor.py
```

Cubren el parseo de la respuesta real de MiniMax, Claude y OpenCode Zen, la
detección de sesión caducada, la lectura de la credencial local de Claude
Code, los permisos del fichero de credenciales, el formateo de duraciones y
el autoarranque.
