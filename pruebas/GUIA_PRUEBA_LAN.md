# Prueba LAN de dos equipos — LocalSync (Fase II)

**Responsable técnico:** Valery Michell Herrera Roca  
**Objetivo:** demostrar transferencia TCP manual entre dos computadores de la misma red local, con confirmación ACK e integridad SHA-256.  
**Alcance:** esta demostración **no equivale** todavía a sincronización automática bidireccional, autenticación ni TLS.

## Preparación (en ambos equipos Ubuntu)

1. Conectar ambos computadores a la **misma LAN confiable**.
2. Clonar el repositorio y ubicarse en su raíz.
3. Instalar Python 3.10+ y, si se van a ejecutar todas las pruebas, las dependencias:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

4. Consultar la IP local de cada equipo: `hostname -I`. Anotar `IP_A` e `IP_B`.
5. Comprobar conectividad: desde A, `ping -c 4 IP_B`; desde B, `ping -c 4 IP_A`.
6. Si UFW está habilitado, abrir el puerto 9001 **solo para la IP del otro computador**, por ejemplo: `sudo ufw allow from IP_B to any port 9001 proto tcp` (adaptar la IP en cada equipo).

## 1. Iniciar un receptor en ambos equipos

Crear una carpeta receptora y abrir una terminal **independiente** en cada equipo:

```bash
mkdir -p archivos_recibidos
python3 -m src.backend.network.p2p_socket --host 0.0.0.0 --port 9001 --directory archivos_recibidos
```

Mantener esa terminal abierta. El receptor mostrará una línea `[RECEPCION_OK]` cuando termine y compruebe un archivo.

## 2. Envío de A hacia B

En otra terminal del equipo A:

```bash
mkdir -p archivos_para_enviar
printf 'Prueba LocalSync: A hacia B\n' > archivos_para_enviar/prueba_A.txt
python3 -m src.backend.network.cliente_tcp --host IP_B --port 9001 --file archivos_para_enviar/prueba_A.txt
sha256sum archivos_para_enviar/prueba_A.txt
```

En el equipo B, comprobar que se recibió:

```bash
ls -lah archivos_recibidos
sha256sum archivos_recibidos/prueba_A.txt
```

**Criterio de aceptación:** emisor muestra `ACK recibido`, receptor muestra `RECEPCION_OK`, y los dos hashes SHA-256 coinciden.

## 3. Envío de B hacia A

Desde el equipo B, en otra terminal:

```bash
mkdir -p archivos_para_enviar
printf 'Prueba LocalSync: B hacia A\n' > archivos_para_enviar/prueba_B.txt
python3 -m src.backend.network.cliente_tcp --host IP_A --port 9001 --file archivos_para_enviar/prueba_B.txt
sha256sum archivos_para_enviar/prueba_B.txt
```

En A:

```bash
sha256sum archivos_recibidos/prueba_B.txt
```

**Criterio de aceptación:** el equipo A recibe el archivo con el mismo SHA-256.

## 4. Pruebas automatizadas

Desde la raíz del repositorio en al menos uno de los equipos:

```bash
pytest -v
pytest -v pruebas/test_dos_nodos_tcp.py
```

La nueva prueba `test_dos_nodos_tcp.py` crea dos nodos independientes sobre **localhost**, por lo que permite probar el intercambio manual en dos sentidos sin necesitar dos equipos físicos. No reemplaza la prueba LAN real.

## Evidencias para presentar

- Captura de `hostname -I` en ambos equipos (se pueden ocultar datos que no sean relevantes).
- Captura de conectividad entre A y B.
- Captura de consola del receptor con `[RECEPCION_OK]`.
- Captura de consola del cliente con `ACK recibido`.
- Comparación de SHA-256 de origen y destino en cada dirección.
- Captura de `pytest -v` con resultado real.
- Si falla algo, registrar el error en lugar de reportar un éxito no verificado.

> **Seguridad:** el servidor TCP de este prototipo no autentica ni cifra conexiones. Usarlo solo en una LAN de prueba confiable y apagarlo al terminar (Ctrl+C). No abrir el puerto 9001 hacia Internet.
