from unittest.mock import patch
from uuid import uuid4
from test.impl.mock_dynamodb_test_case import MockDynamoDbTestCase
import src.github.client as github_client
import src.github.controller as github_controller
import src.asana.controller as asana_controller
import src.dynamodb.client as dynamodb_client
import src.asana.helpers as asana_helpers
from src.github.models import ReviewState
from test.impl.builders import builder


class GithubControllerTest(MockDynamoDbTestCase):
    @patch.object(asana_controller, "update_task")
    @patch.object(asana_controller, "create_task")
    def test_upsert_pull_request_when_task_id_not_found_in_dynamodb(
        self, create_task_mock, update_task_mock
    ):
        # If the task id is not found in dynamodb, then we assume the task
        # doesn't exist and create a new task
        new_task_id = uuid4().hex
        create_task_mock.return_value = new_task_id

        pull_request = builder.pull_request().build()
        with patch.object(
            github_controller, "_add_asana_task_to_pull_request"
        ) as add_asana_task_to_pr_mock:
            github_controller.upsert_pull_request(pull_request)
            add_asana_task_to_pr_mock.assert_called_with(pull_request, new_task_id)

        create_task_mock.assert_called_with(pull_request.repository_id())
        update_task_mock.assert_called_with(pull_request, new_task_id)

        # Assert that the new task id was inserted into the table
        task_id = dynamodb_client.get_asana_id_from_github_node_id(pull_request.id())
        self.assertEqual(task_id, new_task_id)

    @patch.object(asana_controller, "update_task")
    @patch.object(asana_controller, "create_task")
    def test_upsert_pull_request_when_task_id_already_found_in_dynamodb(
        self, create_task_mock, update_task_mock
    ):
        # If the task id is found in dynamodb, then we just update (don't
        # attempt to create)
        pull_request = builder.pull_request().build()

        # Insert the mapping first
        existing_task_id = uuid4().hex
        dynamodb_client.insert_github_node_to_asana_id_mapping(
            pull_request.id(), existing_task_id
        )

        github_controller.upsert_pull_request(pull_request)

        create_task_mock.assert_not_called()
        update_task_mock.assert_called_with(pull_request, existing_task_id)

    @patch.object(github_client, "edit_pr_description")
    def test_add_asana_task_to_pull_request(self, edit_pr_mock):
        pull_request = builder.pull_request("original body").build()
        task_id = uuid4().hex

        github_controller._add_asana_task_to_pull_request(pull_request, task_id)

        # Description was edited with the asana task in the body
        edit_pr_mock.assert_called()
        self.assertRegex(
            pull_request.body(),
            "original body\s*Pull Request synchronized with \[Asana task\]",
        )

    @patch.object(asana_controller, "update_task")
    @patch.object(asana_controller, "upsert_github_comment_to_task")
    def test_upsert_comment_when_task_id_already_found_in_dynamodb(
        self, add_comment_mock, update_task_mock
    ):
        # If the task id is found in dynamodb, then we just update (don't
        # attempt to create)
        pull_request = builder.pull_request().build()
        comment = builder.comment().build()

        # Insert the mapping first
        existing_task_id = uuid4().hex
        dynamodb_client.insert_github_node_to_asana_id_mapping(
            pull_request.id(), existing_task_id
        )

        github_controller.upsert_comment(pull_request, comment)

        add_comment_mock.assert_called_with(comment, existing_task_id)
        update_task_mock.assert_called_with(pull_request, existing_task_id)

    @patch.object(asana_controller, "update_task")
    @patch.object(asana_controller, "upsert_github_comment_to_task")
    def test_upsert_comment_when_task_id_not_found_in_dynamodb(
        self, add_comment_mock, update_task_mock
    ):
        pull_request = builder.pull_request().build()
        comment = builder.comment().build()

        github_controller.upsert_comment(pull_request, comment)
        # TODO: Test that a full sync was performed

    @patch.object(github_client, "set_pull_request_assignee")
    def test_assign_pull_request_to_author(self, set_pr_assignee_mock):
        user = builder.user().login("the_author").name("dont-care")
        pull_request = builder.pull_request().author(user).build()
        with patch.object(pull_request, "set_assignees") as set_assignees_mock:
            github_controller.assign_pull_request_to_author(pull_request)
            set_assignees_mock.assert_called_with([pull_request.author_handle()])

        set_pr_assignee_mock.assert_called_with(
            pull_request.repository_owner_handle(),
            pull_request.repository_name(),
            pull_request.number(),
            pull_request.author_handle(),
        )


class LinkOnlyTest(MockDynamoDbTestCase):
    """Behaviour of upsert_pull_request under SGTM_FEATURE__LINK_ONLY_ENABLED."""

    LINKED_TASK = "1218505056963671"
    BODY_WITH_LINK = (
        "## Task Link\n"
        "https://app.asana.com/1/548620057800108/project/1/task/1218505056963671\n"
    )

    @patch.object(github_controller, "SGTM_FEATURE__LINK_ONLY_ENABLED", True)
    @patch.object(asana_controller, "task_is_reachable", return_value=True)
    @patch.object(asana_controller, "update_task")
    @patch.object(asana_controller, "create_task")
    def test_links_the_existing_task_instead_of_creating_one(
        self, create_task_mock, update_task_mock, reachable_mock
    ):
        pull_request = builder.pull_request().body(self.BODY_WITH_LINK).build()

        github_controller.upsert_pull_request(pull_request)

        create_task_mock.assert_not_called()
        update_task_mock.assert_called_with(pull_request, self.LINKED_TASK)
        self.assertEqual(
            dynamodb_client.get_asana_id_from_github_node_id(pull_request.id()),
            self.LINKED_TASK,
        )

    @patch.object(github_controller, "SGTM_FEATURE__LINK_ONLY_ENABLED", True)
    @patch.object(asana_controller, "update_task")
    @patch.object(asana_controller, "create_task")
    def test_does_nothing_when_no_task_is_linked(
        self, create_task_mock, update_task_mock
    ):
        pull_request = builder.pull_request().body("no link here").build()

        github_controller.upsert_pull_request(pull_request)

        create_task_mock.assert_not_called()
        update_task_mock.assert_not_called()
        self.assertIsNone(
            dynamodb_client.get_asana_id_from_github_node_id(pull_request.id())
        )

    @patch.object(github_controller, "SGTM_FEATURE__LINK_ONLY_ENABLED", False)
    @patch.object(asana_controller, "task_is_reachable", return_value=True)
    @patch.object(asana_controller, "update_task")
    @patch.object(asana_controller, "create_task")
    def test_still_creates_while_the_flag_is_off(
        self, create_task_mock, update_task_mock, reachable_mock
    ):
        # Milestone 3 ships the parser in dry-run: it resolves and logs the
        # linked task, but behaviour is unchanged until the flag flips.
        new_task_id = uuid4().hex
        create_task_mock.return_value = new_task_id
        pull_request = builder.pull_request().body(self.BODY_WITH_LINK).build()

        with patch.object(github_controller, "_add_asana_task_to_pull_request"):
            with patch.object(asana_helpers, "create_attachments"):
                github_controller.upsert_pull_request(pull_request)

        create_task_mock.assert_called_once()
        update_task_mock.assert_called_with(pull_request, new_task_id)

    @patch.object(github_controller, "SGTM_FEATURE__LINK_ONLY_ENABLED", True)
    @patch.object(asana_controller, "task_is_reachable", return_value=True)
    @patch.object(asana_controller, "update_task")
    @patch.object(asana_controller, "create_task")
    def test_an_existing_mapping_still_wins(
        self, create_task_mock, update_task_mock, reachable_mock
    ):
        # A pull request SGTM already made a task for keeps that task, even if
        # the author later pastes a different link.
        pull_request = builder.pull_request().body(self.BODY_WITH_LINK).build()
        existing = uuid4().hex
        dynamodb_client.insert_github_node_to_asana_id_mapping(
            pull_request.id(), existing
        )

        github_controller.upsert_pull_request(pull_request)

        create_task_mock.assert_not_called()
        update_task_mock.assert_called_with(pull_request, existing)

    @patch.object(github_controller, "SGTM_FEATURE__LINK_ONLY_ENABLED", True)
    @patch.object(asana_controller, "task_is_reachable", return_value=False)
    @patch.object(asana_controller, "update_task")
    @patch.object(asana_controller, "create_task")
    def test_refuses_to_bind_to_a_task_it_cannot_read(
        self, create_task_mock, update_task_mock, reachable_mock
    ):
        # A private project, or a deleted task. Binding is permanent and the
        # Lambda cannot delete the row, so a bad bind would wedge the PR.
        pull_request = builder.pull_request().body(self.BODY_WITH_LINK).build()

        github_controller.upsert_pull_request(pull_request)

        reachable_mock.assert_called_once_with(self.LINKED_TASK)
        create_task_mock.assert_not_called()
        update_task_mock.assert_not_called()
        self.assertIsNone(
            dynamodb_client.get_asana_id_from_github_node_id(pull_request.id())
        )

    @patch.object(github_controller, "SGTM_FEATURE__LINK_ONLY_ENABLED", True)
    @patch.object(asana_controller, "task_is_reachable", return_value=False)
    @patch.object(asana_controller, "update_task")
    @patch.object(asana_controller, "create_task")
    def test_an_unreachable_task_is_retried_once_it_becomes_readable(
        self, create_task_mock, update_task_mock, reachable_mock
    ):
        pull_request = builder.pull_request().body(self.BODY_WITH_LINK).build()
        github_controller.upsert_pull_request(pull_request)

        # the author fixes the link, or is granted access
        reachable_mock.return_value = True
        github_controller.upsert_pull_request(pull_request)

        update_task_mock.assert_called_with(pull_request, self.LINKED_TASK)
        self.assertEqual(
            dynamodb_client.get_asana_id_from_github_node_id(pull_request.id()),
            self.LINKED_TASK,
        )


class LinkOnlyRelayTest(MockDynamoDbTestCase):
    """What reaches a task once ordinary chatter stops being relayed."""

    def setUp(self):
        self.pull_request = builder.pull_request().build()
        self.task_id = uuid4().hex
        dynamodb_client.insert_github_node_to_asana_id_mapping(
            self.pull_request.id(), self.task_id
        )

    @patch.object(github_controller, "SGTM_FEATURE__LINK_ONLY_ENABLED", True)
    @patch.object(asana_controller, "update_task")
    @patch.object(asana_controller, "upsert_github_comment_to_task")
    def test_ordinary_comments_are_not_relayed(self, upsert_comment_mock, update_mock):
        github_controller.upsert_comment(self.pull_request, builder.comment().build())

        upsert_comment_mock.assert_not_called()
        update_mock.assert_not_called()

    @patch.object(github_controller, "SGTM_FEATURE__LINK_ONLY_ENABLED", False)
    @patch.object(asana_controller, "update_task")
    @patch.object(asana_controller, "upsert_github_comment_to_task")
    def test_ordinary_comments_still_relay_while_the_flag_is_off(
        self, upsert_comment_mock, update_mock
    ):
        github_controller.upsert_comment(self.pull_request, builder.comment().build())

        upsert_comment_mock.assert_called_once()

    @patch.object(github_controller, "SGTM_FEATURE__LINK_ONLY_ENABLED", True)
    @patch.object(github_controller, "assign_pull_request_to_author")
    @patch.object(asana_controller, "update_task")
    @patch.object(asana_controller, "upsert_github_review_to_task")
    def test_comment_only_reviews_are_not_relayed(
        self, upsert_review_mock, update_mock, assign_mock
    ):
        review = builder.review().state(ReviewState.COMMENTED).build()

        github_controller.upsert_review(self.pull_request, review)

        upsert_review_mock.assert_not_called()
        assign_mock.assert_not_called()

    @patch.object(github_controller, "SGTM_FEATURE__LINK_ONLY_ENABLED", True)
    @patch.object(github_controller, "assign_pull_request_to_author")
    @patch.object(asana_controller, "update_task")
    @patch.object(asana_controller, "upsert_github_review_to_task")
    def test_approvals_are_relayed_and_bounce_the_pull_request(
        self, upsert_review_mock, update_mock, assign_mock
    ):
        review = builder.review().state(ReviewState.APPROVED).build()

        github_controller.upsert_review(self.pull_request, review)

        upsert_review_mock.assert_called_once()
        assign_mock.assert_called_once()

    @patch.object(github_controller, "SGTM_FEATURE__LINK_ONLY_ENABLED", True)
    @patch.object(github_controller, "assign_pull_request_to_author")
    @patch.object(asana_controller, "update_task")
    @patch.object(asana_controller, "upsert_github_review_to_task")
    def test_changes_requested_is_relayed(
        self, upsert_review_mock, update_mock, assign_mock
    ):
        review = builder.review().state(ReviewState.CHANGES_REQUESTED).build()

        github_controller.upsert_review(self.pull_request, review)

        upsert_review_mock.assert_called_once()


if __name__ == "__main__":
    from unittest import main as run_tests

    run_tests()
