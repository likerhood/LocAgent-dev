import json
import tempfile
import unittest
from pathlib import Path

from evaluation.omnigirl_eval.metrics import aggregate_metrics
from evaluation.omnigirl_eval.multilang_entities import extract_entities_for_lines
from evaluation.omnigirl_eval.parse_predictions import parse_raw_text, prediction_from_row
from evaluation.omnigirl_eval.patch_locations import extract_patch_locations


class OmniGIRLEvalTests(unittest.TestCase):
    def test_extract_patch_locations_maps_added_lines_to_source_anchor(self):
        patch = """diff --git a/src/a.js b/src/a.js
--- a/src/a.js
+++ b/src/a.js
@@ -2,3 +2,4 @@ function foo() {
   const a = 1
-  return a
+  const b = 2
+  return a + b
 }
"""
        locations = extract_patch_locations(patch)

        self.assertEqual(len(locations), 1)
        self.assertEqual(locations[0].file_path, "src/a.js")
        self.assertEqual(locations[0].changed_lines, [3])

    def test_python_entity_extraction_finds_class_method(self):
        source = """class A:
    def foo(self):
        value = 1
        return value
"""
        modules, functions, warnings = extract_entities_for_lines(source, "a.py", [3])

        self.assertEqual([module.name for module in modules], ["A"])
        self.assertEqual([function.name for function in functions], ["A.foo"])
        self.assertEqual(warnings, [])

    def test_java_entity_extraction_finds_method(self):
        source = """class A {
  void foo() {
    int value = 1;
  }
}
"""
        modules, functions, warnings = extract_entities_for_lines(source, "src/A.java", [3])

        self.assertEqual([module.name for module in modules], ["A"])
        self.assertEqual([function.name for function in functions], ["A.foo"])
        self.assertEqual(warnings, [])

    def test_javascript_entity_extraction_finds_function(self):
        source = """function buildRegExps(context) {
  let utility = []
  return utility
}
"""
        modules, functions, warnings = extract_entities_for_lines(
            source,
            "src/lib/defaultExtractor.js",
            [2],
        )

        self.assertEqual([module.name for module in modules], ["buildRegExps"])
        self.assertEqual([function.name for function in functions], ["buildRegExps"])
        self.assertEqual(warnings, [])

    def test_parse_raw_text_extracts_file_class_and_function(self):
        text = """
```
src/cssClassHandler.ts
line: 10-30
class: CssClassHandler
function: handleClassWithBrackets
```
"""
        pred = parse_raw_text(text, known_files=["packages/server/src/cssClassHandler.ts"])

        self.assertEqual(pred.files, ["packages/server/src/cssClassHandler.ts"])
        self.assertEqual(pred.modules, ["packages/server/src/cssClassHandler.ts:CssClassHandler"])
        self.assertEqual(pred.functions, ["packages/server/src/cssClassHandler.ts:CssClassHandler.handleClassWithBrackets"])

    def test_prediction_from_row_combines_parsed_and_raw_predictions(self):
        row = {
            "found_files": ["src/actual.js"],
            "found_modules": [],
            "found_entities": [],
            "raw_output_loc": ["src/raw.js\nfunction: rawFn"],
        }
        pred = prediction_from_row(row, source="combined")

        self.assertEqual(pred.files, ["src/actual.js", "src/raw.js"])
        self.assertEqual(pred.functions, ["src/raw.js:rawFn"])

    def test_aggregate_metrics_scores_ranked_predictions(self):
        gt = {"i1": ["a.py"], "i2": ["b.py"]}
        pred = {"i1": ["x.py", "a.py"], "i2": ["b.py"]}

        result, rows = aggregate_metrics(gt, pred, [1, 3], relaxed=False)

        self.assertEqual(result["evaluated_instances"], 2)
        self.assertEqual(result["Acc@1"], 0.5)
        self.assertEqual(result["Recall@3"], 1.0)
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
