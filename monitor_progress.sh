#!/bin/bash
# Monitor del progreso del scraper

while true; do
    clear
    echo "================================================"
    echo "  MONITOREO DEL SCRAPER - $(date '+%H:%M:%S')"
    echo "================================================"
    echo ""

    # Check if scraper is running
    if pgrep -f "run_scraper.py" > /dev/null; then
        echo "✓ Scraper está CORRIENDO"
    else
        echo "✗ Scraper NO está corriendo"
    fi

    echo ""
    python3 -c "
import sqlite3
from settings import get_database_path
conn = sqlite3.connect(get_database_path())
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM users')
users = cursor.fetchone()[0]
cursor.execute('SELECT COUNT(*) FROM interactions')
interactions = cursor.fetchone()[0]
cursor.execute('SELECT COUNT(*) FROM items')
items = cursor.fetchone()[0]
print(f'Items:         {items:,}')
print(f'Usuarios:      {users:,}')
print(f'Interacciones: {interactions:,}')
if users > 0:
    print(f'Ratio:         {interactions/users:.1f} interacciones/usuario')
conn.close()
"
    echo ""
    echo "Presiona Ctrl+C para salir"
    echo "Actualizando en 5 segundos..."
    sleep 5
done
