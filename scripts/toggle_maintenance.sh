#!/bin/bash

# Script to toggle maintenance mode for KNA-RNAS Library documentation

DOCS_DIR="/home/jake/repo/KNA-RNAS-Library/docs/source"
INDEX_FILE="$DOCS_DIR/index.rst"
ACTIVE_BACKUP="$DOCS_DIR/index.rst.active"
MAINTENANCE_FILE="$DOCS_DIR/maintenance.rst"

if [ -f "$ACTIVE_BACKUP" ]; then
    echo "Current status: MAINTENANCE MODE"
    echo "Deactivating maintenance mode..."
    mv "$ACTIVE_BACKUP" "$INDEX_FILE"
    echo "Status: NORMAL MODE activated."
else
    echo "Current status: NORMAL MODE"
    if [ ! -f "$MAINTENANCE_FILE" ]; then
        echo "Error: $MAINTENANCE_FILE not found!"
        exit 1
    fi
    echo "Activating maintenance mode..."
    mv "$INDEX_FILE" "$ACTIVE_BACKUP"
    cp "$MAINTENANCE_FILE" "$INDEX_FILE"
    echo "Status: MAINTENANCE MODE activated."
fi
