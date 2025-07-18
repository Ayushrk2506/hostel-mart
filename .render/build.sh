#!/bin/bash
mkdir -p instance
if [ ! -f instance/database.db ]; then
    echo "Creating SQLite database..."
    sqlite3 instance/database.db < schema.sql  # You must have schema.sql for this to work
fi
