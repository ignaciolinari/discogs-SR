CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT,
    location TEXT,
    joined_date TEXT
);

-- Tabla principal de releases (items)
CREATE TABLE IF NOT EXISTS items (
    item_id INTEGER PRIMARY KEY,
    source_release_id INTEGER,
    title TEXT NOT NULL,
    artist TEXT,
    genre TEXT,
    style TEXT,
    country TEXT,
    released TEXT,
    year INTEGER,
    image_url TEXT,
    format_summary TEXT,
    label_summary TEXT,
    community_have INTEGER DEFAULT 0,
    community_want INTEGER DEFAULT 0,
    community_rating_average REAL DEFAULT 0,
    community_rating_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_items_source_release
ON items(source_release_id);

-- Tabla de sellos
CREATE TABLE IF NOT EXISTS labels (
    label_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    country TEXT,
    profile TEXT
);

CREATE TABLE IF NOT EXISTS item_labels (
    item_id INTEGER NOT NULL,
    label_id INTEGER NOT NULL,
    catalog_number TEXT,
    PRIMARY KEY (item_id, label_id, catalog_number),
    FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE,
    FOREIGN KEY (label_id) REFERENCES labels(label_id) ON DELETE CASCADE
);

-- Tabla de géneros
CREATE TABLE IF NOT EXISTS genres (
    genre_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS item_genres (
    item_id INTEGER NOT NULL,
    genre_id INTEGER NOT NULL,
    PRIMARY KEY (item_id, genre_id),
    FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE,
    FOREIGN KEY (genre_id) REFERENCES genres(genre_id) ON DELETE CASCADE
);

-- Tabla de estilos
CREATE TABLE IF NOT EXISTS styles (
    style_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS item_styles (
    item_id INTEGER NOT NULL,
    style_id INTEGER NOT NULL,
    PRIMARY KEY (item_id, style_id),
    FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE,
    FOREIGN KEY (style_id) REFERENCES styles(style_id) ON DELETE CASCADE
);

-- Tabla de formatos
CREATE TABLE IF NOT EXISTS formats (
    format_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    quantity INTEGER DEFAULT 1,
    description TEXT
);

CREATE TABLE IF NOT EXISTS item_formats (
    item_id INTEGER NOT NULL,
    format_id INTEGER NOT NULL,
    notes TEXT,
    PRIMARY KEY (item_id, format_id),
    FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE,
    FOREIGN KEY (format_id) REFERENCES formats(format_id) ON DELETE CASCADE
);

-- Tabla de interacciones (feedback implícito y opcionalmente rating)
-- Nota sobre rating: NULL indica "no calificado", valores numéricos indican calificación explícita.
-- El sistema normaliza ratings a escala 0-5 donde 0 = "visto pero sin rating" vs NULL = "no visto/no calificado"
CREATE TABLE IF NOT EXISTS interactions (
    interaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    item_id INTEGER NOT NULL,
    interaction_type TEXT,
    rating REAL,
    weight REAL DEFAULT 1.0,
    source TEXT,
    date_added TEXT,
    event_ts TEXT,
    review_text TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (item_id) REFERENCES items(item_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_interactions_user_item_type
ON interactions (user_id, item_id, interaction_type);

-- Tabla de cache de popularidad para el sistema de recomendaciones
-- Esta tabla se reconstruye periódicamente por init_recomendador()
CREATE TABLE IF NOT EXISTS top_items (
    item_id INTEGER PRIMARY KEY,
    cantidad_interacciones INTEGER NOT NULL,
    promedio_rating REAL,
    FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_top_items_rank
ON top_items (promedio_rating DESC, cantidad_interacciones DESC);

-- Tabla de metadatos del sistema de recomendaciones
-- Almacena información como la última actualización de la cache de popularidad
CREATE TABLE IF NOT EXISTS recommender_metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);
