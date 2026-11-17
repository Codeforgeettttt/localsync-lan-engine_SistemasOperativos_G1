# Auditoría LocalSync — Transferencia P2P en LAN (Valery)

**Objetivo:** comprobar envío manual A→B y B→A, archivos y carpetas, integridad SHA-256, autenticación y recuperación básica por reintentos.  
**Alcance honesto:** no hay sincronización automática con Watchdog, propagación de DELETE/MODIFY, TLS obligatorio, reanudación por bloques ni cola persistente.

## 0. Preparación en ambos equipos Ubuntu

Desde la raíz del repositorio en la rama de Valery (o en main después de fusionar el PR):

\`\`\`bash
git fetch origin feature/motor-p2p-pruebas
git switch feature/motor-p2p-pruebas
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
hostname -I
\`\`\`

Ambos equipos deben estar en la **misma red LAN confiable**. Anota IP_A e IP_B.
Comprueba la red: desde A \`ping -c 4 IP_B\` y desde B \`ping -c 4 IP_A\`.

Para el firewall del receptor, si UFW está activo, permite el puerto solo desde la IP del otro equipo:

\`\`\`bash
sudo ufw allow from IP_DEL_OTRO_EQUIPO to any port 9001 proto tcp
\`\`\`

**Autenticación (obligatoria por defecto cuando el servidor escucha fuera de localhost):**
genera una sola clave en uno de los equipos con \`openssl rand -hex 32\` y compártela
de forma privada con el otro integrante. En **cada terminal** que use servidor o
cliente, introduce esa **misma** clave sin escribirla en el comando:

\`\`\`bash
read -rs -p "Clave compartida LocalSync: " LOCALSYNC_AUTH_TOKEN; echo
export LOCALSYNC_AUTH_TOKEN
\`\`\`

No publiques el token en GitHub ni lo muestres en capturas. El reto HMAC verifica que ambos nodos conocen la clave; **por sí solo no cifra el archivo** (ver TLS).

## 1. Servidor receptor (en B, luego también en A)

\`\`\`bash
mkdir -p archivos_recibidos
python3 -m src.backend.network.p2p_socket \
  --host 0.0.0.0 --port 9001 --directory archivos_recibidos \
  --on-conflict keep-both
\`\`\`

Aparecerá \`[SERVIDOR_LISTO]\`. Al completarse un envío, aparecerá
\`[RECEPCION_OK]\` con nombre, tamaño y SHA-256.
Deja el servidor abierto. Para que ambos equipos reciban archivos, inicia
un receptor idéntico en el otro equipo (terminal independiente).

## 2. Enviar un archivo desde A hacia B

En A (en otra terminal, con la misma clave configurada):

\`\`\`bash
mkdir -p archivos_para_enviar
printf 'Prueba LocalSync A hacia B\n' > archivos_para_enviar/prueba_A.txt
python3 -m src.backend.network.cliente_tcp --host IP_B --port 9001
python3 -m src.backend.network.cliente_tcp \
  --host IP_B --port 9001 --file archivos_para_enviar/prueba_A.txt
sha256sum archivos_para_enviar/prueba_A.txt
\`\`\`

En B:

\`\`\`bash
ls -lah archivos_recibidos
sha256sum archivos_recibidos/prueba_A.txt
\`\`\`

Criterio de aceptación: \`ACK recibido\` en A, \`RECEPCION_OK\` en B y hash idéntico.

## 3. Enviar en el sentido contrario B → A

En B (con receptor activo en A):

\`\`\`bash
mkdir -p archivos_para_enviar
printf 'Prueba LocalSync B hacia A\n' > archivos_para_enviar/prueba_B.txt
python3 -m src.backend.network.cliente_tcp \
  --host IP_A --port 9001 --file archivos_para_enviar/prueba_B.txt
sha256sum archivos_para_enviar/prueba_B.txt
\`\`\`

En A: \`sha256sum archivos_recibidos/prueba_B.txt\`.

## 4. Enviar una carpeta, conservar subdirectorios y reintentar

En A:

\`\`\`bash
mkdir -p muestra_local/subcarpeta
printf 'Documento de prueba\n' > muestra_local/subcarpeta/documento.txt
printf 'Otro archivo\n' > muestra_local/segundo.txt
python3 -m src.backend.network.cliente_tcp \
  --host IP_B --port 9001 --directory muestra_local \
  --remote-prefix entregas --retries 2
\`\`\`

En B quedarán \`archivos_recibidos/entregas/subcarpeta/documento.txt\` y
\`archivos_recibidos/entregas/segundo.txt\`.

**Conflictos:** si envías otro archivo con igual nombre pero contenido diferente,
el receptor conservará el original y creará una copia \`.conflict-<hash>.ext\`.
Si se envía dos veces un archivo idéntico, no se crean copias duplicadas.
El servidor también admite \`--on-conflict reject\` o \`overwrite\`; para la auditoría utiliza **keep-both**.

**Reintentos:** \`--retries 2\` repite el envío completo hasta dos veces después
de fallos de conexión. No se reanuda desde el último byte recibido.
El límite por archivo es **100 MiB**.

## 5. TLS opcional (cifrado de extremo a extremo)

Para cifrar las transferencias, genera en el **receptor** un certificado de
prueba para su **IP real**, por ejemplo, sustituye IP_B por la IP correcta:

\`\`\`bash
openssl req -x509 -newkey rsa:3072 -nodes \
  -keyout servidor.key -out servidor.crt -days 7 \
  -subj "/CN=LocalSync" -addext "subjectAltName=IP:IP_B"
chmod 600 servidor.key
\`\`\`

Copia **solo** \`servidor.crt\` al emisor mediante un medio confiable y
reinicia el servidor receptor con las opciones TLS añadidas:

\`\`\`bash
python3 -m src.backend.network.p2p_socket \
  --host 0.0.0.0 --port 9001 --directory archivos_recibidos \
  --tls-cert servidor.crt --tls-key servidor.key
\`\`\`

En el emisor añade \`--tls-ca servidor.crt\` al comando del cliente. La IP usada
con \`--host\` debe coincidir con el SAN del certificado. **No utilices
\`--insecure\` para saltarte la verificación.** Para operar en ambos sentidos
con TLS, cada receptor necesita su propio certificado.

## 6. Pruebas y evidencias que deben quedar listas

\`\`\`bash
python -m pytest -v
python -m pytest -v pruebas/test_lan_completo.py
\`\`\`

Captura:
1. IP local de ambos equipos y comunicación \`ping\`.
2. \`[SERVIDOR_LISTO]\` del receptor y \`[RECEPCION_OK]\`.
3. \`ACK recibido\` y resultado de SHA-256 en ambos lados.
4. Envío B→A y carpeta con un subdirectorio.
5. \`pytest -v\` y ejecución correcta de GitHub Actions.
6. Prueba de conflicto que conserve ambos archivos.

**Seguridad:** compartir las credenciales por canal privado, mantener el puerto
9001 restringido a la LAN, detener con Ctrl+C al acabar. HMAC sin TLS **no**
protege la confidencialidad. No dejar la demo expuesta a Internet.

## 7. Linux con systemd (opcional para reforzar Sistemas Operativos)

Se incluye \`recursos/systemd/localsync-tcp.service\` para ejecutar el
receptor como servicio independiente de FastAPI. Antes de usarlo hay que crear
el usuario de servicio, el entorno virtual en \`/opt/localsync\`, la carpeta
\`/var/lib/localsync/recibidos\` y un archivo de entorno root-only en
\`/etc/localsync/localsync.env\` con la clave compartida. **No** usar la unidad
sin adaptar estas rutas al entorno real. Se adjunta el servicio como plantilla,
no como demostración de que ya está instalado.

\`\`\`bash
sudo systemctl daemon-reload
sudo systemctl enable --now localsync-tcp
sudo systemctl status localsync-tcp --no-pager
sudo journalctl -u localsync-tcp -n 40 --no-pager
\`\`\`

La API FastAPI existente es otro proceso: \`localsync.service\` **no**
inicia automáticamente el receptor TCP.
