# Wiki PG — Wiki técnica personal

Wiki técnica personal donde documento soluciones, configuraciones y apuntes de administración de sistemas. Construida desde cero con Django y desplegada en un servidor propio bajo Proxmox, sin depender de servicios de terceros más allá de Cloudflare.

🔗 **En producción:** [wiki.pablogg.dev](https://wiki.pablogg.dev)

---

## ✨ Características

- **Editor Markdown** en el panel de administración con previsualización en tiempo real y resaltado de sintaxis.
- **Publicación programada** de artículos: se hacen visibles automáticamente en la fecha y hora elegidas.
- **Integración con la API de LinkedIn**: publica automáticamente un post (y un primer comentario con el enlace) al publicar un artículo, con posibilidad de programarlo.
- **Organización por categorías y subcategorías**, con etiquetas y buscador instantáneo que sugiere resultados mientras escribes.
- **Tiempo de lectura estimado** y barra de progreso en cada artículo.
- **SEO**: sitemap.xml, robots.txt y metaetiquetas Open Graph con imagen destacada para compartir en redes.

## 🔒 Seguridad

- **Autenticación de doble factor (2FA)** obligatoria en el panel de administración.
- **Panel admin en ruta oculta** + **honeypot** en la ruta /admin/ que registra los intentos de acceso (IP, usuario y navegador) sin dar acceso real.
- **Protección contra fuerza bruta** con bloqueo automático de IP tras varios intentos fallidos.
- **Cabeceras de seguridad** (HSTS, X-Frame-Options, nosniff, referrer-policy).
- **Cloudflare Tunnel**: el servidor no expone ningún puerto a internet; todo el tráfico entra a través del túnel.
- **Secretos gestionados por variables de entorno** (.env), fuera del control de versiones.

## 🛠️ Stack tecnológico

| Capa | Tecnología |
|------|------------|
| Framework | Django 6 |
| Base de datos | PostgreSQL |
| Servidor de aplicación | Gunicorn |
| Proxy inverso | Nginx |
| Tareas en segundo plano | Celery + Redis |
| Exposición a internet | Cloudflare Tunnel |
| Infraestructura | Contenedor LXC en Proxmox |

## 📐 Arquitectura

\`\`\`
Navegador
   │
   ▼
Cloudflare Tunnel  (sin puertos abiertos)
   │
   ▼
Nginx  ──►  Gunicorn  ──►  Django  ──►  PostgreSQL
                                │
                                ▼
                         Celery + Redis
                     (publicaciones programadas
                       y automatización LinkedIn)
\`\`\`

## 📝 Notas

Proyecto personal de aprendizaje y documentación. El código se comparte con fines de portfolio; la configuración sensible (claves, tokens, credenciales) se gestiona mediante variables de entorno y no está incluida en el repositorio.

---

**Autor:** Pablo Gutiérrez Gracia — Administrador de Sistemas
