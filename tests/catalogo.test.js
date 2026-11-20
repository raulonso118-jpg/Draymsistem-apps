const test = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");

const codigo = fs.readFileSync(path.join(__dirname, "../catalogo.js"), "utf8");

async function ejecutar(fetch) {
  function elemento(tag) {
    return {
      tag, children: [], textContent: "",
      appendChild(hijo) { this.children.push(hijo); }
    };
  }
  const estado = elemento("p");
  const catalogo = elemento("div");
  const document = {
    createElement: elemento,
    getElementById(id) { return id === "estado" ? estado : catalogo; }
  };
  const context = vm.createContext({ document, fetch, URL, console: { error() {} } });
  vm.runInContext(codigo, context);
  await new Promise(resolve => setImmediate(resolve));
  return { estado, catalogo };
}

function publicacion(tag, fecha, archivos, opciones = {}) {
  return {
    tag_name: tag, published_at: fecha, name: opciones.name || tag,
    body: opciones.body || "", draft: opciones.draft || false,
    prerelease: opciones.prerelease || false,
    assets: archivos.map(name => ({
      name, browser_download_url: `https://github.com/raulonso118-jpg/Draymsistem-apps/releases/download/${tag}/${name}`
    }))
  };
}

test("muestra la versión publicada más reciente de cada app con instaladores", async () => {
  const datos = [
    publicacion("beauty-pro-v1.0.6", "2026-01-01", ["beauty.apk"]),
    publicacion("beauty-pro-v1.0.7", "2026-02-01", ["beauty.apk"], { body: "<script>no ejecutar</script>" }),
    publicacion("juego-v2", "2026-02-02", ["juego.exe"]),
    publicacion("beauty-pro-v2", "2026-03-01", ["beta.apk"], { prerelease: true }),
    publicacion("invalida", "2026-04-01", ["app.apk"])
  ];
  const { estado, catalogo } = await ejecutar(async () => ({ ok: true, json: async () => datos }));
  assert.equal(estado.textContent, "");
  assert.equal(catalogo.children.length, 2);
  const beauty = catalogo.children.find(c => c.children[1].textContent === "beauty-pro-v1.0.7");
  assert.equal(beauty.children[2].textContent, "Versión: 1.0.7");
  assert.equal(beauty.children[3].textContent, "<script>no ejecutar</script>");
  assert.equal(beauty.children[3].children.length, 0);
  assert.match(beauty.children[4].href, /beauty\.apk$/);
});

test("rechaza enlaces externos y muestra estado vacío", async () => {
  const release = publicacion("app-v1", "2026-01-01", ["app.apk"]);
  release.assets[0].browser_download_url = "https://ejemplo.com/app.apk";
  const { estado, catalogo } = await ejecutar(async () => ({ ok: true, json: async () => [release] }));
  assert.equal(catalogo.children.length, 0);
  assert.match(estado.textContent, /Todavía no hay/);
});

test("informa errores de GitHub sin simular éxito", async () => {
  const { estado } = await ejecutar(async () => ({ ok: false, status: 403 }));
  assert.match(estado.textContent, /No se pudo cargar/);
  assert.doesNotMatch(estado.textContent, /publicaciones oficiales/);
});

test("consulta todas las páginas de publicaciones", async () => {
  const primera = Array.from({ length: 100 }, (_, i) =>
    publicacion(`app${i}-v1`, "2026-01-01", ["app.apk"]));
  let llamadas = 0;
  const { catalogo } = await ejecutar(async () => ({
    ok: true, json: async () => ++llamadas === 1 ? primera : [publicacion("ultima-v1", "2026-01-01", ["app.apk"])]
  }));
  assert.equal(llamadas, 2);
  assert.equal(catalogo.children.length, 101);
});
