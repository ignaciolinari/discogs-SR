import sqlite3

import settings

# Conectarse a la base que ya creaste
con = sqlite3.connect(str(settings.get_database_path()))
cursor = con.cursor()

# Insertar usuario de prueba
cursor.execute(
    """
INSERT OR IGNORE INTO users (user_id, username, location, joined_date)
VALUES (?, ?, ?, ?)
""",
    ("ignacio001", "ignacio", "Argentina", "2025-09-15"),
)

# Insertar ítem de prueba
cursor.execute(
    """
INSERT OR IGNORE INTO items (item_id, title, artist, year, genre, style, image_url)
VALUES (?, ?, ?, ?, ?, ?, ?)
""",
    (
        12345,
        "Kind of Blue",
        "Miles Davis",
        1959,
        "Jazz",
        "Modal Jazz",
        "https://example.com/kind_of_blue.jpg",
    ),
)

# Insertar interacción de prueba
cursor.execute(
    """
INSERT INTO interactions (user_id, item_id, interaction_type, rating, date_added)
VALUES (?, ?, ?, ?, ?)
""",
    ("ignacio001", 12345, "collection", 5, "2025-09-15"),
)

# Confirmar cambios
con.commit()
con.close()

print("Datos de prueba insertados correctamente ")
