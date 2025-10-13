from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from typing import Any, cast

# Configuramos el path de la base de datos antes de importar recomendar
base_dir = Path(__file__).resolve().parents[1]
if str(base_dir) not in sys.path:
    sys.path.append(str(base_dir))

recomendar = cast(Any, import_module("sr_discogs.recomendar"))


class TestNormalizeRating(unittest.TestCase):
    """Tests para la función normalize_rating que maneja la conversión de ratings."""

    def test_normalize_none(self):
        """None debe convertirse a 0."""
        self.assertEqual(recomendar.normalize_rating(None), 0)

    def test_normalize_zero(self):
        """0 debe mantenerse como 0."""
        self.assertEqual(recomendar.normalize_rating(0), 0)

    def test_normalize_negative(self):
        """Valores negativos deben convertirse a 0."""
        self.assertEqual(recomendar.normalize_rating(-1), 0)
        self.assertEqual(recomendar.normalize_rating(-5), 0)

    def test_normalize_valid_integers(self):
        """Valores enteros válidos (1-5) deben mantenerse."""
        self.assertEqual(recomendar.normalize_rating(1), 1)
        self.assertEqual(recomendar.normalize_rating(3), 3)
        self.assertEqual(recomendar.normalize_rating(5), 5)

    def test_normalize_floats(self):
        """Floats deben convertirse a enteros."""
        self.assertEqual(recomendar.normalize_rating(3.7), 3)
        self.assertEqual(recomendar.normalize_rating(4.2), 4)

    def test_normalize_strings(self):
        """Strings numéricos deben convertirse correctamente."""
        self.assertEqual(recomendar.normalize_rating("3"), 3)
        self.assertEqual(recomendar.normalize_rating("4.5"), 4)

    def test_normalize_above_max(self):
        """Valores > 5 deben limitarse a 5."""
        self.assertEqual(recomendar.normalize_rating(6), 5)
        self.assertEqual(recomendar.normalize_rating(10), 5)
        self.assertEqual(recomendar.normalize_rating(100), 5)

    def test_normalize_invalid_strings(self):
        """Strings no numéricos deben devolver 0."""
        self.assertEqual(recomendar.normalize_rating("invalid"), 0)
        self.assertEqual(recomendar.normalize_rating("abc"), 0)


class TestResolveItemId(unittest.TestCase):
    """Tests para la función _resolve_item_id que normaliza a IDs canónicos."""

    def setUp(self):
        """Configura una base de datos temporal para los tests."""
        self.temp_db = tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False)
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()

        # Guardamos el path original
        self.original_db_path = recomendar.DATABASE_FILE
        # Usamos la base temporal
        recomendar.DATABASE_FILE = self.temp_db_path

        # Limpiamos el cache LRU
        recomendar._resolve_item_id_cached.cache_clear()

        # Creamos el esquema básico
        with sqlite3.connect(self.temp_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE items (
                    item_id INTEGER PRIMARY KEY,
                    source_release_id INTEGER,
                    title TEXT NOT NULL,
                    artist TEXT
                )
            """
            )

            # Caso 1: Un master (ID 1000) con un release asociado (ID 5000)
            cursor.execute(
                "INSERT INTO items (item_id, source_release_id, title, artist) VALUES (?, ?, ?, ?)",
                (1000, 5000, "Master Album", "Artist A"),
            )

            # Caso 2: Un release sin master (ID 6000 = source_release_id 6000)
            cursor.execute(
                "INSERT INTO items (item_id, source_release_id, title, artist) VALUES (?, ?, ?, ?)",
                (6000, 6000, "Release Only Album", "Artist B"),
            )

            # Caso 3: Otro master (ID 2000) con release (ID 7000)
            cursor.execute(
                "INSERT INTO items (item_id, source_release_id, title, artist) VALUES (?, ?, ?, ?)",
                (2000, 7000, "Another Master", "Artist C"),
            )

            conn.commit()

    def tearDown(self):
        """Limpia la base de datos temporal."""
        recomendar.DATABASE_FILE = self.original_db_path
        recomendar._resolve_item_id_cached.cache_clear()
        Path(self.temp_db_path).unlink(missing_ok=True)

    def test_resolve_by_item_id(self):
        """Debe encontrar el item por item_id directamente."""
        result = recomendar._resolve_item_id(1000)
        self.assertEqual(result, 1000)

        result = recomendar._resolve_item_id(6000)
        self.assertEqual(result, 6000)

    def test_resolve_by_source_release_id(self):
        """Debe encontrar el master cuando se busca por source_release_id."""
        # Buscando release 5000 debe devolver el master 1000
        result = recomendar._resolve_item_id(5000)
        self.assertEqual(result, 1000)

        # Buscando release 7000 debe devolver el master 2000
        result = recomendar._resolve_item_id(7000)
        self.assertEqual(result, 2000)

    def test_resolve_nonexistent_id(self):
        """Debe devolver None para IDs que no existen."""
        result = recomendar._resolve_item_id(99999)
        self.assertIsNone(result)

    def test_resolve_none_input(self):
        """Debe manejar None como entrada."""
        result = recomendar._resolve_item_id(None)
        self.assertIsNone(result)

    def test_resolve_invalid_input(self):
        """Debe manejar entradas inválidas."""
        result = recomendar._resolve_item_id("not_a_number")
        self.assertIsNone(result)

    def test_resolve_uses_cache(self):
        """Debe usar el cache LRU eficientemente."""
        # Primera llamada
        result1 = recomendar._resolve_item_id(1000)
        # Segunda llamada (debe venir del cache)
        result2 = recomendar._resolve_item_id(1000)

        self.assertEqual(result1, result2)

        # Verificamos que el cache tiene entradas
        cache_info = recomendar._resolve_item_id_cached.cache_info()
        self.assertGreater(cache_info.hits + cache_info.misses, 0)

    def test_resolve_item_ids_batch(self):
        """Debe resolver múltiples IDs correctamente."""
        ids = [1000, 5000, 6000, 99999, None]
        results = recomendar._resolve_item_ids(ids)

        # Esperamos: 1000 (directo), 1000 (de 5000), 6000 (directo)
        # 1000 no debe duplicarse, 99999 y None se ignoran
        self.assertIn(1000, results)
        self.assertIn(6000, results)
        self.assertEqual(results.count(1000), 1)  # Sin duplicados
        self.assertNotIn(99999, results)

    def test_resolve_item_ids_empty_list(self):
        """Debe manejar listas vacías."""
        results = recomendar._resolve_item_ids([])
        self.assertEqual(results, [])

    def test_resolve_item_ids_none_input(self):
        """Debe manejar None como entrada."""
        results = recomendar._resolve_item_ids(None)
        self.assertEqual(results, [])


class TestDatabaseOperations(unittest.TestCase):
    """Tests para operaciones básicas de base de datos."""

    def setUp(self):
        """Configura una base de datos temporal."""
        self.temp_db = tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False)
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()

        self.original_db_path = recomendar.DATABASE_FILE
        recomendar.DATABASE_FILE = self.temp_db_path

        # Creamos esquema completo
        with sqlite3.connect(self.temp_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT
                )
            """
            )
            cursor.execute(
                """
                CREATE TABLE items (
                    item_id INTEGER PRIMARY KEY,
                    source_release_id INTEGER,
                    title TEXT NOT NULL,
                    artist TEXT
                )
            """
            )
            cursor.execute(
                """
                CREATE TABLE interactions (
                    interaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    item_id INTEGER NOT NULL,
                    interaction_type TEXT,
                    rating REAL,
                    date_added TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (item_id) REFERENCES items(item_id)
                )
            """
            )
            cursor.execute(
                """
                CREATE UNIQUE INDEX idx_interactions_user_item_type
                ON interactions (user_id, item_id, interaction_type)
            """
            )
            conn.commit()

    def tearDown(self):
        """Limpia la base de datos temporal."""
        recomendar.DATABASE_FILE = self.original_db_path
        Path(self.temp_db_path).unlink(missing_ok=True)

    def test_crear_usuario(self):
        """Debe crear un usuario correctamente."""
        recomendar.crear_usuario("test_user")
        self.assertTrue(recomendar.usuario_existe("test_user"))

    def test_crear_usuario_duplicado(self):
        """No debe fallar al crear usuario duplicado."""
        recomendar.crear_usuario("test_user")
        recomendar.crear_usuario("test_user")  # No debe lanzar error
        self.assertTrue(recomendar.usuario_existe("test_user"))

    def test_usuario_existe_false(self):
        """Debe devolver False para usuarios inexistentes."""
        self.assertFalse(recomendar.usuario_existe("nonexistent_user"))

    def test_usuario_existe_empty_string(self):
        """Debe manejar strings vacíos."""
        self.assertFalse(recomendar.usuario_existe(""))

    def test_insertar_interacciones(self):
        """Debe insertar interacciones correctamente."""
        recomendar.crear_usuario("user1")

        # Insertamos un item
        with sqlite3.connect(self.temp_db_path) as conn:
            conn.execute(
                "INSERT INTO items (item_id, source_release_id, title) VALUES (?, ?, ?)",
                (1000, 1000, "Test Album"),
            )
            conn.commit()

        # Insertamos interacción
        recomendar.insertar_interacciones(1000, "user1", 5)

        # Verificamos
        rows = recomendar.sql_select(
            "SELECT rating FROM interactions WHERE user_id = ? AND item_id = ?",
            ["user1", 1000],
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["rating"], 5)

    def test_obtener_disco(self):
        """Debe obtener información de un disco."""
        # Insertamos un item
        with sqlite3.connect(self.temp_db_path) as conn:
            conn.execute(
                "INSERT INTO items (item_id, source_release_id, title, artist) VALUES (?, ?, ?, ?)",
                (1000, 1000, "Test Album", "Test Artist"),
            )
            conn.commit()

        disco = recomendar.obtener_disco(1000)
        self.assertIsNotNone(disco)
        assert disco is not None
        self.assertEqual(disco["title"], "Test Album")
        self.assertEqual(disco["artist"], "Test Artist")

    def test_obtener_disco_nonexistent(self):
        """Debe devolver None para disco inexistente."""
        disco = recomendar.obtener_disco(99999)
        self.assertIsNone(disco)


if __name__ == "__main__":
    unittest.main()
