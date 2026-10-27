/* Wiki PG — comportamiento de la interfaz */
(function () {
    'use strict';

    var root = document.documentElement;
    var mobile = window.matchMedia('(max-width: 860px)');

    /* ---------- Tema ---------- */
    function syncThemeButton() {
        var dark = root.getAttribute('data-theme') === 'dark';
        document.querySelectorAll('[data-theme-toggle]').forEach(function (btn) {
            btn.setAttribute('aria-label', dark ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro');
            btn.title = btn.getAttribute('aria-label');
            var icon = btn.querySelector('i');
            if (icon) icon.className = dark ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
        });
    }
    document.querySelectorAll('[data-theme-toggle]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
            root.setAttribute('data-theme', next);
            try { localStorage.setItem('theme', next); } catch (e) {}
            syncThemeButton();
        });
    });
    syncThemeButton();

    /* ---------- Menú lateral en móvil ---------- */
    var sidebar = document.getElementById('sidebar');
    var overlay = document.querySelector('.sidebar-overlay');
    var menuBtn = document.querySelector('[data-menu-toggle]');
    function setMenu(open) {
        if (!sidebar) return;
        sidebar.classList.toggle('is-open', open);
        overlay.classList.toggle('is-open', open);
        if (menuBtn) {
            menuBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
            menuBtn.setAttribute('aria-label', open ? 'Cerrar menú' : 'Abrir menú');
            menuBtn.querySelector('i').className = open ? 'fa-solid fa-xmark' : 'fa-solid fa-bars';
        }
        if (open) {
            var first = sidebar.querySelector('a');
            if (first) first.focus();
        }
    }
    if (menuBtn) menuBtn.addEventListener('click', function () { setMenu(!sidebar.classList.contains('is-open')); });
    if (overlay) overlay.addEventListener('click', function () { setMenu(false); });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && sidebar && sidebar.classList.contains('is-open')) { setMenu(false); menuBtn.focus(); }
    });

    /* La flecha abre y cierra; el nombre de la categoría navega */
    document.querySelectorAll('.nav-group > summary .nav-link').forEach(function (link) {
        link.addEventListener('click', function (e) { e.stopPropagation(); });
    });

    /* ---------- Buscador en vivo ---------- */
    function esc(t) {
        return String(t).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    document.querySelectorAll('[data-live-search]').forEach(function (input) {
        var form = input.closest('form');
        var box = form.querySelector('.search-results');
        if (!box) return;
        var timer = null, active = -1, lastQuery = '';

        function items() { return box.querySelectorAll('a'); }
        function close() { box.hidden = true; active = -1; input.setAttribute('aria-expanded', 'false'); }
        function mark(i) {
            var list = items();
            list.forEach(function (a, j) { a.setAttribute('aria-selected', j === i ? 'true' : 'false'); });
            active = i;
        }

        input.setAttribute('role', 'combobox');
        input.setAttribute('aria-autocomplete', 'list');
        input.setAttribute('aria-expanded', 'false');

        input.addEventListener('input', function () {
            var q = input.value.trim();
            clearTimeout(timer);
            if (q.length < 2) { close(); return; }
            timer = setTimeout(function () {
                lastQuery = q;
                fetch('/search/api/?q=' + encodeURIComponent(q))
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (q !== lastQuery) return;
                        var html = data.results.map(function (a) {
                            return '<li><a role="option" href="' + esc(a.url) + '">' + esc(a.title) +
                                (a.category ? '<small>' + esc(a.category) + '</small>' : '') + '</a></li>';
                        }).join('');
                        html += '<li><a role="option" class="search-all" href="/search/?q=' + encodeURIComponent(q) + '">' +
                            (data.results.length ? 'Ver todos los resultados de «' + esc(q) + '»' : 'Sin coincidencias en títulos. Buscar «' + esc(q) + '» en todo el texto') +
                            '</a></li>';
                        box.innerHTML = html;
                        box.hidden = false;
                        input.setAttribute('aria-expanded', 'true');
                        active = -1;
                    })
                    .catch(close);
            }, 180);
        });

        input.addEventListener('keydown', function (e) {
            var list = items();
            if (box.hidden || !list.length) return;
            if (e.key === 'ArrowDown') { e.preventDefault(); mark((active + 1) % list.length); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); mark((active - 1 + list.length) % list.length); }
            else if (e.key === 'Enter' && active >= 0) { e.preventDefault(); window.location = list[active].href; }
            else if (e.key === 'Escape') { close(); }
        });

        document.addEventListener('click', function (e) { if (!form.contains(e.target)) close(); });
    });

    /* «/» enfoca el buscador visible, como en muchas herramientas de terminal */
    document.addEventListener('keydown', function (e) {
        if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return;
        var t = e.target;
        if (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) return;
        var inputs = Array.prototype.filter.call(document.querySelectorAll('[data-live-search], .search-page-input'), function (i) {
            return i.offsetParent !== null;
        });
        if (inputs.length) { e.preventDefault(); inputs[inputs.length - 1].focus(); }
    });

    /* ---------- Contenido de artículos ---------- */
    var prose = document.querySelector('.prose');
    if (prose) {
        /* Tablas con scroll horizontal */
        prose.querySelectorAll('table').forEach(function (table) {
            if (table.parentElement.classList.contains('table-wrapper')) return;
            var wrap = document.createElement('div');
            wrap.className = 'table-wrapper';
            table.parentNode.insertBefore(wrap, table);
            wrap.appendChild(table);
        });

        /* Bloques de código: lenguaje + botón Copiar */
        var LANGS = { bash: 'bash', sh: 'sh', shell: 'shell', console: 'consola', powershell: 'PowerShell', ps1: 'PowerShell',
            yaml: 'YAML', yml: 'YAML', ini: 'ini', json: 'JSON', python: 'Python', py: 'Python', sql: 'SQL',
            nginx: 'nginx', apacheconf: 'Apache', dockerfile: 'Dockerfile', xml: 'XML', html: 'HTML', toml: 'TOML',
            jinja: 'Jinja', 'yaml+jinja': 'YAML', batch: 'cmd', bat: 'cmd', cfg: 'cfg', conf: 'conf', diff: 'diff', csharp: 'C#' };

        prose.querySelectorAll('pre').forEach(function (pre) {
            var container = pre.closest('.highlight') || pre;
            if (container.parentElement.classList.contains('code-block')) return;
            var code = pre.querySelector('code') || pre;
            var m = (code.className || '').match(/language-([\w+#-]+)/);
            var lang = m ? (LANGS[m[1].toLowerCase()] || m[1]) : '';
            if (lang === 'text') lang = '';

            var block = document.createElement('figure');
            block.className = 'code-block';
            var head = document.createElement('figcaption');
            head.className = 'code-head';
            head.innerHTML = '<span class="code-lang">' + esc(lang) + '</span>' +
                '<button type="button" class="copy-btn"><i class="fa-regular fa-copy" aria-hidden="true"></i><span>Copiar</span></button>';
            container.parentNode.insertBefore(block, container);
            block.appendChild(head);
            block.appendChild(container);

            var btn = head.querySelector('.copy-btn');
            var label = btn.querySelector('span');
            if (lang) btn.setAttribute('aria-label', 'Copiar código ' + lang);
            btn.addEventListener('click', function () {
                var text = code.innerText.replace(/\n$/, '');
                var done = function () {
                    label.textContent = 'Copiado';
                    btn.classList.add('is-done');
                    btn.querySelector('i').className = 'fa-solid fa-check';
                    setTimeout(function () {
                        label.textContent = 'Copiar';
                        btn.classList.remove('is-done');
                        btn.querySelector('i').className = 'fa-regular fa-copy';
                    }, 1800);
                };
                if (navigator.clipboard && window.isSecureContext) {
                    navigator.clipboard.writeText(text).then(done);
                } else {
                    var ta = document.createElement('textarea');
                    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
                    document.body.appendChild(ta); ta.select();
                    try { document.execCommand('copy'); done(); } catch (e) {}
                    ta.remove();
                }
            });
        });

        /* Barra de progreso de lectura */
        var bar = document.querySelector('.reading-progress');
        if (bar) {
            var ticking = false;
            var update = function () {
                var top = prose.getBoundingClientRect().top + window.scrollY;
                var end = top + prose.offsetHeight - window.innerHeight;
                var p = end > top ? (window.scrollY - top) / (end - top) : 1;
                bar.style.transform = 'scaleX(' + Math.min(1, Math.max(0, p)) + ')';
                ticking = false;
            };
            window.addEventListener('scroll', function () {
                if (!ticking) { ticking = true; requestAnimationFrame(update); }
            }, { passive: true });
            update();
        }

        /* Índice: marca la sección que se está leyendo */
        var toc = document.querySelector('.toc');
        if (toc) {
            var tocQuery = window.matchMedia('(max-width: 1100px)');
            if (tocQuery.matches) toc.removeAttribute('open');
            tocQuery.addEventListener('change', function (e) { if (!e.matches) toc.setAttribute('open', ''); });
            toc.querySelector('summary').addEventListener('click', function (e) {
                if (!tocQuery.matches) e.preventDefault();
            });

            var links = {};
            toc.querySelectorAll('a[href^="#"]').forEach(function (a) {
                links[decodeURIComponent(a.getAttribute('href').slice(1))] = a;
                a.addEventListener('click', function () { if (tocQuery.matches) toc.removeAttribute('open'); });
            });
            var heads = Array.prototype.filter.call(prose.querySelectorAll('h2[id], h3[id], h4[id]'), function (h) { return links[h.id]; });
            if (heads.length && 'IntersectionObserver' in window) {
                var current = null;
                var setCurrent = function (id) {
                    if (current === id) return;
                    if (current && links[current]) links[current].classList.remove('is-current');
                    current = id;
                    if (links[id]) links[id].classList.add('is-current');
                };
                var io = new IntersectionObserver(function () {
                    var line = (parseInt(getComputedStyle(root).getPropertyValue('--topbar-h'), 10) || 56) + 40;
                    var id = heads[0].id;
                    heads.forEach(function (h) { if (h.getBoundingClientRect().top <= line) id = h.id; });
                    setCurrent(id);
                }, { rootMargin: '0px 0px -60% 0px', threshold: [0, 1] });
                heads.forEach(function (h) { io.observe(h); });
            }
        }
    }
    /* ---------- Portada: comando del día ---------- */
    var cmdCard = document.querySelector('[data-cmd-card]');
    var cmdData = document.getElementById('cmd-data');
    if (cmdCard && cmdData) {
        var lista = [];
        try { lista = JSON.parse(cmdData.textContent) || []; } catch (e) {}
        var elTexto = cmdCard.querySelector('[data-cmd-text]');
        var elPrompt = cmdCard.querySelector('[data-cmd-prompt]');
        var elLang = cmdCard.querySelector('[data-cmd-lang]');
        var elLink = cmdCard.querySelector('[data-cmd-link]');
        var elStatus = cmdCard.querySelector('[data-cmd-status]');
        var btnCopy = cmdCard.querySelector('[data-cmd-copy]');
        var btnNext = cmdCard.querySelector('[data-cmd-next]');
        var quieto = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        var actual = 0, tecleo = null;

        // Lo que falta por teclear ocupa su sitio de forma invisible: la tarjeta
        // no cambia de alto mientras se escribe y la página no salta.
        var cursor = cmdCard.querySelector('.cmd-cursor');
        var escrito = document.createElement('span');
        var resto = document.createElement('span');
        resto.className = 'cmd-ghost';
        resto.setAttribute('aria-hidden', 'true');
        var escribir = function (texto, ms) {
            clearInterval(tecleo);
            elTexto.textContent = '';
            if (quieto) { elTexto.textContent = texto; return; }
            elTexto.appendChild(escrito);
            if (cursor) elTexto.appendChild(cursor);
            elTexto.appendChild(resto);
            var i = 0;
            var paso = function () {
                escrito.textContent = texto.slice(0, i);
                resto.textContent = texto.slice(i);
                if (i >= texto.length) {
                    clearInterval(tecleo);
                    elTexto.textContent = texto;
                    if (cursor) elTexto.parentNode.appendChild(cursor);
                }
                i += 1;
            };
            paso();
            tecleo = setInterval(paso, ms);
        };
        var mostrar = function (n, ms) {
            var c = lista[n];
            if (!c) return;
            actual = n;
            cmdCard.setAttribute('data-lang', c.lang);
            elPrompt.textContent = c.prompt;
            elLang.textContent = c.lang;
            elLink.textContent = c.titulo;
            elLink.setAttribute('href', c.url);
            escribir(c.cmd, ms);
        };

        // Una sola animación al cargar: el comando del día se «teclea».
        if (lista.length && !quieto) escribir(lista[0].cmd, 32);

        if (btnNext) btnNext.addEventListener('click', function () {
            mostrar((actual + 1) % lista.length, 14);
            if (elStatus) elStatus.textContent = 'Comando de «' + lista[actual].titulo + '»';
        });
        if (btnCopy) btnCopy.addEventListener('click', function () {
            var texto = lista[actual] ? lista[actual].cmd : elTexto.textContent;
            var label = btnCopy.querySelector('span');
            var icon = btnCopy.querySelector('i');
            var hecho = function () {
                clearInterval(tecleo);
                elTexto.textContent = texto;
                var cur = cmdCard.querySelector('.cmd-cursor');
                if (cur && cur.parentNode === elTexto) elTexto.parentNode.appendChild(cur);
                label.textContent = 'Copiado';
                icon.className = 'fa-solid fa-check';
                btnCopy.classList.add('is-done');
                if (elStatus) elStatus.textContent = 'Comando copiado';
                setTimeout(function () {
                    label.textContent = 'Copiar';
                    icon.className = 'fa-regular fa-copy';
                    btnCopy.classList.remove('is-done');
                }, 1800);
            };
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(texto).then(hecho);
            } else {
                var ta = document.createElement('textarea');
                ta.value = texto; ta.style.position = 'fixed'; ta.style.opacity = '0';
                document.body.appendChild(ta); ta.select();
                try { document.execCommand('copy'); hecho(); } catch (e) {}
                ta.remove();
            }
        });
    }
})();
