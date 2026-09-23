import src.asana.helpers as asana_helpers

from test.impl.builders import builder, build
from test.impl.base_test_case_class import BaseClass

TASK_ID = "1218505056963671"
OTHER_TASK_ID = "1218327558761550"


def _injected(task_id: str) -> str:
    return f"Pull Request synchronized with [Asana task](https://app.asana.com/0/0/{task_id})"


class TestIsTaskCreatedBySgtm(BaseClass):
    def _created(self, body: str, task_id: str = TASK_ID) -> bool:
        return asana_helpers.is_task_created_by_sgtm(
            build(builder.pull_request().body(body)), task_id
        )

    def test_true_when_sgtm_injected_a_link_to_this_task(self):
        self.assertTrue(self._created(f"Some description\n\n\n{_injected(TASK_ID)}"))

    def test_false_when_there_is_no_injected_link(self):
        self.assertFalse(self._created("Some description"))

    def test_false_when_the_task_is_only_linked_by_the_author(self):
        body = f"## Task Link\nhttps://app.asana.com/0/1210863352745931/{TASK_ID}\n"
        self.assertFalse(self._created(body))

    def test_false_when_the_injected_link_was_copied_from_another_pull_request(self):
        # A stack, or a reused description, carries the first pull request's
        # link along. It says nothing about the task this one is bound to.
        body = (
            f"## Task Link\nhttps://app.asana.com/0/1/{TASK_ID}\n\n\n"
            f"{_injected(OTHER_TASK_ID)}"
        )
        self.assertFalse(self._created(body))

    def test_matches_either_of_several_injected_links(self):
        body = f"{_injected(OTHER_TASK_ID)}\n\n\n{_injected(TASK_ID)}"
        self.assertTrue(self._created(body))

    def test_accepts_the_new_asana_url_shape(self):
        body = (
            "Pull Request synchronized with [Asana task]"
            f"(https://app.asana.com/1/548620057800108/project/1/task/{TASK_ID})"
        )
        self.assertTrue(self._created(body))

    def test_does_not_match_a_task_id_that_merely_ends_the_same(self):
        self.assertFalse(self._created(_injected(TASK_ID), task_id=TASK_ID[-9:]))


if __name__ == "__main__":
    from unittest import main as run_tests

    run_tests()
