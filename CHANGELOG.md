# Historial de cambios — LocalSync

Registro técnico de modificaciones comprobables del repositorio, siguiendo una convención inspirada en **Keep a Changelog**. La etiqueta `0.3.0-lan` es la **versión interna actual de la API FastAPI**; no debe interpretarse como un tag o release publicado si no aparece así en GitHub.

## [Sin etiqueta de release] — 2026-11-18: consolidación de documentación

### Documentado
- README renovado con alcance real, instalación en Windows/Ubuntu, operaciones de GUI, CLI y red LAN.
- Referencia de API REST y estado real de SQLite.
- Arquitectura de módulos, despliegue, diagramas editables y secuencia de transferencia TCP.
- Protocolo de tramas `LOCALSYNC_P2P_V1`, autenticación HMAC, SHA-256 y políticas de conflicto.
- Manual de usuario, seguridad, manejo de errores, límites y pruebas.
- Control de versiones, convención de commits, trazabilidad, ramas y procedimiento de releases.
- Fuentes Mermaid corregidas para diferenciar el **motor actual** de la **sincronización futura**.

### Alcance
Son cambios de **documentación**. No constituyen por sí solos una nueva funcionalidad del motor ni un cambio de la versión interna de FastAPI.

## [0.3.0-lan (versión interna)] — Integración del PR #1, 2026-11-18

### Añadido
- Servidor y cliente TCP para transferencias de archivos por LAN.
- Interfaz web responsive: resumen, transferencias, laboratorio virtual y actividad.
- Envío de archivos y carpetas con subdirectorios; receptor independiente y configurable.
- Autenticación por desafío HMAC-SHA256 y soporte opcional de TLS por certificados.
- Validación de SHA-256 y publicación de archivos después de verificar la integridad.
- Manejo de conflictos `keep-both`, `reject` y `overwrite`; reenvíos idempotentes.
- Endpoints locales para preparar, descargar, verificar, renombrar y eliminar archivos.
- Registro de eventos de sesión, controles de conexión y diagnósticos de red.
- Laboratorio Docker de dos contenedores Linux en red privada y prueba TCP sin Docker.
- Plantilla de servicio `systemd` para receptor Linux y guías de instalación.
- Pruebas unitarias, integración FastAPI, Chrome/Playwright, Docker y CI Windows/Ubuntu.

### Corregido y mejorado
- Errores de rutas no autorizadas y validación del destino.
- Mensajes más claros de conexión rechazada, timeout, autenticación y motor Docker apagado.
- Inicio del navegador únicamente después de que FastAPI esté disponible.
- Estado del laboratorio tras limpieza y casos de duplicación/versión conflictiva.
- Conflictos del PR entre `src/backend/api/routes.py`, `src/frontend/index.html` y `src/frontend/js/app.js`, preservando la GUI moderna e incorporando las mejoras provenientes de `main`.

### Evidencia
- [PR #1 fusionado](https://github.com/Codeforgeettttt/localsync-lan-engine_SistemasOperativos_G1/pull/1) mediante [`2cfc6e6`](https://github.com/Codeforgeettttt/localsync-lan-engine_SistemasOperativos_G1/commit/2cfc6e67583e3c01acce7d71e632d961f7ea5b13).
- [Pruebas Windows/Ubuntu](https://github.com/Codeforgeettttt/localsync-lan-engine_SistemasOperativos_G1/actions/runs/44251333149).
- [Pruebas Python, Docker y Chrome](https://github.com/Codeforgeettttt/localsync-lan-engine_SistemasOperativos_G1/actions/runs/44251333232).

### Limitaciones conocidas
- No hay observador Watchdog/inotify en funcionamiento.
- No hay transferencia automática por eventos, propagación remota de `MODIFY`/`DELETE`, ni cola persistente conectada a SQLite.
- No hay reanudación parcial de archivos ni logs de transferencias persistentes en la GUI.
- TLS está disponible, pero **no se activa por defecto**.

## [Fase base] — Estructuración anterior al PR #1

- Arquitectura inicial de dos nodos, FastAPI, modelo relacional SQLite, funciones SHA-256, validaciones y documentos de requisitos.
- Artefactos académicos PDF e imágenes de diseño conservados como historial; pueden reflejar estados antiguos y deben diferenciarse del comportamiento actual.
- Referencia histórica: commit base [`ce7022a`](https://github.com/Codeforgeettttt/localsync-lan-engine_SistemasOperativos_G1/commit/ce7022ab85ec22e544aa754816769a7be7df0350).

---

Para un release futuro, crear un tag explícito solo después de revisar el commit, pasar pruebas y publicar notas. Ver [control de versiones](documentacion/CONTROL_DE_VERSIONES.md).
