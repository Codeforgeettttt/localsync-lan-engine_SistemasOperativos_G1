# Manual de usuario y puesta en marcha de LocalSync

**Uso previsto:** transferir archivos manualmente o mantener una carpeta sincronizada entre dos computadores de una red local. La sincronización requiere activación explícita y autenticación.

## 1. Preparación

Requisitos: Python 3.10 o superior, red LAN privada y puerto TCP 9001 disponible. Windows con el lanzador `py` o Ubuntu con `python3-venv`. Docker es **opcional** y solo se utiliza para simulación virtual.

Desde la raíz de un clon actualizado:

```bash
git switch main
git pull origin main
```

### Windows

Doble clic en `iniciar_localsync.bat`, o desde PowerShell:

```powershell
.\iniciar_localsync.bat
```

El iniciador prepara el entorno virtual `.venv`, instala las dependencias y abre el navegador cuando el servidor responda.

### Ubuntu

```bash
sudo apt install -y python3-venv python3-pip
bash iniciar_localsync.sh
```

**Dirección de la GUI:** `http://127.0.0.1:8080/`. **No abrir HTML como archivo** desde el explorador: la GUI necesita el backend de FastAPI.

## 2. Recorrido de la interfaz

| Sección | Para qué sirve |
| --- | --- |
| **Resumen** | Estado del receptor, archivos preparados y recibidos; accesos rápidos |
| **Transferencias** | Elegir puerto e IP, token, receptor, cargar, enviar, descargar y gestionar archivos |
| **Laboratorio virtual** | Ejecutar Docker o prueba TCP sin Docker; ver logs y descargar evidencia |
| **Actividad** | Consultar las últimas operaciones de la sesión del backend |

### Archivos de envío

- **+ Archivos:** selecciona uno o varios archivos locales.
- **Carpeta:** selecciona un directorio y sus subcarpetas desde un navegador compatible.
- **Arrastrar y soltar:** añade archivos mediante la zona de carga.
- **Enviar:** transfiere un archivo seleccionado.
- **Enviar todos los archivos:** envía la bandeja completa al nodo configurado.
- **SHA-256:** calcula y muestra el hash de archivo en la bandeja local.
- **Renombrar / Eliminar:** administra el archivo de **esa computadora**. No modifica el sistema remoto.

La GUI sube el archivo seleccionado primero a `archivos_para_enviar/` bajo el directorio del proyecto. Esto **no es todavía** transferencia LAN; el envío al otro equipo comienza al pulsar **Enviar** o **Enviar todos**.

### Archivos recibidos

Aparecen en `archivos_recibidos/` y pueden descargarse, renombrarse, eliminarse o comprobar su hash. La carpeta autorizada se protege frente a rutas externas y enlaces simbólicos.

## 3. Transferencia paso a paso entre dos equipos

**Requisitos comunes:** ambos computadores en la misma LAN privada, LocalSync abierto localmente en cada uno, puerto 9001 permitido **solo entre esas direcciones** y mismo token de al menos 16 caracteres.

1. En el **equipo B** (destino), abre **Transferencias** y selecciona **Red local (0.0.0.0)**.
2. Genera un token aleatorio en la GUI o introduce un secreto compartido seguro. **Copia el mismo al equipo A por un canal privado**, nunca en GitHub.
3. En B, inicia el receptor en el puerto 9001. Comprueba que muestre **EN LÍNEA**.
4. Consulta la IPv4 del receptor. La GUI muestra IPs privadas detectadas; en Windows usa `ipconfig` y en Ubuntu `hostname -I` si hay varios adaptadores.
5. En el **equipo A**, en **Conectar con un nodo**, escribe esa IPv4 de B, el puerto 9001 y el mismo token.
6. Pulsa **Comprobar conexión**. Debes observar la confirmación de `ACK`.
7. Prepara uno o más archivos en A; pulsa **Enviar** o **Enviar todos los archivos**.
8. Verifica la confirmación en A y la aparición de archivos en B. Calcula SHA-256 en ambas máquinas para contrastar que el contenido coincide.
9. Para enviar **B → A**, inicia el receptor en A y repite el envío en sentido inverso.

No es necesario que la GUI HTTP esté disponible por la red: cada usuario administra el panel **desde su propio equipo**. La comunicación entre equipos utiliza el puerto TCP, no el HTTP 8080.

## 4. Qué ocurre con nombres duplicados

Por defecto, el receptor usa `keep-both`:

- Si el archivo entrante es idéntico al existente, confirma sin duplicarlo.
- Si tiene **otro contenido con el mismo nombre**, conserva el original y crea una copia como `informe.conflict-<12 caracteres SHA>.pdf`.
- En el cliente CLI existen `--on-conflict reject` (rechaza) y `overwrite` (sustituye explícitamente). Se recomienda **keep-both** para auditoría y uso normal.

Eliminar un archivo desde la bandeja manual solo lo elimina localmente. La sincronización automática tiene una opción separada de propagación de borrados, **desactivada por defecto**; requiere autorización de ambos equipos y archiva el archivo en papelera.

## 5. Ejecución por línea de comandos

En el equipo B (receptor, con token en variable de entorno):

```bash
python3 -m src.backend.network.p2p_socket --host 0.0.0.0 --port 9001 --directory archivos_recibidos
```

En el equipo A (emisor, mismo token):

```bash
python3 -m src.backend.network.cliente_tcp --host 192.168.1.25 --port 9001
python3 -m src.backend.network.cliente_tcp --host 192.168.1.25 --port 9001 --file archivo.txt --retries 2
python3 -m src.backend.network.cliente_tcp --host 192.168.1.25 --port 9001 --directory documentos --remote-prefix recibidos_grupo
```

`192.168.1.25` es un **ejemplo**: reemplázalo por la IP real del destinatario. La variable `LOCALSYNC_AUTH_TOKEN` debe estar establecida en **cada terminal** que use cliente/receptor. Evita poner secretos en comandos de la shell.

**Verificación de hashes:**

```powershell
Get-FileHash .\archivo.txt -Algorithm SHA256
```

```bash
sha256sum archivo.txt
```

## 6. Laboratorio de prueba

### A. Prueba local sin Docker

Dentro del panel, **Laboratorio virtual → Probar sin Docker**, o:

```bash
python simulacion/demo_local.py
```

Se comprueba que dos servidores TCP **en el mismo equipo** reciban envíos, verifiquen SHA-256 y gestionen conflictos. **No son dos computadores diferentes**.

### B. Dos contenedores Linux

Abre Docker Desktop (modo contenedores Linux) o Docker Engine + Compose. En el panel, **Laboratorio virtual → Ejecutar Docker (dos Linux)**, o:

```bash
python simulacion/demo.py
```

Los nodos `nodo-a` y `nodo-b` intercambian archivos por una red Docker interna; el script valida hashes y conflictos. Son dos contenedores aislados pero **comparten kernel**, no dos máquinas virtuales completas.

Comandos de mantenimiento:

```bash
python simulacion/demo.py --status
python simulacion/demo.py --cleanup
```

`--cleanup` elimina contenedores y volúmenes de este laboratorio, incluidos sus archivos de prueba. Desde la GUI se puede descargar un archivo de evidencia **solo de la ejecución que acaba de realizarse en esa sesión**.

## 7. Problemas más comunes

| Situación | Qué comprobar |
| --- | --- |
| El navegador muestra error de conexión | Ejecutar lanzador y comprobar que Uvicorn use `127.0.0.1:8080` |
| Puerto 8080 ocupado | Cerrar otro proceso/instancia que ya lo utilice |
| No se conecta con otro equipo | IPv4 del receptor, red privada, firewall, puerto 9001, receptor iniciado |
| Token rechazado | Verificar que ambos usuarios tengan el **mismo** token |
| Archivo rechazado | Tamaño ≤100 MiB, nombre relativo permitido, formato válido |
| Archivo con nombre repetido | Buscar una copia `.conflict-<hash>` en recibidos |
| Docker no disponible | Abrir Docker Desktop o usar **Probar sin Docker** |
| Archivo recibido no aparece | Actualizar lista; revisar eventos/`RECEPCION_OK` y carpeta correcta |
| Error por cambios locales de Git | No borrar carpetas de usuarios; inspeccionar `git status` antes de `git pull` |

No elevar Uvicorn a `0.0.0.0:8080` para "solucionar" una conexión entre equipos; eso expone controles administrativos y **no es necesario**.

## 8. Cómo detener y conservar la evidencia

- Detener receptor desde **Transferencias → Detener**.
- Cerrar el panel con `Ctrl+C` en la terminal donde arrancó FastAPI.
- Guardar capturas de origen/destino, tiempos, hash y dos direcciones.
- No subir tokens, claves privadas, archivos personales ni bases locales.
- Leer el [plan de validación](PRUEBAS_Y_VALIDACION.md).

**Límites:** el historial del panel manual es volátil, pero la cola y las versiones del motor automático se guardan en SQLite. Hay detección Watchdog/escaneo, borrado remoto opt-in y reanudación parcial por offset. No hay consenso distribuido para resolver ediciones concurrentes.


## 9. Sincronización automática y modo compartido (versión actual)

Para uso completo entre dos equipos:

1. Inicia LocalSync en A y B desde `main`.
2. En ambos paneles, genera/comparte de forma privada un token y habilita el receptor TCP **Red local** con **Recibir directamente en carpeta sincronizada**.
3. En ambos paneles, entra a **Sincronización**, autoriza la IPv4 del otro equipo con puerto 9001 y mismo token. Pulsa **Iniciar sincronización**.
4. Crea un archivo en `carpeta_sincronizada/` de A. Se replicará sin pulsar Enviar. Modifica luego el archivo en B y observa la actualización en A.
5. Consulta en el panel las operaciones pendientes, errores y versiones. Si desconectas uno de los equipos, los envíos fallidos permanecen en SQLite para ser reintentados.
6. Pulsa **Ver versiones** y **Restaurar** si quieres recuperar un contenido anterior.
7. Para buscar el receptor sin introducir su IP, usa **Buscar equipos** con el token compartido y UDP 9002 habilitado. El dispositivo encontrado requiere confirmación manual.
8. Para propagar borrados, marca las opciones del receptor y del motor de sincronización; ambas están apagadas por defecto. Los borrados se archivan en `.localsync_deleted`.

**No equivale a edición colaborativa con consenso:** si A y B editan el mismo archivo exactamente al mismo tiempo, la última versión aplicada puede prevalecer; se conservan respaldos para recuperación.

### Sincronización con servicio

En Ubuntu puedes usar `recursos/systemd/localsync-autosync.service` y `LOCALSYNC_AUTOSTART=1` para iniciar el receptor y Watchdog al arrancar la máquina. En Windows el iniciador GUI es manual salvo que configures una tarea privada. Consulta [Despliegue final](DESPLIEGUE_FINAL.md) para las instrucciones completas.

### Reanudación manual

La casilla **Reanudar envíos interrumpidos** y el argumento CLI `--resume` utilizan parciales persistentes. En caso de corte, el siguiente intento continúa desde el desplazamiento del temporal si el archivo conserva ruta y SHA-256. Los parciales se verifican antes de publicar; no se debe borrar la carpeta `.localsync_partials` durante un envío pendiente.
