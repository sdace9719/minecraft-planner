import json
import os
import sys

class BlueprintValidator:
    def __init__(self, filepath):
        self.filepath = filepath
        self.errors = []
        self.warnings = []

    def load_json(self):
        try:
            with open(self.filepath, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Failed to read JSON: {e}")
            sys.exit(1)

    def validate(self):
        print("Parsing blueprints.json...")
        data = self.load_json()
        blueprints = data.get("blueprints", {})

        for target_item, steps in blueprints.items():
            acquired_items = set()
            byproducts = set()

            for i, step in enumerate(steps):
                step_num = i + 1
                op = step.get("operation")
                prereqs = step.get("prerequisites", [])
                ingredients = step.get("ingredients", {})
                output_item = step.get("item")

                # RULE 1: The Root Node Rule (Bootstrap Paradox)
                # If a node requires no prerequisites, it cannot demand a high-tier tool.
                if not prereqs and op in ["mine", "gather"]:
                    harvest = step.get("harvest", {})
                    min_tier = harvest.get("min_tier")
                    if min_tier in ["stone", "iron", "diamond", "netherite"]:
                        self.errors.append(
                            f"[{target_item}] Step {step_num}: Bootstrap Paradox! '{output_item}' has no prereqs but requires a '{min_tier}' tool."
                        )

                # RULE 2: Chronological Integrity (No Time Travel)
                # The bot must acquire an item earlier in the array before it can use it as a prerequisite.
                for prereq in prereqs:
                    if prereq not in acquired_items:
                        self.errors.append(
                            f"[{target_item}] Step {step_num}: Chronological Error! Requires '{prereq}' before it was generated in this chain."
                        )

                # RULE 3: Ingredient/Prerequisite Parity
                # The logical graph (prereqs) must perfectly match the math (ingredients).
                if op in ["craft", "smelt"]:
                    ingredient_keys = set(ingredients.keys())
                    prereq_set = set(prereqs)
                    station = step.get("station")
                    if station in prereq_set and station not in ingredient_keys:
                        prereq_set.remove(station)
                    
                    if ingredient_keys != prereq_set:
                        missing_in_prereqs = ingredient_keys - prereq_set
                        missing_in_ingredients = prereq_set - ingredient_keys
                        if missing_in_prereqs:
                            self.errors.append(f"[{target_item}] Step {step_num}: Parity Mismatch! {missing_in_prereqs} found in ingredients but missing from prerequisites.")
                        if missing_in_ingredients:
                            self.errors.append(f"[{target_item}] Step {step_num}: Parity Mismatch! {missing_in_ingredients} found in prerequisites but missing from ingredients.")

                # RULE 4: Station Hierarchy Check (Hidden Dependencies)
                # If a recipe needs a station, the bot must have built that station.
                station = step.get("station")
                if station and station not in ["player", "none"]:
                    if station not in acquired_items:
                        self.warnings.append(
                            f"[{target_item}] Step {step_num}: Hidden Dependency! Requires station '{station}', but it was never explicitly crafted in this array."
                        )

                # Add the output to the bot's known inventory for this chain
                acquired_items.add(output_item)

                # Track by-products to prevent false-positives on Chronological checks
                junk = step.get("junk/by-product")
                if junk:
                    if isinstance(junk, list):
                        for j in junk:
                            acquired_items.add(j.get("item"))
                    elif isinstance(junk, dict):
                        acquired_items.add(junk.get("item"))

        self.print_report()

    def print_report(self):
        print("\n" + "="*50)
        print("🛠️  BLUEPRINT VALIDATION REPORT")
        print("="*50)
        print(f"File Scanned: {self.filepath}")
        print(f"Fatal Errors: {len(self.errors)}")
        print(f"Warnings:     {len(self.warnings)}")
        print("-" * 50)

        if self.errors:
            print("\n🚨 FATAL ERRORS (Will Crash the Compiler):")
            for e in self.errors:
                print(f"  ❌ {e}")

        if self.warnings:
            print("\n⚠️  WARNINGS (Might Cause Graph Logic Flaws):")
            # Cap warnings at 50 to prevent terminal flooding
            for w in self.warnings[:50]:
                print(f"  ⚠️ {w}")
            if len(self.warnings) > 50:
                print(f"  ... plus {len(self.warnings) - 50} more warnings hidden.")
        
        if not self.errors and not self.warnings:
            print("\n✅ SUCCESS: Blueprints are mathematically and chronologically flawless!")

if __name__ == "__main__":
    # Assumes the script is run from the project root
    target_path = os.path.join("constants", "blueprints.json")
    
    if not os.path.exists(target_path):
        print(f"❌ Error: Could not locate {target_path}. Make sure you are in the project root.")
    else:
        validator = BlueprintValidator(target_path)
        validator.validate()