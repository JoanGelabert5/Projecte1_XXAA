import json
import os

import psycopg
import redis
from flask import Flask, jsonify, render_template, request
from psycopg.rows import dict_row
from redis.backoff import NoBackoff
from redis.retry import Retry


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        APP_ENV=os.getenv("APP_ENV", "dev"),
        DB_HOST=os.getenv("DB_HOST", "db"),
        DB_PORT=int(os.getenv("DB_PORT", "5432")),
        DB_NAME=os.getenv("DB_NAME", "notes"),
        DB_USER=os.getenv("DB_USER", "notes_app"),
        DB_PASSWORD=os.getenv("DB_PASSWORD", ""),
        CACHE_ENABLED=os.getenv("CACHE_ENABLED", "false").lower() == "true",
        REDIS_HOST=os.getenv("REDIS_HOST", "cache"),
        REDIS_PASSWORD=os.getenv("REDIS_PASSWORD", ""),
        CACHE_TTL=int(os.getenv("CACHE_TTL", "30")),
        MAX_CONTENT_LENGTH=8192,
    )
    if test_config:
        app.config.update(test_config)
    if app.config["CACHE_TTL"] <= 0:
        raise ValueError("CACHE_TTL debe ser mayor que cero")

    cache = None
    if app.config["CACHE_ENABLED"]:
        cache = redis.Redis(
            host=app.config["REDIS_HOST"],
            password=app.config["REDIS_PASSWORD"],
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
            retry_on_timeout=False,
            retry=Retry(NoBackoff(), 0),
        )

    def connect_db():
        return psycopg.connect(
            host=app.config["DB_HOST"],
            port=app.config["DB_PORT"],
            dbname=app.config["DB_NAME"],
            user=app.config["DB_USER"],
            password=app.config["DB_PASSWORD"],
            connect_timeout=2,
            options="-c statement_timeout=2000",
            row_factory=dict_row,
        )

    @app.after_request
    def response_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
        )
        return response

    @app.get("/")
    def index():
        return render_template("index.html", environment=app.config["APP_ENV"])

    @app.get("/status")
    def status():
        # Nunca consultar este estado desde la caché: debe detectar fallos reales.
        database = "disconnected"
        try:
            with connect_db() as connection:
                connection.execute("SELECT 1 FROM notes LIMIT 1")
            database = "connected"
        except psycopg.Error:
            pass

        cache_status = "not_configured"
        if cache is not None:
            try:
                cache_status = "connected" if cache.ping() else "disconnected"
            except redis.RedisError:
                cache_status = "disconnected"
        healthy = database == "connected" and cache_status != "disconnected"
        return jsonify(
            status="healthy" if healthy else "unhealthy",
            environment=app.config["APP_ENV"],
            services={"database": database, "cache": cache_status},
        ), 200 if healthy else 503

    @app.get("/api/notes")
    def list_notes():
        cache_available = cache is not None
        if cache is not None:
            try:
                saved = cache.get("notes:list")
                if saved is not None:
                    return jsonify(notes=json.loads(saved), source="redis", cache="hit")
            except (redis.RedisError, ValueError):
                cache_available = False

        try:
            with connect_db() as connection:
                rows = connection.execute(
                    "SELECT id, content, created_at FROM notes ORDER BY id DESC LIMIT 100"
                ).fetchall()
            notes = [dict(row, created_at=row["created_at"].isoformat()) for row in rows]
        except psycopg.Error:
            return jsonify(error="No se pueden consultar las notas: PostgreSQL no responde."), 503

        cache_state = "disabled" if cache is None else "unavailable"
        if cache_available:
            try:
                cache.setex("notes:list", app.config["CACHE_TTL"], json.dumps(notes))
                cache_state = "miss"
            except redis.RedisError:
                pass
        return jsonify(notes=notes, source="postgresql", cache=cache_state)

    @app.post("/api/notes")
    def create_note():
        payload = request.get_json(silent=True)
        content = payload.get("content") if isinstance(payload, dict) else None
        if not isinstance(content, str) or not 1 <= len(content.strip()) <= 500:
            return jsonify(error="Escribe una nota de entre 1 y 500 caracteres."), 400
        try:
            with connect_db() as connection:
                note = connection.execute(
                    "INSERT INTO notes (content) VALUES (%s) RETURNING id, content, created_at",
                    (content.strip(),),
                ).fetchone()
            # Salir del contexto confirma la transacción antes de invalidar la caché.
        except psycopg.Error:
            return jsonify(error="No se ha guardado la nota: PostgreSQL no responde."), 503
        warning = None
        if cache is not None:
            try:
                cache.delete("notes:list")
            except redis.RedisError:
                warning = "Nota guardada. No se pudo invalidar la caché; expirará según su TTL."
        return jsonify(
            note=dict(note, created_at=note["created_at"].isoformat()), warning=warning
        ), 201

    return app
