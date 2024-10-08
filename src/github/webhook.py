from typing import Optional
from operator import itemgetter
import time

import src.github.graphql.client as graphql_client
from src.dynamodb.lock import dynamodb_lock
import src.github.controller as github_controller
import src.github.logic as github_logic
from src.http import HttpResponse
from src.logger import logger
from src.github.models import PullRequestReviewComment, Review


# https://developer.github.com/v3/activity/events/types/#pullrequestevent
def _handle_pull_request_webhook(payload: dict) -> HttpResponse:
    pull_request_id = payload["pull_request"]["node_id"]
    with dynamodb_lock(pull_request_id):
        pull_request = graphql_client.get_pull_request(pull_request_id)
        # a label change will trigger this webhook, so it may trigger automerge
        github_logic.maybe_automerge_pull_request(pull_request)
        github_logic.maybe_add_automerge_warning_comment(pull_request)
        github_controller.upsert_pull_request(pull_request)
        return HttpResponse("200")


# https://developer.github.com/v3/activity/events/types/#issuecommentevent
def _handle_issue_comment_webhook(payload: dict) -> HttpResponse:
    action, issue, comment = itemgetter("action", "issue", "comment")(payload)

    issue_id = issue["node_id"]
    comment_id = comment["node_id"]
    with dynamodb_lock(issue_id):
        if action in ("created", "edited"):
            pull_request, comment = graphql_client.get_pull_request_and_comment(
                issue_id, comment_id
            )
            github_controller.upsert_comment(pull_request, comment)
            return HttpResponse("200")
        elif action == "deleted":
            logger.info(f"Deleting comment {comment_id}")
            github_controller.delete_comment(comment_id)
            return HttpResponse("200")
        else:
            error_text = f"Unknown action for issue_comment: {action}"
            logger.info(error_text)
            return HttpResponse("400", error_text)


# https://developer.github.com/v3/activity/events/types/#pullrequestreviewevent
def _handle_pull_request_review_webhook(payload: dict) -> HttpResponse:
    pull_request_id = payload["pull_request"]["node_id"]
    review_id = payload["review"]["node_id"]

    with dynamodb_lock(pull_request_id):
        pull_request, review = graphql_client.get_pull_request_and_review(
            pull_request_id, review_id
        )
        github_logic.maybe_automerge_pull_request(pull_request)
        github_controller.upsert_review(pull_request, review)
    return HttpResponse("200")


# https://developer.github.com/v3/activity/events/types/#pullrequestreviewcommentevent
def _handle_pull_request_review_comment(payload: dict):
    """Handle when a pull request review comment is edited or removed.
    When comments are added it either hits:
        1 _handle_issue_comment_webhook (if the comment is on PR itself)
        2 _handle_pull_request_review_webhook (if the comment is on the "Files Changed" tab)
    Note that it hits (2) even if the comment is inline, and doesn't contain a review;
        in those cases Github still creates a review object for it.

    Unfortunately, this payload doesn't contain the node id of the review.
    Instead, it includes a separate, numeric id
    which is stored as `databaseId` on each GraphQL object.

    To get the review, we either:
        (1) query for the comment, and use the `review` edge in GraphQL.
        (2) Iterate through all reviews on the pull request, and find the one whose databaseId matches.
            See get_review_for_database_id()

    We do (1) for comments that were added or edited, but if a comment was just deleted, we have to do (2).

    See https://developer.github.com/v4/object/repository/#fields.
    """
    pull_request_id = payload["pull_request"]["node_id"]
    action = payload["action"]
    comment_id = payload["comment"]["node_id"]

    # This is NOT the node_id, but is a numeric string (the databaseId field).
    review_database_id = payload["comment"]["pull_request_review_id"]

    with dynamodb_lock(pull_request_id):
        if action in ("created", "edited"):
            pull_request, comment = graphql_client.get_pull_request_and_comment(
                pull_request_id, comment_id
            )
            if not isinstance(comment, PullRequestReviewComment):
                raise Exception(
                    f"Unexpected comment type {type(PullRequestReviewComment)} for pull request review"
                )
            review: Optional[Review] = Review.from_comment(comment)
        elif action == "deleted":
            pull_request = graphql_client.get_pull_request(pull_request_id)
            review = graphql_client.get_review_for_database_id(
                pull_request_id, review_database_id
            )
            if review is None:
                # If we deleted the last comment from a review, Github might have deleted the review.
                # If so, we should delete the Asana comment.
                logger.info("No review found in Github. Deleting the Asana comment.")
                github_controller.delete_comment(comment_id)
        else:
            raise ValueError(f"Unexpected action: {action}")

        if review is not None:
            github_controller.upsert_review(pull_request, review)

        return HttpResponse("200")


# https://developer.github.com/v3/activity/events/types/#statusevent
def _handle_status_webhook(payload: dict) -> HttpResponse:
    commit_id = payload["commit"]["node_id"]
    pull_request = graphql_client.get_pull_request_for_commit(commit_id)
    if pull_request is None:
        # This could happen for commits that get pushed outside of the normal
        # pull request flow. These should just be silently ignored.
        logger.warn(f"No pull request found for commit id {commit_id}")
        return HttpResponse("200")

    with dynamodb_lock(pull_request.id()):
        github_logic.maybe_automerge_pull_request(pull_request)
        github_controller.upsert_pull_request(pull_request)
        return HttpResponse("200")

def _handle_check_suite_webhook(payload: dict) -> HttpResponse:
    logger.info(f"Received check_suite webhook: {payload}")
    return HttpResponse("200")

def _handle_check_run_webhook(payload: dict) -> HttpResponse:
    logger.info(f"Received check_run webhook: {payload}")
    return HttpResponse("200")


_events_map = {
    "pull_request": _handle_pull_request_webhook,
    "issue_comment": _handle_issue_comment_webhook,
    "pull_request_review": _handle_pull_request_review_webhook,
    "status": _handle_status_webhook,
    "pull_request_review_comment": _handle_pull_request_review_comment,
    "check_suite": _handle_check_suite_webhook,
    "check_run": _handle_check_run_webhook,
}


def handle_github_webhook(event_type, payload) -> HttpResponse:
    if event_type not in _events_map:
        logger.info(f"No handler for event type {event_type}")
        return HttpResponse("501", f"No handler for event type {event_type}")

    logger.info(f"Received event type {event_type}!")
    # TEMPORARY: sleep for 2 seconds before handling any webhook. We're running
    # into an issue where the Github Webhook sends us a node_id, but when we
    # immediately query that id using the GraphQL API, we get back an error
    # "Could not resolve to a node with the global id of '<node_id>'". This is
    # an attempt to mitigate this issue temporarily by waiting a second to see
    # if Github's data consistency needs a bit of time (does not have
    # read-after-write consistency)
    time.sleep(2)
    return _events_map[event_type](payload)
