# Seguridad, gestión de errores y límites de operación

**Ámbito:** transferencia TCP en una LAN privada y panel administrativo local.  
**Advertencia:** LocalSync es un proyecto académico y **no cuenta con una auditoría externa de seguridad ni un endurecimiento completo de producción**.

## 1. Suposiciones y modelo de amenazas

Activos a proteger: archivos enviados, carpeta autorizada de recepción, integridad del contenido y control del receptor.

Amenazas consideradas:

- Conexiones no autorizadas desde equipos vecinos de la LAN.
- Modificación accidental del archivo durante transferencia.
- Rutas relativas maliciosas que intenten salir del directorio de recepción.
- Corrupción de datos, cortes de conexión o archivos incompletos.
- Sobrescritura accidental de un archivo diferente con nombre idéntico.
- Errores humanos de IP, puerto, clave, certificados y permisos.
- Exposición indebida del panel de administración HTTP.

Amenazas **no resueltas por completo**: atacante activo con control de la red cuando TLS está apagado, denegación de servicio distribuida, endurecimiento multiusuario del filesystem y administración empresarial de claves.

## 2. Controles de seguridad existentes

### A. Exposición de servicios

- **FastAPI + GUI:** los iniciadores lo escuchan en `127.0.0.1:8080`. Middleware rechaza clientes que no provienen de loopback y valida origen web en acciones mutables.
- **Receptor TCP:** `127.0.0.1:9001` por defecto en CLI; al seleccionar modo LAN escucha `0.0.0.0:9001`. La API LAN exige un token de al menos 16 caracteres.
- **Destinos GUI:** se aceptan direcciones IPv4 privadas y de loopback; se rechazan IP públicas, multicast, dirección no especificada y nombres arbitrarios.
- **Ruta antigua `/api/p2p`:** añade `LOCALSYNC_PAR_LAN` como filtro explícito del destinatario; eso **no reemplaza autenticación del receptor**.

### B. Autenticación y cifrado

- El protocolo utiliza reto aleatorio + **HMAC-SHA256** + comparación `hmac.compare_digest`.
- El secreto **no se transmite** como texto en la conversación HMAC, pero debe intercambiarse previamente por canal privado.
- El motor de sockets admite **TLS opcional**, configurado en receptor mediante `--tls-cert`/`--tls-key` y en emisor mediante `--tls-ca`.
- **HMAC sin TLS no cifra los bytes del archivo**. No enviar información confidencial por Wi-Fi público o una red de terceros sin TLS validado.
- La autenticación de demo Docker usa un secreto efímero; no guardar su valor en README, capturas ni commits.
- No exponer el servicio TCP a Internet ni habilitar reenvío de puertos del router.

### C. Integridad y permisos

- SHA-256 de extremo a extremo: el receptor compara su cálculo con el hash anunciado.
- Se rechazan rutas absolutas, `..`, barras inversas, `NUL` y enlaces simbólicos relevantes en destinos.
- El archivo entra primero a `.localsync-*`; solo al validar tamaño y hash se publica.
- `keep-both` evita sobrescritura silenciosa; `reject` y `overwrite` requieren configuración explícita.
- El receptor limita tamaño a **100 MiB por archivo**, mensajes JSON a **1 MiB** y concurrencia mediante pool de workers.
- Se limpian los temporales cuando ocurre un error durante la recepción.

**Limitación importante:** las comprobaciones de path/symlink no sustituyen la protección completa frente a carreras TOCTOU en un sistema de archivos modificado simultáneamente por usuarios hostiles. Usar carpetas con permisos apropiados en una computadora confiable.

## 3. Diagnóstico de errores de red

| Síntoma | Posible causa | Acción recomendada |
| --- | --- | --- |
| `ConnectionRefusedError` / "Conexión rechazada" | No hay receptor escuchando | Iniciar receptor y verificar puerto, IP y firewall |
| `TimeoutError` / "Tiempo agotado" | Equipo inaccesible, firewall o red aislada | Confirmar misma LAN, `ping`, `ipconfig`/`hostname -I` y regla TCP |
| `Autenticación rechazada` | Tokens distintos, expirados o falta de token | Pegar **el mismo secreto** en ambos extremos, nunca publicarlo |
| `ACK no recibido` | Servidor cerrado, error de recepción o protocolo | Revisar logs del receptor y volver a intentar |
| `Versión incompatible` | Trama distinta a `LOCALSYNC_P2P_V1` | Usar la misma versión del repositorio en ambas máquinas |
| `Longitud de mensaje inválida` | Trama JSON dañada o mayor a 1 MiB | Comprobar implementación del emisor; no continuar |
| `Ruta no autorizada` | Ruta absoluta, traversal o symlink | Escoger ruta relativa dentro de la carpeta autorizada |
| `SHA-256 no coincide` | Bytes incompletos o corruptos | El receptor rechaza; comparar origen/destino y reenviar |
| `Archivo supera 100 MiB` | Límite de tamaño por archivo | Dividir archivo externamente o cambiar alcance tras pruebas |
| `Archivo distinto con mismo nombre` | Política `reject` | Usar `keep-both` o renombrar el archivo |
| Aparece `.conflict-...` | Reenvío de versión con contenido distinto | Revisar y conservar la versión correcta; no es un error de integridad |
| `SSL: CERTIFICATE_VERIFY_FAILED` | Emisor no confía en el certificado o el SAN no coincide | Configurar `--tls-ca` correcto y verificar IP/nombre del certificado |
| `Docker no está disponible` | Docker Desktop apagado o no instalado | Iniciar Docker en modo Linux o utilizar la prueba local sin Docker |
| Panel no abre en `8080` | FastAPI detenido o puerto ocupado | Iniciar con scripts de proyecto y revisar terminal |
| `/api/lan/conexion` responde 200 pero `conectado:false` | Respuesta diagnóstica (no éxito de conexión) | Revisar `detalle`; no asumir conectividad |

**No resolver una falla de conexión exponiendo FastAPI con `--host 0.0.0.0`.** Para transferir entre PCs, únicamente el receptor TCP necesita escuchar en la IP de la LAN.

## 4. Manejo de errores por capa

```mermaid
flowchart TD
    A["Operación GUI"] --> B{"Validación HTTP / Pydantic"}
    B -->|"Incorrecta"| C["HTTP 400 / 404 / 409 / 413"]
    B -->|"Válida"| D["Cliente TCP"]
    D --> E{"Conexión + autenticación"}
    E -->|"Falla"| F["Mensaje claro y posible reintento"]
    E -->|"OK"| G["Envío por bloques"]
    G --> H{"Receptor valida SHA-256 y ruta"}
    H -->|"Error"| I["Eliminar temporal y responder ERROR"]
    H -->|"OK"| J["Publicar o manejar conflicto"]
    J --> K["Enviar ACK"]
    F --> L["Error visible y evento local"]
    I --> L
    K --> M["Confirmación y hash en GUI"]
```

### Limitaciones del manejo de errores

- El cliente reintenta ante **ciertos errores de conexión**, no ante todos los rechazos semánticos (por ejemplo, ruta inválida o token incorrecto).
- La carpeta se procesa como un **conjunto de envíos individuales**: algunos archivos pueden llegar y otros fallar. La respuesta informa correctos y errores, no es una transacción de carpeta con rollback.
- No hay reanudación parcial; cada reintento comienza desde el inicio del archivo.
- El historial de operaciones del panel es **volátil** (`deque` en RAM), no un registro de auditoría persistente ni inmutable.
- La cola persistente SQLite **no** está conectada al transporte.
- El protocolo reconoce nombres `MODIFY` y `DELETE`, pero el servidor **no aplica** esas operaciones a destinos remotos.

## 5. Lista de verificación antes de usar en una LAN

- [ ] Ambos equipos en red privada de confianza.
- [ ] Panel web en `127.0.0.1:8080` de cada equipo.
- [ ] IPv4 real del destinatario identificada correctamente.
- [ ] Puerto 9001 permitido **solo desde el otro equipo**.
- [ ] Token largo, privado e idéntico en ambos receptores/emisores.
- [ ] TLS configurado y verificado si los datos son confidenciales.
- [ ] Carpeta de recepción con permisos mínimos necesarios.
- [ ] Se prueban PING/ACK, archivo binario, SHA-256 y reenvío.
- [ ] Se excluyen de capturas y repositorio las claves y los archivos privados.
- [ ] Se cierra el receptor al terminar la prueba.

## 6. Recomendaciones futuras (no implementadas)

Cifrado TLS obligatorio por defecto, certificados gestionados, identidad por dispositivo, lista de peers autorizados, limitación de velocidad y tamaño total por sesión, cancelación de envíos, auditoría persistente, endurecimiento de rutas a nivel de descriptor, reanudación por fragmentos y detección/replicación automáticas.

**Relación con el proyecto:** [Protocolo TCP](PROTOCOLO_TCP.md), [arquitectura](ARQUITECTURA.md), [manual](MANUAL_USUARIO.md).
