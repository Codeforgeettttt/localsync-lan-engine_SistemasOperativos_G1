# Instalación del receptor TCP LocalSync en Ubuntu (systemd)

**Estado:** procedimiento de instalación; el equipo del estudiante debe ejecutarlo y comprobarlo. El archivo de unidad no prueba por sí solo que el servicio esté corriendo.

La unidad `localsync-tcp.service` ejecuta el **servidor de recepción TCP** por separado del servidor web FastAPI. Permite reiniciar el receptor automáticamente si el proceso termina de forma inesperada.

## Antes de comenzar

Necesitas Python 3.10+, permisos sudo, la red LAN configurada y la rama con el código del motor TCP. Si se utiliza un certificado TLS, la unidad debe adaptarse añadiendo `--tls-cert` y `--tls-key` a `ExecStart` y asegurando que el usuario `localsync` pueda leer ambos archivos.

## Instalación (en el equipo receptor)

Ejecutar desde la raíz del repositorio:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip rsync

# Crear cuenta de servicio de mínimos privilegios (si aún no existe).
id localsync >/dev/null 2>&1 || sudo useradd --system --no-create-home --shell /usr/sbin/nologin localsync

sudo mkdir -p /opt/localsync /var/lib/localsync/recibidos /etc/localsync
sudo rsync -a --exclude=.git --exclude=.venv --exclude='*.db' ./ /opt/localsync/
sudo python3 -m venv /opt/localsync/.venv
sudo /opt/localsync/.venv/bin/python -m pip install -r /opt/localsync/requirements.txt
sudo chown -R root:root /opt/localsync
sudo chown -R localsync:localsync /var/lib/localsync
sudo chmod 750 /var/lib/localsync /var/lib/localsync/recibidos

# Archivo de configuración privado, administrado por root.
sudo install -o root -g root -m 600 /dev/null /etc/localsync/localsync.env
sudoedit /etc/localsync/localsync.env
```

En el editor, escribe una línea **sin comillas**:

```ini
LOCALSYNC_AUTH_TOKEN=REEMPLAZAR_POR_TOKEN_FUERTE_DE_AL_MENOS_32_CARACTERES
```

Genera el token con `openssl rand -hex 32`. Debe ser **el mismo** que el emisor, pero no se debe guardar dentro del repositorio.

Después:

```bash
sudo install -m 644 recursos/systemd/localsync-tcp.service /etc/systemd/system/localsync-tcp.service
sudo systemctl daemon-reload
sudo systemctl enable --now localsync-tcp.service
sudo systemctl status localsync-tcp.service --no-pager
sudo journalctl -u localsync-tcp.service -n 40 --no-pager
```

Debe aparecer `active (running)` y `SERVIDOR_LISTO`. Si falla, inspecciona `journalctl`. La unidad está preparada para escuchar en el puerto 9001 con autenticación HMAC. Por defecto **no cifra** datos; configura TLS para una red que no sea un laboratorio privado.

## Prueba de conectividad desde el segundo equipo

En el equipo emisor, define `LOCALSYNC_AUTH_TOKEN` con el mismo valor que el receptor sin publicarlo:

```bash
read -rs -p "Clave compartida LocalSync: " LOCALSYNC_AUTH_TOKEN; echo
export LOCALSYNC_AUTH_TOKEN
python3 -m src.backend.network.cliente_tcp --host IP_RECEPTOR --port 9001
```

Comprueba que el firewall permite conexiones al puerto 9001 **solo desde la IP autorizada**. Por ejemplo, en el receptor:

```bash
sudo ufw allow from IP_EMISOR to any port 9001 proto tcp
```

No redirigir este puerto en el router ni publicarlo en Internet.

## Comandos útiles para la auditoría

```bash
sudo systemctl status localsync-tcp --no-pager
sudo journalctl -u localsync-tcp -f
ss -lntp | grep ':9001'
sudo systemctl restart localsync-tcp
sudo systemctl stop localsync-tcp
```

Para retirar el arranque automático:

```bash
sudo systemctl disable --now localsync-tcp
```

## Limitaciones de esta entrega

- El servicio TCP no inicia automáticamente la API FastAPI ni el observador Watchdog.
- Las transferencias se disparan por el cliente CLI; no existe monitoreo automático de carpetas.
- El proceso corre con el usuario `localsync` y solo debe escribir dentro de la carpeta autorizada.
- Los reintentos repiten archivos completos; no hay reanudación parcial por byte.
- El servicio contiene una ruta fija `/opt/localsync` que debe coincidir con la instalación.
