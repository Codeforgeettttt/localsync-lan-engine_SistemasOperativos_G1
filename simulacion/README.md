# Laboratorio de auditoría LocalSync — dos equipos Linux virtuales

Este laboratorio simula **dos equipos Linux independientes** con Docker Compose. Cada nodo es un contenedor que ejecuta un servidor TCP real en el puerto 9001, tiene almacenamiento separado y se comunica con el otro por una red **bridge privada interna**, sin publicar puertos al anfitrión.

> Son contenedores, **no máquinas virtuales completas**: comparten el kernel Linux de Docker. Para probar sockets TCP, autenticación, integridad y conflictos, sí representan dos hosts separados. No sustituyen una demostración de instalación de systemd en Ubuntu real.

## Requisitos

- Docker Desktop con motor Linux iniciado (Windows) o Docker Engine + Compose v2 (Ubuntu).
- Python 3.10+ instalado en el computador anfitrión.
- Internet la primera vez para descargar `python:3.11-slim`.

No es necesario instalar FastAPI ni dependencias Python adicionales en el anfitrión.

## Un comando para ejecutar toda la prueba

Desde la raíz del repositorio, en la rama de Valery:

```bash
git fetch origin
git switch feature/motor-p2p-pruebas
python simulacion/demo.py
```

En Windows PowerShell también puedes usar `py -3 simulacion/demo.py`.

El script:
1. Genera una clave HMAC temporal de 256 bits, sin escribirla en el repositorio.
2. Construye e inicia `nodo-a` y `nodo-b` y verifica su estado.
3. Realiza PING autenticado en ambas direcciones.
4. Envía `documento_A.txt` de A hacia B y compara SHA-256.
5. Envía un archivo binario B hacia A y compara SHA-256.
6. Envía una carpeta con subcarpeta y comprueba integridad.
7. Modifica un archivo, lo reenvía y verifica que el original permanece y que se crea una sola copia de conflicto.

Si todas las comprobaciones pasan, imprime:

```text
RESULTADO: AUDITORÍA VIRTUAL APROBADA.
```

Si falla una comprobación, el proceso termina con código de error. La prueba es reproducible y **no genera evidencias ficticias**.

## Mostrar resultados y capturas

```bash
python simulacion/demo.py --status
```

Muestra estado de los contenedores y registros recientes. Se puede abrir Docker Desktop y ver los dos nodos del proyecto `localsync-auditoria`.

Para borrar **solo** los contenedores y volúmenes virtuales creados por este laboratorio:

```bash
python simulacion/demo.py --cleanup
```

> Esta limpieza elimina los archivos de prueba de los volúmenes virtuales, no los archivos personales del computador ni el repositorio.

En GitHub Actions se usa `python simulacion/demo.py --cleanup-after` para ejecutar las comprobaciones y limpiar al terminar.

## Evidencias de la auditoría

- Captura de dos contenedores Linux separados en Docker Desktop.
- Consola con PING, ACK, ENVIO_OK y RECEPCION_OK.
- SHA-256 idéntico entre los archivos de origen y destino.
- Evidencia de intercambio A→B y B→A.
- Transferencia de subcarpetas, conservación del original y control de duplicados.
- Ejecución del trabajo de GitHub Actions correspondiente.

## Alcance y limitaciones

- Los nodos utilizan autenticación HMAC sobre una red Docker aislada.
- TLS no está activado en este laboratorio (consultar `pruebas/GUIA_PRUEBA_LAN.md` para el ejercicio TLS).
- Esta prueba cubre el **transporte de archivos**, no Watchdog, borrados automáticos, sincronización en segundo plano ni cola persistente SQLite.
- Para auditar el comportamiento real del servicio `systemd` se necesita una VM Ubuntu o un equipo Linux con ese gestor de servicios.

## Problemas comunes

**Docker no se reconoce:** instala e inicia Docker Desktop.

**No construye los nodos:** verifica que Docker Desktop use contenedores Linux y que la virtualización/WSL2 estén activos.

**Contenedor unhealthy:** consulta `python simulacion/demo.py --status` y sus registros.

**Token incorrecto:** si hay una variable LOCALSYNC_AUTH_TOKEN predefinida, debe tener al menos 16 caracteres. Si no existe, el script genera una clave efímera.

**Ejecuciones repetidas:** cada prueba crea un nombre de lote nuevo, evitando colisiones con archivos de auditorías anteriores.
