"""Fixture transport checks independent of protocol implementation behavior."""
import json
import tempfile
import unittest
from pathlib import Path
from . import extended_corpus as corpus


def example():
    return {"id": "edit-1", "rule": "paper-doll/v3#editing-operations",
            "subject": "paper-doll/v3", "operation": "removeElement",
            "input": {"args": [{"root": "root", "vessels": {"root": {}}}, "root", 0]},
            "expected": {"outcome": "error"}}


class ExtendedCorpusTests(unittest.TestCase):
    def write(self, directory, cases, name="case.json"):
        path = Path(directory) / name
        path.write_text(json.dumps({"corpus": "paper-family-conformance/v2", "cases": cases}))
        return path

    def test_known_case_loads(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(corpus.load_corpus(self.write(directory, [example()]))["cases"], [example()])

    def test_envelope_and_domains_are_strict(self):
        alterations = [{"subject": "paperfold/v1"}, {"operation": "eval"}, {"rule": "wrong"},
                       {"id": "bad@id"}, {"input": {"args": {}}}, {"extra": True},
                       {"expected": {"outcome": "invalid", "includesErrorPaths": []}}]
        with tempfile.TemporaryDirectory() as directory:
            for change in alterations:
                with self.subTest(change=change), self.assertRaises(ValueError):
                    corpus.load_corpus(self.write(directory, [example() | change]))

    def test_duplicate_keys_and_nonfinite_literals_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(directory, [example()])
            original = path.read_text()
            for text in [original.replace('"id": "edit-1"', '"id":"a","id":"b"'),
                         original.replace('"args": [', '"args": [1e400,'),
                         original.replace('"args": [', '"args": [NaN,')]:
                path.write_text(text)
                with self.assertRaises(ValueError): corpus.load_corpus(path)

    def test_portable_numeric_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(directory, [example()])
            template = path.read_text()
            for token in ["9007199254740992", "9007199254740993", "-9007199254740992", "9.007199254740992e15", "1e400"]:
                with self.subTest(token=token):
                    path.write_text(template.replace('"root", 0]', '"root", ' + token + ']'))
                    with self.assertRaises(ValueError): corpus.load_corpus(path)
            for token, expected in [("9007199254740991", 9007199254740991), ("-9007199254740991", -9007199254740991), ("-0", 0), ("1.0", 1), ("0.1", 0.1), ("1e-400", 0)]:
                with self.subTest(token=token):
                    path.write_text(template.replace('"root", 0]', '"root", ' + token + ']'))
                    value = corpus.load_corpus(path)["cases"][0]["input"]["args"][2]
                    self.assertEqual(value, expected)
                    if isinstance(expected, int): self.assertIs(type(value), int)

    def test_ids_unique_across_files(self):
        with tempfile.TemporaryDirectory() as directory:
            first = self.write(directory, [example()], "a.json")
            second = self.write(directory, [example()], "b.json")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                corpus.run_files([first, second], dispatch=lambda _: {"outcome": "error"})

    def test_boolean_number_mismatch_and_numeric_spelling(self):
        self.assertFalse(corpus.matches({"outcome":"ok", "value":[True]}, {"outcome":"ok", "value":[1]}))
        self.assertTrue(corpus.matches({"outcome":"ok", "value":[-0.0, 1]}, {"outcome":"ok", "value":[0, 1.0]}))

    def test_error_categories_and_path_subset(self):
        expected = {"outcome":"invalid", "includesErrorPaths":["$.patch.0"]}
        self.assertTrue(corpus.matches({"outcome":"invalid", "errorPaths":["$", "$.patch.0"]}, expected))
        self.assertFalse(corpus.matches({"outcome":"error"}, expected))
        self.assertFalse(corpus.matches({"outcome":"nonconforming", "errorPaths":["$.patch.0"]}, expected))

    def test_mismatch_is_reported_by_case_id(self):
        with tempfile.TemporaryDirectory() as directory:
            failures = corpus.run_files([self.write(directory, [example()])], dispatch=lambda _: {"outcome":"ok", "value":{}})
            self.assertEqual(len(failures), 1)
            self.assertIn("edit-1", failures[0])

    def test_empty_cases_and_duplicate_case_id_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            for cases in [[], [example(), example()]]:
                with self.assertRaises(ValueError):corpus.load_corpus(self.write(directory, cases))

    def test_boolean_operation_requires_boolean_expectation(self):
        case = example() | {"subject": "papermold/v1", "rule": "papermold/v1#the-judgment",
                            "operation": "conforms", "expected": {"outcome": "ok", "value": 1}}
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            corpus.load_corpus(self.write(directory, [case]))

    def test_operation_arity_is_transport_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            for args in [[], [{}, "root"], [{}, "root", 0, True]]:
                with self.subTest(args=args), self.assertRaises(ValueError):
                    corpus.load_corpus(self.write(directory, [example() | {"input": {"args": args}}]))
            for args in [[{}], [{}, {}, {}]]:
                case = example() | {"operation": "insertVessel", "input": {"args": args}}
                self.assertEqual(corpus.load_corpus(self.write(directory, [case]))["cases"][0], case)

    def test_empty_file_selection_is_not_success(self):
        with self.assertRaises(ValueError): corpus.run_files([])


if __name__ == "__main__": unittest.main()
