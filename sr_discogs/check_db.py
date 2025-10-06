import sqlite3

conn = sqlite3.connect("datos/discogs.db")
cursor = conn.cursor()

print("Tablas en la base de datos:")
for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'"):
    print(row[0])

print("\nEstructura de la tabla users:")
for row in cursor.execute("PRAGMA table_info(users)"):
    print(row)

print("\nEstructura de la tabla items:")
for row in cursor.execute("PRAGMA table_info(items)"):
    print(row)

print("\nEstructura de la tabla interactions:")
for row in cursor.execute("PRAGMA table_info(interactions)"):
    print(row)

print("\nPrimeros 5 registros de users:")
for row in cursor.execute("SELECT * FROM users LIMIT 5"):
    print(row)

print("\nPrimeros 5 registros de items:")
for row in cursor.execute("SELECT * FROM items LIMIT 5"):
    print(row)

print("\nPrimeros 5 registros de interactions:")
for row in cursor.execute("SELECT * FROM interactions LIMIT 5"):
    print(row)

conn.close()
