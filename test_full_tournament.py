#!/usr/bin/env python3
"""Script to test full tournament flow from scratch."""

import sys
sys.path.insert(0, 'src')

# Step 1: Import players using CLI
print("=" * 60)
print("STEP 1: Importando jugadores desde CSV...")
print("=" * 60)
import subprocess
result = subprocess.run([
    sys.executable, "-m", "ettem.cli",
    "import-players",
    "--csv", "data/samples/players_32.csv",
    "--category", "U13"
], capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print(f"ERROR: {result.stderr}")
    sys.exit(1)

# Step 2: Create groups using CLI
print("\n" + "=" * 60)
print("STEP 2: Creando grupos con snake seeding...")
print("=" * 60)
result = subprocess.run([
    sys.executable, "-m", "ettem.cli",
    "build-groups",
    "--config", "config/sample_config.yaml",
    "--category", "U13"
], capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print(f"ERROR: {result.stderr}")
    sys.exit(1)

# Step 3: Fill group results using fill_results.py
print("\n" + "=" * 60)
print("STEP 3: Llenando resultados de grupos...")
print("=" * 60)
result = subprocess.run([sys.executable, "fill_results.py"], capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print(f"ERROR: {result.stderr}")
    sys.exit(1)

# Step 4: Calculate standings
print("\n" + "=" * 60)
print("STEP 4: Calculando standings...")
print("=" * 60)
result = subprocess.run([
    sys.executable, "-m", "ettem.cli",
    "compute-standings",
    "--category", "U13"
], capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print(f"ERROR: {result.stderr}")
    sys.exit(1)

# Step 5: Generate bracket
print("\n" + "=" * 60)
print("STEP 5: Generando bracket...")
print("=" * 60)
result = subprocess.run([
    sys.executable, "-m", "ettem.cli",
    "build-bracket",
    "--category", "U13",
    "--config", "config/sample_config.yaml"
], capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print(f"ERROR: {result.stderr}")
    sys.exit(1)

# Step 5.5: Create bracket matches from slots
print("\n" + "=" * 60)
print("STEP 5.5: Creando partidos del bracket...")
print("=" * 60)
result = subprocess.run([sys.executable, "create_bracket_matches.py"], capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print(f"ERROR: {result.stderr}")
    sys.exit(1)

# Step 6: Fill bracket results
print("\n" + "=" * 60)
print("STEP 6: Llenando resultados de bracket...")
print("=" * 60)
result = subprocess.run([sys.executable, "fill_bracket_results.py"], capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print(f"ERROR: {result.stderr}")
    sys.exit(1)

print("\n" + "=" * 60)
print("[OK] TESTING COMPLETO!")
print("=" * 60)
print("\nPuedes revisar:")
print("  - Dashboard: http://127.0.0.1:8000/")
print("  - Categoría U13: http://127.0.0.1:8000/category/U13")
print("  - Resultados Finales: http://127.0.0.1:8000/category/U13/results")
print("  - Bracket Visual: http://127.0.0.1:8000/bracket/U13")
