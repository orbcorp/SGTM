from src.asana import helpers as asana_helpers

from test.impl.builders import builder, build
from test.impl.base_test_case_class import BaseClass

TASK_ID = "1218505056963671"
OTHER_TASK_ID = "1218327558761550"
NEW_STYLE_URL = f"https://app.asana.com/1/548620057800108/project/1210863352745931/task/{TASK_ID}"
OLD_STYLE_URL = f"https://app.asana.com/0/1210863352745931/{TASK_ID}"


class TestGetLinkedTaskIds(BaseClass):
    def _ids(self, body: str):
        return asana_helpers.get_linked_task_ids(build(builder.pull_request().body(body)))

    # ------------------------------------------------------------------
    # The shapes the PR template and real authors actually produce
    # ------------------------------------------------------------------

    def test_finds_task_under_a_markdown_heading(self):
        # What orbcorp/codez's template renders. The old parser missed this.
        body = f"## Task Link\n{NEW_STYLE_URL}\n\n## AI description of changes\nblah"
        self.assertEqual(self._ids(body), [TASK_ID])

    def test_finds_task_on_the_marker_line(self):
        self.assertEqual(self._ids(f"Task Link: {NEW_STYLE_URL}"), [TASK_ID])

    def test_finds_task_on_the_line_below_the_marker(self):
        self.assertEqual(self._ids(f"Task Link:\n{NEW_STYLE_URL}"), [TASK_ID])

    def test_finds_task_written_as_a_labelled_line_in_the_section(self):
        # Seen in the wild: "Asana: <url>" under the heading.
        body = f"## Task Link\nAsana: {NEW_STYLE_URL}\n"
        self.assertEqual(self._ids(body), [TASK_ID])

    def test_accepts_the_old_url_shape(self):
        self.assertEqual(self._ids(f"Task Link: {OLD_STYLE_URL}"), [TASK_ID])

    def test_accepts_the_upstream_marker(self):
        self.assertEqual(self._ids(f"Asana tasks: {OLD_STYLE_URL}"), [TASK_ID])

    def test_is_case_insensitive(self):
        self.assertEqual(self._ids(f"task link: {NEW_STYLE_URL}"), [TASK_ID])

    def test_finds_several_tasks_and_deduplicates(self):
        body = f"## Task Link\n{NEW_STYLE_URL} {OLD_STYLE_URL}\nhttps://app.asana.com/0/1/{OTHER_TASK_ID}"
        self.assertEqual(self._ids(body), [TASK_ID, OTHER_TASK_ID])

    # ------------------------------------------------------------------
    # Traps taken from real codez pull requests
    # ------------------------------------------------------------------

    def test_ignores_a_task_mentioned_in_prose_outside_the_section(self):
        body = (
            "## Human description of changes\n"
            f"Not addressed here: the hardcoded default (https://app.asana.com/0/1/{OTHER_TASK_ID}).\n"
            f"## Task Link\n{NEW_STYLE_URL}\n"
        )
        self.assertEqual(self._ids(body), [TASK_ID])

    def test_ignores_an_example_url_inside_an_html_comment(self):
        # The codez template carries an Asana url in a comment; a naive parser
        # links it on every single pull request.
        body = (
            "## Task Link\n"
            f"<!-- paste it here, e.g. https://app.asana.com/0/1/{OTHER_TASK_ID} -->\n"
            f"{NEW_STYLE_URL}\n"
        )
        self.assertEqual(self._ids(body), [TASK_ID])

    def test_never_links_sgtms_own_injected_link(self):
        body = (
            "## Task Link\n\n\n"
            f"Pull Request synchronized with [Asana task](https://app.asana.com/0/0/{OTHER_TASK_ID})"
        )
        self.assertEqual(self._ids(body), [])

    def test_ignores_a_trailing_query_parameter(self):
        body = f"Task Link: {NEW_STYLE_URL}?project=42"
        self.assertEqual(self._ids(body), [TASK_ID])

    def test_ignores_numbers_that_are_not_task_ids(self):
        body = f"Task Link: {NEW_STYLE_URL} (see PR-1234)"
        self.assertEqual(self._ids(body), [TASK_ID])

    def test_ignores_a_project_url_with_no_task(self):
        self.assertEqual(self._ids("Task Link: https://app.asana.com/0/12081111"), [])

    def test_section_stops_at_the_next_heading(self):
        body = (
            "## Task Link\n\n"
            "## AI description of changes\n"
            f"see {OTHER_TASK_ID} at https://app.asana.com/0/1/{OTHER_TASK_ID}\n"
        )
        self.assertEqual(self._ids(body), [])

    # ------------------------------------------------------------------
    # Nothing to find
    # ------------------------------------------------------------------

    def test_returns_empty_when_the_section_is_absent(self):
        self.assertEqual(self._ids("Blah blah blah\nblah\n"), [])

    def test_returns_empty_when_the_section_is_unfilled(self):
        self.assertEqual(self._ids("## Task Link\n\n## Testing\n"), [])

    def test_returns_empty_for_a_malformed_description(self):
        self.assertEqual(self._ids("Blah\nTask Link:\neng jank"), [])

    def test_prose_beginning_with_the_words_is_not_a_marker(self):
        # An inline marker needs its colon, or this sentence binds the PR to
        # whatever task it happens to mention.
        body = f"Task Link is not required; see {NEW_STYLE_URL}"
        self.assertEqual(self._ids(body), [])

    def test_a_heading_section_survives_blank_lines(self):
        # A heading owns everything up to the next heading. An intro paragraph
        # and a blank line above the url are still the same section.
        body = f"## Task Link\nTracking this under:\n\n{NEW_STYLE_URL}\n\n## Testing\n"
        self.assertEqual(self._ids(body), [TASK_ID])

    def test_an_inline_marker_ends_at_a_blank_line(self):
        body = f"Task Link:\nsome note\n\nunrelated {NEW_STYLE_URL}\n"
        self.assertEqual(self._ids(body), [])

    def test_requires_a_real_asana_url(self):
        # "app.asana.com/" appearing inside some other host is not a task link.
        body = f"Task Link: https://example.com/app.asana.com/0/1/{TASK_ID}"
        self.assertEqual(self._ids(body), [])

    def test_does_not_match_a_word_merely_starting_with_the_marker(self):
        self.assertEqual(self._ids(f"Task Linkage is broken, see {NEW_STYLE_URL}"), [])


if __name__ == "__main__":
    from unittest import main as run_tests

    run_tests()
