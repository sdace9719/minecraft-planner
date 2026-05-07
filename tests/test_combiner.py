import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from planner.combiner import CombinerError, combine_tasks


class CombinerTests(unittest.TestCase):
    def test_workstation_cap_for_crafting_table(self):
        tasks = [
            {
                "id": "CRAFT:crafting_table",
                "name": "crafting_table",
                "quantity": 2,
                "dependencies": ["dep_a"],
                "operation_type": "craft",
            },
            {
                "id": "CRAFT:crafting_table",
                "name": "crafting_table",
                "quantity": 4,
                "dependencies": ["dep_b"],
                "operation_type": "craft",
            },
            {
                "id": "CRAFT:crafting_table",
                "name": "crafting_table",
                "quantity": 1,
                "dependencies": ["dep_a", "dep_c"],
                "operation_type": "craft",
            },
        ]

        merged = combine_tasks(tasks)
        self.assertEqual(len(merged), 1)
        task = merged[0]
        self.assertEqual(task["id"], "CRAFT:crafting_table")
        self.assertEqual(task["name"], "crafting_table")
        self.assertEqual(task["quantity"], 1)
        self.assertEqual(task["operation_type"], "craft")
        self.assertEqual(task["dependencies"], ["dep_a", "dep_b", "dep_c"])

    def test_non_workstation_quantities_sum(self):
        tasks = [
            {
                "id": "CRAFT:stick",
                "name": "stick",
                "quantity": 3,
                "dependencies": ["dep_a"],
                "operation_type": "craft",
            },
            {
                "id": "CRAFT:stick",
                "name": "stick",
                "quantity": 5,
                "dependencies": ["dep_b"],
                "operation_type": "craft",
            },
        ]
        merged = combine_tasks(tasks)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["quantity"], 8)
        self.assertEqual(merged[0]["dependencies"], ["dep_a", "dep_b"])

    def test_dependency_deduplication(self):
        tasks = [
            {
                "id": "SMELT:stone",
                "name": "stone",
                "quantity": 10,
                "dependencies": ["x", "y", "x"],
                "operation_type": "smelt",
            },
            {
                "id": "SMELT:stone",
                "name": "stone",
                "quantity": 4,
                "dependencies": ["y", "z"],
                "operation_type": "smelt",
            },
        ]
        merged = combine_tasks(tasks)
        self.assertEqual(merged[0]["dependencies"], ["x", "y", "z"])

    def test_validation_errors(self):
        with self.assertRaises(CombinerError):
            combine_tasks([{"id": "x"}])
        with self.assertRaises(CombinerError):
            combine_tasks(
                [
                    {
                        "id": "x",
                        "name": "stick",
                        "quantity": -1,
                        "dependencies": [],
                        "operation_type": "craft",
                    }
                ]
            )
        with self.assertRaises(CombinerError):
            combine_tasks(
                [
                    {
                        "id": "x",
                        "name": "stick",
                        "quantity": 1,
                        "dependencies": "bad",
                        "operation_type": "craft",
                    }
                ]
            )

    def test_conflicting_name_or_operation_raises(self):
        with self.assertRaises(CombinerError):
            combine_tasks(
                [
                    {
                        "id": "same",
                        "name": "stick",
                        "quantity": 1,
                        "dependencies": [],
                        "operation_type": "craft",
                    },
                    {
                        "id": "same",
                        "name": "oak_planks",
                        "quantity": 1,
                        "dependencies": [],
                        "operation_type": "craft",
                    },
                ]
            )
        with self.assertRaises(CombinerError):
            combine_tasks(
                [
                    {
                        "id": "same",
                        "name": "stick",
                        "quantity": 1,
                        "dependencies": [],
                        "operation_type": "craft",
                    },
                    {
                        "id": "same",
                        "name": "stick",
                        "quantity": 1,
                        "dependencies": [],
                        "operation_type": "smelt",
                    },
                ]
            )


if __name__ == "__main__":
    unittest.main()
