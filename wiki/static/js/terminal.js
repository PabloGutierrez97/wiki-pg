// Widget del terminal: comandos (/terminal/cmd/) y preguntas a la IA en streaming (/terminal/ask/).
(function() {
  var fab = document.getElementById('term-fab');
  var win = document.getElementById('term-window');
  var body = document.getElementById('term-body');
  var output = document.getElementById('term-output');
  var input = document.getElementById('term-input');
  var btnClose = document.getElementById('term-btn-close');
  var btnMin = document.getElementById('term-btn-min');
  var btnMax = document.getElementById('term-btn-max');
  var history = [];
  var histIdx = -1;
  var started = false;
  var minimized = false;
  var maximized = false;
  var ocupado = false;

  var PUBLICOS = ['help','whoami','about','stack','ls','cat','buscar','tree','stats','neofetch','contact','date','wikis','ask','clear'];
  var CONOCIDOS = PUBLICOS.concat(['sudo','exit','logout','quit']);

  var COLORES = {
    'verde': '#28c840', 'azul': '#4f8ef7', 'amarillo': '#febc2e',
    'gris': '#888', 'rojo': '#ff5f57'
  };

  // Escapa también las comillas: el texto acaba dentro de atributos (href de los enlaces)
  // y una URL con " podría añadir atributos como onmouseover.
  function esc(t) {
    return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
            .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  }

  function colorear(texto) {
    var t = esc(texto);
    t = t.replace(/\[\[(verde|azul|amarillo|gris|rojo)\]\]/g, function(m, c){
      return '<span style="color:' + COLORES[c] + ';">';
    });
    t = t.replace(/\[\[\/\]\]/g, '</span>');
    t = t.replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener" style="color:#4f8ef7;">$1</a>');
    t = t.replace(/(^|[\s>])(\/article\/[a-z0-9\-]+\/)/g, '$1<a href="$2" style="color:#4f8ef7;">$2</a>');
    return t;
  }

  function renderMD(raw) {
    var s = esc(raw);
    var blocks = [];
    s = s.replace(/```[a-zA-Z0-9]*\n?([\s\S]*?)```/g, function(m, code){
      blocks.push(code.replace(/\n+$/, ''));
      return '\u0000CB' + (blocks.length - 1) + '\u0000';
    });
    s = s.replace(/\[\[(verde|azul|amarillo|gris|rojo)\]\]/g, function(m, c){ return '<span style="color:' + COLORES[c] + ';">'; });
    s = s.replace(/\[\[\/\]\]/g, '</span>');
    s = s.replace(/^(\s*)[\*\-]\s+/gm, '$1\u2022 '); /* MD-BULLETS */
    s = s.replace(/`([^`\n]+)`/g, '<code class="tcode">$1</code>');
    s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
    s = s.replace(/^\s*#{1,6}\s*(.+)$/gm, '<strong>$1</strong>');
    s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener" style="color:#4f8ef7;">$1</a>');
    s = s.replace(/(^|[\s>])(\/article\/[a-z0-9\-]+\/)/g, '$1<a href="$2" style="color:#4f8ef7;">$2</a>');
    s = s.replace(/\u0000CB(\d+)\u0000/g, function(m, i){ return '<pre class="tpre">' + blocks[parseInt(i, 10)] + '</pre>'; });
    return s;
  }

  var bannerLines = [
    '[[verde]]Wiki PG — Terminal interactivo[[/]]',
    'Explora la wiki como si fuera un servidor.',
    'Escribe [[amarillo]]help[[/]] para empezar o [[amarillo]]ask <pregunta>[[/]] para hablar con la IA.',
    ' '
  ];

  function printLine(text, isPrompt) {
    var div = document.createElement('div');
    if (isPrompt) {
      div.innerHTML = '<span style="color:#28c840;">pgg@wiki</span><span style="color:#666;">:</span><span style="color:#4f8ef7;">~</span><span style="color:#666;">$</span> ' + esc(text);
    } else {
      div.innerHTML = colorear(text);
    }
    output.appendChild(div);
  }

  function _lev(a,b){
    var m=a.length,n=b.length,d=[],i,j;
    for(i=0;i<=m;i++){d[i]=[i];}
    for(j=0;j<=n;j++){d[0][j]=j;}
    for(i=1;i<=m;i++){for(j=1;j<=n;j++){
      var c=(a.charAt(i-1)===b.charAt(j-1))?0:1;
      d[i][j]=Math.min(d[i-1][j]+1,d[i][j-1]+1,d[i-1][j-1]+c);
    }}
    return d[m][n];
  }
  function _sugerir(tok){
    var best=null,bd=99;
    PUBLICOS.forEach(function(c){var x=_lev(tok,c); if(x<bd){bd=x;best=c;}});
    return bd<=2?best:null;
  }

  function run(cmd) {
    printLine(cmd, true);
    if (/^ask(\s|$)/i.test(cmd)) { runAsk(cmd); return; }
    fetch('/terminal/cmd/', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({command: cmd})
    })
    .then(function(r){ return r.json(); })
    .then(function(data){
      if (data.clear) { output.innerHTML = ''; return; }
      if (data.output) { printLine(data.output, false); }
      body.scrollTop = body.scrollHeight;
    })
    .catch(function(){ printLine('[[rojo]]Error de conexion.[[/]]', false); body.scrollTop = body.scrollHeight; });
  }

  // ---- Pregunta a la IA -------------------------------------------------
  // Mientras la IA trabaja, el terminal se comporta como uno real: el prompt
  // desaparece (el proceso "tiene" la terminal), una línea de estado muestra
  // un spinner y los segundos, y Ctrl+C cancela. Al terminar vuelve el prompt.
  var SPIN = ['⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏'];
  var sinMovimiento = !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
  var conTeclado = !!(window.matchMedia && matchMedia('(hover: hover) and (pointer: fine)').matches);
  var promptLine = document.getElementById('term-prompt-line');
  var peticion = null;

  function runAsk(cmd) {
    ocupado = true;
    input.disabled = true;
    promptLine.style.display = 'none';
    var div = document.createElement('div');
    div.className = 't-ask';
    var estado = document.createElement('div');
    estado.className = 't-estado';
    estado.setAttribute('role', 'status');
    div.appendChild(estado);
    output.appendChild(div);

    var t0 = Date.now(), frame = 0, timer = null, buffer = '';
    function pintarEstado() {
      var seg = Math.floor((Date.now() - t0) / 1000);
      estado.innerHTML = '<span class="t-spin" aria-hidden="true">' + (sinMovimiento ? '…' : SPIN[frame++ % SPIN.length]) + '</span>' +
        'pensando<span class="t-tiempo">' + seg + 's</span>' +
        (conTeclado && seg >= 3 ? '<span class="t-pista">ctrl+c cancela</span>' : '');
      body.scrollTop = body.scrollHeight;
    }
    pintarEstado();
    timer = setInterval(pintarEstado, sinMovimiento ? 1000 : 90);

    function parar() { if (timer) { clearInterval(timer); timer = null; } }
    function pintar(escribiendo) {
      div.innerHTML = renderMD(buffer) + (escribiendo ? '<span class="t-cursor" aria-hidden="true"></span>' : '');
      body.scrollTop = body.scrollHeight;
    }
    function liberar() {
      peticion = null;
      ocupado = false;
      input.disabled = false;
      promptLine.style.display = 'flex';
      body.scrollTop = body.scrollHeight;
      try { input.focus(); } catch (e) {}
    }

    peticion = window.AbortController ? new AbortController() : null;
    fetch('/terminal/ask/', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({command: cmd}),
      signal: peticion ? peticion.signal : undefined
    })
    .then(function(resp){
      if (!resp.ok) { throw new Error('http'); }
      if (!resp.body || !resp.body.getReader) {
        return resp.text().then(function(t){ parar(); buffer = t; pintar(false); });
      }
      var reader = resp.body.getReader();
      var dec = new TextDecoder();
      function leer(){
        return reader.read().then(function(r){
          if (r.done) { parar(); pintar(false); return; }
          var txt = dec.decode(r.value, {stream: true});
          if (txt) { parar(); buffer += txt; pintar(true); }
          return leer();
        });
      }
      return leer();
    })
    .then(liberar)
    .catch(function(err){
      parar();
      if (err && err.name === 'AbortError') {
        div.innerHTML = (buffer ? renderMD(buffer) + '\n' : '') + colorear('[[gris]]^C cancelado[[/]]');
      } else if (!buffer) {
        div.innerHTML = colorear('[[rojo]]Error de conexion.[[/]] Vuelve a intentarlo en un momento.');
      } else {
        pintar(false);
      }
      liberar();
    });
  }

  // Ctrl+C cancela la pregunta en curso (si no hay texto seleccionado que copiar).
  document.addEventListener('keydown', function(e){
    if (!peticion || !e.ctrlKey || (e.key !== 'c' && e.key !== 'C')) return;
    if (win.style.display !== 'flex') return;
    var sel = window.getSelection ? String(window.getSelection()) : '';
    if (sel) return;
    e.preventDefault();
    peticion.abort();
  });

  function applySize() {
    if (minimized) {
      body.style.display = 'none';
      win.style.height = 'auto';
    } else {
      body.style.display = 'block';
      if (maximized) {
        win.style.width = 'min(900px, calc(100vw - 32px))';
        win.style.height = 'calc(100vh - 120px)';
        win.style.bottom = '24px';
      } else {
        win.style.width = 'min(440px, calc(100vw - 32px))';
        win.style.height = 'min(540px, calc(100vh - 140px))';
        win.style.bottom = '94px';
      }
    }
  }

  function openWin() {
    win.style.display = 'flex';
    if (!started) {
      bannerLines.forEach(function(l){ printLine(l, false); });
      started = true;
    }
    applySize();
    setTimeout(function(){ input.focus(); }, 50);
  }
  function closeWin() { win.style.display = 'none'; }

  fab.addEventListener('mouseenter', function(){ fab.style.transform = 'scale(1.08)'; });
  fab.addEventListener('mouseleave', function(){ fab.style.transform = 'scale(1)'; });
  fab.addEventListener('click', function(){
    if (win.style.display === 'flex') closeWin(); else openWin();
  });
  btnClose.addEventListener('click', closeWin);
  btnMin.addEventListener('click', function(){ minimized = !minimized; applySize(); });
  btnMax.addEventListener('click', function(){ maximized = !maximized; if (minimized) minimized = false; applySize(); });

  input.addEventListener('keydown', function(e) {
    if (e.key === 'Tab') {
      e.preventDefault();
      var v = input.value.replace(/^\s+/,'');
      if (v.indexOf(' ') !== -1) return;
      if (!v) { printLine('[[gris]]' + PUBLICOS.join('  ') + '[[/]]', false); body.scrollTop = body.scrollHeight; return; }
      var ms = PUBLICOS.filter(function(c){ return c.indexOf(v.toLowerCase()) === 0; });
      if (ms.length === 1) { input.value = ms[0] + ' '; }
      else if (ms.length > 1) { printLine('[[gris]]' + ms.join('  ') + '[[/]]', false); body.scrollTop = body.scrollHeight; }
      return;
    }
    if (e.key === 'Enter') {
      if (ocupado) { e.preventDefault(); return; }
      var raw = input.value.trim();
      input.value = '';
      if (!raw) return;
      history.unshift(raw); histIdx = -1;
      var tok = raw.split(/\s+/)[0].toLowerCase();
      if (CONOCIDOS.indexOf(tok) === -1) {
        printLine(raw, true);
        var sug = _sugerir(tok);
        printLine('[[rojo]]comando no reconocido:[[/]] ' + tok, false);
        if (sug) { printLine('[[gris]]quisiste decir[[/]] [[azul]]' + sug + '[[/]][[gris]]?[[/]]', false); }
        else { printLine('[[gris]]escribe[[/]] [[amarillo]]help[[/]] [[gris]]para ver los comandos.[[/]]', false); }
        body.scrollTop = body.scrollHeight;
        return;
      }
      run(raw);
      setTimeout(function(){ body.scrollTop = body.scrollHeight; }, 30);
      return;
    }
    if (e.key === 'ArrowUp') {
      if (histIdx < history.length - 1) { histIdx++; input.value = history[histIdx]; }
      e.preventDefault();
      return;
    }
    if (e.key === 'ArrowDown') {
      if (histIdx > 0) { histIdx--; input.value = history[histIdx]; }
      else { histIdx = -1; input.value = ''; }
      e.preventDefault();
      return;
    }
  });

  function _ajustarTeclado(){
    if (win.style.display !== 'flex') return;
    if (window.innerWidth > 520 || !window.visualViewport) { win.style.top = 'auto'; return; }
    var vp = window.visualViewport;
    var kb = Math.max(0, window.innerHeight - vp.height - vp.offsetTop);
    if (kb > 120) {
      win.style.top = (vp.offsetTop + 8) + 'px';
      win.style.bottom = 'auto';
      win.style.height = (vp.height - 16) + 'px';
    } else {
      win.style.top = 'auto';
      applySize();
    }
  }
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', _ajustarTeclado);
    window.visualViewport.addEventListener('scroll', _ajustarTeclado);
  }
  body.addEventListener('click', function(e){ if (e.target.closest && e.target.closest('a')) return; input.focus(); });
})();
