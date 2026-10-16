# Recorrido explicado para la memoria y la defensa

## 1. Qué hace el arranque

`./run.sh up-dev` selecciona `docker-compose.dev.yml`, carga `.env.dev` y usa el proyecto `practica1-dev`. Ejecuta `up --build -d --wait`: construye la imagen web, arranca en segundo plano y espera los healthchecks. PostgreSQL usa una imagen oficial ya preparada; Flask usa nuestra imagen construida con el Dockerfile.

El Dockerfile parte de Python 3.13, instala `requirements.txt`, copia `app` y selecciona el usuario 10001. Las dependencias se copian antes que el código para reutilizar esa capa si solo cambiamos Python, HTML o JavaScript. En desarrollo Compose sustituye el comando Gunicorn por Flask con recarga y monta el código local como solo lectura; en producción se ejecuta el código que quedó dentro de la imagen.

Compose crea los recursos con prefijos separados. Por ejemplo, `practica1-dev_db_data` y `practica1-prod_db_data` son volúmenes distintos aunque ambos YAML utilicen la clave `db_data`.

## 2. Recorrido de una escritura

1. El navegador carga `/`: Flask devuelve la plantilla HTML y el navegador descarga JavaScript y CSS.
2. El usuario escribe una nota y pulsa Guardar.
3. JavaScript envía `POST /api/notes` con JSON: `{"content":"Mi nota"}`.
4. Flask valida que el contenido sea texto de 1 a 500 caracteres.
5. Psycopg conecta con el servicio `db` usando el usuario `notes_app` y ejecuta una inserción parametrizada.
6. Al salir correctamente del contexto de conexión, la transacción se confirma. PostgreSQL conserva los datos en su volumen.
7. En producción Flask intenta borrar `notes:list` de Redis, porque la lista almacenada ya puede estar desactualizada.
8. La API devuelve HTTP 201 y la nota creada. JavaScript muestra el mensaje y vuelve a consultar la lista.

Un 201 indica creación correcta; un 400 indica datos inválidos; un 503 indica que la operación no puede completarse por una dependencia no disponible. Un fallo de red después de confirmar la escritura puede impedir recibir la respuesta aunque la nota se haya guardado: la interfaz recomienda consultar la lista antes de reintentar.

## 3. Por qué los nombres y puertos son diferentes

El navegador entra por `localhost:5000` en desarrollo y `localhost:8000` en producción. Ambos contenedores web escuchan internamente en 5000; Docker publica un puerto distinto del anfitrión para cada uno.

Dentro del contenedor web, `localhost` sería el propio contenedor. Para alcanzar PostgreSQL usamos `db:5432`; para Redis, `cache:6379`. Docker resuelve esos nombres en la red de cada proyecto. No hay que publicar 5432 ni 6379 para permitir esta comunicación.

La web se conecta a `frontend` y a `backend`. Los servicios de datos solo están en `backend`, configurada como interna. La publicación de puertos en Compose habilita el acceso desde el anfitrión; el nombre frontend no publica servicios por sí solo. La auditoría confirmó que los únicos puertos publicados son 127.0.0.1:5000 y 127.0.0.1:8000.

## 4. Qué demuestra la persistencia

La prueba guarda una nota identificable y después elimina el contenedor de PostgreSQL. Al arrancar otro contenedor, Compose vuelve a montar el mismo volumen en `/var/lib/postgresql/data`. El nuevo proceso encuentra el almacenamiento existente y recupera la nota.

En la ejecución histórica del 9 de octubre comprobamos directamente por SQL que la nota #2 seguía presente en cada entorno. Las ejecuciones posteriores generan otros identificadores, registrados en sus evidencias. Así Redis no puede ocultar una pérdida de datos devolviendo una copia antigua. Los dos entornos contienen su propia nota #2: los identificadores son locales a cada base de datos.

Recrear un contenedor, eliminar un volumen y realizar una copia de seguridad son operaciones diferentes. El volumen sobrevive al contenedor, pero no protege frente a eliminar el propio volumen ni sustituye a un backup.

## 5. Qué aporta Redis

La lectura de una lista sigue el patrón de consultar primero la caché. Si la clave no existe, la web consulta SQL y guarda una copia temporal. Si existe, responde con ella y evita la consulta SQL de la lista.

La interfaz mostró primero `source=postgresql` y después `source=redis`. El TTL es 30 segundos, de modo que una copia expira automáticamente. Tras escribir una nota se elimina la clave antes de la siguiente lectura. La invalidación y la escritura SQL pertenecen a servicios distintos: no hay una transacción distribuida ni consistencia estricta ante concurrencia. El README documenta esta limitación.

Los healthchecks siguen consultando las conexiones aunque las listas se sirvan desde Redis. Por tanto, usar caché reduce las consultas de lectura de notas; no elimina toda actividad SQL.

## 6. Qué comprobamos al provocar fallos

- Con Redis detenido, `/status` devuelve 503 y la página muestra Sin conexión. La lista sigue funcionando mediante PostgreSQL.
- Con PostgreSQL detenido y sin una lista en caché, la lectura devuelve 503 y la página muestra el error. Si quedara una copia válida en Redis, podría servirse, pero `/status` seguiría mostrando el fallo SQL.
- Al recuperar los servicios, las comprobaciones vuelven a detectar conexiones correctas. La página no necesita recargarse manualmente para actualizar el estado.

El navegador repite la comprobación cinco segundos después de finalizar la anterior. Docker comprueba por separado cada contenedor y necesita varios fallos antes de marcarlo unhealthy. Esto explica por qué el estado Docker y el de la página pueden cambiar en momentos distintos.

## 7. Detalles que conviene defender

- **Separación de configuración:** `.env.dev` y `.env.prod` permiten puertos y secretos distintos con el mismo código. Compose recibe `--env-file` de forma explícita.
- **Doble dólar en YAML:** `$$DB_PASSWORD` evita que Compose sustituya esa referencia en el equipo anfitrión; el shell del contenedor la resolverá al ejecutar su healthcheck.
- **Usuario limitado:** la web corre como UID 10001. En PostgreSQL, `notes_app` no es superusuario: puede leer e insertar notas, pero no borrarlas. Ambas propiedades se verificaron en ejecución.
- **Inicialización:** `db/init.sh` se ejecuta únicamente sobre un volumen vacío. No se ejecuta de nuevo en cada arranque ni cambia contraseñas de un volumen existente.
- **Parada:** `./run.sh down dev` elimina contenedores y redes conservando el volumen. `down -v` borraría también los datos y no forma parte del comando de parada preparado.
- **Resultados:** las pruebas unitarias comprueban decisiones del código con servicios simulados; las de integración comprueban los contenedores reales. Se ejecutaron ambas.

## 8. API, salida ASCII y comprobación independiente de caché

`curl` es un cliente HTTP externo al proyecto. `curl -i http://localhost:8000/api/notes` solicita la lista y muestra cabeceras y cuerpo. Flask atiende esa ruta en `app/__init__.py`, dentro de `list_notes()`: no existe una carpeta llamada `api`.

El JSON lo construye `jsonify()`. Si Redis devuelve `notes:list`, Flask añade `source=redis` y `cache=hit`; esos campos son información declarada por la aplicación. Antes de enviar el JSON, `response_headers()` aplica `ascii_text()` de forma recursiva. La normalización NFKD y la conversión ASCII eliminan tildes y símbolos no representables, conservando los originales en los servicios de datos.

Para contrastar el uso de Redis, cerrar la página web y evitar otras consultas simultáneas:

```bash
./run.sh cache-stats --once
curl -s http://localhost:8000/api/notes
curl -s http://localhost:8000/api/notes
./run.sh cache-stats --once
```

La segunda lectura debería aumentar `keyspace_hits` antes de que expire el TTL de 30 segundos. La consulta interna es `./run.sh compose prod exec -T cache redis-cli INFO stats`: `cache` selecciona el servicio; `redis-cli` es el cliente; `INFO stats` pide estadísticas al servidor Redis. `grep` filtra los dos contadores. `./run.sh cache-stats` repite la consulta con `watch` cada segundo; salir con Ctrl+C.

Son contadores globales de la instancia: no certifican por sí solos qué petición causó cada incremento si hay otras consultas. Los healthchecks usan PING, no GET de la lista. `Cache-Control: no-store` regula el almacenamiento HTTP del cliente o un proxy; no impide que Flask use Redis.

## 9. Guion de arranque y demostración

1. Ejecutar `./run.sh init`, `./run.sh up-dev` y `./run.sh up-prod`.
2. Mostrar `./run.sh status dev` y `./run.sh status prod`: dos y tres contenedores, respectivamente.
3. Abrir los puertos 5000 y 8000, crear notas diferentes y explicar el aislamiento de datos.
4. Mostrar `./run.sh db-test prod` y la comprobación de Redis del apartado anterior.
5. Ejecutar `./run.sh verify prod` para demostrar persistencia y recuperación. Esta prueba crea notas y provoca interrupciones temporales.
6. Consultar de nuevo el estado de ambos entornos.

Para recrear los contenedores conservando notas, ejecutar `./run.sh down dev` y `./run.sh down prod`, y después los comandos de arranque. Para una demostración con bases vacías, los siguientes comandos **eliminan permanentemente todas las notas de ambos entornos**:

```bash
./run.sh compose dev down --volumes --remove-orphans
./run.sh compose prod down --volumes --remove-orphans
./run.sh up-dev
./run.sh up-prod
```

No es necesario borrar imágenes para recrear contenedores y bases vacías. Conservar los archivos `.env` permite reutilizar la configuración; en una copia nueva del proyecto, `init` genera las credenciales.

## 10. Conceptos para la defensa

- **Imagen:** plantilla usada para crear contenedores; el Dockerfile construye la de la web.
- **Contenedor:** proceso aislado y su entorno de ejecución. No sustituye al volumen persistente.
- **Compose:** define y coordina servicios, redes, volúmenes y healthchecks.
- **Volumen:** conserva PostgreSQL aunque se elimine el contenedor; borrarlo elimina los datos.
- **Healthcheck:** comprueba que el servicio responde. Un fallo no reinicia automáticamente el contenedor.
- **TTL:** tiempo de vida de una copia en Redis; 30 segundos por defecto.
- **Configuración:** los `.env` privados separan credenciales y código; no se entregan.

