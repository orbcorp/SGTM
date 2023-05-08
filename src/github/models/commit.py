from typing import Dict, Any, Optional
from src.logger import logger
import copy


class Commit(object):
    BUILD_SUCCESSFUL = "SUCCESS"
    BUILD_PENDING = "PENDING"
    BUILD_FAILED = "FAILURE"

    def __init__(self, raw_commit: Dict[str, Any]):
        self._raw = copy.deepcopy(raw_commit)

    # A commit's status can be None while the logic to start tests runs right after committing.
    def status(self) -> Optional[str]:
        status = self._raw["commit"].get("status")
        status_check_rollup = self._raw["commit"].get("statusCheckRollup")
        if status is None:
            status = status_check_rollup
            
        # Only return success if statusCheckRollup is also success
        logger.info("status: %s", status)
        logger.info("status check rollup: %s", status_check_rollup)
        if status == Commit.BUILD_SUCCESSFUL:
            if status_check_rollup != Commit.BUILD_SUCCESSFUL:
                logger.info("status check rollup is not success when status is")
                status = status_check_rollup

        if status is None:
            return None
        else:
            return status.get("state", None)

    def node_id(self) -> str:
        return self._raw["commit"]["node_id"]

    def to_raw(self) -> Dict[str, Any]:
        return copy.deepcopy(self._raw)
