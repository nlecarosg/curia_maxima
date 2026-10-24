/* Lee solo datos.json, publicado en el mismo origen. No llama a otros dominios. */

const MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

const ESTADOS = {
  vigente: "Vigente",
  derogada: "Derogada",
  modificada: "Modificada",
  borrador: "Borrador",
  publicada: "Publicada",
  adoptada: "Adoptada",
  retirada: "Retirada",
  "no actualizado": "No actualizado",
};

const TIPOS_NORMA = {
  constitucion: "Constitución",
  ley: "Ley",
  decreto: "Decreto",
  decreto_exento: "Decreto exento",
  resolucion: "Resolución",
  resolucion_exenta: "Resolución exenta",
  ordenanza: "Ordenanza",
};

const TIPOS_PROPUESTA = { nueva: "Nueva", "derogación": "Derogación" };
const RELACIONES = { modifica: "Modifica", complementa: "Complementa", deroga: "Deroga", cita: "Cita" };
const CARGOS = { diputado: "diputado", diputada: "diputada", senador: "senador", senadora: "senadora" };
let datosSitio = null;
let ordenPropuestas = null;

const ACCIONES = {
  presentada: "presentada",
  patrocinada: "patrocinada",
  indicada: "indicada",
  aprobada: "aprobada",
  rechazada: "rechazada",
  retirada: "retirada",
};

function nodo(etiqueta, contenido, clase) {
  const elemento = document.createElement(etiqueta);
  if (clase) elemento.className = clase;
  if (contenido != null) elemento.textContent = String(contenido);
  return elemento;
}

function urlSegura(url) {
  return typeof url === "string" && /^https:\/\/[^\s]+$/.test(url);
}

function ancla(prefijo, id) {
  return `${prefijo}-${String(id).replace(/[^A-Za-z0-9_-]/g, "")}`;
}

function enlace(url, etiqueta, clase) {
  if (!urlSegura(url)) return nodo("span", etiqueta, clase);
  const a = document.createElement("a");
  a.href = url;
  a.rel = "noopener noreferrer";
  a.textContent = etiqueta;
  if (clase) a.className = clase;
  return a;
}

function enlaceInterno(id, etiqueta) {
  const a = document.createElement("a");
  a.href = `#${id}`;
  a.textContent = etiqueta;
  return a;
}

function formatoNumero(valor, maxDecimales = 4) {
  if (typeof valor !== "number" || !Number.isFinite(valor)) return "—";
  const factor = 10 ** maxDecimales;
  const redondeado = Math.round(valor * factor) / factor;
  return new Intl.NumberFormat("es-CL", { maximumFractionDigits: maxDecimales }).format(redondeado);
}

function formatoFecha(iso) {
  const coincidencia = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
  if (!coincidencia) return iso ? String(iso) : "—";
  const fecha = new Date(Date.UTC(Number(coincidencia[1]), Number(coincidencia[2]) - 1, Number(coincidencia[3])));
  return new Intl.DateTimeFormat("es-CL", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(fecha);
}

function formatoInstante(iso) {
  const texto = String(iso || "");
  const coincidencia = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/.exec(texto);
  if (!coincidencia) return texto || "—";
  return `${formatoFecha(coincidencia[1])}, ${coincidencia[2]} UTC`;
}

function etiquetaEstado(estado) {
  return ESTADOS[estado] || (estado ? String(estado) : "Sin estado");
}

function claseEstado(estado) {
  const base = String(estado || "desconocido").replace(/\s+/g, "-");
  return `estado estado-${base}`;
}

function aviso(mensaje) {
  const parrafo = nodo("p", mensaje, "aviso");
  parrafo.setAttribute("role", "alert");
  return parrafo;
}

function lineaRepositorio(url) {
  const parrafo = nodo("p", "", "repo");
  parrafo.append("Repositorio: ");
  parrafo.append(enlace(url, url ? url.replace("https://github.com/", "") : "no disponible"));
  parrafo.append(".");
  return parrafo;
}

function listaErrores(errores) {
  if (!Array.isArray(errores) || errores.length === 0) return null;
  const lista = document.createElement("ul");
  lista.className = "errores";
  for (const error of errores) lista.append(nodo("li", error));
  return lista;
}

function htmlProsa(html) {
  const documento = new DOMParser().parseFromString(String(html || ""), "text/html");
  const permitidos = new Set(["P", "H1", "H2", "H3", "OL", "UL", "LI", "BLOCKQUOTE", "STRONG", "EM", "A", "BR"]);
  function limpiar(padre) {
    for (const hijo of [...padre.childNodes]) {
      if (hijo.nodeType === Node.TEXT_NODE) continue;
      if (hijo.nodeType !== Node.ELEMENT_NODE || !permitidos.has(hijo.tagName)) {
        hijo.replaceWith(document.createTextNode(hijo.textContent || ""));
        continue;
      }
      if (hijo.tagName === "A") {
        const href = hijo.getAttribute("href") || "";
        for (const atributo of [...hijo.attributes]) hijo.removeAttribute(atributo.name);
        if (!urlSegura(href)) {
          hijo.replaceWith(document.createTextNode(hijo.textContent || ""));
          continue;
        }
        hijo.setAttribute("href", href);
        hijo.rel = "noopener noreferrer";
      } else {
        for (const atributo of [...hijo.attributes]) hijo.removeAttribute(atributo.name);
      }
      limpiar(hijo);
    }
  }
  limpiar(documento.body);
  const prosa = document.createElement("div");
  prosa.className = "prosa";
  prosa.append(...documento.body.childNodes);
  return prosa;
}

function colorDe(variable, respaldo) {
  const valor = getComputedStyle(document.documentElement).getPropertyValue(variable).trim();
  return valor || respaldo;
}

function grafico(puntos, descripcion) {
  const figura = document.createElement("figure");
  figura.className = "grafico";
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", descripcion);
  figura.append(svg);
  const leyenda = document.createElement("figcaption");
  leyenda.textContent = descripcion;
  figura.append(leyenda);
  let anchoPrevio = 0;

  function dibujar() {
    const ancho = Math.max(280, Math.round(figura.clientWidth || 320));
    if (ancho === anchoPrevio && svg.childNodes.length) return;
    anchoPrevio = ancho;
    const alto = 220;
    const margen = { izq: 56, der: 8, sup: 14, inf: 32 };
    svg.setAttribute("viewBox", `0 0 ${ancho} ${alto}`);
    svg.replaceChildren();
    if (!puntos.length) return;

    const valores = puntos.map((punto) => punto.valor);
    let minimo = Math.min(...valores);
    let maximo = Math.max(...valores);
    if (minimo === maximo) {
      minimo -= 1;
      maximo += 1;
    }
    const holgura = (maximo - minimo) * 0.12;
    const yMin = minimo - holgura;
    const yMax = maximo + holgura;
    const interior = ancho - margen.izq - margen.der;
    const xDe = (indice) => {
      if (puntos.length === 1) return margen.izq + interior / 2;
      return margen.izq + (indice / (puntos.length - 1)) * interior;
    };
    const yDe = (valor) => margen.sup + (1 - (valor - yMin) / (yMax - yMin)) * (alto - margen.sup - margen.inf);
    const ns = "http://www.w3.org/2000/svg";
    const tinta = colorDe("--muted", "#4e483f");
    const linea = colorDe("--grafico", "#243044");
    const suave = colorDe("--linea", "#d4cbb8");
    const sello = colorDe("--sello", "#732222");

    function figuraSvg(nombre, atributos) {
      const elemento = document.createElementNS(ns, nombre);
      for (const [clave, valor] of Object.entries(atributos)) elemento.setAttribute(clave, String(valor));
      return elemento;
    }

    for (const marca of [minimo, (minimo + maximo) / 2, maximo]) {
      const y = yDe(marca);
      svg.append(figuraSvg("line", { x1: margen.izq, y1: y, x2: ancho - margen.der, y2: y, stroke: suave, "stroke-width": 1 }));
      const texto = figuraSvg("text", {
        x: margen.izq - 8,
        y: y + 4,
        "text-anchor": "end",
        fill: tinta,
        "font-size": 12,
        "font-family": "system-ui, sans-serif",
      });
      texto.textContent = formatoNumero(marca, 1);
      svg.append(texto);
    }

    if (puntos.length >= 2) {
      const trazo = puntos.map((punto, indice) => `${indice === 0 ? "M" : "L"}${xDe(indice).toFixed(1)},${yDe(punto.valor).toFixed(1)}`).join(" ");
      const base = yDe(minimo).toFixed(1);
      svg.append(figuraSvg("path", {
        d: `${trazo} L${xDe(puntos.length - 1).toFixed(1)},${base} L${xDe(0).toFixed(1)},${base} Z`,
        fill: linea,
        "fill-opacity": "0.08",
      }));
      svg.append(figuraSvg("path", {
        d: trazo,
        fill: "none",
        stroke: linea,
        "stroke-width": 2,
        "stroke-linejoin": "round",
        "stroke-linecap": "round",
      }));
    }

    const ultimo = puntos[puntos.length - 1];
    svg.append(figuraSvg("circle", {
      cx: xDe(puntos.length - 1),
      cy: yDe(ultimo.valor),
      r: 4,
      fill: sello,
    }));

    const etiquetas = [];
    puntos.forEach((punto, indice) => {
      const mes = punto.fecha.slice(5, 7);
      const mostrar = indice === 0 || indice === puntos.length - 1 || mes === "01";
      if (mostrar) etiquetas.push({ indice, x: xDe(indice) });
    });
    const visibles = [];
    for (const etiqueta of etiquetas) {
      const previa = visibles[visibles.length - 1];
      if (previa && etiqueta.x - previa.x < 52) {
        if (etiqueta.indice === puntos.length - 1) visibles.pop();
        else continue;
      }
      visibles.push(etiqueta);
    }
    for (const etiqueta of visibles) {
      const anclaTexto = etiqueta.indice === 0 ? "start" : etiqueta.indice === puntos.length - 1 ? "end" : "middle";
      const texto = figuraSvg("text", {
        x: etiqueta.x,
        y: alto - 8,
        "text-anchor": anclaTexto,
        fill: tinta,
        "font-size": 12,
        "font-family": "system-ui, sans-serif",
      });
      const [anio, mes] = puntos[etiqueta.indice].fecha.split("-");
      texto.textContent = `${MESES_CORTOS[Number(mes) - 1] || mes} ${anio}`;
      svg.append(texto);
    }
  }

  dibujar();
  if (typeof ResizeObserver === "function") {
    const observador = new ResizeObserver(() => dibujar());
    observador.observe(figura);
  }
  return figura;
}

function tablaSerie(puntos) {
  const detalles = document.createElement("details");
  const resumen = document.createElement("summary");
  resumen.textContent = "Ver los valores de la serie";
  detalles.append(resumen);
  const contenedor = document.createElement("div");
  contenedor.className = "tabla-contenedor";
  const tabla = document.createElement("table");
  const titulo = document.createElement("caption");
  titulo.textContent = "Valor del índice en cada fecha";
  tabla.append(titulo);
  const cabeza = document.createElement("thead");
  const filaCabeza = document.createElement("tr");
  for (const nombre of ["Fecha del dato", "Valor"]) {
    const th = document.createElement("th");
    th.scope = "col";
    th.textContent = nombre;
    filaCabeza.append(th);
  }
  cabeza.append(filaCabeza);
  tabla.append(cabeza);
  const cuerpo = document.createElement("tbody");
  for (const punto of puntos) {
    const fila = document.createElement("tr");
    const fecha = document.createElement("td");
    fecha.textContent = formatoFecha(punto.fecha);
    const valor = document.createElement("td");
    valor.textContent = formatoNumero(punto.valor);
    fila.append(fecha, valor);
    cuerpo.append(fila);
  }
  tabla.append(cuerpo);
  contenedor.append(tabla);
  detalles.append(contenedor);
  return detalles;
}

function fichaIndicador(serie) {
  const articulo = document.createElement("article");
  articulo.className = "ficha";
  const cabecera = document.createElement("div");
  cabecera.className = "ficha-cabecera";
  cabecera.append(nodo("p", serie.codigo || serie.id, "codigo"));
  cabecera.append(nodo("p", etiquetaEstado(serie.estado), claseEstado(serie.estado)));
  articulo.append(cabecera);
  articulo.append(nodo("h3", serie.nombre || "Indicador"));
  if (serie.unidad) articulo.append(nodo("p", serie.unidad, "unidad"));

  if (serie.estado === "no actualizado") {
    const texto = serie.error
      ? `La serie no se actualizó: ${serie.error} Se muestra el último valor guardado, si existe.`
      : "La serie no se actualizó. Se muestra el último valor guardado, si existe.";
    articulo.append(aviso(texto));
  } else if (serie.error) {
    articulo.append(aviso(serie.error));
  }

  if (serie.ultimo && typeof serie.ultimo.valor === "number") {
    articulo.append(nodo("p", formatoNumero(serie.ultimo.valor), "valor"));
    const fecha = nodo("p", "", "fecha");
    fecha.append("Fecha del dato: ");
    const tiempo = document.createElement("time");
    tiempo.dateTime = serie.ultimo.fecha;
    tiempo.textContent = formatoFecha(serie.ultimo.fecha);
    fecha.append(tiempo);
    fecha.append(".");
    articulo.append(fecha);
  } else {
    articulo.append(nodo("p", "Sin valor publicado.", "sin-valor"));
  }

  const fuente = nodo("p", "", "fuente");
  fuente.append("Fuente: ");
  if (serie.organismo && serie.url_fuente) {
    fuente.append(enlace(serie.url_fuente, serie.organismo));
    fuente.append(".");
  } else if (serie.organismo) {
    fuente.append(serie.organismo);
    fuente.append(" (sin enlace utilizable).");
  } else if (serie.url_fuente) {
    fuente.append(enlace(serie.url_fuente, "Consulta de origen"));
    fuente.append(".");
  } else {
    fuente.append("no indicada.");
  }
  articulo.append(fuente);

  const puntos = Array.isArray(serie.puntos) ? serie.puntos.filter((punto) => typeof punto.valor === "number" && punto.fecha) : [];
  if (puntos.length) {
    const primero = puntos[0];
    const ultimo = puntos[puntos.length - 1];
    const descripcion = `Desde ${formatoNumero(primero.valor)} el ${formatoFecha(primero.fecha)} hasta ${formatoNumero(ultimo.valor)} el ${formatoFecha(ultimo.fecha)}.`;
    articulo.append(grafico(puntos, descripcion));
    articulo.append(tablaSerie(puntos));
  }

  const meta = nodo("p", "", "meta");
  if (serie.capturado_en) meta.append(`Captura: ${formatoInstante(serie.capturado_en)}. `);
  meta.append(enlace(serie.enlace_repositorio, "Archivo de la serie"));
  articulo.append(meta);
  return articulo;
}

function renderIndicadores(seccion) {
  const contenido = document.querySelector("#indicadores .contenido");
  contenido.replaceChildren();
  if (!seccion || seccion.ok === false) {
    contenido.append(aviso((seccion && seccion.aviso) || "No se pudieron cargar los indicadores."));
    if (seccion && seccion.repositorio) contenido.append(lineaRepositorio(seccion.repositorio));
    return;
  }
  contenido.append(lineaRepositorio(seccion.repositorio));
  const series = Array.isArray(seccion.series) ? seccion.series : [];
  if (!series.length) {
    contenido.append(nodo("p", seccion.aviso || "No hay indicadores publicados.", "vacio"));
    const erroresVacios = listaErrores(seccion.errores);
    if (erroresVacios) contenido.append(erroresVacios);
    return;
  }
  const parrilla = document.createElement("div");
  parrilla.className = "parrilla";
  for (const serie of series) parrilla.append(fichaIndicador(serie));
  contenido.append(parrilla);
  const errores = listaErrores(seccion.errores);
  if (errores) contenido.append(errores);
}

function definicion(filas) {
  const lista = document.createElement("dl");
  lista.className = "ficha-datos";
  for (const [termino, valor] of filas) {
    lista.append(nodo("dt", termino));
    const dd = document.createElement("dd");
    if (valor instanceof Node) dd.append(valor);
    else dd.textContent = valor || "—";
    lista.append(dd);
  }
  return lista;
}

function subencabezado(texto) {
  return nodo("h4", texto, "subencabezado");
}

function compararFechaPropuesta(a, b) {
  const fechaA = String((a && a.fecha) || "");
  const fechaB = String((b && b.fecha) || "");
  if (fechaA !== fechaB) return fechaB.localeCompare(fechaA);
  return String((a && a.id) || "").localeCompare(String((b && b.id) || ""));
}

function modoPropuestas() {
  if (ordenPropuestas) return ordenPropuestas;
  return window.espectroUI && espectroUI.hayVector() ? "ajuste" : "fecha";
}

function propuestasParaMostrar(seccion) {
  const repo = seccion && Array.isArray(seccion.items) ? seccion.items : [];
  const extra = window.espectroUI ? espectroUI.propuestasExtra() : [];
  const ids = new Set(repo.map((item) => item.id));
  return repo.concat(extra.filter((item) => item && !ids.has(item.id)));
}

function ordenarPropuestasLista(items) {
  const modo = modoPropuestas();
  const vectorListo = Boolean(window.espectroUI && espectroUI.hayVector());
  return items.slice().sort((a, b) => {
    if (modo === "ajuste" && vectorListo) {
      const aa = espectroUI.notaAjuste(a.posicion);
      const bb = espectroUI.notaAjuste(b.posicion);
      if (aa != null && bb != null && aa !== bb) return bb - aa;
      if (aa == null && bb != null) return 1;
      if (bb == null && aa != null) return -1;
    }
    return compararFechaPropuesta(a, b);
  });
}

function controlesPropuestas() {
  const barra = document.createElement("div");
  barra.className = "controles";
  const etiqueta = document.createElement("label");
  etiqueta.append(nodo("span", "Orden"));
  const select = document.createElement("select");
  select.id = "orden-propuestas";
  for (const [valor, texto] of [
    ["fecha", "Fecha, la más reciente primero"],
    ["ajuste", "Ajuste a mi posición"],
  ]) {
    const opcion = document.createElement("option");
    opcion.value = valor;
    opcion.textContent = texto;
    if (valor === modoPropuestas()) opcion.selected = true;
    select.append(opcion);
  }
  select.addEventListener("change", () => {
    if (select.value === "ajuste" && !(window.espectroUI && espectroUI.hayVector())) {
      const avisoOrden = document.getElementById("aviso-orden-propuestas");
      if (avisoOrden) {
        avisoOrden.hidden = false;
        avisoOrden.textContent = "Para ordenar por ajuste, primero responda Mi espectro. Sus respuestas quedan en este navegador.";
      }
      select.value = "fecha";
      return;
    }
    ordenPropuestas = select.value;
    if (datosSitio) renderPropuestas(datosSitio.propuestas);
    const nuevo = document.getElementById("orden-propuestas");
    if (nuevo) nuevo.focus();
  });
  etiqueta.append(select);
  const avisoOrden = nodo("p", "", "aviso");
  avisoOrden.id = "aviso-orden-propuestas";
  avisoOrden.hidden = true;
  avisoOrden.setAttribute("role", "status");
  barra.append(etiqueta, avisoOrden);
  return barra;
}

function invitacionEspectro() {
  if (window.espectroUI && espectroUI.hayVector()) return null;
  const linea = nodo("p", "", "sin-ajuste");
  const enlace = document.createElement("a");
  enlace.href = "#espectro";
  enlace.textContent = "Responda Mi espectro";
  linea.append(enlace);
  linea.append(" para ver el índice de ajuste de cada propuesta y ordenarlas. Esas respuestas no salen de este navegador.");
  return linea;
}

function fichaLocal(propuesta) {
  const articulo = document.createElement("article");
  articulo.className = "mocion";
  articulo.id = ancla("propuesta", propuesta.id);
  articulo.append(nodo(
    "p",
    "Ejemplo. Esta ficha no está en el repositorio de propuestas. No es una moción y no debe citarse como posición de Curia Máxima.",
    "ejemplo",
  ));
  const cabecera = document.createElement("div");
  cabecera.className = "tarjeta-cabecera";
  cabecera.append(nodo("p", propuesta.id, "codigo"));
  cabecera.append(nodo("p", etiquetaEstado(propuesta.estado), claseEstado(propuesta.estado)));
  articulo.append(cabecera);
  articulo.append(nodo("h3", propuesta.titulo || "Propuesta"));
  if (window.espectroUI) articulo.append(espectroUI.bloqueAjuste(propuesta));
  const autores = (propuesta.autores || [])
    .map((autor) => (autor.tipo ? `${autor.nombre} (${autor.tipo})` : autor.nombre))
    .join(", ");
  articulo.append(definicion([
    ["Tipo", TIPOS_PROPUESTA[propuesta.tipo] || propuesta.tipo || "—"],
    ["Fecha", propuesta.fecha ? formatoFecha(propuesta.fecha) : "—"],
    ["Autores", autores || "—"],
  ]));
  articulo.append(subencabezado("Texto de ejemplo"));
  articulo.append(nodo("p", propuesta.resumen || ""));
  return articulo;
}

function renderPropuestas(seccion) {
  const contenido = document.querySelector("#propuestas .contenido");
  contenido.replaceChildren();
  if (!seccion || seccion.ok === false) {
    contenido.append(aviso((seccion && seccion.aviso) || "No se pudieron cargar las propuestas."));
    if (seccion && seccion.repositorio) contenido.append(lineaRepositorio(seccion.repositorio));
  } else {
    contenido.append(lineaRepositorio(seccion.repositorio));
    if (seccion.aviso) contenido.append(nodo("p", seccion.aviso, "vacio"));
  }
  const items = ordenarPropuestasLista(propuestasParaMostrar(seccion));
  if (!items.length) {
    if (seccion && seccion.ok !== false) {
      contenido.append(nodo("p", seccion.aviso || "No hay propuestas publicadas.", "vacio"));
    }
    const erroresVacios = seccion ? listaErrores(seccion.errores) : null;
    if (erroresVacios) contenido.append(erroresVacios);
    return;
  }
  contenido.append(controlesPropuestas());
  const invitacion = invitacionEspectro();
  if (invitacion) contenido.append(invitacion);
  for (const propuesta of items) {
    if (propuesta.origen === "ejemplo-local") {
      contenido.append(fichaLocal(propuesta));
      continue;
    }
    const articulo = document.createElement("article");
    articulo.className = "mocion";
    articulo.id = ancla("propuesta", propuesta.id);
    if (propuesta.ejemplo) {
      articulo.append(nodo(
        "p",
        "Ejemplo de formato. No es una propuesta real y no debe citarse como posición de Curia Máxima.",
        "ejemplo",
      ));
    }
    const cabecera = document.createElement("div");
    cabecera.className = "tarjeta-cabecera";
    cabecera.append(nodo("p", propuesta.id, "codigo"));
    cabecera.append(nodo("p", etiquetaEstado(propuesta.estado), claseEstado(propuesta.estado)));
    articulo.append(cabecera);
    articulo.append(nodo("h3", propuesta.titulo || "Propuesta"));
    if (window.espectroUI) articulo.append(espectroUI.bloqueAjuste(propuesta));
    const autores = (propuesta.autores || [])
      .map((autor) => (autor.tipo ? `${autor.nombre} (${autor.tipo})` : autor.nombre))
      .join(", ");
    articulo.append(definicion([
      ["Tipo", TIPOS_PROPUESTA[propuesta.tipo] || propuesta.tipo || "—"],
      ["Fecha", propuesta.fecha ? formatoFecha(propuesta.fecha) : "—"],
      ["Autores", autores || "—"],
    ]));

    articulo.append(subencabezado("Normas relacionadas"));
    const normas = propuesta.normas_relacionadas || [];
    if (!normas.length) articulo.append(nodo("p", "Ninguna.", "vacio"));
    else {
      const lista = document.createElement("ul");
      lista.className = "sublista";
      for (const norma of normas) {
        const item = document.createElement("li");
        const relacion = RELACIONES[norma.relacion] || norma.relacion;
        if (relacion) item.append(`${relacion}: `);
        item.append(enlace(norma.enlace, norma.titulo));
        if (norma.id) item.append(nodo("span", ` (${norma.id})`, "codigo-en-linea"));
        lista.append(item);
      }
      articulo.append(lista);
    }

    articulo.append(subencabezado("Indicadores relacionados"));
    const kpis = propuesta.kpis_relacionados || [];
    if (!kpis.length) articulo.append(nodo("p", "Ninguno.", "vacio"));
    else {
      const lista = document.createElement("ul");
      lista.className = "sublista";
      for (const kpi of kpis) {
        const item = document.createElement("li");
        item.textContent = kpi.id ? `${kpi.descripcion} (${kpi.id})` : kpi.descripcion;
        lista.append(item);
      }
      articulo.append(lista);
    }

    articulo.append(subencabezado("Historial de adopción"));
    const historial = propuesta.historial_adopcion || [];
    if (!historial.length) articulo.append(nodo("p", "Sin actos de adopción registrados.", "vacio"));
    else {
      const lista = document.createElement("ul");
      lista.className = "sublista";
      for (const acto of historial) {
        const item = document.createElement("li");
        const partes = [
          acto.fecha ? formatoFecha(acto.fecha) : null,
          acto.cargo ? (CARGOS[acto.cargo] || acto.cargo) : null,
          acto.legislador || null,
          acto.accion ? (ACCIONES[acto.accion] || acto.accion) : null,
        ].filter(Boolean);
        item.append(partes.join(" · ") || "Acto");
        if (acto.referencia) item.append(` — ${acto.referencia}`);
        if (acto.enlace) {
          item.append(" ");
          item.append(enlace(acto.enlace, "Referencia"));
        }
        lista.append(item);
      }
      articulo.append(lista);
    }

    articulo.append(subencabezado("Texto"));
    articulo.append(htmlProsa(propuesta.cuerpo_html));
    const archivo = nodo("p", "", "meta");
    archivo.append(enlace(propuesta.enlace_repositorio, "Texto en el repositorio"));
    articulo.append(archivo);
    contenido.append(articulo);
  }
  const errores = listaErrores(seccion.errores);
  if (errores) contenido.append(errores);
}

function formatoNumeroLegal(numero) {
  const texto = String(numero || "");
  if (!/^\d+$/.test(texto) || texto.length <= 3) return texto;
  const corte = texto.length - 3;
  return `${texto.slice(0, corte)}.${texto.slice(corte)}`;
}

function rotuloNorma(norma) {
  const tipo = TIPOS_NORMA[norma.tipo] || norma.tipo || "Norma";
  const numero = formatoNumeroLegal(norma.numero);
  return numero ? `${tipo} N° ${numero}` : tipo;
}

function renderNormas(seccion) {
  const contenido = document.querySelector("#normas .contenido");
  contenido.replaceChildren();
  if (!seccion || seccion.ok === false) {
    contenido.append(aviso((seccion && seccion.aviso) || "No se pudieron cargar las normas."));
    if (seccion && seccion.repositorio) contenido.append(lineaRepositorio(seccion.repositorio));
    return;
  }
  contenido.append(lineaRepositorio(seccion.repositorio));
  const items = Array.isArray(seccion.items) ? seccion.items : [];
  if (!items.length) {
    contenido.append(nodo("p", seccion.aviso || "No hay normas publicadas.", "vacio"));
    return;
  }
  const porId = new Set(items.map((norma) => norma.id));
  for (const norma of items) {
    const articulo = document.createElement("article");
    articulo.className = "norma";
    articulo.id = ancla("norma", norma.id);
    const cabecera = document.createElement("div");
    cabecera.className = "tarjeta-cabecera";
    cabecera.append(nodo("p", rotuloNorma(norma), "codigo"));
    cabecera.append(nodo("p", etiquetaEstado(norma.estado), claseEstado(norma.estado)));
    articulo.append(cabecera);
    articulo.append(nodo("h3", norma.titulo || norma.id));
    if (norma.estado === "derogada") {
      const linea = nodo("p", "", "derogacion");
      if (norma.derogada_por && porId.has(norma.derogada_por)) {
        linea.append("Derogada por ");
        linea.append(enlaceInterno(ancla("norma", norma.derogada_por), norma.derogada_por));
        linea.append(".");
      } else if (norma.derogada_por) {
        linea.append("Derogada por ");
        const codigo = nodo("span", norma.derogada_por, "codigo-en-linea");
        linea.append(codigo);
        linea.append(". Esa norma no está copiada en el repositorio.");
      } else {
        linea.textContent = "Figura como derogada, pero el archivo no indica qué norma la derogó.";
      }
      articulo.append(linea);
    }
    articulo.append(definicion([
      ["Organismo", norma.organismo || "—"],
      ["Publicación", norma.fecha_publicacion ? formatoFecha(norma.fecha_publicacion) : "—"],
      ["Versión del texto", norma.version ? formatoFecha(norma.version) : "—"],
      ["Identificador", norma.id || "—"],
    ]));
    const fuente = nodo("p", "", "fuente");
    if (norma.fuente) fuente.append(enlace(norma.fuente, "Texto en la fuente oficial"));
    else fuente.textContent = "Fuente oficial no indicada.";
    articulo.append(fuente);
    if (norma.texto) {
      const detalles = document.createElement("details");
      const resumen = document.createElement("summary");
      resumen.textContent = "Leer el texto guardado";
      detalles.append(resumen);
      detalles.append(nodo("pre", norma.texto, "texto-norma"));
      articulo.append(detalles);
    }
    const archivo = nodo("p", "", "meta");
    archivo.append(enlace(norma.enlace_repositorio, "JSON en el repositorio"));
    articulo.append(archivo);
    contenido.append(articulo);
  }
  const errores = listaErrores(seccion.errores);
  if (errores) contenido.append(errores);
}

function falloGeneral(mensaje) {
  const general = document.getElementById("aviso-general");
  general.hidden = false;
  general.textContent = mensaje;
  for (const id of ["espectro", "propuestas", "rankings", "indicadores", "normas"]) {
    const contenido = document.querySelector(`#${id} .contenido`);
    if (contenido) contenido.replaceChildren(aviso(mensaje));
  }
}

function pintarDesdeDatos() {
  if (!datosSitio) return;
  const trabajos = [
    ["espectro", "No se pudo mostrar Mi espectro.", () => {
      if (window.espectroUI) espectroUI.renderEspectro();
    }],
    ["propuestas", "No se pudieron mostrar las propuestas.", () => renderPropuestas(datosSitio.propuestas)],
    ["rankings", "No se pudieron mostrar los rankings.", () => {
      if (window.espectroUI) espectroUI.renderRankings();
    }],
    ["indicadores", "No se pudieron mostrar los indicadores.", () => renderIndicadores(datosSitio.indicadores)],
    ["normas", "No se pudieron mostrar las normas.", () => renderNormas(datosSitio.normas)],
  ];
  for (const [id, mensaje, pintar] of trabajos) {
    try {
      pintar();
    } catch {
      const contenido = document.querySelector(`#${id} .contenido`);
      if (contenido) contenido.replaceChildren(aviso(mensaje));
    }
  }
}

function anotarGeneracion(iso) {
  const nodoFecha = document.getElementById("generado");
  if (!iso) {
    nodoFecha.textContent = "La fecha de armado de esta página no viene en los datos.";
    return;
  }
  nodoFecha.textContent = `Datos reunidos el ${formatoInstante(iso)} desde los repositorios públicos. Se actualizan al publicar el sitio y una vez al día. El navegador no vuelve a consultarlos.`;
}

async function main() {
  let datos;
  try {
    const respuesta = await fetch("datos.json", { cache: "no-store" });
    if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
    datos = await respuesta.json();
    if (!datos || typeof datos !== "object") throw new Error("formato");
  } catch {
    falloGeneral("No se pudo cargar los datos publicados. Puede ser un fallo de esta página. Recargue más tarde: el resto del sitio sigue en pie.");
    return;
  }
  anotarGeneracion(datos.generado_en);
  datosSitio = datos;
  if (window.espectroUI) {
    espectroUI.recibir(datos.espectro || null);
    espectroUI.alCambiar = (motivo) => {
      if (motivo === "borrar") ordenPropuestas = "fecha";
      if (motivo === "guardar") ordenPropuestas = "ajuste";
      pintarDesdeDatos();
    };
  }
  pintarDesdeDatos();
}

main();
