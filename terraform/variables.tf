variable "aws_region" {
  type        = string
  description = "The AWS region to create resources in"
  default     = "us-east-1"
}

variable "api_key_s3_object" {
  type        = string
  description = "Name of the API key object"
}


variable "api_key_s3_bucket_name" {
  type        = string
  description = "Name of the API key S3 bucket"
}

variable "lambda_code_s3_bucket_name" {
  type        = string
  description = "Name of the S3 bucket that stores the Lambda functions code"
}

variable "lambda_function_timeout" {
  type        = number
  description = "Timeout used for the AWS Lambda function"
  default     = 120
}


variable "terraform_backend_s3_bucket_name" {
  type        = string
  description = "S3 bucket name to store the Terraform state"
}

variable "terraform_backend_dynamodb_lock_table" {
  type        = string
  description = "The DynamoDb table to store the Terraform state lock"
}

variable "asana_users_project_id" {
  type        = string
  description = "Project ID that holds the tasks that map Github handles to Asana user ids"
}

variable "sgtm_feature__automerge_enabled" {
  type        = string
  description = "'true' if behavior to automerge pull requests with Github labels is enabled"
  default     = "false"
}

variable "sgtm_feature__autocomplete_enabled" {
  type        = string
  description = "'true' if behavior to autocomplete linked tasks with Github labels is enabled"
  default     = "false"
}
