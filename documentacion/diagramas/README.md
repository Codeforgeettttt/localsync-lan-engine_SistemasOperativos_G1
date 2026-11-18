# Diagramas de LocalSync

Los archivos `.mmd` de la carpeta [fuentes_mermaid](fuentes_mermaid/) contienen **fuentes editables**. Se pueden visualizar con Mermaid Live Editor o incrustar en bloques `mermaid` de GitHub Markdown.

## Diagramas vigentes (estado del código)

| Fuente | Diagrama | Alcance |
| --- | --- | --- |
| [arquitectura_p2p.mmd](fuentes_mermaid/arquitectura_p2p.mmd) | Componentes y comunicación entre dos equipos | **Implementación actual** |
| [estructura_y_flujo.mmd](fuentes_mermaid/estructura_y_flujo.mmd) | Secuencia del envío real | **Implementación actual** |
| [despliegue_lan.mmd](fuentes_mermaid/despliegue_lan.mmd) | Despliegue físico y puertos | **Implementación actual** |
| [estados_transferencia.mmd](fuentes_mermaid/estados_transferencia.mmd) | Transiciones y errores de una transferencia | **Implementación actual** |
| [modelo_relacional.mmd](fuentes_mermaid/modelo_relacional.mmd) | Seis tablas de SQLite | **Esquema definido; no conectado totalmente** |
| [flujo_sincronizacion_8_etapas.mmd](fuentes_mermaid/flujo_sincronizacion_8_etapas.mmd) | Pipeline de sincronización futura | **Diseño propuesto, no implementado** |

**Precaución:** las imágenes `arquitectura_inicial.png`, `estructura_producto.png` y los PDF históricos forman parte de la documentación original. Pueden mostrar fases anteriores, componentes proyectados y estados obsoletos. Para una presentación técnica del sistema actual utilizar los diagramas `.mmd` arriba y [ARQUITECTURA.md](../ARQUITECTURA.md).

## Distinciones fundamentales

- **TCP:** envía archivos manualmente entre los equipos.
- **HMAC:** autentica al par, no cifra los bytes.
- **TLS opcional:** cifra el canal cuando se configura un certificado confiable.
- **SQLite:** tiene el modelo relacional, pero no orquesta una cola de transferencias en producción.
- **Watchdog:** no es todavía un observador en funcionamiento; su diagrama está rotulado como diseño futuro.
