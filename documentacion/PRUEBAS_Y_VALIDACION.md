# Plan de pruebas, validación y evidencias de LocalSync

**Proyecto:** LocalSync LAN Engine, Grupo G1 · **Estado:** pruebas automatizadas y laboratorios implementados; prueba física reportada por el equipo, pendiente de adjuntar evidencia técnica detallada en este documento.

## 1. Estrategia de validación

Se evalúan cuatro niveles separados:

1. **Unitarias:** cálculo SHA-256, rutas válidas/inválidas, formato y parser de tramas.
2. **Integración en localhost:** receptor + cliente TCP reales, autenticación, archivos y carpetas, conflictos, conexión interrumpida.
3. **Laboratorio automatizado:** dos contenedores Linux en una red Docker privada, volúmenes separados, envíos A→B y B→A.
4. **Prueba de campo:** dos **computadores físicos**, con IPv4 de una LAN real, firewall y hash en emisor/receptor.

El alcance de una prueba en localhost **no** equivale al de una LAN física; dos contenedores Docker comparten kernel y **no** son máquinas virtuales completas. La prueba en dos computadores debe conservar evidencias propias.

## 2. Matriz de pruebas funcionales

| Código | Caso | Evidencia o procedimiento | Criterio de aceptación |
| --- | --- | --- | --- |
| PT-01 | Conectar a receptor activo | PING y ACK | `conectado:true` / ACK |
| PT-02 | Receptor fuera de línea | IP/puerto sin servidor | Mensaje claro, sin falso éxito |
| PT-03 | Archivo de texto A→B | `enviar_archivo` y recepción | Archivo presente y hash idéntico |
| PT-04 | Binario B→A | Comparar bytes y SHA-256 | Integridad exacta |
| PT-05 | Carpeta anidada | Envío recursivo | Subdirectorios y archivos íntegros |
| PT-06 | Autenticación HMAC correcta | Token idéntico | Conexión autorizada |
| PT-07 | Token incorrecto | Token no coincidente | Conexión rechazada |
| PT-08 | TLS (si está configurado) | Certificado de prueba | Handshake validado y envío correcto |
| PT-09 | Ruta traversal | `../` o ruta absoluta | Rechazo sin escribir fuera de base |
| PT-10 | Transferencia incompleta / SHA incorrecto | Simular socket o bytes truncados | No publicar archivo inválido; limpiar temporales |
| PT-11 | Conflicto de nombre | Distinto contenido con mismo nombre | Original conservado, versión alternativa |
| PT-12 | Reenvío idéntico | Repetir archivo | No crear duplicados |
| PT-13 | Múltiples clientes | Thread pool | Transferencias independientes verificadas |
| PT-14 | Máximo de tamaño | Archivo superior a 100 MiB | Rechazo coherente |
| PT-15 | Subida web | Multipart local | Archivo preparado en carpeta autorizada |
| PT-16 | Gestión local | Verificar, renombrar, eliminar | API/GUI coherentes, sin borrar remoto |
| PT-17 | GUI Chrome | Browser E2E con Playwright | Controles funcionales, sin errores JS |
| PT-18 | Dos nodos sin Docker | `simulacion/demo_local.py` | A↔B, hash y conflictos correctos |
| PT-19 | Dos nodos Linux Docker | `simulacion/demo.py` | Red privada y transferencias correctas |
| PT-20 | Prueba física LAN | Dos PCs reales | ACK + hashes iguales en ambos sentidos |

## 3. Correspondencia de pruebas y código

| Archivo | Alcance principal |
| --- | --- |
| `pruebas/test_integridad_sha256.py` | SHA-256 |
| `pruebas/test_integridad_y_rutas.py` | Validación de rutas |
| `pruebas/test_tcp_servidor.py` | Servidor, framing y comunicación |
| `pruebas/test_cliente_tcp.py` | Cliente, conexión y envío |
| `pruebas/test_transferencia.py` | Recepción y comprobación del contenido |
| `pruebas/test_dos_nodos_tcp.py` | Dos nodos TCP locales independientes |
| `pruebas/test_lan_completo.py` | Autenticación, TLS, conflictos, concurrencia y rutas |
| `pruebas/test_api_p2p.py` | Endpoint de compatibilidad P2P |
| `pruebas/test_api_destino.py` | Destinos IPv4 permitidos/rechazados |
| `pruebas/test_panel_lan.py` | FastAPI: subir, transferir, descargar y gestionar |
| `pruebas/test_demo_local.py` | Prueba de dos nodos TCP sin Docker |
| `pruebas/test_panel_navegador.py` | Navegador Chrome/Playwright (job dedicado) |
| `pruebas/test_panel_simulacion_docker.py` | API de ejecución de Docker (job dedicado) |

Ejecutar las pruebas desde la **raíz** del proyecto:

```bash
python -m pip install -r requirements.txt
python -m pytest -v
python -m unittest discover -s pruebas -p "test_*.py" -v
```

Dos pruebas especializadas se **omiten** en la suite general y se habilitan con variables de entorno en sus respectivos jobs de CI. Un `skipped` esperado no implica que todo el laboratorio haya sido probado en ese job general.

## 4. Integración continua

- [`.github/workflows/tests.yml`](../.github/workflows/tests.yml): se activa en `push` / `pull_request`, ejecuta `unittest` en **Windows y Ubuntu**.
- [`.github/workflows/pruebas.yml`](../.github/workflows/pruebas.yml): `pytest`, validación de JavaScript, Docker y Chrome. Se activa con `pull_request` hacia `main`, `workflow_dispatch` y push a `feature/motor-p2p-pruebas`. **No se activa en cada push a `main` por su configuración actual**.
- Se guardan capturas visuales mediante artefacto `localsync-gui-capturas` cuando se ejecuta el trabajo de navegador.

Evidencia verificable de integración del PR #1 (18-11-2026):

- [LocalSync CI — Windows y Ubuntu](https://github.com/Codeforgeettttt/localsync-lan-engine_SistemasOperativos_G1/actions/runs/44251333149).
- [Pruebas LocalSync — Python, Docker y Chrome](https://github.com/Codeforgeettttt/localsync-lan-engine_SistemasOperativos_G1/actions/runs/44251333232).
- [PR #1 fusionado](https://github.com/Codeforgeettttt/localsync-lan-engine_SistemasOperativos_G1/pull/1).

**Interpretación:** los CI de ese commit estaban aprobados; no son una garantía universal ni sustituyen repetir pruebas después de cada cambio técnico.

## 5. Ejecución de laboratorio reproducible

### A. Prueba localhost sin Docker

```bash
python simulacion/demo_local.py
```

La evidencia debe mostrar `PRUEBA LOCAL APROBADA` y hashes idénticos. No afirmar que representa dos sistemas operativos virtualizados.

### B. Docker (dos contenedores)

```bash
python simulacion/demo.py
python simulacion/demo.py --status
```

Debe mostrar `RESULTADO: AUDITORÍA VIRTUAL APROBADA`. Comprobar `nodo-a` y `nodo-b`, red `lan_virtual`, hashes idénticos y conflicto conservado. Limpiar con `python simulacion/demo.py --cleanup` solo después de tomar evidencias (elimina volúmenes de prueba).

### C. GUI

Desde `http://127.0.0.1:8080/` → **Laboratorio virtual**. Ejecutar la prueba deseada, observar resultado y descargar el archivo de texto desde **Descargar evidencia**. No confundir el último resultado de la GUI con los logs históricos de CI.

## 6. Acta para la prueba física entre equipos

**El equipo ha comunicado que la transferencia física funcionó**, pero aquí no se inventan datos de red, latencias, tamaños, capturas ni hashes.

Completar el siguiente formato con la sesión real:

| Campo | Registrar durante la prueba |
| --- | --- |
| Fecha y hora | A completar |
| Commit exacto de `main` | `git rev-parse --short HEAD` |
| Sistema operativo del equipo A/B | A completar |
| IPv4 privada del equipo A/B | A completar (si hay restricciones de privacidad, ocultar en evidencia pública) |
| Puerto TCP | 9001 o el valor realmente usado |
| Archivo y tamaño | A completar |
| SHA-256 origen | A completar |
| SHA-256 destino | A completar |
| A → B / B → A | ACK y recepción observados |
| Resultado / incidente | A completar |
| Evidencia (foto/video/log) | Ruta o enlace al archivo correspondiente |

En Windows: `Get-FileHash -Algorithm SHA256 .\archivo.txt`. En Ubuntu: `sha256sum archivo.txt`. No compartir el token, el `.env` ni claves de TLS.

## 7. Evidencia mínima recomendada para sustentación

- Captura del panel y receptor activo **en ambos equipos**.
- Captura de IP privada y prueba de comunicación (ocultando detalles sensibles al publicar).
- Envío, `ACK` y archivo recibido en las dos direcciones.
- Comparación de SHA-256 de cada transferencia.
- Prueba de carpeta anidada y nombre conflictivo.
- Capturas/logs de Docker y `pytest`/CI aprobados.
- Explicación de diferencias entre prueba de localhost, contenedores y LAN real.
- Declaración precisa del alcance: no hay observador Watchdog ni reanudación por bloques.

## 8. Condiciones de cierre

La entrega técnica del **transporte manual de archivos** puede considerarse lista cuando: la suite pasa en la rama final, las evidencias de campo se anexan, la GUI y CLI demuestran A↔B, el receptor rechaza operaciones inválidas y la documentación es consistente con código y estado real. Si el profesor exige **sincronización automática**, ese requisito sigue pendiente y debe planificarse por separado.
