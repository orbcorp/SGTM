"""
Test case that should be used for tests that require integration with dynamodb
or other external resources.
"""
import boto3  # type: ignore
from moto import mock_aws  # type: ignore
from src.config import OBJECTS_TABLE, USERS_TABLE, LOCK_TABLE
from .base_test_case_class import BaseClass
from .mock_dynamodb_test_data_helper import MockDynamoDbTestDataHelper


class MockDynamoDbTestCase(BaseClass):

    """
        The boto3.client instance, mocked by moto, that should be used in the tests.
    """

    client = None

    """
        The test data helper, which knows how to interact with our dynamodb tables for the purpose
        of test data
    """
    test_data = None

    aws_mock = None

    @classmethod
    def tearDownClass(cls):
        cls.test_data = None
        cls.client = None
        cls.aws_mock.stop()

    @classmethod
    def setUpClass(cls):
        cls.aws_mock = mock_aws()
        cls.aws_mock.start()
        client = boto3.client("dynamodb")

        # our DynamoDb Schema #DynamoDbSchema
        client.create_table(
            AttributeDefinitions=[
                {"AttributeName": "github-node", "AttributeType": "S",}
            ],
            TableName=OBJECTS_TABLE,
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "github-node", "KeyType": "HASH",}],
        )

        client.create_table(
            AttributeDefinitions=[
                {"AttributeName": "github/handle", "AttributeType": "S",},
            ],
            TableName=USERS_TABLE,
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "github/handle", "KeyType": "HASH",}],
        )

        client.create_table(
            AttributeDefinitions=[
                {"AttributeName": "lock_key", "AttributeType": "S",},
                {"AttributeName": "sort_key", "AttributeType": "S",},
            ],
            TableName=LOCK_TABLE,
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[
                {"AttributeName": "lock_key", "KeyType": "HASH",},
                {"AttributeName": "sort_key", "KeyType": "RANGE",},
            ],
        )
        cls.client = client
        cls.test_data = MockDynamoDbTestDataHelper(client)
