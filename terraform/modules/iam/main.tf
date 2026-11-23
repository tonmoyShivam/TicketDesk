# Least-privilege roles: the EC2 instance role, and an optional GitHub Actions
# deploy role (OIDC, no stored AWS keys).

variable "name" { type = string }
variable "bucket_arn" { type = string }
variable "db_secret_arn" { type = string }
variable "app_log_group_arn" { type = string }
variable "instance_arn" { type = string }
variable "github_repository" { type = string }
variable "create_github_oidc_provider" { type = bool }

data "aws_partition" "current" {}
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ------------------------------------------------------------------ EC2 instance role

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "app" {
  statement {
    sid       = "AttachmentObjects"
    actions   = ["s3:PutObject", "s3:GetObject", "s3:GetObjectTagging"]
    resources = ["${var.bucket_arn}/attachments/*"]
  }
  statement {
    sid       = "ReadDatabaseSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.db_secret_arn]
  }
  statement {
    sid       = "ShipContainerLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
    resources = ["${var.app_log_group_arn}:*"]
  }
}

resource "aws_iam_role" "app" {
  name               = "${var.name}-ec2-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy" "app" {
  name   = "ticketdesk-app"
  role   = aws_iam_role.app.id
  policy = data.aws_iam_policy_document.app.json
}

# Session Manager shell and Run Command instead of SSH (no key pair, no port 22).
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.app.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "app" {
  name = "${var.name}-ec2-profile"
  role = aws_iam_role.app.name
}

# ------------------------------------------------------------------ GitHub Actions deploy role

locals {
  github_enabled = var.github_repository != ""
  oidc_url       = "token.actions.githubusercontent.com"
  oidc_arn = local.github_enabled ? (
    var.create_github_oidc_provider
    ? aws_iam_openid_connect_provider.github[0].arn
    : "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/${local.oidc_url}"
  ) : ""
}

resource "aws_iam_openid_connect_provider" "github" {
  count           = local.github_enabled && var.create_github_oidc_provider ? 1 : 0
  url             = "https://${local.oidc_url}"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

data "aws_iam_policy_document" "github_assume" {
  count = local.github_enabled ? 1 : 0
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.oidc_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_url}:sub"
      values   = ["repo:${var.github_repository}:ref:refs/heads/main"]
    }
  }
}

data "aws_iam_policy_document" "github_deploy" {
  count = local.github_enabled ? 1 : 0
  statement {
    sid     = "RunDeployCommandOnAppInstanceOnly"
    actions = ["ssm:SendCommand"]
    resources = [
      var.instance_arn,
      "arn:${data.aws_partition.current.partition}:ssm:${data.aws_region.current.name}::document/AWS-RunShellScript",
    ]
  }
  statement {
    sid       = "ReadCommandResult"
    actions   = ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations"]
    resources = ["*"] # these read-only actions do not support resource-level permissions
  }
}

resource "aws_iam_role" "github" {
  count              = local.github_enabled ? 1 : 0
  name               = "${var.name}-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_assume[0].json
}

resource "aws_iam_role_policy" "github" {
  count  = local.github_enabled ? 1 : 0
  name   = "ssm-redeploy"
  role   = aws_iam_role.github[0].id
  policy = data.aws_iam_policy_document.github_deploy[0].json
}

output "instance_profile_name" { value = aws_iam_instance_profile.app.name }
output "github_deploy_role_arn" { value = local.github_enabled ? aws_iam_role.github[0].arn : "" }
