data "aws_caller_identity" "current" {}

locals {
  name        = var.project
  bucket_name = "${var.project}-attachments-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
  app_log     = "/${var.project}/app"
}

module "network" {
  source   = "./modules/network"
  name     = local.name
  vpc_cidr = var.vpc_cidr

  availability_zones = var.availability_zones
}

module "security" {
  source            = "./modules/security"
  name              = local.name
  vpc_id            = module.network.vpc_id
  allowed_http_cidr = var.allowed_http_cidr
}

module "rds" {
  source                = "./modules/rds"
  name                  = local.name
  private_subnet_ids    = module.network.private_subnet_ids
  db_security_group_id  = module.security.db_security_group_id
  instance_class        = var.db_instance_class
  backup_retention_days = var.db_backup_retention_days
}

module "s3" {
  source        = "./modules/s3"
  bucket_name   = local.bucket_name
  force_destroy = var.force_destroy_bucket
}

module "lambda" {
  source        = "./modules/lambda"
  name          = local.name
  bucket_id     = module.s3.bucket_id
  bucket_arn    = module.s3.bucket_arn
  source_file   = "${path.root}/../lambda/file_processor.py"
  max_upload_mb = var.max_upload_mb
}

module "cloudwatch" {
  source               = "./modules/cloudwatch"
  name                 = local.name
  aws_region           = var.aws_region
  app_log_group_name   = local.app_log
  instance_id          = module.ec2.instance_id
  db_instance_id       = module.rds.db_instance_id
  lambda_function_name = module.lambda.function_name
  lambda_log_group     = module.lambda.log_group_name
  alert_email          = var.alert_email
}

module "iam" {
  source                      = "./modules/iam"
  name                        = local.name
  bucket_arn                  = module.s3.bucket_arn
  db_secret_arn               = module.rds.master_secret_arn
  app_log_group_arn           = module.cloudwatch.app_log_group_arn
  github_repository           = var.github_repository
  create_github_oidc_provider = var.create_github_oidc_provider
  instance_arn                = module.ec2.instance_arn
}

module "ec2" {
  source                = "./modules/ec2"
  name                  = local.name
  aws_region            = var.aws_region
  instance_type         = var.instance_type
  subnet_id             = module.network.public_subnet_id
  security_group_id     = module.security.app_security_group_id
  instance_profile_name = module.iam.instance_profile_name
  repo_url              = var.repo_url
  repo_branch           = var.repo_branch
  db_host               = module.rds.address
  db_port               = module.rds.port
  db_name               = module.rds.db_name
  db_secret_arn         = module.rds.master_secret_arn
  bucket_name           = module.s3.bucket_id
  app_log_group_name    = local.app_log
  max_upload_mb         = var.max_upload_mb
}
