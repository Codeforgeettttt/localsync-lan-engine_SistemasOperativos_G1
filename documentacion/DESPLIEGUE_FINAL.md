# Despliegue final de LocalSync — Windows, Ubuntu y dos nodos LAN

**Última revisión:** 18 de noviembre de 2026.  
**Código fuente:** rama `main`. **Arquitectura:** interfaz FastAPI local + receptor TCP + vigilancia Watchdog/escaneo + cola SQLite + historial de versiones y recuperación de transferencias.

> **Qué queda fuera del despliegue:** resolución automática de conflictos de ediciones exactamente simultáneas, un servidor de coordinación en internet y una auditoría externa de seguridad. En la carpeta compartida se usa la última versión aplicada, conservando un respaldo previo. El sistema no pretende reemplazar servicios empresariales de almacenamiento.

## 1. Lo que queda disponible al instalar

- Envíos manuales de archivos y carpetas, con SHA-256 y HMAC.
- **Sincronización automática opt-in**: detectar archivos nuevos/modificados y replicarlos a los pares aprobados.
- **Bidireccional entre dos equipos**: cada uno observa su carpeta; el receptor puede depositar cambios en esa misma carpeta.
- **Watchdog** para avisar cambios y escaneo periódico como respaldo.
- **SQLite persistente**: trabajos pendientes de envío, número de intentos y últimos errores; reenvíos al recuperar el enlace.
- **Reanudación TCP** de un archivo desde los bytes del temporal conservado en el receptor, con verificación SHA-256 al completar.
- **Control de versiones**: copias de contenidos anteriores bajo `datos_locales/versiones` y botón de restauración desde GUI.
- **Descubrimiento LAN por UDP 9002** firmado con un token compartido. **Encontrar un equipo no lo autoriza**: el usuario confirma el par.
- **Borrado remoto opcional** con papelera recuperable; apagado por defecto.
- **TLS opcional**, mediante certificados configurados en ambos equipos.
- Simulaciones locales, Docker TCP y Docker de sincronización bidireccional.

## 2. Puertos y directorios

| Uso | Puerto / carpeta | Exposición |
| --- | --- | --- |
| Panel web de administración | TCP `127.0.0.1:8080` | **Solo ese computador** |
| Transferencia y sincronización TCP | `9001/TCP` | Solo desde IP(s) de las PC autorizadas |
| Descubrimiento opcional | `9002/UDP` | Solo red LAN privada |
| Carpeta vigilada por defecto | `carpeta_sincronizada/` | Local; archivos nuevos se envían automáticamente |
| Preparados para envío manual | `archivos_para_enviar/` | Local |
| Recibidos manualmente | `archivos_recibidos/` | Local |
| Cola de operaciones | `datos_locales/sync.db` | SQLite, no subir a Git |
| Versiones recuperables | `datos_locales/versiones/` | Nunca publicar como archivos del repositorio |
| Parciales de transferencias | `carpeta_sincronizada/.localsync_partials/` o carpeta receptora | Internos; no eliminar durante la recuperación |
| Papelera de borrados recibidos | `carpeta_sincronizada/.localsync_deleted/` | Recuperable manualmente |

Los directorios internos se excluyen del observador y de los envíos para no crear ciclos.

## 3. Instalación en Windows (dos computadores)

Requisitos: Python 3.10+, PowerShell, LAN privada y permiso para `9001/TCP` en el firewall desde el otro equipo. **Docker NO es obligatorio** para la aplicación real.

En **cada equipo**:

```powershell
git switch main
git pull origin main
.\iniciar_localsync.bat
```

El iniciador configura Python y abre `http://127.0.0.1:8080/`. Mantén la terminal ejecutándose durante la sincronización.

### Activar la réplica bidireccional desde la GUI

1. Conecta **ambos computadores** a la misma LAN privada.
2. En un equipo, en **Transferencias → Generar token**, crea un token y compártelo con el segundo equipo por un medio privado.
3. En **cada computadora**, en la sección **Receptor TCP**, selecciona **Red local (0.0.0.0)**, puerto **9001**, **Recibir directamente en carpeta sincronizada**, introduce el mismo token y pulsa **Iniciar receptor**.
4. En **cada computadora**, entra en **Sincronización**, añade la **IP del otro equipo**, puerto **9001** y el mismo token; pulsa **Autorizar equipo** y después **Iniciar sincronización**.
5. Introduce un archivo de prueba dentro de `carpeta_sincronizada/` del equipo A: el archivo debe aparecer en la carpeta equivalente del equipo B. Modifícalo en B para probar el sentido contrario.
6. En **Sincronización**, revisa el estado de la cola, los eventos y las versiones recuperables. Si B está desconectado, el envío permanece pendiente para reintentarse cuando vuelva.
7. Para descubrir IPs sin escribirlas: en **Transferencias → Buscar equipos**, introduce el token. Si el firewall bloquea **UDP 9002**, introduce la IPv4 manualmente.

**Borrados:** desactivados por defecto. Para replicarlos, habilita la casilla correspondiente **antes** de arrancar el receptor y al iniciar la sincronización. El receptor mueve el archivo borrado a `.localsync_deleted`. En un entorno compartido sensible, deja esta opción desactivada.

**Reanudación:** en el panel de transferencia manual, deja marcada **Reanudar envíos interrumpidos**. Las transferencias del motor automático utilizan reanudación por defecto.

### Windows: arrancar el proceso con sincronización ya configurada

El modo GUI requiere que, tras un reinicio, el usuario vuelva a habilitar la vigilancia y reautorice el par si el token solo estaba en memoria. Para un inicio no interactivo se puede configurar `LOCALSYNC_AUTOSTART=1` junto con `LOCALSYNC_AUTH_TOKEN` y `LOCALSYNC_SYNC_PEER` en un entorno privado del proceso. **No guardes el token en Git, un archivo .bat compartido ni en parámetros de una tarea programada.**

Un administrador puede utilizar el Programador de tareas de Windows con un lanzador privado, pero el manejo de credenciales y permisos debe adaptarse a las políticas del computador. El arranque automático seguro no se activa por defecto.

## 4. Despliegue como servicio persistente en Ubuntu

### 4.1. Preparar un usuario de servicio y la aplicación

En **cada Ubuntu**:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip rsync openssl
id localsync >/dev/null 2>&1 || sudo useradd --system --no-create-home --shell /usr/sbin/nologin localsync

sudo mkdir -p /opt/localsync /etc/localsync
sudo install -d -o localsync -g localsync -m 750 /var/lib/localsync
for dir in shared versions upload inbox; do
  sudo install -d -o localsync -g localsync -m 750 "/var/lib/localsync/$dir"
done
sudo rsync -a --exclude=.git --exclude=.venv --exclude=datos_locales \
  --exclude=carpeta_sincronizada --exclude='*.db' ./ /opt/localsync/
sudo python3 -m venv /opt/localsync/.venv
sudo /opt/localsync/.venv/bin/python -m pip install -r /opt/localsync/requirements.txt
sudo chown -R root:root /opt/localsync
```

Ejecutar desde la raíz del repositorio. El servicio corre sin privilegios elevados con archivos de aplicación propiedad de `root` y solo escribe en `/var/lib/localsync`.

### 4.2. Configuración privada del servicio

Genera **una sola clave** segura y compártela con el otro integrante por canal privado:

```bash
openssl rand -hex 32
```

En **cada computadora**, crea el archivo protegido (modifica `IP_DEL_OTRO_EQUIPO` por su IPv4 real):

```bash
sudo install -o root -g root -m 600 /dev/null /etc/localsync/autosync.env
sudoedit /etc/localsync/autosync.env
```

Contenido de ejemplo **sin credenciales reales**:

```ini
LOCALSYNC_AUTOSTART=1
LOCALSYNC_AUTH_TOKEN=REEMPLAZAR_POR_EL_MISMO_TOKEN_LARGO_EN_AMBOS
LOCALSYNC_SYNC_PEER=IP_DEL_OTRO_EQUIPO
LOCALSYNC_SYNC_PEER_PORT=9001
LOCALSYNC_P2P_PORT=9001
LOCALSYNC_ALLOW_REMOTE_DELETE=0
LOCALSYNC_SYNC_DIR=/var/lib/localsync/shared
LOCALSYNC_SYNC_DB=/var/lib/localsync/sync.db
LOCALSYNC_VERSIONS_DIR=/var/lib/localsync/versions
LOCALSYNC_UPLOAD_DIR=/var/lib/localsync/upload
LOCALSYNC_RECEIVE_DIR=/var/lib/localsync/inbox
```

Si cambias IP/puerto, actualiza el archivo y reinicia el servicio. El token permanece en el archivo local root-only; **no lo pegues en GitHub ni lo muestres en capturas**.

### 4.3. Instalar y habilitar systemd

```bash
sudo install -o root -g root -m 644 recursos/systemd/localsync-autosync.service \
  /etc/systemd/system/localsync-autosync.service
sudo systemctl daemon-reload
sudo systemctl enable --now localsync-autosync.service
sudo systemctl status localsync-autosync.service --no-pager
sudo journalctl -u localsync-autosync.service -n 60 --no-pager
```

Debe verse el servicio en ejecución, servidor TCP iniciado, y el motor de vigilancia activo. Para iniciar/parar:

```bash
sudo systemctl restart localsync-autosync.service
sudo systemctl stop localsync-autosync.service
sudo journalctl -u localsync-autosync.service -f
```

**La GUI queda disponible solo en el navegador del propio Ubuntu** (`127.0.0.1:8080`); no se ha diseñado como panel remoto de administración.

### 4.4. Firewall

En el receptor Ubuntu, configura UFW **solo para la IP del otro equipo**:

```bash
sudo ufw allow from IP_DEL_OTRO_EQUIPO to any port 9001 proto tcp
# Solo si se desea descubrimiento:
sudo ufw allow from IP_DEL_OTRO_EQUIPO to any port 9002 proto udp
```

No abras 8080 al resto de la LAN ni publiques 9001 en el router.

### 4.5. TLS (si se transmiten datos sensibles)

HMAC autentica al nodo, **pero sin TLS el contenido viaja sin cifrar**. El motor admite:

```ini
LOCALSYNC_TLS_CERT=/etc/localsync/servidor.crt
LOCALSYNC_TLS_KEY=/etc/localsync/servidor.key
LOCALSYNC_TLS_CA=/etc/localsync/certificado-del-par.crt
LOCALSYNC_TLS_SERVER_NAME=IP_DEL_OTRO_EQUIPO
```

Genera certificados cuyo SAN contenga la IP real, intercambia certificados públicos por un canal confiable y configura los permisos de `.key` para que **solo el usuario de servicio** pueda leerlo. La clave privada no debe quedar en un directorio público ni en el repositorio. Para un ejemplo de laboratorio, consulta [Guía LAN](../pruebas/GUIA_PRUEBA_LAN.md).

## 5. Comprobaciones posteriores a instalar

```bash
# Status HTTP local
curl -fsS http://127.0.0.1:8080/api/sync/estado
# Socket del receptor
ss -lntp | grep ':9001'
# Carpeta compartida
ls -lah /var/lib/localsync/shared
```

Crea un archivo de prueba en A, confirma que aparece en B y compara hashes:

```bash
sha256sum /var/lib/localsync/shared/archivo_de_prueba.txt
```

Luego modifica en B y confirma el cambio en A. Prueba desconexión/reconexión y revisa `/api/sync/estado` (pendientes y reintentos). Para verificar borrados, habilita la opción **solo con un archivo de prueba** y comprueba el respaldo en `.localsync_deleted`.

## 6. Auditoría reproducible sin usar los equipos físicos

**Pruebas Python:**

```bash
python -m pytest -v
```

**Laboratorio Docker manual TCP:**

```bash
python simulacion/demo.py --cleanup-after
```

**Laboratorio Docker de sincronización automática real en dos contenedores:**

```bash
python simulacion/demo_autosync.py --cleanup-after
```

Ambos laboratorios Docker tienen redes y volúmenes independientes. `--cleanup-after` destruye sus volúmenes de prueba al terminar.

Consulta [GitHub Actions](https://github.com/Codeforgeettttt/localsync-lan-engine_SistemasOperativos_G1/actions) para confirmar resultados del commit exacto. La aplicación no utiliza Docker para transferir archivos en una LAN real.

## 7. Seguridad, alcance y actualizaciones

- **Elimina completamente los archivos de prueba** de carpetas compartidas solo cuando ya no sean necesarios.
- No guardes proyectos personales, secretos ni credenciales en GitHub.
- El borrado remoto es opt-in, archivado y requiere autenticación.
- La cola de SQLite y las versiones son **persistentes**, pero los tokens de pares introducidos desde GUI están en memoria; si reinicias, reautoriza o configura el arranque con variables protegidas.
- La réplica entre dos nodos aplica cambios a cada carpeta. **No** implementa vector clocks ni resolución automática de modificaciones simultáneas: la última versión aplicada prevalece, con respaldo anterior.
- La reanudación usa parciales persistentes y SHA-256 final. Los parciales de envíos abandonados **no se purgan automáticamente**; revisa el consumo de disco periódicamente.
- Para cambiar código: `git pull origin main`, reinstalar dependencias si hay cambios en `requirements.txt`, ejecutar pruebas, reiniciar servicio y comprobar estado.
- No confundir la comunicación LAN, la instalación de dependencias y GitHub Actions: son procesos distintos.

## 8. Checklist de despliegue

- [ ] Clon actualizado a `main` en ambos PCs.
- [ ] Python y dependencias instaladas.
- [ ] Token largo e idéntico, distribuido por canal privado.
- [ ] IP privada del otro equipo configurada.
- [ ] Firewall limitado al par.
- [ ] Receptor TCP y sincronización activos.
- [ ] Crear archivo en A y confirmar copia en B con SHA-256.
- [ ] Editar en B y confirmar actualización en A.
- [ ] Desconectar/reconectar y verificar que se vacía la cola.
- [ ] Restaurar una versión anterior desde el panel.
- [ ] Si se autoriza DELETE, comprobar que aparece en papelera.
- [ ] Comprobar reinicio y arranque automático si usa `systemd`.
- [ ] Guardar evidencia de IPs, ACK, SHA, logs y commit exacto sin mostrar secretos.

**Resultado esperado:** después de estas comprobaciones, solo quedará operar el sistema y registrar evidencias en el entorno real.
