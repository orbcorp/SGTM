from unittest.mock import patch, Mock, MagicMock, call
from test.impl.builders import builder, build


from test.impl.base_test_case_class import BaseClass

from src.github.models import Review, Comment
from src.asana import controller


@patch("src.asana.helpers.asana_comment_from_github_review")
@patch("src.asana.client.add_comment")
@patch("src.dynamodb.client.insert_github_node_to_asana_id_mapping")
@patch("src.dynamodb.client.bulk_insert_github_node_to_asana_id_mapping")
class TestUpsertGithubReviewToTask(BaseClass):
    REVIEW_ID = "12345"
    ASANA_COMMENT_ID = "56789"
    ASANA_TASK_ID = "abcde"
    ASANA_COMMENT_BODY = "<body>Here's a comment</body>"

    def _mock_comment(self, id):
        return MagicMock(spec=Comment, id=MagicMock(return_value=id))

    def _mock_review(self, id, comments=[]):
        return MagicMock(
            spec=Review,
            id=MagicMock(return_value=id),
            comments=MagicMock(return_value=comments),
        )

    @patch("src.dynamodb.client.get_asana_id_from_github_node_id", return_value=None)
    def test_created_review_with_no_comments(
        self,
        get_asana_id_from_github_node_id,
        bulk_insert_github_node_to_asana_id_mapping,
        insert_github_node_to_asana_id_mapping,
        add_comment,
        asana_comment_from_github_review,
    ):
        review = self._mock_review(self.REVIEW_ID)
        asana_comment_from_github_review.return_value = self.ASANA_COMMENT_BODY

        add_comment.return_value = self.ASANA_COMMENT_ID

        controller.upsert_github_review_to_task(review, self.ASANA_TASK_ID)

        add_comment.assert_called_once_with(self.ASANA_TASK_ID, self.ASANA_COMMENT_BODY)
        asana_comment_from_github_review.assert_called_once_with(review)
        insert_github_node_to_asana_id_mapping.assert_called_once_with(
            self.REVIEW_ID, self.ASANA_COMMENT_ID
        )
        get_asana_id_from_github_node_id.assert_called_once_with(self.REVIEW_ID)

    @patch("src.dynamodb.client.get_asana_id_from_github_node_id", return_value=None)
    def test_created_review_with_comments(
        self,
        get_asana_id_from_github_node_id,
        bulk_insert_github_node_to_asana_id_mapping,
        insert_github_node_to_asana_id_mapping,
        add_comment,
        asana_comment_from_github_review,
    ):
        review = self._mock_review(
            self.REVIEW_ID, [self._mock_comment("123"), self._mock_comment("456")]
        )
        asana_comment_from_github_review.return_value = self.ASANA_COMMENT_BODY

        add_comment.return_value = self.ASANA_COMMENT_ID

        controller.upsert_github_review_to_task(review, self.ASANA_TASK_ID)

        insert_github_node_to_asana_id_mapping.assert_called_once_with(
            self.REVIEW_ID, self.ASANA_COMMENT_ID
        )
        bulk_insert_github_node_to_asana_id_mapping.assert_called_once_with(
            [("123", self.ASANA_COMMENT_ID), ("456", self.ASANA_COMMENT_ID)]
        )
        add_comment.assert_called_once_with(self.ASANA_TASK_ID, self.ASANA_COMMENT_BODY)
        get_asana_id_from_github_node_id.assert_called_once_with(self.REVIEW_ID)
        asana_comment_from_github_review.assert_called_once_with(review)

    @patch("src.asana.client.update_comment")
    @patch(
        "src.dynamodb.client.get_asana_id_from_github_node_id",
        return_value=ASANA_COMMENT_ID,
    )
    def test_updated_review_with_comments(
        self,
        get_asana_id_from_github_node_id,
        update_comment,
        bulk_insert_github_node_to_asana_id_mapping,
        insert_github_node_to_asana_id_mapping,
        add_comment,
        asana_comment_from_github_review,
    ):
        review = self._mock_review(
            self.REVIEW_ID, [self._mock_comment("123"), self._mock_comment("456")]
        )
        asana_comment_from_github_review.return_value = self.ASANA_COMMENT_BODY

        controller.upsert_github_review_to_task(review, self.ASANA_TASK_ID)

        get_asana_id_from_github_node_id.assert_called_once_with(self.REVIEW_ID)
        asana_comment_from_github_review.assert_called_once_with(review)
        update_comment.assert_called_once_with(
            self.ASANA_COMMENT_ID, self.ASANA_COMMENT_BODY
        )
        bulk_insert_github_node_to_asana_id_mapping.assert_called_once_with(
            [("123", self.ASANA_COMMENT_ID), ("456", self.ASANA_COMMENT_ID)]
        )
        add_comment.assert_not_called()


@patch("src.asana.client.complete_task")
@patch("src.asana.helpers.get_linked_task_ids")
@patch("src.asana.logic.should_autocomplete_tasks_on_merge", return_value=True)
class TestMaybeCompleteTasksOnMerge(BaseClass):
    def test_noop_if_no_task_ids_to_complete(
        self,
        should_autocomplete_tasks_on_merge_mock,
        get_linked_task_ids_mock,
        complete_task_mock,
    ):
        get_linked_task_ids_mock.return_value = []
        pull_request = build(builder.pull_request().merged(True))
        controller.maybe_complete_tasks_on_merge(pull_request)
        complete_task_mock.assert_not_called()

    def test_updates_tasks_with_completed_true_if_has_task_id(
        self,
        should_autocomplete_tasks_on_merge_mock,
        get_linked_task_ids_mock,
        complete_task_mock,
    ):
        task_ids = ["123", "456"]
        get_linked_task_ids_mock.return_value = task_ids
        pull_request = build(builder.pull_request().merged(True))
        controller.maybe_complete_tasks_on_merge(pull_request)
        complete_task_mock.assert_any_call(task_ids[0])
        complete_task_mock.assert_any_call(task_ids[1])


TASK_ID = "1218505056963671"
SGTM_BODY = (
    "Some description\n\n\n"
    f"Pull Request synchronized with [Asana task](https://app.asana.com/0/0/{TASK_ID})"
)
LINKED_BODY = f"## Task Link\nhttps://app.asana.com/0/1/{TASK_ID}\n"


@patch("src.asana.controller.maybe_complete_tasks_on_merge")
@patch("src.asana.client.add_followers")
@patch("src.asana.client.update_task")
@patch(
    "src.asana.helpers.extract_task_fields_from_pull_request",
    return_value={"name": "PR", "followers": ["follower"]},
)
@patch("src.asana.helpers.task_followers_from_pull_request", return_value=["follower"])
class TestUpdateTaskLinkOnly(BaseClass):
    """Which tasks update_task may overwrite, and which it may only add to."""

    @patch("src.asana.controller.SGTM_FEATURE__LINK_ONLY_ENABLED", True)
    def test_a_task_sgtm_created_keeps_its_full_sync(
        self, followers, extract_fields, update_task, add_followers, complete
    ):
        # Otherwise a pull request open when the flag flips never completes the
        # task SGTM made for it.
        pull_request = build(builder.pull_request().body(SGTM_BODY))

        controller.update_task(pull_request, TASK_ID)

        update_task.assert_called_once_with(TASK_ID, {"name": "PR"})
        complete.assert_called_once_with(pull_request)

    @patch("src.asana.controller.SGTM_FEATURE__LINK_ONLY_ENABLED", True)
    def test_a_linked_task_is_only_added_to(
        self, followers, extract_fields, update_task, add_followers, complete
    ):
        pull_request = build(builder.pull_request().body(LINKED_BODY))

        controller.update_task(pull_request, TASK_ID)

        update_task.assert_not_called()
        extract_fields.assert_not_called()
        add_followers.assert_called_once_with(TASK_ID, ["follower"])

    @patch("src.asana.controller.SGTM_FEATURE__LINK_ONLY_ENABLED", True)
    def test_a_linked_task_stays_additions_only_after_the_link_is_edited_away(
        self, followers, extract_fields, update_task, add_followers, complete
    ):
        # The mapping outlives the description. Once the author removes the
        # link, the task must still not be treated as SGTM's.
        pull_request = build(builder.pull_request().body("link removed"))

        controller.update_task(pull_request, TASK_ID)

        update_task.assert_not_called()

    @patch("src.asana.controller.SGTM_FEATURE__LINK_ONLY_ENABLED", True)
    def test_a_copied_injected_link_for_another_task_does_not_count(
        self, followers, extract_fields, update_task, add_followers, complete
    ):
        body = LINKED_BODY + (
            "\n\n\nPull Request synchronized with "
            "[Asana task](https://app.asana.com/0/0/1218327558761550)"
        )
        pull_request = build(builder.pull_request().body(body))

        controller.update_task(pull_request, TASK_ID)

        update_task.assert_not_called()

    @patch("src.asana.controller.SGTM_FEATURE__LINK_ONLY_ENABLED", False)
    def test_every_task_is_fully_synced_while_the_flag_is_off(
        self, followers, extract_fields, update_task, add_followers, complete
    ):
        pull_request = build(builder.pull_request().body("link removed"))

        controller.update_task(pull_request, TASK_ID)

        update_task.assert_called_once_with(TASK_ID, {"name": "PR"})


if __name__ == "__main__":
    from unittest import main as run_tests

    run_tests()
