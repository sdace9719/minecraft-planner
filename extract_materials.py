import nbtlib
import json
import sys
import re
from collections import Counter

def read_varint(data, index):
    """Read a VarInt from a byte array."""
    value = 0
    shift = 0
    while True:
        b = data[index]
        value |= (b & 0x7F) << shift
        index += 1
        if not (b & 0x80):
            break
        shift += 7
    return value, index

def extract_materials(schem_path, output_path):
    print(f"Loading Sponge schematic: {schem_path}")
    nbt = nbtlib.load(schem_path)
    root = nbt.root
    
    if 'Palette' not in root or 'BlockData' not in root:
        print("Error: Not a valid Sponge schematic (missing Palette or BlockData)")
        sys.exit(1)
        
    palette = root['Palette']
    # Inverse map to get name from ID
    inv_palette = {int(v): k for k, v in palette.items()}
    
    block_data = bytes(root['BlockData'])
    
    # Extract all indices from BlockData
    indices = []
    i = 0
    while i < len(block_data):
        idx, i = read_varint(block_data, i)
        indices.append(idx)
        
    counts = Counter(indices)
    
    materials = {}
    for idx, count in counts.items():
        full_name = inv_palette.get(idx)
        if not full_name:
            continue
            
        # Strip block states (e.g. minecraft:oak_stairs[facing=north] -> minecraft:oak_stairs)
        clean_name = re.split(r'[\[]', full_name)[0]
        
        # Strip namespace (e.g. minecraft:stone -> stone)
        if ":" in clean_name:
            clean_name = clean_name.split(":")[1]
            
        if clean_name in ["air", "cave_air", "void_air", "water", "lava"]:
            continue
            
        materials[clean_name] = materials.get(clean_name, 0) + count
        
    # Convert to the list format expected by generate_dag.py
    output_list = [{"name": name, "quantity": qty} for name, qty in materials.items()]
    
    with open(output_path, "w") as f:
        json.dump(output_list, f, indent=2)
        
    print(f"Extracted {len(output_list)} unique materials to {output_path}")
    for item in output_list:
        print(f"  - {item['name']}: {item['quantity']}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 extract_materials.py <input.schem> <output.json>")
        sys.exit(1)
    extract_materials(sys.argv[1], sys.argv[2])
