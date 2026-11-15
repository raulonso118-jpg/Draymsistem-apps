"use strict";

const REPOSITORIO = "raulonso118-jpg/Draymsistem-apps";
const EXTENSIONES = /\.(apk|exe|msi|dmg|zip|appimage)$/i;

function enlaceSeguro(url) {
  try {
    const enlace = new URL(url);
    return enlace.protocol === "https:" &&
      enlace.hostname === "github.com" &&
      enlace.pathname.startsWith(`/${REPOSITORIO}/releases/download/`);
  } catch {
    return false;
  }
}

function agregarTexto(padre, etiqueta, texto, clase) {
  const elemento = document.createElement(etiqueta);
  if (clase) elemento.className = clase;
  elemento.textContent = texto;
  padre.appendChild(elemento);
  return elemento;
}

function mostrarAplicaciones(publicaciones) {
  const catalogo = document.getElementById("catalogo");
  const estado = document.getElementById("estado");
  const aplicaciones = new Set();
  let total = 0;

  for (const publicacion of publicaciones) {
    if (publicacion.draft || publicacion.prerelease) continue;
    const etiqueta = typeof publicacion.tag_name === "string" ? publicacion.tag_name : "";
    const partes = etiqueta.match(/^([a-z0-9]+(?:-[a-z0-9]+)*)-v(.+)$/);
    if (!partes || aplicaciones.has(partes[1])) continue;
    const archivos = Array.isArray(publicacion.assets) ? publicacion.assets.filter(
      archivo => typeof archivo.name === "string" &&
        EXTENSIONES.test(archivo.name) && enlaceSeguro(archivo.browser_download_url)
    ) : [];
    if (!archivos.length) continue;

    aplicaciones.add(partes[1]);
    const tarjeta = document.createElement("article");
    tarjeta.className = "tarjeta";
    agregarTexto(tarjeta, "p", "APLICACIÓN", "etiqueta");
    agregarTexto(tarjeta, "h3", publicacion.name || partes[1]);
    agregarTexto(tarjeta, "p", `Versión: ${partes[2]}`);
    if (publicacion.body) agregarTexto(tarjeta, "p", publicacion.body, "descripcion-app");
    for (const archivo of archivos) {
      const enlace = agregarTexto(tarjeta, "a", `Descargar ${archivo.name}`, "descarga");
      enlace.href = archivo.browser_download_url;
    }
    catalogo.appendChild(tarjeta);
    total++;
  }

  estado.textContent = total ? "" : "Todavía no hay aplicaciones publicadas.";
}

async function cargarCatalogo() {
  const estado = document.getElementById("estado");
  try {
    const publicaciones = [];
    for (let pagina = 1; ; pagina++) {
      const respuesta = await fetch(`https://api.github.com/repos/${REPOSITORIO}/releases?per_page=100&page=${pagina}`);
      if (!respuesta.ok) throw new Error(`GitHub respondió ${respuesta.status}`);
      const lote = await respuesta.json();
      if (!Array.isArray(lote)) throw new Error("Respuesta de GitHub inesperada");
      publicaciones.push(...lote);
      if (lote.length < 100) break;
    }
    publicaciones.sort((a, b) => (b.published_at || "").localeCompare(a.published_at || ""));
    mostrarAplicaciones(publicaciones);
  } catch (error) {
    console.error("No se pudo cargar el catálogo:", error);
    estado.textContent = "No se pudo cargar el catálogo. Inténtalo más tarde o usa el enlace a publicaciones oficiales.";
  }
}

cargarCatalogo();
