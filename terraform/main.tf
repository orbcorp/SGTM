provider "aws" {
  region = var.aws_region
}

### LAMBDA

# Gives the Lambda function permissions to read/write from the DynamoDb tables
resource "aws_iam_policy" "lambda-function-dynamodb-policy" {
  policy     = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:Scan",
        "dynamodb:PutItem",
        "dynamodb:BatchWriteItem"
      ],
      "Resource": [
        "${aws_dynamodb_table.sgtm-lock.arn}",
        "${aws_dynamodb_table.sgtm-objects.arn}",
        "${aws_dynamodb_table.sgtm-users.arn}"
      ],
      "Effect": "Allow"
    },
    {
      "Action": [
        "dynamodb:DeleteItem",
        "dynamodb:UpdateItem"
      ],
      "Resource": [
        "${aws_dynamodb_table.sgtm-lock.arn}"
      ],
      "Effect": "Allow"
    }
  ]
}
EOF
}

# Gives the Lambda function permissions to create cloudwatch logs
resource "aws_iam_policy" "lambda-function-cloudwatch-policy" {
  policy     = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": [
        "arn:aws:logs:${var.aws_region}:*:log-group:/aws/lambda/${aws_lambda_function.sgtm.function_name}:*",
        "arn:aws:logs:${var.aws_region}:*:log-group:/aws/lambda/${aws_lambda_function.sgtm_sync_users.function_name}:*"
      ],
      "Effect": "Allow"
    }
  ]
}
EOF
}

resource "aws_iam_role" "iam_for_lambda_function" {
  name = "iam_for_lambda"

  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": "sts:AssumeRole",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Effect": "Allow"
    }
  ]
}
EOF
}

resource "aws_iam_role_policy_attachment" "lambda-function-dynamo-db-access-policy-attachment" {
  role       = aws_iam_role.iam_for_lambda_function.name
  policy_arn = aws_iam_policy.lambda-function-dynamodb-policy.arn
}

resource "aws_iam_role_policy_attachment" "lambda-function-cloudwatch-policy-attachment" {
  role       = aws_iam_role.iam_for_lambda_function.name
  policy_arn = aws_iam_policy.lambda-function-cloudwatch-policy.arn
}

resource "aws_iam_role_policy_attachment" "lambda-function-api-keys" {
  role       = aws_iam_role.iam_for_lambda_function.name
  policy_arn = aws_iam_policy.LambdaFunctionApiKeysBucketAccess.arn
}

resource "aws_iam_policy" "LambdaFunctionApiKeysBucketAccess" {
  policy     = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": [
        "s3:GetObject",
        "s3:GetObjectVersion"
      ],
      "Resource": [
        "${aws_s3_bucket.api_key_bucket.arn}/*"
      ],
      "Effect": "Allow"
    },
    {
      "Action": [
        "kms:Decrypt"
      ],
      "Resource": [
        "${aws_kms_key.api_encryption_key.arn}"
      ],
      "Effect": "Allow"
    }
  ]
}
EOF
}


resource "aws_s3_bucket" "lambda_code_s3_bucket" {
  bucket = var.lambda_code_s3_bucket_name
}

resource "aws_s3_bucket_object" "lambda_code_bundle" {
  bucket = aws_s3_bucket.lambda_code_s3_bucket.bucket
  key    = "sgtm_bundle.zip"
  source = "../build/function.zip"
  etag = filemd5("../build/function.zip")
}

resource "aws_lambda_function" "sgtm" {
  s3_bucket     = aws_s3_bucket.lambda_code_s3_bucket.bucket
  s3_key        = aws_s3_bucket_object.lambda_code_bundle.key
  function_name = "sgtm"
  role          = aws_iam_role.iam_for_lambda_function.arn
  handler       = "src.handler.handler"
  source_code_hash = filebase64sha256("../build/function.zip")

  runtime = "python3.7"

  timeout = var.lambda_function_timeout
  environment {
    variables = {
      API_KEYS_S3_BUCKET  = var.api_key_s3_bucket_name,
      API_KEYS_S3_KEY     = var.api_key_s3_object,
      SGTM_FEATURE__AUTOMERGE_ENABLED = var.sgtm_feature__automerge_enabled,
      SGTM_FEATURE__AUTOCOMPLETE_ENABLED = var.sgtm_feature__autocomplete_enabled, 
    }
  }
}

resource "aws_lambda_function" "sgtm_sync_users" {
  s3_bucket     = aws_s3_bucket.lambda_code_s3_bucket.bucket
  s3_key        = aws_s3_bucket_object.lambda_code_bundle.key
  function_name = "sgtm_sync_users"
  role          = aws_iam_role.iam_for_lambda_function.arn
  handler       = "src.sync_users.handler.handler"
  source_code_hash = filebase64sha256("../build/function.zip")

  runtime = "python3.7"

  timeout = 900
  environment {
    variables = {
      API_KEYS_S3_BUCKET     = var.api_key_s3_bucket_name,
      API_KEYS_S3_KEY        = var.api_key_s3_object
      ASANA_USERS_PROJECT_ID = var.asana_users_project_id
    }
  }
}

resource "aws_cloudwatch_event_rule" "execute_sgtm_sync_users_event_rule" {
  name        = "execute_sgtm_sync_users"
  description = "Execute Lambda function sgtm_sync_users on a cron-style schedule"
  schedule_expression = "rate(1 hour)"
}

resource "aws_lambda_permission" "lambda_permission_for_sgtm_sync_users_schedule_event" {
  statement_id  = "AllowSGTMSyncUsersInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.sgtm_sync_users.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.execute_sgtm_sync_users_event_rule.arn
}

resource "aws_cloudwatch_event_target" "execute_sgtm_sync_users_event_target" {
  target_id = "execute_sgtm_sync_users_event_target"
  rule      = aws_cloudwatch_event_rule.execute_sgtm_sync_users_event_rule.name
  arn       = aws_lambda_function.sgtm_sync_users.arn
}

### API

resource "aws_api_gateway_rest_api" "sgtm_rest_api" {
  name        = "SgtmRestApi"
  description = "The API gateway for SGTM lambda function"
  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

resource "aws_api_gateway_resource" "sgtm_resource" {
  rest_api_id = aws_api_gateway_rest_api.sgtm_rest_api.id
  parent_id   = aws_api_gateway_rest_api.sgtm_rest_api.root_resource_id
  path_part   = "sgtm"
}

resource "aws_api_gateway_method" "sgtm_post" {
  rest_api_id   = aws_api_gateway_rest_api.sgtm_rest_api.id
  resource_id   = aws_api_gateway_resource.sgtm_resource.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_deployment" "sgtm_deployment" {
  depends_on  = [aws_api_gateway_integration.sgtm_lambda_integration]
  rest_api_id = aws_api_gateway_rest_api.sgtm_rest_api.id
  stage_name  = "default"
}

resource "aws_api_gateway_method_response" "proxy" {
  rest_api_id = aws_api_gateway_rest_api.sgtm_rest_api.id
  resource_id = aws_api_gateway_resource.sgtm_resource.id
  http_method = aws_api_gateway_method.sgtm_post.http_method
  status_code = "200"
}

resource "aws_api_gateway_integration" "sgtm_lambda_integration" {
  rest_api_id             = aws_api_gateway_rest_api.sgtm_rest_api.id
  resource_id             = aws_api_gateway_resource.sgtm_resource.id
  http_method             = aws_api_gateway_method.sgtm_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.sgtm.invoke_arn
}

resource "aws_api_gateway_integration_response" "sgtm_proxy_response" {
  depends_on = [aws_api_gateway_integration.sgtm_lambda_integration]
  rest_api_id = aws_api_gateway_rest_api.sgtm_rest_api.id
  resource_id = aws_api_gateway_resource.sgtm_resource.id
  http_method = aws_api_gateway_method.sgtm_post.http_method
  status_code = aws_api_gateway_method_response.proxy.status_code
}

resource "aws_lambda_permission" "lambda_permission_for_sgtm_rest_api" {
  statement_id  = "AllowSGTMAPIInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.sgtm.function_name
  principal     = "apigateway.amazonaws.com"

  # More: http://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-control-access-using-iam-policies-to-invoke-api.html
  source_arn = "${aws_api_gateway_rest_api.sgtm_rest_api.execution_arn}/*/${aws_api_gateway_method.sgtm_post.http_method}${aws_api_gateway_resource.sgtm_resource.path}"
}


### DYNAMODB
# ##DynamoDbSchema The DynamoDbSchema's source of truth is to be found here, in the sgtm/terraform/main.tf, except for
# the sgtm_terraform_state_lock table, which has it's source of truth in scripts/setup.py

resource "aws_dynamodb_table" "sgtm-lock" {
  name           = "sgtm-lock"
  read_capacity  = 15
  write_capacity = 15
  hash_key       = "lock_key"
  range_key      = "sort_key"

  attribute {
    name = "lock_key"
    type = "S"
  }

  attribute {
    name = "sort_key"
    type = "S"
  }

  ttl {
    attribute_name = "expiry_time"
    enabled        = true
  }
}

resource "aws_dynamodb_table" "sgtm-objects" {
  name           = "sgtm-objects"
  read_capacity  = 5
  write_capacity = 5
  hash_key       = "github-node"

  attribute {
    name = "github-node"
    type = "S"
  }

  # Since this is a table that contains important data that we can't recover,
  # adding prevent_destroy saves us from accidental updates that would destroy
  # this resource
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_dynamodb_table" "sgtm-users" {
  name           = "sgtm-users"
  read_capacity  = 5
  write_capacity = 5
  hash_key       = "github/handle"

  attribute {
    name = "github/handle"
    type = "S"
  }

  # Since this is a table that contains important data that we can't recover,
  # adding prevent_destroy saves us from accidental updates that would destroy
  # this resource
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_kms_key" "api_encryption_key" {
  description             = "This key is used to encrypt api key bucket objects"
  deletion_window_in_days = 10
}

resource "aws_s3_bucket" "api_key_bucket" {
  bucket = var.api_key_s3_bucket_name
  server_side_encryption_configuration {
    rule {
      apply_server_side_encryption_by_default {
        kms_master_key_id = aws_kms_key.api_encryption_key.arn
        sse_algorithm     = "aws:kms"
      }
    }
  }
}
