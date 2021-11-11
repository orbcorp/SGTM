from typing import Optional
from . import client as asana_client
from . import helpers as asana_helpers
from . import logic as asana_logic
from src.github.models import Comment, PullRequest, Review
from src.logger import logger
from src.dynamodb import client as dynamodb_client
from src.github import helpers as github_helpers


def create_task(repository_id: str) -> Optional[str]:
    # TODO: Allow overrides with environment variables?
    project_id = dynamodb_client.get_asana_id_from_github_node_id(repository_id)
    if project_id is None:
        logger.warn(f"No project id found for repository id {repository_id}")
        return None
    else:
        due_date_str = asana_helpers.default_due_date_str()
        return asana_client.create_task(project_id, due_date_str=due_date_str)


def update_task(pull_request: PullRequest, task_id: str):
    task_url = asana_helpers.task_url_from_task_id(task_id)
    pr_url = pull_request.url()
    logger.info(f"Updating task {task_url} for pull request {pr_url}")

    fields = asana_helpers.extract_task_fields_from_pull_request(pull_request)

    # TODO: Should extract_task_fields_from_pull_request be broken into two
    # methods, one for fields and one for followers?
    update_task_fields = {
        k: v
        for k, v in fields.items()
        if k in ("assignee", "name", "html_notes", "completed", "custom_fields")
    }
    asana_client.update_task(task_id, update_task_fields)
    asana_client.add_followers(task_id, fields["followers"])
    maybe_complete_tasks_on_merge(pull_request)


def create_review_subtask(pull_request: PullRequest, parent_task_id: str, reviewer_handle: str):
    asana_id = asana_helpers.asana_user_id_from_github_handle(reviewer_handle)
    task_name = asana_helpers.subtask_name_from_pull_request(pull_request)
    task_description = asana_helpers.subtask_description_from_pull_request(
        pull_request, reviewer_handle
    )
    due_date_str = asana_helpers.default_due_date_str()
    return asana_client.create_subtask(
        parent_task_id, asana_id, task_name, task_description, due_date_str=due_date_str
    )


def update_subtask(pull_request: PullRequest, subtask_id):
    is_task_completed = asana_client.is_task_completed(subtask_id)
    if is_task_completed:
        # We must re-open the task
        asana_client.update_task(subtask_id, {"completed": False})
        asana_client.add_comment(
            subtask_id,
            f"<body>{pull_request.author_handle()} has asked you to re-review the PR.</body>"
        )


def maybe_complete_tasks_on_merge(pull_request: PullRequest):
    if asana_logic.should_autocomplete_tasks_on_merge(pull_request):
        task_ids_to_complete_on_merge = asana_helpers.get_linked_task_ids(pull_request)
        for complete_on_merge_task_id in task_ids_to_complete_on_merge:
            asana_client.complete_task(complete_on_merge_task_id)


def upsert_github_comment_to_task(comment: Comment, task_id: str):
    github_comment_id = comment.id()
    asana_comment_id = dynamodb_client.get_asana_id_from_github_node_id(
        github_comment_id
    )
    if asana_comment_id is None:
        logger.info(f"Adding comment {github_comment_id} to task {task_id}")

        asana_helpers.create_attachments(comment.body(), task_id)

        asana_comment_id = asana_client.add_comment(
            task_id, asana_helpers.asana_comment_from_github_comment(comment)
        )
        dynamodb_client.insert_github_node_to_asana_id_mapping(
            github_comment_id, asana_comment_id
        )
    else:
        logger.info(
            f"Comment {github_comment_id} already synced to task {task_id}. Updating."
        )
        asana_client.update_comment(
            asana_comment_id, asana_helpers.asana_comment_from_github_comment(comment)
        )


def upsert_github_review_to_task(review: Review, task_id: str):
    github_review_id = review.id()
    asana_comment_id = dynamodb_client.get_asana_id_from_github_node_id(
        github_review_id
    )
    if asana_comment_id is None:
        logger.info(f"Adding review {github_review_id} to task {task_id}")
        asana_comment_id = asana_client.add_comment(
            task_id, asana_helpers.asana_comment_from_github_review(review)
        )
        dynamodb_client.insert_github_node_to_asana_id_mapping(
            github_review_id, asana_comment_id
        )
    else:
        logger.info(
            f"Review {github_review_id} already synced to task {task_id}. Updating."
        )
        asana_client.update_comment(
            asana_comment_id, asana_helpers.asana_comment_from_github_review(review)
        )

    dynamodb_client.bulk_insert_github_node_to_asana_id_mapping(
        [(c.id(), asana_comment_id) for c in review.comments()]
    )


def update_subtask_after_review(pull_request: PullRequest, review: Review, subtask_id: str) -> None:
    logger.info(f"Updating subtask {subtask_id} for pull request {pull_request.url()}")
    if asana_logic.should_complete_subtask(pull_request, review):
        asana_client.complete_task(subtask_id)


def delete_comment(github_comment_id: str):
    asana_comment_id = dynamodb_client.get_asana_id_from_github_node_id(
        github_comment_id
    )
    if asana_comment_id is not None:
        asana_client.delete_comment(asana_comment_id)
