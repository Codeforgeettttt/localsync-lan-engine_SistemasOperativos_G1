# Integración entre interfaz, API y transporte TCP

**Documento actualizado al código fusionado en `main`, 18-11-2026.**

> Este archivo sustituye la descripción del panel antiguo y de los datos de demostración. La aplicación incluye **transferencia TCP manual, sincronización automática Watchdog, reanudación por offset y cola SQLite persistente**; se activan desde pestañas distintas de la GUI.

## Componentes y límites

```mermaid
flowchart LR
    UI["GUI HTML/CSS/JS"] -->|"fetch HTTP localhost :8080"| API["FastAPI /api/lan"]
    API --> UP["Bandeja archivos_para_enviar"]
    API --> TX["Cliente TCP"]
    API --> RXA["Receptor local TCP :9001"]
    TX -->|"Red LAN privada + HMAC; TLS opcional"| RXB["Receptor TCP otro equipo"]
    RXB --> SHA["Ruta segura + SHA-256"]
    SHA --> FS["Carpeta recibidos"]
    API -. "Esquema / diagnóstico" .-> BD[("SQLite local")]
```

**No confundir:**
- Los eventos del panel se registran **en RAM**.
- El motor automático usa **sync.db** para registrar operaciones y versiones, independiente de las tablas académicas iniciales; la actividad manual de la GUI sigue siendo volátil.
- La API HTTP está confinada a localhost. La conexión de red real viaja por el canal **TCP 9001**, separado.
- La ruta heredada `/api/p2p` tiene restricciones adicionales de destinatario; para la GUI actual se utiliza `/api/lan`.

## Contratos más importantes

| Operación GUI | Endpoint FastAPI | Motor |
| --- | --- | --- |
| Estado/receptor | `GET /api/lan/estado` | `lan_routes.py` |
| Detectar IP | `GET /api/lan/red` | `lan_routes.py` |
| Preparar archivos | `POST /api/lan/archivos` | Upload a bandeja local |
| Comprobar nodo | `POST /api/lan/conexion` | `comprobar_conexion` (PING/ACK) |
| Enviar uno | `POST /api/lan/enviar` | `enviar_archivo` |
| Enviar carpeta | `POST /api/lan/enviar-carpeta` | `enviar_carpeta` |
| Iniciar/detener receptor | `POST /api/lan/receptor/iniciar` / `detener` | `NodoP2PTCP.servir` |
| Verificar/renombrar/eliminar | `GET /api/lan/archivo/verificar` / `PATCH` / `DELETE /api/lan/archivo` | Gestión local |
| Simulación virtual | `POST /api/lan/simulacion/iniciar` | `simulacion/demo.py` |
| Prueba local sin Docker | `POST /api/lan/simulacion/local` | `simulacion/demo_local.py` |
| Guardar evidencia virtual | `GET /api/lan/simulacion/evidencia` | Texto de logs de sesión |

Para campos, validaciones y códigos HTTP: [API_Y_DATOS.md](API_Y_DATOS.md).

## Ejecución actual

En Windows, desde la raíz:

```powershell
.\iniciar_localsync.bat
```

En Ubuntu:

```bash
bash iniciar_localsync.sh
```

El navegador abre `http://127.0.0.1:8080/`. El motor receptor debe iniciarse desde la pestaña **Transferencias**; al seleccionar modo LAN exige token compartido de longitud mínima. Abrir TCP 9001 en firewall para la IP del otro computador (solo en red privada). Para emitir, preparar el archivo desde la GUI, configurar IP/puerto/token del receptor y pulsar **Enviar**.

## Verificación

```bash
python -m pytest -v
python simulacion/demo_local.py
# Requiere Docker Desktop o Docker Engine Linux:
python simulacion/demo.py
```

En los dos computadores reales: registrar ACK, archivo recibido y **hash SHA-256 igual** en ambos. El equipo reportó una prueba física funcional; completar acta de evidencias sin inventar valores: [PRUEBAS_Y_VALIDACION.md](PRUEBAS_Y_VALIDACION.md).

## Alcance y documentación vigente

- El transporte manual, HMAC, integridad y GUI están implementados.
- TLS está disponible **opcionalmente** y requiere certificados para activarse.
- El motor automático sí dispone de Watchdog, réplica, cola persistente y reanudación. `DELETE` remoto es opt-in y guarda en papelera; las modificaciones utilizan `CREATE_RESUME` y respaldos, no un comando `MODIFY` separado.
- Los diseños PDF y las capturas de fases anteriores se conservan como historial, **no reemplazan el estado actual**.

Diagramas: [ARQUITECTURA.md](ARQUITECTURA.md), [fuentes Mermaid](diagramas/fuentes_mermaid/). Protocolo: [PROTOCOLO_TCP.md](PROTOCOLO_TCP.md). Seguridad: [SEGURIDAD_Y_ERRORES.md](SEGURIDAD_Y_ERRORES.md).

## Integración del motor automático

```mermaid
flowchart LR
  GUI["GUI Sincronización"] -->|"/api/sync"| API["FastAPI localhost"]
  API --> W["Watchdog + escaneo"]
  W --> DB[("SQLite sync.db: cola y versiones")]
  DB --> TX["TCP CREATE_RESUME / DELETE opt-in"]
  TX --> RX["Receptor del otro equipo"]
  RX --> FS[("Carpeta compartida + respaldos")]
```

La pestaña **Sincronización** permite autorizar pares, iniciar/detener vigilancia, comprobar cola y restaurar versiones. En **Transferencias**, la opción *Recibir directamente en carpeta sincronizada* convierte al receptor en destino del espejo. La búsqueda de equipos UDP 9002 solo funciona con token HMAC compartido y requiere selección manual. El servicio puede iniciarse automáticamente con variables protegidas siguiendo [DESPLIEGUE_FINAL.md](DESPLIEGUE_FINAL.md).
