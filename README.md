# Fundación Pensar La Rioja — actualización diaria de noticias

Esta carpeta parte del HTML recibido, conserva su contenido y agrega una sección de titulares relacionados. La tarea diaria consulta los canales RSS oficiales de Política y Economía de Perfil, filtra titulares que mencionan **Lacunza**, **La Rioja** o gentilicios riojanos, y muestra solo el titular, la fecha y el enlace a la nota original. No copia sumarios ni redacta noticias.

La página original ya incluía fuentes históricas de La Voz y Perfil; esas referencias quedan intactas. La automatización inicial usa Perfil porque su página de canales RSS permite exhibir títulos y enlaces en sitios web. Para agregar otro medio, primero hay que confirmar su RSS oficial y sus condiciones de uso.

## Publicar con GitHub y Vercel

1. Descomprimí esta carpeta y subí **su contenido** a un repositorio de GitHub. `index.html` debe quedar en la raíz del repositorio.
2. En Vercel, importá ese repositorio. Usá la raíz como directorio del proyecto; no hace falta compilar la página estática. Dejá conectado el repositorio para que Vercel publique cuando haya cambios en la rama de producción.
3. En GitHub, abrí **Settings → Actions → General → Workflow permissions**, habilitá permisos de lectura y escritura para los workflows y guardá. El workflow necesita permiso para actualizar `data/news.json`.
4. Abrí **Actions → Actualizar noticias diariamente → Run workflow** para probarlo enseguida. El archivo de noticias se actualizará y el cambio en la rama conectada hará que Vercel publique una nueva versión.
5. Después se ejecuta todos los días a las **11:00 de Argentina** (GitHub puede demorarse algunos minutos). Si no hay titulares nuevos, la sección lo indica; si falla la lectura del RSS, no borra el último archivo publicado.

No hay claves privadas ni tokens dentro del HTML o del código. El workflow usa Python estándar y la fuente RSS pública de Perfil.

## Archivos principales

- `index.html`: página original con el bloque de noticias automático.
- `data/news.json`: titulares actualmente publicados; se actualiza con cada ejecución.
- `scripts/update_news.py`: lectura, filtro y generación del JSON.
- `.github/workflows/daily-news.yml`: ejecución diaria y manual desde GitHub Actions.

## Fuente y condiciones

- [Canales RSS de Perfil](https://www.perfil.com/canales-rss)
- Canales usados: Política y Economía. El sitio muestra los titulares y enlaces, y enlaza directamente a Perfil para leer cada nota.
