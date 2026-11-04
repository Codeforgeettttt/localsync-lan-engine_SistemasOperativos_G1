/**
 * Lógica del Panel Web Local - LocalSync (Grupo G1)
 * Integrantes: Valery Michell Herrera Roca, Daniel Felipe Rojas Gonzales
 */
(function () {
    if (window.__LOCALSYNC_UI_LOADED__) return;
    window.__LOCALSYNC_UI_LOADED__ = true;

    const statusContainer = document.getElementById("apiStatusContainer");
    const controlFeedback = document.getElementById("controlFeedback");
    const btnRefresh = document.getElementById("btnRefresh");
    const btnInitDb = document.getElementById("btnInitDb");
    const btnPause = document.getElementById("btnPause");
    const btnResume = document.getElementById("btnResume");

    async function cargarEstadoAPI() {
        try {
            const resp = await fetch("/api/estado");
            if (!resp.ok) throw new Error("HTTP " + resp.status);
            const data = await resp.json();
            const bd = data.estado_base_datos_sqlite || {};
            const motor = data.estado_motor_local || {};
            statusContainer.innerHTML = `
                <p><strong>Fase Reportada:</strong> ${data.fase_proyecto}</p>
                <p><strong>Modo Simulación UI:</strong> ${data.es_simulacion ? "Sí (Datos de demostración identificados)" : "No"}</p>
                <p><strong>Sistema Detectado:</strong> ${data.entorno_real_detectado.sistema_operativo} (Python ${data.entorno_real_detectado.python_version})</p>
                <p><strong>Base de Datos SQLite Inicializada:</strong> ${bd.bd_inicializada ? "Sí (" + bd.tablas_detectadas.length + " tablas)" : "No inicializada aún"}</p>
                <p><strong>Bandera Pausa (Memoria API):</strong> ${motor.sincronizacion_pausada ? "Pausada" : "Activa"} | <strong>Watchdog:</strong> ${motor.watchdog_estado_desarrollo}</p>
            `;
        } catch (err) {
            statusContainer.innerHTML = `
                <p><strong>[MODO ARCHIVO ESTÁTICO SIN SERVIDOR UVICORN ACTIVO]</strong></p>
                <p>Para consultar <code>/api/estado</code> en vivo, ejecuta: <code>uvicorn src.backend.api.routes:app --host 127.0.0.1 --port 8080</code></p>
            `;
        }
    }

    async function inicializarBD() {
        try {
            const resp = await fetch("/api/inicializar-bd", { method: "POST" });
            const data = await resp.json();
            controlFeedback.textContent = data.mensaje || "Esquema SQLite procesado.";
            await cargarEstadoAPI();
        } catch (err) {
            controlFeedback.textContent = "No se pudo contactar /api/inicializar-bd (verifica que Uvicorn esté activo).";
        }
    }

    async function cambiarPausa(pausar) {
        try {
            const resp = await fetch("/api/control/pausa", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ pausar: pausar })
            });
            const data = await resp.json();
            controlFeedback.textContent = `Bandera sincronizacion_pausada = ${data.sincronizacion_pausada} (${data.alcance_accion})`;
            await cargarEstadoAPI();
        } catch (err) {
            controlFeedback.textContent = "Acción no enviada: el servidor local Uvicorn no está en ejecución.";
        }
    }

    if (btnRefresh) btnRefresh.addEventListener("click", cargarEstadoAPI);
    if (btnInitDb) btnInitDb.addEventListener("click", inicializarBD);
    if (btnPause) btnPause.addEventListener("click", () => cambiarPausa(true));
    if (btnResume) btnResume.addEventListener("click", () => cambiarPausa(false));

    cargarEstadoAPI();
})();
