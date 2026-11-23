output "app_url" {
  description = "Open this in a browser (first boot takes ~5 minutes after apply finishes)."
  value       = "http://${module.ec2.public_dns}"
}

output "instance_id" {
  value = module.ec2.instance_id
}

output "attachments_bucket" {
  value = module.s3.bucket_id
}

output "db_endpoint" {
  value = module.rds.address
}

output "db_secret_arn" {
  description = "RDS-managed secret holding the DB credentials (the value is never in Terraform state)."
  value       = module.rds.master_secret_arn
}

output "lambda_function" {
  value = module.lambda.function_name
}

output "lambda_log_group" {
  value = module.lambda.log_group_name
}

output "app_log_group" {
  value = module.cloudwatch.app_log_group_name
}

output "dashboard_url" {
  value = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards/dashboard/${module.cloudwatch.dashboard_name}"
}

output "github_deploy_role_arn" {
  description = "Set as the AWS_DEPLOY_ROLE_ARN repository variable for the deploy workflow."
  value       = module.iam.github_deploy_role_arn
}
