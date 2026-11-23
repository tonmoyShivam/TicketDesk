# Application host: Amazon Linux 2023, Docker Compose (app + nginx), IMDSv2.

variable "name" { type = string }
variable "aws_region" { type = string }
variable "instance_type" { type = string }
variable "subnet_id" { type = string }
variable "security_group_id" { type = string }
variable "instance_profile_name" { type = string }
variable "repo_url" { type = string }
variable "repo_branch" { type = string }
variable "db_host" { type = string }
variable "db_port" { type = number }
variable "db_name" { type = string }
variable "db_secret_arn" { type = string }
variable "bucket_name" { type = string }
variable "app_log_group_name" { type = string }
variable "max_upload_mb" { type = number }

data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_instance" "app" {
  ami                    = data.aws_ssm_parameter.al2023.value
  instance_type          = var.instance_type
  subnet_id              = var.subnet_id
  vpc_security_group_ids = [var.security_group_id]
  iam_instance_profile   = var.instance_profile_name
  monitoring             = false

  metadata_options {
    http_tokens                 = "required" # IMDSv2 only
    http_endpoint               = "enabled"
    http_put_response_hop_limit = 2 # lets the app container reach the instance role credentials
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 20
    encrypted             = true
    delete_on_termination = true
  }

  # No secrets in user data: the DB password stays in Secrets Manager and
  # SECRET_KEY is generated on the instance.
  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    aws_region    = var.aws_region
    repo_url      = var.repo_url
    repo_branch   = var.repo_branch
    db_host       = var.db_host
    db_port       = var.db_port
    db_name       = var.db_name
    db_secret_arn = var.db_secret_arn
    bucket_name   = var.bucket_name
    app_log_group = var.app_log_group_name
    max_upload_mb = var.max_upload_mb
  })
  user_data_replace_on_change = true

  tags = { Name = "${var.name}-app" }

  lifecycle {
    ignore_changes = [ami] # don't replace the server every time a new AMI is published
  }
}

output "instance_id" { value = aws_instance.app.id }
output "instance_arn" { value = aws_instance.app.arn }
output "public_dns" { value = aws_instance.app.public_dns }
