# DraymSistem Apps

Catálogo público estático. La administración se hace desde GitHub Releases
con una cuenta autorizada; no existe un formulario de subida en la página.
Los archivos publicados y el código de este repositorio son públicos.

## Publicar una aplicación

1. En GitHub entra a este repositorio y abre **Releases → Draft a new release**.
2. Crea una etiqueta con el formato `nombre-app-vversion`, por ejemplo
   `beauty-pro-v1.0.6`. Usa minúsculas, números y guiones para el nombre.
   Usa siempre el mismo nombre para las versiones posteriores de esa aplicación.
3. En **Release title** escribe el nombre que se mostrará, por ejemplo `Beauty Pro`.
   La descripción se mostrará como texto en la tarjeta.
4. Adjunta los instaladores que quieres distribuir (APK, EXE, MSI, DMG, ZIP o
   AppImage) y elige **Publish release**. No marques la versión como prerelease.

El catálogo muestra la publicación más reciente por fecha de cada aplicación
que tenga al menos un instalador compatible. Los borradores, prereleases y
publicaciones sin archivos compatibles no aparecen. Si se publica una
versión antigua después de una nueva, aparecerá como la más reciente; revisa
qué publicas. Al retirar una publicación, se mostrará la anterior disponible.
La consulta depende de la API pública de GitHub y puede fallar temporalmente
o llegar a su límite; la página ofrece un enlace alternativo a Releases.

Las versiones anteriores siguen siendo accesibles en Releases. No publiques
claves, contraseñas, archivos de firma ni información privada. Protege tu
cuenta de GitHub con autenticación de dos factores y conserva una copia segura
de la llave de firma fuera del repositorio.

Para una actualización Android, usa el mismo identificador y certificado de
firma y aumenta el `versionCode`. El usuario debe confirmar la instalación.
La página no avisa por sí sola a las apps instaladas sobre actualizaciones.

## Publicar la página

En **Settings → Pages**, selecciona **Deploy from a branch**, `main` y
`/ (root)`. GitHub indicará la URL y el estado de publicación. Para pruebas
locales ejecuta `python3 -m http.server 8000` y visita `http://localhost:8000`.
