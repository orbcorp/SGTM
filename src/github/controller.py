from typing import Optional

import src.dynamodb.client as dynamodb_client
import src.asana.controller as asana_controller
from . import logic as github_logic
from . import client as github_client
import src.asana.helpers as asana_helpers
from src.github.models import Comment, PullRequest, Review
from src.logger import logger
from src.config import SGTM_FEATURE__LINK_ONLY_ENABLED


def _linked_task(pull_request: PullRequest) -> Optional[str]:
    """
    Returns the Asana task the pull request links, if any.

    Logged on every pull request event, whether or not link-only is enabled, so
    that the hit rate can be measured from CloudWatch before the flag is flipped.
    """
    task_ids = asana_helpers.get_linked_task_ids(pull_request)
    if not task_ids:
        logger.info(f"LINK pr={pull_request.number()} result=no_link")
        return None

    task_id = task_ids[0]
    if not asana_controller.task_is_reachable(task_id):
        # Binding is permanent -- the mapping is read before the body on every
        # later event, and the Lambda has no DeleteItem on sgtm-objects to undo
        # it. Refusing to bind leaves the pull request unbound, so a corrected
        # link is picked up on the next event instead of wedging the PR.
        logger.info(
            f"LINK pr={pull_request.number()} result=unreachable task={task_id}"
        )
        return None

    logger.info(f"LINK pr={pull_request.number()} result=linked task={task_id}")
    return task_id


def upsert_pull_request(pull_request: PullRequest):
    pull_request_id = pull_request.id()
    task_id = dynamodb_client.get_asana_id_from_github_node_id(pull_request_id)
    if task_id is None:
        linked_task_id = _linked_task(pull_request)

        if linked_task_id is not None and SGTM_FEATURE__LINK_ONLY_ENABLED:
            task_id = linked_task_id
            logger.info(
                f"Linking task {task_id} for pull request {pull_request_id}"
            )
            dynamodb_client.insert_github_node_to_asana_id_mapping(
                pull_request_id, task_id
            )
        elif SGTM_FEATURE__LINK_ONLY_ENABLED:
            # No linked task, and we no longer create one.
            return
        else:
            task_id = asana_controller.create_task(pull_request.repository_id())
            if task_id is None:
                # TODO: Handle this case
                return

            logger.info(
                f"Task created for pull request {pull_request_id}: {task_id}"
            )
            dynamodb_client.insert_github_node_to_asana_id_mapping(
                pull_request_id, task_id
            )
            asana_helpers.create_attachments(pull_request.body(), task_id)
            _add_asana_task_to_pull_request(pull_request, task_id)
    else:
        logger.info(
            f"Task found for pull request {pull_request_id}, updating task {task_id}"
        )
    asana_controller.update_task(pull_request, task_id)


def _add_asana_task_to_pull_request(pull_request: PullRequest, task_id: str):
    owner = pull_request.repository_owner_handle()
    task_url = asana_helpers.task_url_from_task_id(task_id)
    new_body = github_logic.inject_asana_task_into_pull_request_body(
        pull_request.body(), task_url
    )
    github_client.edit_pr_description(
        owner, pull_request.repository_name(), pull_request.number(), new_body
    )

    # Update the PullRequest object to represent the new body, so we don't have
    # to query it again
    pull_request.set_body(new_body)


def upsert_comment(pull_request: PullRequest, comment: Comment):
    if SGTM_FEATURE__LINK_ONLY_ENABLED:
        # Ordinary pull request comments are not relayed. They are not
        # decisions, and the GitHub card on the task already carries a comment
        # count, so a reader can see they exist without each one arriving as a
        # notification.
        return

    pull_request_id = pull_request.id()
    task_id = dynamodb_client.get_asana_id_from_github_node_id(pull_request_id)
    if task_id is None:
        logger.info(
            f"Task not found for pull request {pull_request_id}. Running a full sync!"
        )
        # TODO: Full sync
    else:
        asana_controller.upsert_github_comment_to_task(comment, task_id)
        asana_controller.update_task(pull_request, task_id)


def upsert_review(pull_request: PullRequest, review: Review):
    pull_request_id = pull_request.id()
    task_id = dynamodb_client.get_asana_id_from_github_node_id(pull_request_id)
    if task_id is None:
        logger.info(
            f"Task not found for pull request {pull_request_id}. Running a full sync!"
        )
        # TODO: Full sync
    else:
        is_decision = review.is_approval_or_changes_requested()
        if is_decision or not SGTM_FEATURE__LINK_ONLY_ENABLED:
            # Only approvals and changes-requested are relayed. A review that
            # merely comments -- including the empty review GitHub fabricates
            # for a bare inline comment -- is chatter, and the card already
            # shows that review activity is happening.
            logger.info(
                f"Found task id {task_id} for pull_request {pull_request_id}. Adding review now."
            )
            asana_controller.upsert_github_review_to_task(review, task_id)
        if is_decision:
            assign_pull_request_to_author(pull_request)
        asana_controller.update_task(pull_request, task_id)


def assign_pull_request_to_author(pull_request: PullRequest):
    owner = pull_request.repository_owner_handle()
    new_assignee = pull_request.author_handle()
    github_client.set_pull_request_assignee(
        owner, pull_request.repository_name(), pull_request.number(), new_assignee
    )
    # so we don't have to re-query the PR
    pull_request.set_assignees([new_assignee])


def delete_comment(github_comment_id: str):
    asana_controller.delete_comment(github_comment_id)
