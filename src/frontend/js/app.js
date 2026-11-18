/* LocalSync: controles reales de la interfaz local */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const state = {view: "resumen", files: {envios:[], recibidos:[]}, demo: null, toastTimer: null, lastApiError: ""};

  function notify(message, error = false) {
    const box = $("toast");
    box.textContent = String(message);
    box.classList.toggle("error", error); box.classList.add("show");
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => box.classList.remove("show"), 4500);
  }
  function clock() {
    $("localClock").textContent = new Intl.DateTimeFormat("es-CO",
      {hour:"2-digit", minute:"2-digit", hour12:false}).format(new Date());
  }
  async function api(url, opts = {}) {
    let response;
    try { response = await fetch(url, {cache:"no-store", ...opts}); }
    catch { throw new Error("No se pudo conectar con FastAPI. Comprueba que Uvicorn esté activo."); }
    let result;
    try { result = await response.json(); }
    catch { throw new Error("La API no devolvió una respuesta JSON válida."); }
    if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail
      : (result.mensaje || "Error HTTP " + response.status));
    return result;
  }
  function post(url, obj = {}) {
    return api(url, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(obj)});
  }
  async function action(button, callback) {
    if (button.disabled) return;
    button.disabled = true;
    try { await callback(); }
    catch (e) { notify(e.message || String(e), true); }
    finally { button.disabled = false; }
  }
  function showView(view) {
    if (!["resumen","transferir","laboratorio","actividad"].includes(view)) return;
    state.view = view;
    document.querySelectorAll("[data-view]").forEach((part) => part.hidden = part.dataset.view !== view);
    document.querySelectorAll("[data-nav]").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.nav === view);
      if (btn.dataset.nav === view) btn.setAttribute("aria-current","page");
      else btn.removeAttribute("aria-current");
    });
    $("breadcrumbSection").textContent = {
      resumen:"Resumen", transferir:"Transferencias", laboratorio:"Laboratorio virtual", actividad:"Actividad",
    }[view];
    document.querySelector(".sidebar").classList.remove("visible");
    if (view === "laboratorio") loadDemo();
    if (view === "transferir") refreshFiles();
    if (view === "actividad") loadLAN();
    window.scrollTo(0, 0);
  }
  function bytes(n) {
    n = Number(n) || 0;
    return n < 1024 ? n+" B" : n < 1048576 ? (n/1024).toFixed(1)+" KiB"
      : (n/1048576).toFixed(2)+" MiB";
  }
  function badge(element, label, color = "muted") {
    element.textContent = label; element.className = "tag "+color;
  }
  function renderEvents(events) {
    const list = $("historyList"); list.replaceChildren();
    if (!events || !events.length) return empty(list,"No hay eventos en esta sesión.");
    for (const ev of events) {
      const row = document.createElement("div"); row.className = "event-item";
      const icon = document.createElement("span"); icon.className = "event-icon"; icon.textContent = "✓";
      const detail = document.createElement("div"); detail.className = "event-copy";
      const name = document.createElement("strong"); name.textContent = ev.tipo;
      const text = document.createElement("small"); text.textContent = ev.detalle;
      const timestamp = document.createElement("span"); timestamp.className = "event-time";
      const d = new Date(ev.fecha);
      timestamp.textContent = Number.isNaN(d.valueOf()) ? "" : d.toLocaleTimeString("es-CO");
      detail.append(name,text); row.append(icon,detail,timestamp); list.append(row);
    }
  }
  async function loadLAN() {
    try {
      const r = await api("/api/lan/estado");
      const active = Boolean(r.receptor.activo);
      $("statReceiver").textContent = active ? "En línea" : "Apagado";
      $("statReceiverDetail").textContent = active ? r.receptor.host+" : "+r.receptor.puerto
        : r.receptor.error || "Sin servicio TCP iniciado";
      $("statQueue").textContent = String(r.envios);
      $("statReceived").textContent = String(r.recibidos);
      $("sidebarState").textContent = active ? "Receptor activo" : "Receptor detenido";
      $("sidebarDot").classList.toggle("online", active);
      $("topologyLocalState").textContent = active ? "Escuchando" : "En espera";
      $("topologyLocal").textContent = active ? r.receptor.host+" : "+r.receptor.puerto : "Receptor local";
      badge($("receiverBadge"), active ? "EN LÍNEA" : "APAGADO", active ? "" : "muted");
      $("startReceiver").disabled = active; $("stopReceiver").disabled = !active;
      renderEvents(r.historial);
      state.lastApiError = "";
    } catch(e) {
      $("statReceiver").textContent = "No disponible";
      $("sidebarState").textContent = "API no disponible";
      if (state.lastApiError !== e.message) notify(e.message,true);
      state.lastApiError = e.message;
    }
  }
  async function loadIPs() {
    try {
      const info = await api("/api/lan/red");
      const ips = info.ips_locales || [];
      $("localIpInfo").textContent = ips.length
        ? "IP(s) detectadas: " + ips.join(", ") + ". Para recibir desde otro equipo, utiliza la IP del adaptador de tu LAN."
        : "No se detectó una IP privada. En Windows usa ipconfig; en Ubuntu usa hostname -I.";
    } catch { $("localIpInfo").textContent = "Consulta tu IP con ipconfig (Windows) o hostname -I (Ubuntu)."; }
  }
  function endpoint() {
    const host = $("remoteHost").value.trim(), port = Number($("remotePort").value);
    if (!host) throw new Error("Escribe la dirección IP del receptor.");
    if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error("Puerto inválido.");
    $("topologyRemote").textContent = host+" : "+port;
    return {host, puerto:port, token:$("sharedToken").value};
  }
  async function checkConnection() {
    const result = await post("/api/lan/conexion",endpoint());
    badge($("connectionBadge"), result.conectado ? "CONECTADO" : "SIN CONEXIÓN",
      result.conectado ? "" : "danger");
    $("connectionMessage").textContent = result.detalle;
    if (!result.conectado) throw new Error(result.detalle);
    notify("Conexión TCP comprobada con ACK."); await loadLAN();
  }
  async function startReceiver() {
    const port = Number($("receiverPort").value), lan = $("receiverMode").value === "lan";
    if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error("Puerto de receptor inválido.");
    const result = await post("/api/lan/receptor/iniciar",
      {modo_lan:lan,puerto:port,token:$("sharedToken").value});
    $("remotePort").value = String(result.puerto);
    if (!lan) $("remoteHost").value = "127.0.0.1";
    notify(lan ? "Receptor LAN iniciado; usa el mismo token en el otro equipo."
      : "Receptor local iniciado.");
    await loadLAN();
  }
  function empty(container,text) {
    container.replaceChildren();
    const e = document.createElement("div"); e.className = "empty-state"; e.textContent = text;
    container.append(e);
  }
  function fileRow(file, received) {
    const row = document.createElement("div"); row.className = "file-row";
    const glyph = document.createElement("span"); glyph.className = "file-symbol";
    glyph.textContent = received ? "⇩" : "⇧";
    const info = document.createElement("div"); info.className = "file-meta";
    const name = document.createElement("div"); name.className = "file-name";
    name.textContent = file.ruta; name.title = file.ruta;
    const detail = document.createElement("small"); detail.textContent = bytes(file.tamano);
    info.append(name,detail);
    const buttons = document.createElement("div"); buttons.className = "file-actions";
    const bandeja = received ? "recibidos" : "envios";
    function makeButton(text, callback, danger = false) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = danger ? "btn btn-small btn-danger" : "btn btn-outline btn-small";
      button.textContent = text;
      button.addEventListener("click", () => action(button, callback));
      buttons.append(button);
    }
    if (received) {
      const link = document.createElement("a");
      link.className = "btn btn-outline btn-small"; link.textContent = "↓ Descargar";
      link.href = "/api/lan/descargar?ruta=" + encodeURIComponent(file.ruta);
      buttons.append(link);
    } else {
      makeButton("⇧ Enviar", async () => {
        const result = await post("/api/lan/enviar", {...endpoint(),ruta:file.ruta,reintentos:2});
        notify("Envío completado con ACK. SHA-256: " + result.sha256.slice(0,16) + "…");
        await loadLAN(); await refreshFiles();
      });
    }
    makeButton("✓ SHA-256", async () => {
      const r = await api("/api/lan/archivo/verificar?bandeja=" + bandeja +
        "&ruta=" + encodeURIComponent(file.ruta));
      detail.textContent = bytes(r.tamano) + " · SHA-256: " + r.sha256;
      detail.title = r.sha256;
      notify("Integridad calculada correctamente.");
    });
    makeButton("✎ Renombrar", async () => {
      const actual = file.ruta.split("/").pop();
      const nuevo = window.prompt("Nuevo nombre (sin carpetas):",actual);
      if (nuevo === null) return;
      if (!nuevo.trim() || nuevo === actual) return;
      const result = await api("/api/lan/archivo", {
        method:"PATCH", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({bandeja,ruta:file.ruta,nuevo_nombre:nuevo.trim()})
      });
      notify("Archivo renombrado: "+result.ruta);
      await refreshFiles(); await loadLAN();
    });
    makeButton("Eliminar", async () => {
      if (!window.confirm("¿Eliminar de "+bandeja+" el archivo "+file.ruta+"? Esta acción no se puede deshacer.")) return;
      await api("/api/lan/archivo",{
        method:"DELETE",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({bandeja,ruta:file.ruta})
      });
      notify("Archivo eliminado: "+file.ruta);
      await refreshFiles(); await loadLAN();
    },true);
    row.append(glyph,info,buttons);
    return row;
  }
  async function refreshFiles() {
    try {
      const data = await api("/api/lan/archivos");
      state.files = data;
      const out = $("outgoingFiles"), incoming = $("incomingFiles");
      if (!data.envios.length) empty(out,"Todavía no hay archivos preparados.");
      else {out.replaceChildren();data.envios.forEach(f => out.append(fileRow(f,false)));}
      if (!data.recibidos.length) empty(incoming,"Los archivos recibidos aparecerán aquí.");
      else {incoming.replaceChildren();data.recibidos.forEach(f => incoming.append(fileRow(f,true)));}
      $("outgoingCount").textContent = data.envios.length+" archivos preparados";
      $("sendAll").disabled = data.envios.length === 0;
    } catch(e) {notify(e.message,true);}
  }
  async function upload(files) {
    if (!files || !files.length) return;
    let count = 0, failed = 0;
    $("uploadStatus").className = "operation-status busy";
    for (const [i,file] of Array.from(files).entries()) {
      $("uploadStatus").textContent = "Cargando " + (i+1) + "/" + files.length + ": " + file.name;

      if (file.size > 100*1024*1024) {failed++;notify(file.name+" supera 100 MiB",true);continue;}
      const form = new FormData();
      form.append("archivo",file,file.name);
      form.append("ruta",file.webkitRelativePath || file.name);
      try {
        await api("/api/lan/archivos",{method:"POST",body:form});
        count++;
      } catch(e) {failed++;notify(file.name+": "+e.message,true);}
    }
    $("uploadStatus").className = failed ? "operation-status error" : "operation-status";
    $("uploadStatus").textContent = "Carga finalizada: " + count + " preparado(s), " + failed + " error(es).";
    if (count) notify(count+" archivo(s) preparados.");
    await refreshFiles();await loadLAN();
  }
  function progress(lines,status) {
    let current = 0;
    lines.forEach(line => {
      const m = line.match(/\[([1-6])\/6\]/);
      if (m) current = Math.max(current, Number(m[1]));
    });
    if (status === "aprobado") current = 6;
    $("labProgress").style.width = Math.round(current/6*100)+"%";
    document.querySelectorAll("[data-test]").forEach(el =>
      el.classList.toggle("done",Number(el.dataset.test)<=current));
  }
  async function loadDemo() {
    try {
      const demo = await api("/api/lan/simulacion/estado");
      const previous = state.demo && state.demo.estado;
      state.demo = demo;
      const labels = {sin_ejecutar:"Sin ejecutar",ejecutando:"En ejecución",
        aprobado:"Aprobado",fallido:"Fallido"};
      const label = labels[demo.estado] || demo.estado;
      $("statDemo").textContent = label;
      $("labResult").textContent = label;
      badge($("labBadge"),label.toUpperCase(),
        demo.estado === "aprobado" ? "" : demo.estado === "fallido" ? "danger" : "muted");
      $("labStateDescription").textContent =
        demo.estado === "aprobado" ? "Dos nodos y todas las transferencias verificadas."
        : demo.estado === "fallido" ? "Consulta los registros para identificar el error."
        : demo.estado === "ejecutando" ? "Los contenedores están ejecutando las comprobaciones..."
        : demo.docker_disponible ? "Docker está disponible. Ejecuta la simulación."
        : "Instala o inicia Docker Desktop para ejecutar este laboratorio.";
      $("runSimulation").disabled = demo.estado === "ejecutando" || !demo.docker_disponible;
      $("cleanupSimulation").disabled = demo.estado === "ejecutando" || !demo.docker_disponible;
      const pre = $("labLog");
      const output = demo.salida.length ? demo.salida.join("\n")
        : "Esperando una simulación.\nPara comenzar, pulsa «Ejecutar simulación completa».";
      if (pre.textContent !== output) {
        const atBottom = pre.scrollTop+pre.clientHeight >= pre.scrollHeight-70;
        pre.textContent = output;
        if (atBottom) pre.scrollTop = pre.scrollHeight;
      }
      progress(demo.salida,demo.estado);
      $("downloadEvidence").hidden = demo.estado === "sin_ejecutar";
      if (previous === "ejecutando" && demo.estado === "aprobado")
        notify("¡Auditoría virtual aprobada! Ya puedes descargar la evidencia.");
      else if (previous === "ejecutando" && demo.estado === "fallido")
        notify("La simulación falló. Consulta el registro.",true);
    } catch(e) {notify(e.message,true);}
  }
  function events() {
    document.querySelectorAll("[data-nav]").forEach(b =>
      b.addEventListener("click",()=>showView(b.dataset.nav)));
    document.querySelectorAll("[data-jump]").forEach(b =>
      b.addEventListener("click",()=>showView(b.dataset.jump)));
    $("menuToggle").addEventListener("click",() =>
      document.querySelector(".sidebar").classList.toggle("visible"));
    $("refreshAll").addEventListener("click",()=>Promise.all([loadLAN(),refreshFiles(),loadDemo()]));
    $("refreshHistory").addEventListener("click",loadLAN);
    $("refreshFiles").addEventListener("click",refreshFiles);
    $("remoteHost").addEventListener("change",() =>
      $("topologyRemote").textContent=$("remoteHost").value+" : "+$("remotePort").value);
    $("checkConnection").addEventListener("click",() => action($("checkConnection"),checkConnection));
    $("startReceiver").addEventListener("click",() => action($("startReceiver"),startReceiver));
    $("stopReceiver").addEventListener("click",() => action($("stopReceiver"),async () => {
      await post("/api/lan/receptor/detener");notify("Receptor detenido.");await loadLAN();
    }));
    $("toggleToken").addEventListener("click",() => {
      const input=$("sharedToken");input.type=input.type==="password"?"text":"password";
    });
    $("newToken").addEventListener("click",() => {
      const random=new Uint8Array(24);crypto.getRandomValues(random);
      $("sharedToken").value=Array.from(random,b=>b.toString(16).padStart(2,"0")).join("");
      notify("Token seguro generado; úsalo en ambos equipos LAN.");
    });
    $("copyToken").addEventListener("click",() => action($("copyToken"),async () => {
      if (!$("sharedToken").value) throw new Error("Primero genera o escribe un token.");
      await navigator.clipboard.writeText($("sharedToken").value);
      notify("Token copiado; compártelo de forma privada.");
    }));
    $("uploadFiles").addEventListener("change",async event => {
      await upload(event.target.files);event.target.value="";
    });
    $("uploadFolder").addEventListener("change",async event => {
      await upload(event.target.files);event.target.value="";
    });
    const drop=$("dropZone");
    drop.addEventListener("click",()=>$("uploadFiles").click());
    drop.addEventListener("keydown",event => {
      if (event.key==="Enter"||event.key===" ") {event.preventDefault();$("uploadFiles").click();}
    });
    drop.addEventListener("dragover",event => {event.preventDefault();drop.classList.add("dragging");});
    drop.addEventListener("dragleave",()=>drop.classList.remove("dragging"));
    drop.addEventListener("drop",event => {
      event.preventDefault();drop.classList.remove("dragging");upload(event.dataTransfer.files);
    });
    $("sendAll").addEventListener("click",()=>action($("sendAll"),async () => {
      $("sendStatus").className = "operation-status busy";
      $("sendStatus").textContent = "Transfiriendo archivos por TCP. No cierres esta ventana.";
      try {
        const result=await post("/api/lan/enviar-carpeta",{...endpoint(),prefijo:"LocalSync"});
        $("sendStatus").textContent = result.mensaje;
        $("sendStatus").className = result.errores ? "operation-status error" : "operation-status";
        notify(result.mensaje,result.errores>0);
        await loadLAN();await refreshFiles();
      } catch(e) {
        $("sendStatus").textContent = "No se completó el envío: "+e.message;
        $("sendStatus").className = "operation-status error";
        throw e;
      }
    }));
    $("runSimulation").addEventListener("click",()=>action($("runSimulation"),async () => {
      await post("/api/lan/simulacion/iniciar");
      notify("Simulación Docker iniciada.");
      showView("laboratorio");await loadDemo();
    }));
    $("cleanupSimulation").addEventListener("click",()=>action($("cleanupSimulation"),async () => {
      if (!confirm("¿Eliminar los contenedores y volúmenes de prueba del laboratorio?")) return;
      await post("/api/lan/simulacion/limpiar");
      notify("Limpieza del laboratorio iniciada.");await loadDemo();
    }));
  }
  async function start() {
    events();clock();
    await Promise.all([loadLAN(),refreshFiles(),loadDemo(),loadIPs()]);
    setInterval(clock,30000);
    setInterval(()=>{if(!document.hidden)loadLAN();},5000);
    setInterval(()=>{
      if(!document.hidden&&(state.view==="laboratorio"||state.demo?.estado==="ejecutando"))loadDemo();
    },1700);
    setInterval(()=>{if(!document.hidden&&state.view==="transferir")refreshFiles();},7500);
  }
  start();
})();
