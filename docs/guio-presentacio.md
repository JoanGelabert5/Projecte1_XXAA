# Guió de presentació de la pràctica, des de zero

Durada orientativa: 20–25 minuts, més el temps de construcció. Executa els blocs un a un i explica el resultat abans de continuar. Aquest document és un guió: preparar-lo no ha executat cap neteja ni cap prova.

## 0. Presentar l'objectiu i comprovar Docker

**Què dir:** «Presentaré una aplicació de notes amb dos entorns separats. Desenvolupament utilitza Flask i PostgreSQL; producció utilitza Gunicorn, PostgreSQL i Redis. Començaré eliminant el desplegament anterior perquè es vegi tot el procés.»

```bash
cd ~/Escritorio/Projecte1_XXAA
docker info --format '{{.ServerVersion}}'
docker compose version
docker ps -a --filter label=com.docker.compose.project=practica1-dev
docker ps -a --filter label=com.docker.compose.project=practica1-prod
```

Si Docker no respon, resol el problema abans de començar. Les URLs del guió assumeixen els ports per defecte: 5000 i 8000.

## 1. Esborrar el desplegament anterior

**Què dir:** «Ara eliminaré els contenidors, les xarxes, els volums amb les notes i les imatges locals de la web dels dos entorns. Conservaré el codi font i la configuració privada.»

**Aquest bloc elimina permanentment les notes de dev i prod.** Només afecta els dos projectes de la pràctica. No utilitzis una neteja global com `docker system prune`.

```bash
./run.sh init
./run.sh compose dev down --volumes --remove-orphans --rmi local
./run.sh compose prod down --volumes --remove-orphans --rmi local
```

`init` assegura que existeixen els fitxers necessaris per executar Compose; si ja existeixen, els conserva. Les imatges base descarregades i la caché de construcció poden continuar a Docker. Al pas de construcció farem servir `--no-cache` per executar novament les capes de la web.

**Demostrar el punt de partida:**

```bash
docker ps -a --filter label=com.docker.compose.project=practica1-dev
docker ps -a --filter label=com.docker.compose.project=practica1-prod
docker network ls --filter label=com.docker.compose.project=practica1-dev
docker network ls --filter label=com.docker.compose.project=practica1-prod
docker volume ls --filter label=com.docker.compose.project=practica1-dev
docker volume ls --filter label=com.docker.compose.project=practica1-prod
```

**Què s'ha de veure:** cap recurs d'aquests projectes a les llistes. Si una ordre de neteja falla o queden recursos, revisa l'error abans de continuar.

## 2. Explicar els fitxers que reconstruiran el sistema

Mostra a l'editor, en aquest ordre:

| Fitxer | Què explicar |
| --- | --- |
| `Dockerfile` | Parteix de Python, instal·la dependències, copia l'aplicació i executa amb un usuari sense privilegis. El comandament per defecte és Gunicorn. |
| `docker-compose.dev.yml` | Dos serveis, Flask amb recàrrega i codi local muntat de només lectura. |
| `docker-compose.prod.yml` | Tres serveis, Gunicorn i Redis; codi incorporat a la imatge. |
| `.env.dev.example` i `.env.prod.example` | Plantilles de configuració; els fitxers privats contenen les credencials. |
| `db/init.sh` | Inicialitza la base quan el volum és buit i crea l'usuari limitat de l'aplicació. |
| `run.sh` | Selecciona el projecte, el Compose i el fitxer de variables correctes. |

No mostris el contingut dels `.env` privats ni un `docker inspect` complet: contenen credencials.

```bash
./run.sh compose dev config --quiet
./run.sh compose prod config --quiet
```

**Què s'ha de veure:** les ordres acaben sense errors. Això valida la configuració, encara no acredita el funcionament dels serveis.

## 3. Construir i arrencar desenvolupament

**Què dir:** «Primer construiré la imatge; després crearé els contenidors. Una imatge és la plantilla i un contenidor és una instància en execució.»

```bash
./run.sh compose dev build --no-cache
./run.sh compose dev up -d --wait --wait-timeout 180
./run.sh status dev
./run.sh db-test dev
```

**Què s'ha de veure:** `web` i `db` saludables; la consulta SQL retorna `connection_ok = 1`.

Obre <http://localhost:5000> i crea la nota `Nota nomes de DEV`.

**Què explicar:** PostgreSQL connectat, Redis no configurat i dades llegides des de PostgreSQL. El port 5000 de l'ordinador apunta al port 5000 del contenidor web.

## 4. Construir i arrencar producció

```bash
./run.sh compose prod build --no-cache
./run.sh compose prod up -d --wait --wait-timeout 180
./run.sh status prod
./run.sh db-test prod
```

Obre <http://localhost:8000> i crea `Nota nomes de PROD`.

**Què s'ha de veure:** tres serveis saludables: `web`, `db` i `cache`. La nota de DEV no apareix a PROD, ni a la inversa.

**Què dir:** «Els dos entorns conviuen amb projectes, xarxes i volums diferents. Producció publica el port 8000 de l'ordinador, però la web continua escoltant al port 5000 dins del contenidor.»

## 5. Explicar les xarxes i el contenidor compartit

```bash
docker network ls --filter label=com.docker.compose.project=practica1-prod
docker network inspect practica1-prod_frontend --format '{{json .Containers}}'
docker network inspect practica1-prod_backend --format '{{json .Containers}}'
```

**Què s'ha de veure:** `frontend` conté `web`; `backend` conté `web`, `db` i `cache`. L'identificador de `web` coincideix a les dues sortides.

```bash
docker inspect practica1-prod-web-1 --format '{{range $name, $net := .NetworkSettings.Networks}}{{printf "%s: %s\n" $name $net.IPAddress}}{{end}}'
docker network inspect practica1-prod_backend --format '{{.Internal}}'
```

**Què dir:** «És un sol contenidor web connectat a dues xarxes, amb una IP per xarxa. No són quatre contenidors. La xarxa backend és interna i les dades no publiquen ports. El navegador accedeix a la web gràcies al port publicat; el nom frontend no publica res per si mateix.»

## 6. Demostrar Redis: primera lectura i reutilització

Tanca les pàgines web per evitar lectures simultànies. Executa les consultes seguides, abans que caduqui la caché (30 segons per defecte).

```bash
./run.sh compose prod exec -T cache redis-cli DEL notes:list
./run.sh cache-stats --once
curl -sS http://localhost:8000/api/notes
curl -sS http://localhost:8000/api/notes
./run.sh cache-stats --once
```

**Què s'ha de veure:** primera lectura amb `source=postgresql`, `cache=miss`; segona amb `source=redis`, `cache=hit`. Els comptadors de Redis també augmenten. `DEL` pot retornar 0 o 1, segons si hi havia una còpia.

**Què dir:** «He eliminat només la còpia de la llista a Redis, no les notes. La primera consulta recupera les dades de PostgreSQL i les desa temporalment a Redis. La segona reutilitza aquesta còpia.»

Per demostrar la invalidació en escriure:

```bash
curl -sS -X POST http://localhost:8000/api/notes -H 'Content-Type: application/json' -d '{"content":"Nota per demostrar invalidacio"}'
curl -sS http://localhost:8000/api/notes
```

**Què s'ha de veure:** la nova nota i una lectura des de PostgreSQL, perquè escriure invalida la còpia anterior.

## 7. Demostrar persistència eliminant el contenidor de la base

**Què dir:** «Ara eliminaré el contenidor de PostgreSQL, però conservaré el volum. Compararé els identificadors i consultaré directament SQL per demostrar que les notes sobreviuen.»

```bash
docker inspect practica1-prod-db-1 --format '{{.Id}}'
./run.sh compose prod stop db
./run.sh compose prod rm -f db
docker volume ls --filter label=com.docker.compose.project=practica1-prod
./run.sh compose prod up -d --wait --wait-timeout 180 db
docker inspect practica1-prod-db-1 --format '{{.Id}}'
./run.sh compose prod exec -T db sh -c 'PGPASSWORD="$DB_PASSWORD" psql -h 127.0.0.1 -U "$DB_USER" -d "$POSTGRES_DB" -c "SELECT id, content FROM notes ORDER BY id;"'
```

**Què s'ha de veure:** identificador nou del contenidor i les notes anteriors presents a SQL. La consulta directa evita confondre persistència amb una còpia a Redis.

**Què dir:** «Les dades viuen al volum. Si hagués eliminat també el volum amb `down --volumes`, les hauria perdut, com a la neteja inicial.»

## 8. Provocar fallades i recuperar els serveis

### Redis deixa de funcionar

```bash
./run.sh compose prod stop cache
curl -i http://localhost:8000/status
curl -sS http://localhost:8000/api/notes
```

**Resultat esperat:** `/status` retorna 503, però la llista funciona des de PostgreSQL amb `cache=unavailable`.

```bash
./run.sh compose prod start cache
./run.sh compose prod up -d --wait --wait-timeout 180
curl -i http://localhost:8000/status
```

**Resultat esperat:** recuperació i HTTP 200.

### PostgreSQL deixa de funcionar

Buida primer la còpia de Redis per evitar que emmascari la fallada de lectura:

```bash
./run.sh compose prod exec -T cache redis-cli DEL notes:list
./run.sh compose prod stop db
curl -i http://localhost:8000/status
curl -i http://localhost:8000/api/notes
```

**Resultat esperat:** HTTP 503 a les dues consultes.

```bash
./run.sh compose prod start db
./run.sh compose prod up -d --wait --wait-timeout 180
curl -i http://localhost:8000/status
```

**Què dir:** «El healthcheck detecta el problema; no reinicia automàticament un contenidor només perquè sigui unhealthy. El seu estat pot trigar més a canviar que la resposta de l'API perquè exigeix diversos errors.»

## 9. Executar les proves i mostrar l'estat final

Amb les pàgines tancades i sense altres consultes simultànies:

```bash
./run.sh unit dev
./run.sh test dev
./run.sh test prod
./run.sh verify dev
./run.sh verify prod
./run.sh status dev
./run.sh status prod
```

**Què explicar:** les unitàries simulen dependències; `test` comprova HTTP real i crea notes; `verify` automatitza comprovacions de persistència i fallades, amb interrupcions temporals. Mostra els resultats reals: si una prova falla, no la presentis com a superada. Pots consultar `./run.sh logs dev` o `./run.sh logs prod` per diagnosticar-la.

**Estat final esperat:** dos contenidors saludables a dev i tres a prod, quatre xarxes i dos volums de dades separats.

## 10. Preparar l'entrega i tancar la presentació

```bash
./run.sh package
```

**Què s'ha de veure:** es genera `dist/practica1.zip`, sense credencials privades.

**Frase final:** «He reconstruït els dos entorns des d'un desplegament buit i he mostrat l'aïllament, les connexions, la caché, la persistència i la recuperació davant de fallades.»

Deixa els serveis en marxa per a les preguntes. Quan acabi la demostració, si els vols retirar conservant les notes:

```bash
./run.sh down dev
./run.sh down prod
```

Aquesta parada conserva els volums, a diferència de la neteja inicial.
