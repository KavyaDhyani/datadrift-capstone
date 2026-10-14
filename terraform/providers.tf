provider "aws" {
  region = var.aws_region

  # offline_plan = true lets `terraform plan` run without an AWS account (dummy keys, no API calls).
  # It is only for demonstrating the plan; `apply` needs real credentials and offline_plan = false.
  skip_credentials_validation = var.offline_plan
  skip_requesting_account_id  = var.offline_plan
  skip_metadata_api_check     = var.offline_plan
  skip_region_validation      = var.offline_plan

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
