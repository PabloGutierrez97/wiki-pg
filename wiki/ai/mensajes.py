"""Textos fijos de la IA. Usan el marcado de colores del terminal: [[color]]texto[[/]]."""

PREFIJO = "[[verde]]IA[[/]] [[gris]].[[/]] "

RAPIDO = "[[amarillo]]Vas muy rapido.[[/]] Espera un poco antes de volver a preguntar."
EN_CURSO = "[[amarillo]]Ya tienes una pregunta en curso.[[/]] Espera a que termine la respuesta."
OCUPADA = ("[[amarillo]]La IA esta atendiendo a otras personas ahora mismo.[[/]] "
           "Vuelve a preguntar en unos segundos.")
NO_DISPONIBLE = "[[rojo]]La IA no esta disponible ahora mismo.[[/]] Intentalo de nuevo en un momento."
SIN_RESPUESTA = "No he podido generar una respuesta. Prueba a reformular la pregunta."
USO = "Uso: [[amarillo]]ask <pregunta>[[/]]  (ej: ask que es rclone?)"
DEMASIADO_LARGA = "[[rojo]]La pregunta es demasiado larga[[/]] (maximo 300 caracteres)."

FUERA_DE_TEMA = (PREFIJO + "Solo puedo ayudarte con la wiki de Pablo y con temas de "
                 "sistemas, redes, virtualizacion y DevOps. No escribo articulos, historias ni recetas, "
                 "y no invento nada sobre Pablo.\n\n"
                 "[[gris]]Prueba con[[/]] [[amarillo]]ls[[/]][[gris]],[[/]] [[amarillo]]buscar <tema>[[/]] "
                 "[[gris]]o[[/]] [[amarillo]]help[[/]][[gris]].[[/]]")

MANIPULACION = (PREFIJO + "No puedo cambiar de papel ni saltarme mis instrucciones: solo respondo como el "
                "asistente de la wiki, sobre sistemas, redes y lo que hay publicado aqui.\n\n"
                "[[gris]]Prueba con[[/]] [[amarillo]]ask que es proxmox[[/]] [[gris]]o[[/]] [[amarillo]]help[[/]][[gris]].[[/]]")
ATAQUE = (PREFIJO + "No ayudo a atacar sistemas o cuentas ajenas. Si lo que quieres es proteger los tuyos, "
          "preguntame como (por ejemplo: [[amarillo]]ask como protejo mi wifi[[/]]).")

PISTA_PERFIL = ("\n\n[[gris]]Para saber mas, escribe[[/]] [[amarillo]]stack[[/]] [[gris]]o[[/]] "
                "[[amarillo]]whoami[[/]][[gris]].[[/]]")

COMO_FUNCIONA = (
    PREFIJO + "Funciono con un modelo de lenguaje [[azul]]Llama 3.2[[/]] ejecutandose en local a traves de "
    "[[azul]]Ollama[[/]], sin depender de ninguna API externa. "
    "Para responder sobre la wiki uso un sistema RAG: busco los fragmentos mas relevantes de los articulos con "
    "embeddings ([[azul]]bge-m3[[/]]) y similitud coseno, y se los paso al modelo. "
    "Todo esta montado sobre [[azul]]Django[[/]], que hace de proxy seguro hacia el servidor de IA, y la "
    "respuesta te llega en streaming.")

COSENO = (
    PREFIJO + "La [[azul]]similitud coseno[[/]] mide lo parecidos que son dos textos por su significado. "
    "Primero convierto tu pregunta y cada fragmento de los articulos en un vector de numeros (un embedding de "
    "1024 dimensiones con bge-m3) que representa su sentido. "
    "Luego calculo el coseno del angulo entre el vector de tu pregunta y el de cada fragmento: va de 0 (nada "
    "que ver) a 1 (practicamente el mismo tema). "
    "Me quedo con los fragmentos de mayor puntuacion y se los paso al modelo. Lo bueno es que compara el "
    "significado, no las palabras exactas: por eso 'copiar archivos a la nube' encuentra el articulo de "
    "rclone aunque no digas 'rclone'.")


def leer(slug):
    return "\n\n[[gris]]Leer:[[/]] /article/" + slug + "/"


def ultimo_articulo(articulo):
    return (PREFIJO + "El ultimo articulo publicado es [[azul]]" + articulo.title + "[[/]], del " +
            articulo.created_at.strftime('%d/%m/%Y') + "." + leer(articulo.slug))


def presentacion_fija(perfil):
    """Presentación de Pablo sin modelo, con los datos del perfil."""
    nombre = (perfil.nombre or 'Pablo Gutierrez Gracia').strip()
    cargo = (perfil.cargo or '').strip()
    empresa = (perfil.empresa or '').strip()
    texto = '[[verde]]' + nombre + '[[/]]'
    if cargo and empresa:
        texto += ' es ' + cargo + ' en ' + empresa + '.'
    elif cargo:
        texto += ' es ' + cargo + '.'
    else:
        texto += '.'
    if (perfil.descripcion or '').strip():
        texto += ' ' + perfil.descripcion.strip()
    return (PREFIJO + texto + '\n\n[[gris]]Escribe[[/]] [[amarillo]]stack[[/]] [[gris]]para ver con que '
            'tecnologias trabaja, o[[/]] [[amarillo]]contact[[/]] [[gris]]para su contacto.[[/]]')
