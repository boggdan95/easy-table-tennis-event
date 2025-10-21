#!/bin/bash
# ========================================================================
# Easy Table Tennis Event Manager - Test Script (Linux/Mac)
# ========================================================================
# This script tests the complete V1 functionality

set -e  # Exit on error

echo ""
echo "============================================================"
echo "  Easy Table Tennis Event Manager - V1 Test Suite"
echo "============================================================"
echo ""

# Change to project directory
cd "$(dirname "$0")"

echo "[1/7] Cleaning previous test data..."
rm -rf .ettem out
mkdir -p out
echo "   ✓ Cleaned"

echo ""
echo "[2/7] Importing players (Spanish - default)..."
ettem import-players --csv data/samples/players.csv --category U13
echo "   ✓ Players imported"

echo ""
echo "[3/7] Building groups..."
ettem build-groups --config config/sample_config.yaml --out out/
echo "   ✓ Groups created"

echo ""
echo "[4/7] Computing standings (initial - before matches)..."
ettem compute-standings --out out/
echo "   ✓ Standings computed"

echo ""
echo "[5/7] Building bracket..."
ettem build-bracket --out out/
echo "   ✓ Bracket created"

echo ""
echo "[6/7] Exporting data to CSV..."
ettem export --what groups --format csv --out out/
ettem export --what standings --format csv --out out/
ettem export --what bracket --format csv --out out/
echo "   ✓ Data exported to out/ directory"

echo ""
echo "[7/7] Testing i18n (English)..."
ettem --lang en --help > /dev/null 2>&1
echo "   ✓ i18n working"

echo ""
echo "============================================================"
echo "  ✓ All CLI tests passed!"
echo "============================================================"
echo ""
echo "Generated files:"
ls -1 out/*.csv 2>/dev/null || echo "No CSV files found"
echo ""
echo "Database created at: .ettem/ettem.sqlite"
echo ""
echo "============================================================"
echo "  Starting Web Panel..."
echo "============================================================"
echo ""
echo "The web panel will open at: http://127.0.0.1:8000"
echo ""
echo "In the web panel you can:"
echo "  1. View groups and players"
echo "  2. Enter match results"
echo "  3. View standings"
echo "  4. View knockout bracket"
echo ""
echo "Press Ctrl+C to stop the server when done"
echo ""
read -p "Press Enter to start the server..."
echo ""
echo "Starting server..."
ettem open-panel
