# Offline plan test with mocked AWS (no credentials needed):  terraform test  /  tofu test
mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_data "aws_region" {
    defaults = { name = "ap-south-1" }
  }
  mock_data "aws_ssm_parameter" {
    defaults = { value = "ami-0123456789abcdef0" }
  }
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{}" }
  }
  mock_resource "aws_s3_bucket" {
    defaults = { arn = "arn:aws:s3:::ticketdesk-attachments-123456789012-ap-south-1" }
  }
  mock_resource "aws_lambda_function" {
    defaults = { arn = "arn:aws:lambda:ap-south-1:123456789012:function:ticketdesk-file-processor" }
  }
  mock_resource "aws_cloudwatch_log_group" {
    defaults = { arn = "arn:aws:logs:ap-south-1:123456789012:log-group:/ticketdesk/app" }
  }
  mock_resource "aws_instance" {
    defaults = { arn = "arn:aws:ec2:ap-south-1:123456789012:instance/i-0abc" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/mock" }
  }
  mock_resource "aws_sns_topic" {
    defaults = { arn = "arn:aws:sns:ap-south-1:123456789012:ticketdesk-alerts" }
  }
  mock_resource "aws_cloudwatch_metric_alarm" {
    defaults = { arn = "arn:aws:cloudwatch:ap-south-1:123456789012:alarm:mock" }
  }
  mock_resource "aws_iam_openid_connect_provider" {
    defaults = { arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com" }
  }
}

variables {
  repo_url           = "https://github.com/example/ticketdesk.git"
  allowed_http_cidr  = "203.0.113.10/32"
  availability_zones = ["ap-south-1a", "ap-south-1b"]
}

# Apply-mode runs (mocked) so outputs can be checked. RDS is replaced by fixed
# outputs here because mocked RDS can't produce its nested secret block.
run "core_stack" {
  override_module {
    target = module.rds
    outputs = {
      db_instance_id    = "ticketdesk-db"
      address           = "ticketdesk-db.abc.ap-south-1.rds.amazonaws.com"
      port              = 5432
      db_name           = "ticketdesk"
      master_secret_arn = "arn:aws:secretsmanager:ap-south-1:123456789012:secret:rds!db-abc"
    }
  }

  command = apply

  assert {
    condition     = startswith(output.app_url, "http://")
    error_message = "app_url output"
  }
  assert {
    condition     = length(module.cloudwatch) > 0
    error_message = "cloudwatch module"
  }
  assert {
    condition     = output.github_deploy_role_arn == ""
    error_message = "GitHub role must be off by default"
  }
}

run "with_github_and_alerts" {
  command = apply
  override_module {
    target = module.rds
    outputs = {
      db_instance_id    = "ticketdesk-db"
      address           = "ticketdesk-db.abc.ap-south-1.rds.amazonaws.com"
      port              = 5432
      db_name           = "ticketdesk"
      master_secret_arn = "arn:aws:secretsmanager:ap-south-1:123456789012:secret:rds!db-abc"
    }
  }
  variables {
    github_repository = "example/ticketdesk"
    alert_email       = "ops@example.com"
  }
  assert {
    condition     = output.github_deploy_role_arn != ""
    error_message = "GitHub deploy role should be created"
  }
}

run "rejects_bad_cidr" {
  command = plan
  override_module {
    target = module.rds
    outputs = {
      db_instance_id    = "ticketdesk-db"
      address           = "db.example"
      port              = 5432
      db_name           = "ticketdesk"
      master_secret_arn = "arn:aws:secretsmanager:ap-south-1:123456789012:secret:x"
    }
  }
  variables {
    allowed_http_cidr = "my-ip"
  }
  expect_failures = [var.allowed_http_cidr]
}
