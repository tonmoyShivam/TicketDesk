# S3 ObjectCreated (attachments/ prefix) -> file processor Lambda.

variable "name" { type = string }
variable "bucket_id" { type = string }
variable "bucket_arn" { type = string }
variable "source_file" { type = string }
variable "max_upload_mb" { type = number }

locals {
  function_name = "${var.name}-file-processor"
}

data "archive_file" "code" {
  type        = "zip"
  source_file = var.source_file
  output_path = "${path.root}/.build/file_processor.zip"
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = 14
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "permissions" {
  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.this.arn}:*"]
  }
  statement {
    sid       = "ReadAndTagAttachments"
    actions   = ["s3:GetObject", "s3:PutObjectTagging"]
    resources = ["${var.bucket_arn}/attachments/*"]
  }
}

resource "aws_iam_role" "this" {
  name               = "${local.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy" "this" {
  name   = "file-processor"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.permissions.json
}

resource "aws_lambda_function" "this" {
  function_name    = local.function_name
  description      = "Validates and tags TicketDesk attachments uploaded to S3"
  role             = aws_iam_role.this.arn
  runtime          = "python3.12"
  handler          = "file_processor.handler"
  filename         = data.archive_file.code.output_path
  source_code_hash = data.archive_file.code.output_base64sha256
  timeout          = 60
  memory_size      = 256

  environment {
    variables = {
      MAX_BYTES          = tostring(var.max_upload_mb * 1024 * 1024)
      ALLOWED_EXTENSIONS = "png,jpg,jpeg,gif,pdf,txt,log,csv,docx,xlsx"
    }
  }

  depends_on = [aws_cloudwatch_log_group.this, aws_iam_role_policy.this]
}

resource "aws_lambda_permission" "s3" {
  statement_id   = "AllowS3Invoke"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.this.function_name
  principal      = "s3.amazonaws.com"
  source_arn     = var.bucket_arn
  source_account = split(":", aws_lambda_function.this.arn)[4]
}

resource "aws_s3_bucket_notification" "this" {
  bucket = var.bucket_id

  lambda_function {
    lambda_function_arn = aws_lambda_function.this.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "attachments/"
  }

  depends_on = [aws_lambda_permission.s3]
}

output "function_name" { value = aws_lambda_function.this.function_name }
output "log_group_name" { value = aws_cloudwatch_log_group.this.name }
