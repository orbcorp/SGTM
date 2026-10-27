# Should be able to use vars directly in main.tf, but can't
# in backend configuration, so we use terragrunt for now.
# See: https://github.com/hashicorp/terraform/issues/13022
remote_state {
  backend = "s3"

  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }

  config = {
    bucket = "${get_env("TF_VAR_terraform_backend_s3_bucket_name")}"
    dynamodb_table = "sgtm_terraform_state_lock"
    region = "us-east-1"

    key = "terraform.tfstate"
  }
}

# Terraform runs from a copy in .terragrunt-cache, so put the bundle where main.tf's relative path points
terraform {
  before_hook "copy_lambda_bundle" {
    commands = concat(get_terraform_commands_that_need_vars(), ["validate"])
    execute  = ["sh", "-c", "mkdir -p ../build && cp '${get_terragrunt_dir()}/../build/function.zip' ../build/function.zip"]
  }
}
