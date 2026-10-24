/* Cuestionario, índice de ajuste y rankings.
   La misma fórmula está en curia_maxima.espectro.ajuste.
   Las respuestas viven solo en localStorage. No se envían a ningún servidor. */

const CLAVE_ESPECTRO = "curia-maxima-espectro";
const TIPOS_ACTOR = { bot: "Bot de ejemplo", figura: "Figura de ejemplo" };

let paqueteEspectro = null;
let rehacerEspectro = false;
let avisoEspectro = "";
let ordenActores = null;

function el(etiqueta, contenido, clase) {
  const elemento = document.createElement(etiqueta);
  if (clase) elemento.className = clase;
  if (contenido != null && contenido !== "") elemento.textContent = String(contenido);
  return elemento;
}

function boton(texto, clase, alClick) {
  const elemento = document.createElement("button");
  elemento.type = "button";
  elemento.className = clase;
  elemento.textContent = texto;
  elemento.addEventListener("click", alClick);
  return elemento;
}

function idsEjes() {
  return paqueteEspectro ? paqueteEspectro.ejes.map((eje) => eje.id) : [];
}

function indiceAjuste(persona, posicion, ejes) {
  if (!persona || !posicion || !ejes || !ejes.length) return null;
  let suma = 0;
  for (const eje of ejes) {
    const p = persona[eje];
    const q = posicion[eje];
    if (typeof p !== "number" || typeof q !== "number" || !Number.isFinite(p) || !Number.isFinite(q)) {
      return null;
    }
    suma += Math.abs(p - q);
  }
  const bruto = 100 * (1 - suma / (2 * ejes.length));
  const acotado = Math.min(100, Math.max(0, bruto));
  return Math.floor(acotado + 0.5);
}

function vectorDe(respuestas) {
  if (!paqueteEspectro || !respuestas) return null;
  const grupos = {};
  for (const eje of paqueteEspectro.ejes) grupos[eje.id] = [];
  for (const afirmacion of paqueteEspectro.afirmaciones) {
    const valor = Number(respuestas[afirmacion.id]);
    if (!Number.isInteger(valor) || valor < 1 || valor > 5) return null;
    if (!grupos[afirmacion.eje]) return null;
    grupos[afirmacion.eje].push(((valor - 3) / 2) * afirmacion.sentido);
  }
  const vector = {};
  for (const eje of paqueteEspectro.ejes) {
    const valores = grupos[eje.id];
    if (!valores || !valores.length) return null;
    vector[eje.id] = valores.reduce((acumulado, item) => acumulado + item, 0) / valores.length;
  }
  return vector;
}

function leerGuardado() {
  let crudo = null;
  try {
    crudo = localStorage.getItem(CLAVE_ESPECTRO);
  } catch {
    return null;
  }
  if (!crudo) return null;
  try {
    const datos = JSON.parse(crudo);
    if (!datos || datos.version !== 1 || !datos.respuestas || typeof datos.respuestas !== "object") {
      return { invalido: true };
    }
    if (!paqueteEspectro || datos.cuestionario_id !== paqueteEspectro.cuestionario_id) {
      return { invalido: true };
    }
    const vector = vectorDe(datos.respuestas);
    if (!vector) return { invalido: true };
    return { respuestas: datos.respuestas, vector };
  } catch {
    return { invalido: true };
  }
}

function vectorActual() {
  const datos = leerGuardado();
  if (!datos || datos.invalido) return null;
  return datos.vector;
}

function guardarRespuestas(respuestas) {
  if (!paqueteEspectro || !vectorDe(respuestas)) return false;
  const cuerpo = JSON.stringify({
    version: 1,
    cuestionario_id: paqueteEspectro.cuestionario_id,
    respuestas,
  });
  try {
    localStorage.setItem(CLAVE_ESPECTRO, cuerpo);
    return true;
  } catch {
    return false;
  }
}

function borrarRespuestas() {
  let habia = false;
  try {
    habia = localStorage.getItem(CLAVE_ESPECTRO) != null;
    localStorage.removeItem(CLAVE_ESPECTRO);
  } catch {
    avisoEspectro = "No se pudo usar el almacenamiento de este navegador. No se envió nada a un servidor.";
    return;
  }
  rehacerEspectro = false;
  ordenActores = "nombre";
  avisoEspectro = habia
    ? "Se borraron las respuestas de este navegador."
    : "No había respuestas guardadas en este navegador.";
}

function notificarEspectro(motivo) {
  if (typeof espectroUI.alCambiar === "function") espectroUI.alCambiar(motivo);
  else espectroUI.renderEspectro();
}

function formatoEje(valor) {
  const numero = new Intl.NumberFormat("es-CL", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(valor);
  return valor > 0 ? `+${numero}` : numero;
}

function ladoEje(eje, valor) {
  if (valor > 0.15) {
    return `hacia ${eje.polo_positivo.charAt(0).toLowerCase()}${eje.polo_positivo.slice(1)}`;
  }
  if (valor < -0.15) {
    return `hacia ${eje.polo_negativo.charAt(0).toLowerCase()}${eje.polo_negativo.slice(1)}`;
  }
  return "cerca del centro";
}

function porqueEjes() {
  const detalles = document.createElement("details");
  const resumen = document.createElement("summary");
  resumen.textContent = "Por qué estos ejes";
  detalles.append(resumen);
  const lista = document.createElement("dl");
  lista.className = "ficha-datos";
  for (const eje of paqueteEspectro.ejes) {
    lista.append(el("dt", eje.nombre), el("dd", eje.explicacion));
  }
  detalles.append(lista);
  return detalles;
}

function marcasEje(eje, posicion, vector, etiquetaOtro) {
  const fila = el("div", null, "eje");
  fila.append(el("p", eje.nombre, "eje-nombre"));
  const polos = el("div", null, "eje-polos");
  polos.append(el("span", eje.polo_negativo), el("span", eje.polo_positivo));
  fila.append(polos);
  const pista = el("div", null, "pista");
  pista.setAttribute("aria-hidden", "true");
  pista.append(el("span", null, "pista-cero"));
  function marca(valor, clase) {
    const punto = el("span", null, `marca ${clase}`);
    const left = Math.min(100, Math.max(0, ((valor + 1) / 2) * 100));
    punto.style.left = `${left}%`;
    pista.append(punto);
  }
  if (vector && typeof vector[eje.id] === "number") marca(vector[eje.id], "marca-usted");
  if (posicion && typeof posicion[eje.id] === "number") marca(posicion[eje.id], "marca-otro");
  fila.append(pista);
  const partes = [];
  if (vector && typeof vector[eje.id] === "number") {
    partes.push(`Usted ${formatoEje(vector[eje.id])}, ${ladoEje(eje, vector[eje.id])}.`);
  }
  if (posicion && typeof posicion[eje.id] === "number") {
    partes.push(`${etiquetaOtro} ${formatoEje(posicion[eje.id])}, ${ladoEje(eje, posicion[eje.id])}.`);
  }
  fila.append(el("p", partes.length ? `${eje.nombre}: ${partes.join(" ")}` : eje.nombre, "eje-lectura"));
  return fila;
}

function bloqueAjuste(entidad, etiquetaOtro) {
  const caja = el("div", null, "ajuste");
  if (!paqueteEspectro) return caja;
  const posicion = entidad && entidad.posicion;
  if (!posicion) {
    caja.append(el("p", "Esta ficha no tiene posición en los ejes.", "vacio"));
    return caja;
  }
  const vector = vectorActual();
  const etiqueta = etiquetaOtro || "La ficha";
  if (!vector) {
    const linea = el("p", "", "sin-ajuste");
    const enlace = document.createElement("a");
    enlace.href = "#espectro";
    enlace.textContent = "Responda Mi espectro";
    linea.append(enlace);
    linea.append(" para ver el índice de ajuste. Esas respuestas no salen de este navegador.");
    caja.append(linea);
  } else {
    const nota = indiceAjuste(vector, posicion, idsEjes());
    caja.append(el("p", "Índice de ajuste a su posición", "codigo"));
    const valor = el("p", nota == null ? "—" : `${nota}%`, "ajuste-valor");
    caja.append(valor);
    if (paqueteEspectro.formula_frase) caja.append(el("p", paqueteEspectro.formula_frase, "ajuste-frase"));
    if (paqueteEspectro.formula_detalle) {
      const detalles = document.createElement("details");
      const resumen = document.createElement("summary");
      resumen.textContent = "Cómo se calcula";
      detalles.append(resumen, el("p", paqueteEspectro.formula_detalle));
      caja.append(detalles);
    }
  }
  if (entidad && entidad.posicion_comentario) {
    caja.append(el("p", entidad.posicion_comentario, "ejemplo"));
  }
  for (const eje of paqueteEspectro.ejes) caja.append(marcasEje(eje, posicion, vector, etiqueta));
  if (vector) {
    const leyenda = el("p", "", "leyenda-marcas");
    leyenda.append(el("span", "Usted", "muestra muestra-usted"));
    leyenda.append(el("span", etiqueta, "muestra muestra-otro"));
    caja.append(leyenda);
  }
  return caja;
}

function renderFormulario(previas) {
  const caja = el("div", null, "cuestionario");
  caja.append(el("p", paqueteEspectro.nota, "ejemplo"));
  caja.append(porqueEjes());
  const formulario = document.createElement("form");
  formulario.noValidate = true;
  formulario.addEventListener("submit", (evento) => evento.preventDefault());
  const respuestasPrevias = previas || {};
  paqueteEspectro.afirmaciones.forEach((afirmacion, indice) => {
    const campo = document.createElement("fieldset");
    campo.className = "afirmacion";
    campo.id = `campo-${afirmacion.id}`;
    const leyenda = document.createElement("legend");
    leyenda.textContent = afirmacion.texto;
    campo.append(leyenda);
    campo.append(el("p", `${indice + 1} de ${paqueteEspectro.afirmaciones.length}`, "codigo"));
    for (const opcion of paqueteEspectro.escala) {
      const etiqueta = document.createElement("label");
      etiqueta.className = "opcion";
      const input = document.createElement("input");
      input.type = "radio";
      input.name = afirmacion.id;
      input.value = String(opcion.valor);
      if (respuestasPrevias[afirmacion.id] === opcion.valor) input.checked = true;
      etiqueta.append(input, document.createTextNode(` ${opcion.etiqueta}`));
      campo.append(etiqueta);
    }
    formulario.append(campo);
  });
  const estado = el("p", "", "aviso");
  estado.id = "estado-formulario";
  estado.hidden = true;
  estado.setAttribute("role", "status");
  const acciones = el("div", null, "acciones");
  acciones.append(boton("Ver mi espectro", "primario", () => {
    const respuestas = {};
    let primeraFalta = null;
    for (const afirmacion of paqueteEspectro.afirmaciones) {
      const campo = formulario.querySelector(`#campo-${afirmacion.id}`);
      const marcado = formulario.querySelector(`input[name="${afirmacion.id}"]:checked`);
      if (!marcado) {
        if (campo) campo.classList.add("falta");
        if (!primeraFalta) primeraFalta = campo;
        continue;
      }
      if (campo) campo.classList.remove("falta");
      respuestas[afirmacion.id] = Number(marcado.value);
    }
    if (primeraFalta) {
      estado.hidden = false;
      estado.textContent = "Falta responder al menos una afirmación. Está marcada en el formulario.";
      primeraFalta.scrollIntoView({ block: "center" });
      const radio = primeraFalta.querySelector("input");
      if (radio) radio.focus();
      return;
    }
    if (!guardarRespuestas(respuestas)) {
      estado.hidden = false;
      estado.textContent = "No se pudieron guardar las respuestas en este navegador. No se enviaron a ningún servidor.";
      return;
    }
    rehacerEspectro = false;
    ordenActores = "ajuste";
    avisoEspectro = "";
    notificarEspectro("guardar");
  }));
  acciones.append(boton("Borrar mis respuestas de este navegador", "borrar", () => {
    borrarRespuestas();
    notificarEspectro("borrar");
  }));
  formulario.append(estado, acciones);
  formulario.append(el(
    "p",
    "Sus respuestas se guardan solo en este navegador (localStorage). No se envían a ningún servidor.",
    "meta",
  ));
  caja.append(formulario);
  return caja;
}

function renderResultado(guardado) {
  const caja = el("div", null, "resultado");
  caja.append(el(
    "p",
    "Ejemplo. Este resultado solo describe el cuestionario de muestra, no una clasificación política real.",
    "ejemplo",
  ));
  caja.append(el("h3", "Su resultado"));
  const lecturas = paqueteEspectro.ejes.map((eje) => {
    const valor = guardado.vector[eje.id];
    return `${eje.nombre} ${formatoEje(valor)}, ${ladoEje(eje, valor)}`;
  });
  caja.append(el("p", `${lecturas.join(". ")}.`));
  for (const eje of paqueteEspectro.ejes) caja.append(marcasEje(eje, null, guardado.vector, ""));
  caja.append(el("p", "La marca indica su posición entre los dos polos del eje.", "leyenda-marcas"));
  caja.append(porqueEjes());
  const acciones = el("div", null, "acciones");
  const aPropuestas = document.createElement("a");
  aPropuestas.href = "#propuestas";
  aPropuestas.className = "boton-enlace primario";
  aPropuestas.textContent = "Ver propuestas según este resultado";
  const aRankings = document.createElement("a");
  aRankings.href = "#rankings";
  aRankings.className = "boton-enlace";
  aRankings.textContent = "Ver rankings";
  acciones.append(
    aPropuestas,
    aRankings,
    boton("Responder de nuevo", "", () => {
      rehacerEspectro = true;
      avisoEspectro = "";
      espectroUI.renderEspectro();
    }),
    boton("Borrar mis respuestas de este navegador", "borrar", () => {
      borrarRespuestas();
      notificarEspectro("borrar");
    }),
  );
  caja.append(acciones);
  caja.append(el(
    "p",
    "Sus respuestas se guardan solo en este navegador (localStorage). No se envían a ningún servidor.",
    "meta",
  ));
  return caja;
}

function renderEspectro() {
  const contenido = document.querySelector("#espectro .contenido");
  if (!contenido) return;
  contenido.replaceChildren();
  if (!paqueteEspectro) {
    contenido.append(el("p", "Esta versión de los datos no trae el cuestionario.", "aviso"));
    return;
  }
  if (avisoEspectro) {
    const estado = el("p", avisoEspectro, "aviso");
    estado.setAttribute("role", "status");
    contenido.append(estado);
  }
  const guardado = leerGuardado();
  if (guardado && guardado.invalido) {
    contenido.append(el(
      "p",
      "Había datos de otra versión en este navegador. No se usaron para el índice. Puede borrarlos.",
      "aviso",
    ));
  }
  if (!rehacerEspectro && guardado && guardado.vector) contenido.append(renderResultado(guardado));
  else contenido.append(renderFormulario(guardado && !guardado.invalido ? guardado.respuestas : null));
}

function compararActores(a, b, modo, vector) {
  if (modo === "ajuste" && vector) {
    const aa = indiceAjuste(vector, a.posicion, idsEjes());
    const bb = indiceAjuste(vector, b.posicion, idsEjes());
    if (aa != null && bb != null && aa !== bb) return bb - aa;
    if (aa == null && bb != null) return 1;
    if (bb == null && aa != null) return -1;
  }
  return String(a.nombre).localeCompare(String(b.nombre), "es");
}

function fichaActor(actor, indice, modo, vector) {
  const articulo = el("article", null, "ficha actor");
  articulo.id = `actor-${actor.id}`;
  articulo.append(el("p", "Ejemplo. No es una persona real ni un bot en producción.", "ejemplo"));
  if (modo === "ajuste" && vector) articulo.append(el("p", `Puesto ${indice + 1}`, "puesto"));
  const cabecera = el("div", null, "tarjeta-cabecera");
  cabecera.append(el("p", TIPOS_ACTOR[actor.tipo] || "Actor de ejemplo", "codigo"));
  articulo.append(cabecera);
  articulo.append(el("h3", actor.nombre));
  articulo.append(el("p", actor.resumen));
  articulo.append(bloqueAjuste(actor, "Este actor"));
  const lista = document.createElement("dl");
  lista.className = "ficha-datos";
  const temas = document.createElement("dd");
  temas.textContent = (actor.temas || []).join(", ") || "—";
  lista.append(el("dt", "Temas"), temas);
  lista.append(el("dt", "Participación de ejemplo"), el("dd", `${actor.actividad} de 100`));
  articulo.append(lista);
  articulo.append(el(
    "p",
    "La participación es un número ficticio para mostrar otro parámetro además de los ejes. No es una medición.",
    "meta",
  ));
  return articulo;
}

function renderRankings() {
  const contenido = document.querySelector("#rankings .contenido");
  if (!contenido) return;
  contenido.replaceChildren();
  if (!paqueteEspectro || !Array.isArray(paqueteEspectro.actores)) {
    contenido.append(el("p", "No se publicaron actores de ejemplo.", "vacio"));
    return;
  }
  if (paqueteEspectro.nota_actores) contenido.append(el("p", paqueteEspectro.nota_actores, "ejemplo"));
  const vector = vectorActual();
  const modo = ordenActores || (vector ? "ajuste" : "nombre");
  const barra = el("div", null, "controles");
  const etiqueta = document.createElement("label");
  etiqueta.append(el("span", "Orden"));
  const select = document.createElement("select");
  select.id = "orden-rankings";
  for (const [valor, texto] of [["ajuste", "Ajuste a mi posición"], ["nombre", "Nombre"]]) {
    const opcion = document.createElement("option");
    opcion.value = valor;
    opcion.textContent = texto;
    if (valor === modo) opcion.selected = true;
    select.append(opcion);
  }
  select.addEventListener("change", () => {
    if (select.value === "ajuste" && !vectorActual()) {
      const aviso = document.getElementById("aviso-orden-rankings");
      if (aviso) {
        aviso.hidden = false;
        aviso.textContent = "Para ordenar por ajuste, primero responda Mi espectro. Sus respuestas quedan en este navegador.";
      }
      select.value = ordenActores || "nombre";
      return;
    }
    ordenActores = select.value;
    renderRankings();
    const nuevo = document.getElementById("orden-rankings");
    if (nuevo) nuevo.focus();
  });
  etiqueta.append(select);
  const avisoOrden = el("p", "", "aviso");
  avisoOrden.id = "aviso-orden-rankings";
  avisoOrden.hidden = true;
  avisoOrden.setAttribute("role", "status");
  barra.append(etiqueta, avisoOrden);
  contenido.append(barra);
  if (!vector) {
    const linea = el("p", "", "sin-ajuste");
    const enlace = document.createElement("a");
    enlace.href = "#espectro";
    enlace.textContent = "Responda Mi espectro";
    linea.append(enlace);
    linea.append(" para ordenar este ranking por ajuste. Esas respuestas no salen de este navegador.");
    contenido.append(linea);
  }
  const actores = paqueteEspectro.actores.slice().sort((a, b) => compararActores(a, b, modo, vector));
  actores.forEach((actor, indice) => contenido.append(fichaActor(actor, indice, modo, vector)));
}

const espectroUI = window.espectroUI = {
  alCambiar: null,
  recibir(paquete) {
    paqueteEspectro = paquete && typeof paquete === "object" ? paquete : null;
  },
  hayVector() {
    return vectorActual() != null;
  },
  notaAjuste(posicion) {
    const vector = vectorActual();
    if (!vector || !posicion) return null;
    return indiceAjuste(vector, posicion, idsEjes());
  },
  propuestasExtra() {
    if (!paqueteEspectro || !Array.isArray(paqueteEspectro.propuestas_ejemplo)) return [];
    return paqueteEspectro.propuestas_ejemplo;
  },
  bloqueAjuste,
  renderEspectro,
  renderRankings,
};
